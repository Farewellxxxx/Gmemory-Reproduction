import json

import pytest


def test_audit_rejects_future_history_and_unrecorded_rules(tmp_path):
    from repro.audit_evidence import audit_run
    (tmp_path/'episodes').mkdir()
    context=dict(task_main='move ball',task_description='ball in rooma',label=True,
                 state_chain=json.dumps([{'graph':{'action':'move rooma roomb','observation':'arrived'}}]))
    old=dict(task_main='move ball',task_description='ball in rooma',task_trajectory='> move rooma roomb\narrived\n')
    rows=[dict(task_id=i,memory_before=dict(insights=[])) for i in range(2)]
    (tmp_path/'results.jsonl').write_text('\n'.join(map(json.dumps,rows)),encoding='utf-8')
    for i in range(2):
        (tmp_path/'episodes'/f'{i:03d}.json').write_text(json.dumps(dict(context=context)),encoding='utf-8')
    event=dict(event='retrieval',task_id=0,prior_memory_size=0,successful=[old],insights=[])
    path=tmp_path/'memory_events.jsonl'
    path.write_text(json.dumps(event),encoding='utf-8')
    with pytest.raises(ValueError,match='previous completed'):
        audit_run(tmp_path)
    event.update(task_id=1,prior_memory_size=1)
    path.write_text(json.dumps(event),encoding='utf-8')
    assert audit_run(tmp_path)['successful_histories_checked']==1
    event['insights']=['rule absent from previous snapshot']
    path.write_text(json.dumps(event),encoding='utf-8')
    with pytest.raises(ValueError,match='previous snapshot'):
        audit_run(tmp_path)
