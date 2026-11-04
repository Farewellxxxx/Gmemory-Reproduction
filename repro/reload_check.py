"""Verify a finished memory run in a fresh process, with LLM calls prohibited."""
import argparse
import json
import os
from pathlib import Path

from repro.runtime import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    os.chdir(root)
    run=Path(args.run_dir)
    os.environ['OPENAI_API_BASE']='https://example.invalid/v1'
    os.environ['OPENAI_API_KEY']='offline-reload-placeholder'
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['ANONYMIZED_TELEMETRY']='False'
    from mas.memory import GMemory
    from mas.utils import EmbeddingFunc
    import torch
    torch.set_num_threads(2)
    cfg=json.loads((run/'manifest.json').read_text(encoding='utf-8'))['config']
    expected=json.loads((run/'final_memory.json').read_text(encoding='utf-8'))
    old_docs=json.loads((run/'memory_documents.json').read_text(encoding='utf-8'))
    def forbidden(*args,**kwargs):
        raise AssertionError('Reload validation must not call a language model')
    global_config={key:cfg[key] for key in ['hop','start_insights_threshold','rounds_per_insights','insights_point_num']}
    global_config['working_dir']=str(run/'memory')
    memory=GMemory(namespace='g-memory',global_config=global_config,llm_model=forbidden,
                   embedding_func=EmbeddingFunc(os.getenv('GMEMORY_EMBEDDING_MODEL',str(root/'.cache/all-MiniLM-L6-v2'))))
    docs=memory.main_memory.get(include=['documents','metadatas'])
    def by_id(value):
        return {identifier:(text,meta) for identifier,text,meta in zip(value['ids'],value['documents'],value['metadatas'])}
    result=dict(memory_size=memory.memory_size,graph_nodes=memory.task_layer.graph.number_of_nodes(),
                graph_edges=memory.task_layer.graph.number_of_edges(),
                insights_equal=memory.insights_layer.insights_memory==expected['insights'],
                records_equal=by_id(docs)==by_id(old_docs),language_model_calls=0)
    assert result['memory_size']==expected['memory_size']
    assert result['graph_nodes']==expected['graph_nodes']
    assert result['graph_edges']==expected['graph_edges']
    assert result['records_equal'] and result['insights_equal']
    graph=memory.task_layer.graph
    write_json(run/'task_graph.json',dict(directed=graph.is_directed(),
               nodes=[dict(id=node,**attrs) for node,attrs in graph.nodes(data=True)],
               links=[dict(source=source,target=target,**attrs) for source,target,attrs in graph.edges(data=True)]))
    if docs['documents']:
        successful,failed,insights=memory._retrieve_memory_raw(docs['documents'][0],successful_topk=1,failed_topk=1)
        result['retrieval_after_reload']=dict(successful=len(successful),failed=len(failed),insights=len(insights))
        assert successful or failed
    write_json(run/'reload_check.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
