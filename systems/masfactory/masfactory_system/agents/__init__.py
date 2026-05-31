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
from .critic_consensus import (
    CriticPass1Node,
    CriticPass2Node,
    CriticPass3Node,
    CriticSnapshot1Node,
    CriticSnapshot2Node,
    CriticSnapshot3Node,
    CriticVoteNode,
    consensus_chain_edges,
    consensus_chain_nodes,
    consensus_passes,
)
from .critic_debate import (
    DebatePass1Node,
    DebatePass2Node,
    DebatePass3Node,
    DebateSnapshot1Node,
    DebateSnapshot2Node,
    DebateSnapshot3Node,
    debate_chain_edges,
    debate_chain_nodes,
    debate_rounds,
)
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
    "CriticPass1Node",
    "CriticPass2Node",
    "CriticPass3Node",
    "CriticSnapshot1Node",
    "CriticSnapshot2Node",
    "CriticSnapshot3Node",
    "CriticVoteNode",
    "consensus_chain_edges",
    "consensus_chain_nodes",
    "consensus_passes",
    "DebatePass1Node",
    "DebatePass2Node",
    "DebatePass3Node",
    "DebateSnapshot1Node",
    "DebateSnapshot2Node",
    "DebateSnapshot3Node",
    "debate_chain_edges",
    "debate_chain_nodes",
    "debate_rounds",
    "SurvivorNode",
    "AnalystNode",
    "PersistenceNode",
    "PrepareCurrentActorNode",
    "AccumulateActorNode",
    "actor_loop_done",
]
