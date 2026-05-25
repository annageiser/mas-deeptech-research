"""The Agent / CustomNode steps that make up System A's graph.

Mapping to the architecture diagram (Container A "MAS Factory"):

  Planner               -> agents/planner.py        (Agent)
  Retriever             -> agents/retriever.py      (CustomNode — calls collection/)
  --- per-actor Loop ---
    PrepareCurrentActor -> agents/loop_nodes.py     (CustomNode — picks one actor's docs)
    Extractor           -> agents/extractor.py      (Agent)
    Classifier          -> agents/classifier.py     (Agent)
    Critic              -> agents/critic.py         (Agent)
    AccumulateActor     -> agents/loop_nodes.py     (CustomNode — appends to run-wide totals)
  --- after loop ---
  Survivor              -> agents/survivor.py       (CustomNode — kept for backward compat)
  Analyst               -> agents/analyst.py        (Agent)
  Persistence           -> agents/persistence.py    (CustomNode — writes Supabase + audit)
"""

from .planner import PlannerNode
from .retriever import RetrieverNode
from .extractor import ExtractorNode
from .classifier import ClassifierNode
from .critic import CriticNode
from .survivor import SurvivorNode
from .analyst import AnalystNode
from .persistence import PersistenceNode
from .loop_nodes import (
    AccumulateActorNode,
    PrepareCurrentActorNode,
    actor_loop_done,
)

__all__ = [
    "PlannerNode",
    "RetrieverNode",
    "ExtractorNode",
    "ClassifierNode",
    "CriticNode",
    "SurvivorNode",
    "AnalystNode",
    "PersistenceNode",
    "PrepareCurrentActorNode",
    "AccumulateActorNode",
    "actor_loop_done",
]
