"""Summarize recorded outcomes, check paired conditions, export sanitized evidence."""
import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil

from repro.runtime import redact,write_json


def read_rows(path):
    path=Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def summarize_run(folder):
    folder=Path(folder)
    results=read_rows(folder/'results.jsonl')
    calls=read_rows(folder/'calls.jsonl')
    domains=defaultdict(list)
    for row in results:
        domains[row['task']['game_name']].append(row)
    purposes=defaultdict(lambda:dict(calls=0,prompt_tokens=0,completion_tokens=0,estimated_ca=0.0,seconds=0.0))
    for row in calls:
        group=purposes[row['purpose']]
        group['calls']+=1
        group['prompt_tokens']+=row.get('usage',{}).get('prompt_tokens',0)
        group['completion_tokens']+=row.get('usage',{}).get('completion_tokens',0)
        group['estimated_ca']+=row.get('estimated_ca',0)
        group['seconds']+=row.get('elapsed_seconds',0)
    events=read_rows(folder/'memory_events.jsonl')
    actions=Counter()
    roles=Counter()
    for path in sorted((folder/'episodes').glob('*.json')):
        episode=json.loads(path.read_text(encoding='utf-8'))
        chain=episode.get('context',{}).get('state_chain','[]')
        if isinstance(chain,str):
            chain=json.loads(chain)
        for state in chain:
            graph=state.get('graph',{})
            action=graph.get('action','').lower()
            actions['agent_steps']+=1
            if 'think' in action:
                actions['thought_steps']+=1
            elif 'check' in action or 'look around' in action:
                actions['query_steps']+=1
            else:
                actions['physical_action_attempts']+=1
                actions['invalid_physical_actions']+=graph.get('reward',0)<0
            roles.update(node['agent_name'] for node in state.get('nodes',[]) if 'agent_name' in node)
    successes=sum(bool(row['success']) for row in results)
    status=json.loads((folder/'status.json').read_text(encoding='utf-8'))
    budget_path=folder/'budget_at_end.json'
    pending=json.loads(budget_path.read_text(encoding='utf-8')).get('pending',{}) if budget_path.exists() else {}
    call_ids={row.get('call_id') for row in calls}
    return dict(status=status['status'],completed_tasks=len(results),successes=successes,
                success_rate=successes/len(results) if results else None,
                mean_progress_reward=sum(row['reward'] for row in results)/len(results) if results else None,
                environment_steps=sum(row['environment_steps'] for row in results),
                **{key:actions[key] for key in ['agent_steps','thought_steps','query_steps',
                    'physical_action_attempts','invalid_physical_actions']},
                role_action_counts=dict(roles),
                api_calls=len(calls),api_errors=sum(row['status']!='ok' for row in calls),
                unresolved_calls=sum(row['status']=='error' and 'usage' not in row for row in calls),
                unresolved_reserved_ca=sum(amount for identifier,amount in pending.items() if identifier in call_ids),
                finish_reasons=dict(Counter(row.get('finish_reason','unreported') for row in calls)),
                prompt_tokens=sum(x['prompt_tokens'] for x in purposes.values()),
                completion_tokens=sum(x['completion_tokens'] for x in purposes.values()),
                estimated_ca=sum(x['estimated_ca'] for x in purposes.values()),
                api_seconds=sum(x['seconds'] for x in purposes.values()),
                by_purpose=dict(purposes),
                by_domain={domain:dict(tasks=len(rows),successes=sum(bool(row['success']) for row in rows),
                           mean_reward=sum(row['reward'] for row in rows)/len(rows)) for domain,rows in domains.items()},
                memory_events=dict(Counter(row['event'] for row in events)),
                retrievals_with_successful_history=sum(row['event']=='retrieval' and bool(row.get('successful')) for row in events),
                retrievals_with_insights=sum(row['event']=='retrieval' and bool(row.get('insights')) for row in events),
                projections_with_empty_input=sum(row['event']=='projection' and not row['raw'] for row in events))


def validate_pair(first,second):
    for name in ['tasks','config','data_sha256']:
        if first[name]!=second[name]:
            raise ValueError(f'Paired {name} differ')
    def runtime_sources(manifest):
        return {path:digest for path,digest in manifest['source_sha256'].items()
                if path.startswith(('mas/','tasks/')) or path in
                ['repro/runtime.py','repro/protocol.py','repro/observed_memory.py','repro/run.py']}
    if runtime_sources(first)!=runtime_sources(second):
        raise ValueError('Paired runtime source differs')


def export_run(source,destination):
    source,destination=Path(source),Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    for name in ['manifest.json','status.json','results.jsonl','final_memory.json','task_graph.json','budget_at_end.json','reload_check.json','evidence_audit.json']:
        if (source/name).exists():
            (destination/name).write_text(redact((source/name).read_text(encoding='utf-8')),encoding='utf-8')
    for name in ['calls.jsonl','workflow.jsonl','memory_events.jsonl','memory_documents.json']:
        if (source/name).exists():
            with gzip.open(destination/(name+'.gz'),'wt',encoding='utf-8') as stream:
                stream.write(redact((source/name).read_text(encoding='utf-8')))
    with gzip.open(destination/'episodes.jsonl.gz','wt',encoding='utf-8') as stream:
        for path in sorted((source/'episodes').glob('*.json')):
            stream.write(redact(json.dumps(dict(file=path.name,episode=json.loads(path.read_text(encoding='utf-8'))),ensure_ascii=False))+'\n')
    events=read_rows(source/'memory_events.jsonl')
    selected=next((row for row in events if row['event']=='retrieval' and row.get('insights') and row.get('successful')),None)
    if selected is None:
        selected=next((row for row in events if row['event']=='retrieval' and row.get('insights')),None)
    if selected:
        identifier=selected['task_id']
        write_json(destination/'selected_trace.json',dict(task_id=identifier,retrieval=selected,
                   projections=[row for row in events if row['task_id']==identifier and row['event']=='projection'],
                   episode=json.loads((source/'episodes'/f'{identifier:03d}.json').read_text(encoding='utf-8'))))
    hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.iterdir() if path.is_file()}
    write_json(destination/'SHA256.json',hashes)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gmemory',default='runs/gmemory')
    parser.add_argument('--baseline',default='runs/no-memory')
    parser.add_argument('--output',default='artifacts/first-run')
    args=parser.parse_args()
    first,second=Path(args.gmemory),Path(args.baseline)
    validate_pair(json.loads((first/'manifest.json').read_text(encoding='utf-8')),
                  json.loads((second/'manifest.json').read_text(encoding='utf-8')))
    report=dict(gmemory=summarize_run(first),no_memory=summarize_run(second),
                paired_conditions_verified=True,
                interpretation='Single ordered online diagnostic subset; not full-paper replication or statistical evidence of improvement.')
    destination=Path(args.output)
    destination.mkdir(parents=True,exist_ok=False)
    write_json(destination/'summary.json',report)
    export_run(first,destination/'gmemory')
    export_run(second,destination/'no-memory')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
