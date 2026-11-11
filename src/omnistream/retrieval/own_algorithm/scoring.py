"""Fact scores and nearest-seed paths (spec C5 step 4)."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping, Sequence

import numpy as np

from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.models import Subgraph
from omnistream.retrieval.own_algorithm.pagerank import _graph


def score_facts(
    subgraph: Subgraph,
    pagerank: Mapping[str, float],
    question_embedding: np.ndarray,
    fact_embeddings: Mapping[str, np.ndarray],
) -> dict[str, float]:
    """Cosine times mean endpoint PR, clipping negative cosine to zero.

    "Times the PageRank of the fact's two endpoints" is interpreted as their
    arithmetic mean, which keeps scale comparable across facts (spec C5).
    Missing embeddings contribute zero; the pipeline embeds them first.
    """
    if any(not math.isfinite(v) or v < 0 for v in pagerank.values()):
        raise ValueError("PageRank scores must be finite and non-negative")
    scores = {}
    for fact in subgraph.facts:
        similarity = (
            float(
                EmbeddingService.cosine_similarity(
                    question_embedding, fact_embeddings[fact.id]
                )[0]
            )
            if fact.id in fact_embeddings
            else 0.0
        )
        scores[fact.id] = (
            max(0.0, similarity)
            * (pagerank.get(fact.subject_id, 0) + pagerank.get(fact.object_id, 0))
            / 2
        )
    return scores


def seed_paths(
    subgraph: Subgraph, seed_ids: Sequence[str]
) -> dict[str, tuple[str, ...]]:
    """BFS to the nearer endpoint; lexicographic full paths resolve equal distances."""
    graph = _graph(subgraph)
    paths = {i: (i,) for i in sorted(set(seed_ids) & graph.nodes)}
    queue = deque(paths)
    while queue:
        node = queue.popleft()
        for neighbor in sorted(graph[node]):
            if neighbor not in paths:
                paths[neighbor] = (*paths[node], neighbor)
                queue.append(neighbor)
    result = {}
    for fact in subgraph.facts:
        choices = [paths[i] for i in (fact.subject_id, fact.object_id) if i in paths]
        result[fact.id] = min(choices, key=lambda p: (len(p), p)) if choices else ()
    return result
