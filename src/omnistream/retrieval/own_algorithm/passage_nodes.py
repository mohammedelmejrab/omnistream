"""Passage nodes in the own retriever's Personalized PageRank (HippoRAG 2 style).

The graph already stores each passage as an ``Episodic`` node linked by
``MENTIONS`` to the entities extracted from it. This module adds those passages
to the PPR graph next to the entity subgraph, restarts the walk at the seed
entities AND at densely retrieved passages (down-weighted, as in HippoRAG 2),
and ranks passages by their stationary probability. The top passages are
returned as text chunks, so the answer model reads whole passages (not only
fact sentences) and passage recall is measured on the graph's own ranking.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import networkx as nx

from omnistream.retrieval.models import Chunk, Subgraph

# Dense candidates that join the graph as restart passages.
DENSE_K = 20
# Restart mass of dense passages relative to seed entities (HippoRAG 2's 0.05).
PASSAGE_WEIGHT = 0.05
# Passages returned as chunks.
PASSAGE_TOP = 5
# Per-entity cap on linked passages, so hub entities cannot flood the graph.
MENTION_CAP = 100

_MENTIONS = """
UNWIND $ids AS id
MATCH (n:Entity {uuid: id})
CALL {
  WITH n
  MATCH (ep:Episodic)-[:MENTIONS]->(n)
  WHERE ep.group_id IN $bubbles AND ep.item_id IS NOT NULL
  RETURN ep LIMIT $cap
}
RETURN ep.item_id AS item, ep.group_id AS bubble, collect(n.uuid) AS entities
"""

_TEXTS = """
UNWIND $items AS it
MATCH (ep:Episodic {group_id: it.bubble, item_id: it.item})
RETURN it.item AS item, it.bubble AS bubble, head(collect(ep.content)) AS text
"""


def _node(bubble: str, item: str) -> str:
    return f"passage::{bubble}::{item}"


def passage_graph(
    subgraph: Subgraph,
    mentions: Sequence[tuple[str, str, Sequence[str]]],
    dense: Mapping[tuple[str, str], float],
) -> nx.Graph:
    """Entity edges (facts, SAME_AS) plus passage-entity MENTIONS edges."""
    graph = nx.Graph()
    graph.add_nodes_from(sorted(subgraph.entities))
    for a, b in sorted(
        [*((f.subject_id, f.object_id) for f in subgraph.facts), *subgraph.same_as]
    ):
        graph.add_edge(a, b, weight=graph.get_edge_data(a, b, {}).get("weight", 0) + 1)
    for bubble, item, entities in mentions:
        node = _node(bubble, item)
        for entity in sorted(set(entities)):
            if entity in subgraph.entities:
                graph.add_edge(node, entity, weight=1.0)
    for bubble, item in sorted(dense):
        graph.add_node(_node(bubble, item))
    return graph


def rank_passages(
    graph: nx.Graph,
    seed_weights: Mapping[str, float],
    dense: Mapping[tuple[str, str], float],
    *,
    passage_weight: float = PASSAGE_WEIGHT,
    damping: float = 0.85,
) -> list[tuple[str, str, float]]:
    """PPR restarting at entities (sum 1) and dense passages (sum passage_weight)."""
    restart: dict[str, float] = {}
    entity_total = math.fsum(max(0.0, w) for i, w in seed_weights.items() if i in graph)
    for node, weight in seed_weights.items():
        if node in graph and entity_total > 0:
            restart[node] = max(0.0, weight) / entity_total
    dense_total = math.fsum(max(0.0, s) for s in dense.values())
    if dense_total > 0:
        for (bubble, item), score in dense.items():
            node = _node(bubble, item)
            restart[node] = restart.get(node, 0.0) + (
                passage_weight * max(0.0, score) / dense_total
            )
    if not restart or not math.fsum(restart.values()):
        return []
    ranks = nx.pagerank(
        graph,
        alpha=damping,
        personalization={n: restart.get(n, 0.0) for n in graph},
        weight="weight",
        max_iter=1000,
        tol=1e-12,
    )
    out = []
    for node, score in ranks.items():
        if node.startswith("passage::"):
            _, bubble, item = node.split("::", 2)
            out.append((bubble, item, score))
    out.sort(key=lambda row: (-row[2], row[0], row[1]))
    return out


class PassageNodes:
    """Reads MENTIONS and passage text from the graph store; ranks via PPR."""

    def __init__(self, graph, top: int = PASSAGE_TOP, cap: int = MENTION_CAP):
        self.graph = graph
        self.top = top
        self.cap = cap

    def rank(
        self,
        subgraph: Subgraph,
        seed_weights: Mapping[str, float],
        dense_chunks: Sequence[Chunk],
        bubbles: Sequence[str],
    ) -> tuple[Chunk, ...]:
        dense: dict[tuple[str, str], float] = {}
        dense_text: dict[tuple[str, str], Chunk] = {}
        for chunk in dense_chunks:
            key = (chunk.bubble, chunk.item_id)
            if chunk.score > dense.get(key, float("-inf")):
                dense[key] = chunk.score
            dense_text.setdefault(key, chunk)
        mentions = [
            (row["bubble"], row["item"], row["entities"])
            for row in self.graph._run(
                _MENTIONS, ids=sorted(subgraph.entities), bubbles=list(bubbles),
                cap=self.cap,
            )
        ]
        graph = passage_graph(subgraph, mentions, dense)
        ranked = rank_passages(graph, seed_weights, dense)[: self.top]
        if not ranked:
            return ()
        missing = [
            {"bubble": b, "item": i} for b, i, _ in ranked if (b, i) not in dense_text
        ]
        texts = {
            (row["bubble"], row["item"]): row["text"] or ""
            for row in (self.graph._run(_TEXTS, items=missing) if missing else [])
        }
        chunks = []
        for bubble, item, score in ranked:
            known = dense_text.get((bubble, item))
            text = texts.get((bubble, item), "") if known is None else known.text
            if not text:
                continue
            chunks.append(
                Chunk(
                    id=f"passage:{item}",
                    text=text,
                    item_id=item,
                    bubble=bubble,
                    source_url=known.source_url if known else None,
                    published_at=known.published_at if known else None,
                    score=score,
                )
            )
        return tuple(chunks)
