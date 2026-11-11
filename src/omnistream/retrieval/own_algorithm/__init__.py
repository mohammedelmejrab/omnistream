"""The ``own`` retrieval algorithm (spec C5). Step 5, fact fusion, lives here."""

from omnistream.retrieval.own_algorithm.fact_fusion import (
    DEFAULT_HALF_LIVES,
    FactCandidate,
    FusedFact,
    corroboration_confidence,
    fuse_facts,
    recency_score,
)

__all__ = [
    "DEFAULT_HALF_LIVES",
    "FactCandidate",
    "FusedFact",
    "corroboration_confidence",
    "fuse_facts",
    "recency_score",
]

from omnistream.retrieval.own_algorithm.pagerank import personalized_pagerank
from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever
from omnistream.retrieval.own_algorithm.scoring import score_facts, seed_paths
from omnistream.retrieval.own_algorithm.seeding import Seed, seed_entities

__all__ += [
    "OwnRetriever",
    "Seed",
    "personalized_pagerank",
    "score_facts",
    "seed_entities",
    "seed_paths",
]
