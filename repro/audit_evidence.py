"""Match retrieved content to completed past episodes and pre-task rule snapshots."""
import argparse
import json
from pathlib import Path

from repro.runtime import write_json


def audit_run(folder):
    from repro.analyze import read_rows
    folder=Path(folder)
    events=read_rows(folder/'memory_events.jsonl')
    previous_successes=set()
    retrievals=histories=rules=0
    for result in read_rows(folder/'results.jsonl'):
        index=result['task_id']
        context=json.loads((folder/'episodes'/f'{index:03d}.json').read_text(encoding='utf-8'))['context']
        for event in events:
            if event['task_id']!=index or event['event']!='retrieval':
                continue
            if event['prior_memory_size']!=index:
                raise ValueError('Retrieval memory size does not match completed past episodes')
            retrievals+=1
            for old in event['successful']:
                signature=(old['task_main'],old['task_description'],old['task_trajectory'])
                if signature not in previous_successes:
                    raise ValueError('Retrieved history has no identical previous completed success')
                histories+=1
            previous_rules={rule['rule'] for rule in result['memory_before']['insights']}
            for rule in event['insights']:
                if rule not in previous_rules:
                    raise ValueError('Retrieved rule is absent from previous snapshot')
                rules+=1
        if context['label']:
            chain=json.loads(context['state_chain'])
            trajectory=''.join('> '+state['graph']['action']+'\n'+state['graph']['observation']+'\n' for state in chain)
            previous_successes.add((context['task_main'],context['task_description'],trajectory))
    return dict(memory_retrievals_checked=retrievals,successful_histories_checked=histories,
                retrieved_rules_checked=rules,checked_content_matches_prior_evidence=True,
                scope='Completed episodes only; successful trajectory text and retrieved rule snapshots, not every internal graph edge.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    args=parser.parse_args()
    result=audit_run(args.run_dir)
    write_json(Path(args.run_dir)/'evidence_audit.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
