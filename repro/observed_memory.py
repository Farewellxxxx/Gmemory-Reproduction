"""Observation-only wrappers around the upstream memory implementation."""
from copy import deepcopy
from functools import wraps

from mas.memory import GMemory
from mas.memory.common import MASMessage
from repro.runtime import append_json, utc_now


class ObservedGMemory(GMemory):
    def __init__(self,*args,event_path,**kwargs):
        self.event_path=event_path
        self.episode=None
        super().__init__(*args,**kwargs)
        for name in ['finetune_insights','merge_insights']:
            self._observe_insight_operation(name)

    def event(self,kind,**values):
        append_json(self.event_path,dict(time_utc=utc_now(),task_id=self.episode,event=kind,**values))

    def summary(self):
        return dict(memory_size=self.memory_size,
                    graph_nodes=self.task_layer.graph.number_of_nodes(),
                    graph_edges=self.task_layer.graph.number_of_edges(),
                    insights=deepcopy(self.insights_layer.insights_memory))

    def _observe_insight_operation(self,name):
        method=getattr(self.insights_layer,name)
        @wraps(method)
        def observed(*args,**kwargs):
            self.event(name+'_begin',memory_size=self.memory_size,
                       rules=deepcopy(self.insights_layer.insights_memory))
            result=method(*args,**kwargs)
            self.event(name+'_end',memory_size=self.memory_size,
                       rules=deepcopy(self.insights_layer.insights_memory))
            return result
        setattr(self.insights_layer,name,observed)

    def retrieve_memory(self,*args,**kwargs):
        result=super().retrieve_memory(*args,**kwargs)
        successful,failed,insights=result
        self.event('retrieval',query=kwargs.get('query_task',args[0] if args else None),
                   prior_memory_size=self.memory_size,
                   successful=[MASMessage.to_dict(task) for task in successful],
                   failed=[MASMessage.to_dict(task) for task in failed],insights=insights)
        return result

    def project_insights(self,raw_insights,role=None,task_traj=None):
        result=super().project_insights(raw_insights,role,task_traj)
        self.event('projection',role=role,raw=raw_insights,projected=result)
        return result

    def add_memory(self,mas_message):
        self.event('add_memory_begin',label=mas_message.label,task=mas_message.task_main,
                   memory_size=self.memory_size)
        super().add_memory(mas_message)
        self.event('add_memory_end',**self.summary())
