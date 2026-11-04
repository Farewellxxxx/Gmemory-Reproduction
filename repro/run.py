"""Run one bounded arm. Invoke from the repository root with python -m repro.run."""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
from types import SimpleNamespace

from repro.protocol import create_run_dir,select_tasks
from repro.runtime import Budget,TrackedLLM,RunHalted,append_json,write_json,redact,utc_now

ROOT=Path(__file__).resolve().parents[1]


def source_manifest():
    paths=[]
    for directory in ['mas','tasks','repro']:
        paths.extend((ROOT/directory).rglob('*.py'))
    return {str(path.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def parse_args():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/reproduction.json')
    parser.add_argument('--env-file',default='.env')
    parser.add_argument('--output',required=True)
    parser.add_argument('--budget-file',required=True)
    parser.add_argument('--deadline-utc')
    parser.add_argument('--arm',choices=['g-memory','none'],default='g-memory')
    parser.add_argument('--per-domain',type=int)
    parser.add_argument('--probe',action='store_true')
    return parser.parse_args()


def main():
    args=parse_args()
    os.chdir(ROOT)
    from dotenv import load_dotenv
    load_dotenv(args.env_file,override=True)
    cfg=json.loads(Path(args.config).read_text(encoding='utf-8'))
    if args.per_domain is not None:
        cfg['per_domain']=args.per_domain
    if os.environ.get('OPENAI_API_BASE','').rstrip('/') != cfg['base_url']:
        raise ValueError('Configured API endpoint differs from approved protocol')
    if not os.environ.get('OPENAI_API_KEY'):
        raise ValueError('Set OPENAI_API_KEY locally before running')
    os.environ.setdefault('MPLBACKEND','Agg')
    os.environ.setdefault('ANONYMIZED_TELEMETRY','False')
    os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
    os.environ.setdefault('NLTK_DATA',str(ROOT/'.cache'/'nltk_data'))
    deadline=args.deadline_utc or (datetime.now(timezone.utc)+timedelta(hours=cfg['max_hours'])).isoformat()
    budget=Budget(args.budget_file,cfg['budget_ca'],deadline,
                  cfg['input_ca_per_million'],cfg['output_ca_per_million'])
    output=create_run_dir(args.output)
    model=TrackedLLM(budget,output/'calls.jsonl',model=cfg['model'])
    model.arm='probe' if args.probe else args.arm
    write_json(output/'status.json',dict(status='started',time_utc=utc_now()))
    started=time.monotonic()
    try:
        if args.probe:
            answer=model([SimpleNamespace(role='user',content='Reply with exactly OK.')],temperature=0,max_tokens=16)
            write_json(output/'probe.json',dict(answer=answer,model_requested=cfg['model'],provider=cfg['provider']))
            print('Connectivity probe completed; see probe.json and calls.jsonl.')
        else:
            run_arm(cfg,args.arm,output,model)
        write_json(output/'status.json',dict(status='complete',time_utc=utc_now(),
                   elapsed_seconds=time.monotonic()-started))
    except (RunHalted,KeyboardInterrupt) as exc:
        write_json(output/'status.json',dict(status='interrupted',time_utc=utc_now(),reason=redact(exc)))
        print(redact(exc),file=sys.stderr)
        return 2
    except Exception as exc:
        import traceback
        (output/'failure.txt').write_text(redact(traceback.format_exc()),encoding='utf-8')
        write_json(output/'status.json',dict(status='failed',time_utc=utc_now(),error_type=type(exc).__name__))
        print(redact(traceback.format_exc()),file=sys.stderr)
        return 1
    finally:
        budget._read()
        write_json(output/'budget_at_end.json',budget.state)
    return 0


def run_arm(cfg,arm,output,model):
    sys.path.insert(0,str(ROOT/'tasks'))
    import numpy as np
    import torch
    from envs import get_task,get_env
    from mas.memory import MASMemoryBase
    from mas.memory.common import MASMessage
    from mas.reasoning import ReasoningIO
    from mas.utils import EmbeddingFunc
    from mas_workflow.autogen import AutoGen
    from prompts import get_dataset_system_prompt,get_task_few_shots
    from repro.observed_memory import ObservedGMemory

    random.seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    torch.manual_seed(cfg['seed'])
    torch.set_num_threads(2)
    tasks=select_tasks(get_task('pddl'),cfg['domains'],cfg['per_domain'])
    embedding_name=os.getenv('GMEMORY_EMBEDDING_MODEL')
    if not embedding_name:
        local=ROOT/'.cache'/'all-MiniLM-L6-v2'
        embedding_name=str(local) if (local/'download-manifest.json').exists() else cfg['embedding_model']
    manifest=dict(time_utc=utc_now(),arm=arm,config=cfg,tasks=tasks,
                  git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  source_sha256=source_manifest(),python=sys.version,platform=platform.platform(),
                  data_sha256=hashlib.sha256((ROOT/'data/pddl/test.jsonl').read_bytes()).hexdigest(),
                  packages={name:importlib.metadata.version(name) for name in
                  ['torch','sentence-transformers','langchain-chroma','chromadb','finch-clust','gym','numpy','openai']})
    local_manifest=Path(embedding_name)/'download-manifest.json'
    if local_manifest.exists():
        manifest['embedding_manifest']=json.loads(local_manifest.read_text(encoding='utf-8'))
    write_json(output/'manifest.json',manifest)
    embedding=EmbeddingFunc(embedding_name) if arm=='g-memory' else None
    mem_config={key:cfg[key] for key in ['hop','start_insights_threshold','rounds_per_insights','insights_point_num']}
    mem_config['working_dir']=str(output/'memory')
    memory_args=dict(namespace=arm,global_config=mem_config,llm_model=model,embedding_func=embedding)
    memory=ObservedGMemory(**memory_args,event_path=output/'memory_events.jsonl') if arm=='g-memory' else MASMemoryBase(**memory_args)
    env=get_env('pddl',None,cfg['max_steps'])
    mas=AutoGen()

    class Observer:
        def log(self,message):
            append_json(output/'workflow.jsonl',dict(task_id=model.task_id,message=message))

    mas.add_observer(Observer())
    mas.build_system(ReasoningIO(model),memory,env,cfg)
    for index,task in enumerate(tasks):
        model.task_id=index
        if arm=='g-memory':
            memory.episode=index
        write_json(output/'status.json',dict(status='running',task_index=index,task=task,time_utc=utc_now()))
        task_cfg=deepcopy(task)
        task_main,task_description=env.set_env(task_cfg)
        domain_info=env.env.unwrapped._get_debug_info()
        domain_files={name:dict(path=str(Path(path).relative_to(ROOT)).replace('\\','/'),
                      sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
                      for name,path in domain_info.items()}
        task_cfg.update(task_main=task_main,task_description=task_description,
                        few_shots=get_task_few_shots('pddl',task_cfg,cfg['few_shots']))
        instruction=get_dataset_system_prompt('pddl',task_cfg)
        for agent in mas.agents_team.values():
            agent.add_task_instruction(instruction)
        before=memory.summary() if arm=='g-memory' else dict(memory_size=0,insights=[])
        begin_calls=model.budget.state['settled_calls']
        begin_cost=model.budget.state['spent_ca']
        began=time.monotonic()
        reward,done=mas.schedule(task_cfg)
        after=memory.summary() if arm=='g-memory' else dict(memory_size=0,insights=[])
        row=dict(task_id=index,task=task,task_main=task_main,domain_files=domain_files,
                 success=bool(done),reward=float(reward),environment_steps=env.steps,
                 action_count=len(env.history)//3,elapsed_seconds=time.monotonic()-began,
                 api_calls=model.budget.state['settled_calls']-begin_calls,
                 estimated_ca=model.budget.state['spent_ca']-begin_cost,
                 memory_before=before,memory_after=after)
        write_json(output/'episodes'/f'{index:03d}.json',dict(result=row,
                   context=MASMessage.to_dict(memory.current_task_context),history=env.history))
        append_json(output/'results.jsonl',row)
        if arm=='g-memory':
            write_json(output/'snapshots'/f'{index:03d}.json',after)
        print(f"{arm} {index+1}/{len(tasks)} {task['game_name']}[{task['problem_index']}] "
              f"success={done} reward={reward:.3f} calls={row['api_calls']} "
              f"estimated_CA={row['estimated_ca']:.5f}",flush=True)
    if arm=='g-memory':
        records=memory.main_memory.get(include=['documents','metadatas'])
        write_json(output/'memory_documents.json',records)
        write_json(output/'final_memory.json',memory.summary())


if __name__=='__main__':
    raise SystemExit(main())
