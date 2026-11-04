"""Real PDDL checks: no fake state engine or LLM calls."""
import os
import subprocess
import sys

import pytest


def test_model_import_does_not_print_credentials():
    result = subprocess.run([sys.executable, '-c', 'import mas.llm'],
                            capture_output=True, text=True, env=os.environ.copy())
    assert result.returncode == 0, result.stderr
    assert 'unit-test-secret-do-not-print' not in result.stdout + result.stderr


def test_pddl_loads_without_optional_benchmark_packages():
    from envs import get_task, get_env
    tasks = get_task('pddl')
    assert len(tasks) == 60
    assert tasks[0]['game_name'] == 'barman'
    assert tasks[20]['game_name'] == 'blockworld'
    assert get_env('pddl', None, 30).max_trials == 30
    assert 'alfworld' not in sys.modules
    assert 'scienceworld' not in sys.modules


@pytest.mark.parametrize('game', ['barman', 'blockworld', 'gripper', 'tyreworld'])
def test_real_reset_returns_full_initial_observation(game):
    from envs import get_env
    env = get_env('pddl', None, 30)
    goal, description = env.set_env({'game_name': game, 'problem_index': 0})
    first = env._get_obs()
    assert first.strip()
    env.reset()
    assert env._get_obs() == first
    assert env._get_goal() == goal
    assert first in description
    actions = [a for a in env._get_action_space() if a not in ['check valid actions', 'look around']]
    before = env.last_obs
    observation, reward, done = env.step(actions[0])
    assert env.last_obs != before
    assert isinstance(observation, str)
    assert isinstance(done, bool)
    env.reset()
    assert env._get_obs() == first
    assert env.steps == 0
    assert env.reward == 0

