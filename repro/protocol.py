from copy import deepcopy
from pathlib import Path


def select_tasks(tasks,domains,per_domain):
    if per_domain <= 0 or len(set(domains)) != len(domains) or not domains:
        raise ValueError('Require positive count and unique nonempty domains')
    chosen=[]
    for domain in domains:
        candidates=[task for task in tasks if task['game_name']==domain]
        if len(candidates)<per_domain:
            raise ValueError(f'Insufficient tasks for {domain}')
        chosen.extend(deepcopy(candidates[:per_domain]))
    return chosen


def create_run_dir(path):
    path=Path(path)
    path.mkdir(parents=True,exist_ok=False)
    return path
