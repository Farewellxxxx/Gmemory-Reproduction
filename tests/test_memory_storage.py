"""Storage/FINCH integration fixtures; these are not scientific benchmark runs."""
from types import SimpleNamespace

import pytest


def test_finch_api_clusters_two_separated_pairs(tmp_path):
    from mas.memory.mas_memory.GMemory import TaskLayer
    vectors={'a':[1.,0.],'b':[0.99,0.01],'c':[0.,1.],'d':[0.01,0.99]}
    layer=TaskLayer(str(tmp_path),'test',SimpleNamespace(
        _embedding_function=SimpleNamespace(embed_query=lambda s:vectors[s])))
    layer.graph.add_nodes_from(vectors)
    layer.cluster_tasks()
    labels=dict(layer)
    assert labels['a']==labels['b']
    assert labels['c']==labels['d']
    assert labels['a']!=labels['c']


def test_real_chroma_and_graph_reload_preserve_one_trajectory(tmp_path):
    from mas.memory import GMemory
    from mas.memory.common import MASMessage
    class Embedding:
        def embed_query(self,text):
            return [1.,float(len(text))/100.,0.5]
        def embed_documents(self,texts):
            return [self.embed_query(t) for t in texts]
    args=dict(namespace='test',global_config={'working_dir':str(tmp_path)},
              embedding_func=Embedding(),llm_model=lambda *a,**kw:'1. Move the block.')
    memory=GMemory(**args)
    msg=MASMessage(task_main='Move a block',task_description='Block on table',label=True)
    msg.move_state('pick up block','Holding block',reward=1)
    memory.add_memory(msg)
    restored=GMemory(**args)
    assert restored.memory_size==1
    assert list(restored.task_layer.graph)==['Move a block']
    successes,failures,rules=restored._retrieve_memory_raw('Move a block',successful_topk=1,failed_topk=0)
    assert len(successes)==1
    assert 'Holding block' in successes[0].task_trajectory
    assert successes[0].get_extra_field('key_steps')=='1. Move the block.'
    assert failures==[]
