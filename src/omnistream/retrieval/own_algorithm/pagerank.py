"""Undirected Personalized PageRank (spec C5 step 3)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import networkx as nx

from omnistream.retrieval.models import Subgraph


def _graph(subgraph: Subgraph) -> nx.Graph:
    """Count parallel fact and identity edges as transition weights."""
    graph = nx.Graph()
    graph.add_nodes_from(sorted(subgraph.entities))
    for a, b in [
        *((f.subject_id, f.object_id) for f in subgraph.facts),
        *subgraph.same_as,
    ]:
        graph.add_edge(a, b, weight=graph.get_edge_data(a, b, {}).get("weight", 0) + 1)
    return graph


def personalized_pagerank(
    subgraph: Subgraph, seed_ids: Sequence[str], *, damping: float = 0.85
) -> dict[str, float]:
    """Restart uniformly at present seeds, including dangling/isolated seeds."""
    if not math.isfinite(damping) or not 0 <= damping < 1:
        raise ValueError("damping must be within [0, 1)")
    graph = _graph(subgraph)
    if not graph:
        return {}
    seeds = set(seed_ids) & graph.nodes
    if not seeds:
        raise ValueError("no seeds present in subgraph")
    personalization = {i: float(i in seeds) / len(seeds) for i in graph}
    return nx.pagerank(
        graph,
        alpha=damping,
        personalization=personalization,
        weight="weight",
        max_iter=1000,
        tol=1e-12,
    )
