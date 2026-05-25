"""The seven Agent / CustomNode steps that make up System A's graph.

Mapping to the architecture diagram (Container A "MAS Factory"):

  Planner       -> agents/planner.py        (Agent)
  Retriever     -> agents/retriever.py      (CustomNode — calls collection/)
  Extractor     -> agents/extractor.py      (Agent)
  Classifier    -> agents/classifier.py     (Agent)
  Critic        -> agents/critic.py         (Agent)
  Survivor      -> agents/survivor.py       (CustomNode — Critic-filter bridge)
  Analyst       -> agents/analyst.py        (Agent)
  Persistence   -> agents/persistence.py    (CustomNode — writes Supabase + audit)
"""

from .planner import PlannerNode
from .retriever import RetrieverNode
from .extractor import ExtractorNode
from .classifier import ClassifierNode
from .critic import CriticNode
from .survivor import SurvivorNode
from .analyst import AnalystNode
from .persistence import PersistenceNode

__all__ = [
    "PlannerNode",
    "RetrieverNode",
    "ExtractorNode",
    "ClassifierNode",
    "CriticNode",
    "SurvivorNode",
    "AnalystNode",
    "PersistenceNode",
]
