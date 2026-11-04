"""Load only the requested benchmark and its optional dependencies."""
import json
from importlib import import_module

from .base_env import BaseEnv, BaseRecorder

TASKS_PATH = {
    'alfworld':'data/alfworld/alfworld_tasks_suffix.json',
    'fever':'data/fever/fever_dev.jsonl',
    'pddl':'data/pddl/test.jsonl',
    'sciworld':'data/sciworld/test.jsonl',
}
TASK_NAMES = ['barman','blockworld','gripper','tyreworld']
_MODULES = {
    'alfworld':('.alfworld_env','AlfworldEnv','AlfworldRecorder'),
    'fever':('.fever_env','FeverEnv','FeverRecorder'),
    'sciworld':('.sciworld_env','SciworldEnv','SciworldRecorder'),
    'pddl':('.pddl_env.pddl_env','PDDLEnv','PDDLRecorder'),
}


def _module(task):
    if task not in _MODULES:
        raise ValueError(f'Unsupported task type: {task}')
    return import_module(_MODULES[task][0],__name__)


def get_env(task: str,env_config: dict,max_trials: int) -> BaseEnv:
    return getattr(_module(task),_MODULES[task][1])(env_config,max_trials)


def get_recorder(task: str,working_dir: str,namespace: str) -> BaseRecorder:
    return getattr(_module(task),_MODULES[task][2])(working_dir=working_dir,namespace=namespace)


def get_task(task: str) -> list[dict]:
    module=_module(task)
    if task=='pddl':
        return module.get_all_environment_configs(TASK_NAMES,TASKS_PATH[task])
    with open(TASKS_PATH[task],encoding='utf-8') as reader:
        if task=='alfworld':
            return [dict(task=row['goal'],env_kwargs=dict(config='alfworld',gamefile=row['gamefile']),
                         task_type=module.prefixes[module.get_env_name_from_gamefile(row['gamefile'])],
                         env_name=module.get_env_name_from_gamefile(row['gamefile'])) for row in json.load(reader)]
        rows=[json.loads(line) for line in reader if line.strip()]
    if task=='fever':
        return [dict(task=row['claim'],answer=row['label'],env_name='fever') for row in rows][:100]
    return [dict(id=row['id'],task_name=row['additional_info']['env_name'],
                 var=row['additional_info']['var'],modified_goal=row['goal'],
                 subgoals=row['subgoals'],difficulty=row['difficulty'],
                 simplification_str=module.build_simplification_str()) for row in rows]
