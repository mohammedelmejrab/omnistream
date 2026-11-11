"""C5 retrieval: rank fusion and hybrid dense/sparse search."""

from omnistream.retrieval.fusion import (
    FusedResult,
    RankedItem,
    ranks_from_scores,
    reciprocal_rank_fusion,
)
from omnistream.retrieval.hybrid import HybridRetriever, RetrievedChunk
from omnistream.retrieval.sparse import BM25Index

__all__ = [
    "BM25Index",
    "FusedResult",
    "HybridRetriever",
    "RankedItem",
    "RetrievedChunk",
    "ranks_from_scores",
    "reciprocal_rank_fusion",
]

from omnistream.retrieval.models import (
    Chunk,
    Citation,
    Entity,
    Fact,
    ItemPart,
    RetrievalMode,
    RetrievalResult,
    ScoredFact,
    Subgraph,
    TimeScope,
)
from omnistream.retrieval.protocols import GraphStore, ItemStore, Retriever

__all__ += [
    "Chunk",
    "Citation",
    "Entity",
    "Fact",
    "GraphStore",
    "ItemPart",
    "ItemStore",
    "RetrievalMode",
    "RetrievalResult",
    "Retriever",
    "ScoredFact",
    "Subgraph",
    "TimeScope",
]

from omnistream.retrieval.modes import RetrievalDispatcher
from omnistream.retrieval.router import BubbleInfo, QueryRouter, RoutingDecision

__all__ += ["BubbleInfo", "QueryRouter", "RetrievalDispatcher", "RoutingDecision"]
