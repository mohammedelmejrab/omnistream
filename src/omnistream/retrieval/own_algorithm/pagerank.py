"""Undirected Personalized PageRank (spec C5 step 3)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import networkx as nx

from omnistream.retrieval.models import Subgraph


def _graph(subgraph: Subgraph) -> nx.Graph:
    """Count parallel fact and identity edges as transition weights."""
    graph = nx.Graph()
    graph.add_nodes_from(sorted(subgraph.entities))
    for a, b in sorted(
        [
            *((f.subject_id, f.object_id) for f in subgraph.facts),
            *subgraph.same_as,
        ]
    ):
        graph.add_edge(a, b, weight=graph.get_edge_data(a, b, {}).get("weight", 0) + 1)
    return graph


def personalized_pagerank(
    subgraph: Subgraph,
    seed_ids: Sequence[str],
    *,
    damping: float = 0.85,
    seed_weights: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Restart at seeds proportional to nonnegative scores (uniform if all zero)."""
    if not math.isfinite(damping) or not 0 <= damping < 1:
        raise ValueError("damping must be within [0, 1)")
    graph = _graph(subgraph)
    if not graph:
        return {}
    seeds = set(seed_ids) & graph.nodes
    if not seeds:
        raise ValueError("no seeds present in subgraph")
    weights = {
        i: float(seed_weights.get(i, 0)) if seed_weights is not None else 1.0
        for i in sorted(seeds)
    }
    if any(not math.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError("seed weights must be finite and non-negative")
    total = math.fsum(weights.values())
    if total == 0:
        weights = {i: 1.0 for i in sorted(seeds)}
        total = len(seeds)
    personalization = {i: weights.get(i, 0) / total for i in graph}
    return nx.pagerank(
        graph,
        alpha=damping,
        personalization=personalization,
        weight="weight",
        max_iter=1000,
        tol=1e-12,
    )
