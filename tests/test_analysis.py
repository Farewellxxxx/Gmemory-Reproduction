import json

import pytest


def test_summary_uses_recorded_success_and_all_billed_usage(tmp_path):
    from repro.analyze import summarize_run
    (tmp_path/'results.jsonl').write_text('\n'.join(json.dumps(row) for row in [
        {'task_id':0,'task':{'game_name':'gripper'},'success':True,'reward':1,'environment_steps':3},
        {'task_id':1,'task':{'game_name':'gripper'},'success':False,'reward':0.5,'environment_steps':30}]),encoding='utf-8')
    (tmp_path/'calls.jsonl').write_text('\n'.join(json.dumps(row) for row in [
        {'status':'ok','purpose':'agent_action','usage':{'prompt_tokens':100,'completion_tokens':10},'estimated_ca':0.000147,'elapsed_seconds':2},
        {'status':'error','purpose':'project_insights','usage':{'prompt_tokens':20,'completion_tokens':0},'estimated_ca':0.000021,'elapsed_seconds':1}]),encoding='utf-8')
    (tmp_path/'status.json').write_text(json.dumps({'status':'interrupted'}),encoding='utf-8')
    result=summarize_run(tmp_path)
    assert result['completed_tasks']==2
    assert result['successes']==1
    assert result['success_rate']==0.5
    assert result['mean_progress_reward']==0.75
    assert result['prompt_tokens']==120
    assert result['estimated_ca']==pytest.approx(0.000168)
    assert result['status']=='interrupted'
    assert result['api_errors']==1


def test_pair_validation_rejects_task_or_runtime_drift():
    from repro.analyze import validate_pair
    common={'tasks':[{'game_name':'gripper','problem_index':0}],
            'config':{'model':'gpt-4o-mini'},'source_sha256':{'mas/a.py':'abc','repro/run.py':'def'},'data_sha256':'data'}
    validate_pair(common,dict(common,source_sha256=dict(common['source_sha256'],**{'repro/analyze.py':'new'})))
    with pytest.raises(ValueError,match='tasks'):
        validate_pair(common,dict(common,tasks=[]))
    with pytest.raises(ValueError,match='source'):
        validate_pair(common,dict(common,source_sha256={'mas/a.py':'changed','repro/run.py':'def'}))


def test_summary_separates_thoughts_queries_and_invalid_physical_actions(tmp_path):
    from repro.analyze import summarize_run
    (tmp_path/'status.json').write_text(json.dumps({'status':'complete'}),encoding='utf-8')
    (tmp_path/'episodes').mkdir()
    chain=[{'graph':{'action':action,'reward':reward},'nodes':[{'agent_name':role}]} for action,reward,role in [
        ('think: next ball',-1,'solver'),('check valid actions',0,'ground_truth'),
        ('pick ball1 rooma left',0,'solver'),('drop ball1 roomb left',-1,'solver')]]
    episode={'context':{'state_chain':json.dumps(chain)}}
    (tmp_path/'episodes'/'000.json').write_text(json.dumps(episode),encoding='utf-8')
    result=summarize_run(tmp_path)
    assert result['agent_steps']==4
    assert result['thought_steps']==1
    assert result['query_steps']==1
    assert result['physical_action_attempts']==2
    assert result['invalid_physical_actions']==1
    assert result['role_action_counts']=={'solver':3,'ground_truth':1}
