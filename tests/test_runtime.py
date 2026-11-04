"""Regression tests for money, secrets and incomplete API responses."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest


def future():
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def test_budget_persists_spend_and_unresolved_reservations(tmp_path):
    from repro.runtime import Budget
    path = tmp_path / 'budget.json'
    budget = Budget(path, 1, future())
    first = budget.reserve(2000, 512)
    budget.settle(first, 1000, 100)
    pending = budget.reserve(2000, 512)
    restarted = Budget(path, 1)
    assert restarted.state['spent_ca'] == pytest.approx(0.00147)
    assert pending in restarted.state['pending']
    assert restarted.state['deadline_utc'] == budget.state['deadline_utc']
    with pytest.raises(ValueError):
        Budget(path, 50)


def test_budget_rejects_next_request_before_overspending(tmp_path):
    from repro.runtime import Budget, RunHalted
    budget = Budget(tmp_path/'budget.json', 0.001, future())
    with pytest.raises(RunHalted, match='budget'):
        budget.reserve(2000, 512)
    assert budget.state['pending'] == {}


def test_expired_budget_prevents_requests(tmp_path):
    from repro.runtime import Budget, RunHalted
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    budget = Budget(tmp_path/'budget.json', 1, past)
    with pytest.raises(RunHalted, match='deadline'):
        budget.reserve(100, 16)


def test_api_normalizes_none_caps_output_and_records_usage(tmp_path):
    from repro.runtime import Budget, TrackedLLM
    sent = []
    def create(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(
            id='test-response', model='gpt-4o-mini-test',
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=100),
            choices=[SimpleNamespace(message=SimpleNamespace(content='move rooma to roomb'),finish_reason='stop')])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    budget = Budget(tmp_path/'budget.json', 1, future())
    llm = TrackedLLM(budget, tmp_path/'calls.jsonl', client=client)
    result = llm([SimpleNamespace(role='user',content='test')], max_tokens=None, num_comps=None)
    assert result == 'move rooma to roomb'
    assert sent[0]['max_tokens'] == 512
    assert sent[0]['n'] == 1
    row = json.loads((tmp_path/'calls.jsonl').read_text())
    assert row['usage'] == {'prompt_tokens':1000,'completion_tokens':100}
    assert row['estimated_ca'] == pytest.approx(0.00147)
    assert not budget.state['pending']


@pytest.mark.parametrize('kind', ['network', 'missing_usage', 'empty'])
def test_bad_api_response_halts_and_keeps_auditable_record(tmp_path, kind):
    from repro.runtime import Budget, TrackedLLM, RunHalted
    def create(**kwargs):
        if kind == 'network':
            raise TimeoutError('connection failed with sk-secret-that-must-never-be-published')
        return SimpleNamespace(
            id='bad-response',model='gpt-4o-mini',
            usage=None if kind == 'missing_usage' else SimpleNamespace(prompt_tokens=10,completion_tokens=0),
            choices=[SimpleNamespace(message=SimpleNamespace(content=''),finish_reason='stop')])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    budget = Budget(tmp_path/'budget.json', 1, future())
    llm = TrackedLLM(budget,tmp_path/'calls.jsonl',client=client,retry_backoff=0)
    with pytest.raises(RunHalted):
        llm([SimpleNamespace(role='user',content='test')])
    log = (tmp_path/'calls.jsonl').read_text()
    assert 'sk-secret-that-must-never-be-published' not in log
    rows=[json.loads(line) for line in log.splitlines()]
    assert all(row['status']=='error' for row in rows)
    assert len(rows)==(3 if kind=='network' else 1)
    if kind != 'empty':
        assert budget.state['pending']


def test_task_selection_is_bounded_and_preserves_declared_order():
    from repro.protocol import select_tasks
    source = [{'game_name':g,'problem_index':i} for g in ['barman','blockworld','gripper','tyreworld'] for i in range(10)]
    chosen = select_tasks(source, ['blockworld','gripper','barman','tyreworld'], 6)
    assert len(chosen) == 24
    assert [(r['game_name'],r['problem_index']) for r in chosen[:7]] == [('blockworld',0),('blockworld',1),('blockworld',2),('blockworld',3),('blockworld',4),('blockworld',5),('gripper',0)]
    with pytest.raises(ValueError):
        select_tasks(source, ['blockworld'], 0)
    with pytest.raises(ValueError):
        select_tasks(source, ['blockworld'], 11)


def test_existing_run_directory_is_never_overwritten(tmp_path):
    from repro.protocol import create_run_dir
    target = tmp_path/'run'
    create_run_dir(target)
    (target/'evidence.txt').write_text('keep me')
    with pytest.raises(FileExistsError):
        create_run_dir(target)
    assert (target/'evidence.txt').read_text() == 'keep me'


def test_transient_provider_failure_retries_with_separate_reservation_and_log(tmp_path):
    from repro.runtime import Budget,TrackedLLM
    attempts=[]
    class ProviderError(Exception):
        status_code=525
    def create(**kwargs):
        attempts.append(kwargs)
        if len(attempts)==1:
            raise ProviderError('temporary proxy failure')
        return SimpleNamespace(id='recovered',model='gpt-4o-mini',
            usage=SimpleNamespace(prompt_tokens=20,completion_tokens=2),
            choices=[SimpleNamespace(message=SimpleNamespace(content='OK'),finish_reason='stop')])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    budget=Budget(tmp_path/'budget.json',1,future())
    llm=TrackedLLM(budget,tmp_path/'calls.jsonl',client=client,max_attempts=3,retry_backoff=0)
    assert llm([SimpleNamespace(role='user',content='test')])=='OK'
    rows=[json.loads(line) for line in (tmp_path/'calls.jsonl').read_text().splitlines()]
    assert [row['status'] for row in rows]==['error','ok']
    assert [row['attempt'] for row in rows]==[1,2]
    assert rows[0]['logical_call_id']==rows[1]['logical_call_id']
    assert len(budget.state['pending'])==1
    assert budget.state['settled_calls']==1
    assert llm.attempts_count==2


@pytest.mark.parametrize('status,expected_attempts',[(525,3),(401,1)])
def test_retry_exhaustion_and_nonretryable_error_remain_bounded(tmp_path,status,expected_attempts):
    from repro.runtime import Budget,TrackedLLM,RunHalted
    class ProviderError(Exception):
        status_code=status
    def create(**kwargs):
        raise ProviderError('no response')
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    budget=Budget(tmp_path/'budget.json',1,future())
    llm=TrackedLLM(budget,tmp_path/'calls.jsonl',client=client,max_attempts=3,retry_backoff=0)
    with pytest.raises(RunHalted):
        llm([SimpleNamespace(role='user',content='test')])
    assert llm.attempts_count==expected_attempts
    assert len(budget.state['pending'])==expected_attempts
