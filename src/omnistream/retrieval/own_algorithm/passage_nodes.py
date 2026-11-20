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
# Candidate pool for the optional cross-encoder passage rerank (top PPR
# passages plus the dense candidates).
RERANK_POOL = 20
RRF_K = 60
# Re-seeding (second walk): entities of the top passages of the first walk
# become extra restart nodes; their 1-hop neighbourhood joins the graph.
RESEED_TOP = 3
RESEED_MAX_EDGES = 300

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

_PASSAGE_ENTITIES = """
UNWIND $items AS it
MATCH (ep:Episodic {group_id: it.bubble, item_id: it.item})-[:MENTIONS]->(n:Entity)
WHERE n.group_id = it.bubble
RETURN it.item AS item, it.bubble AS bubble, collect(DISTINCT n.uuid) AS entities
"""

# Second-hop expansion: passages that share an entity with a head passage.
_NEIGHBOR_PASSAGES = """
UNWIND $items AS it
MATCH (ep:Episodic {group_id: it.bubble, item_id: it.item})-[:MENTIONS]->(n:Entity)
WHERE n.group_id = it.bubble
CALL (n, it) {
  MATCH (other:Episodic)-[:MENTIONS]->(n)
  WHERE other.group_id = it.bubble AND other.item_id IS NOT NULL
    AND other.item_id <> it.item
  RETURN other LIMIT $cap
}
RETURN it.item AS head, other.item_id AS item, other.group_id AS bubble,
       head(collect(other.content)) AS text
"""
HOP_HEADS = 2
HOP_PER_ENTITY = 10

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
    fact_weight: Mapping[str, float] | None = None,
) -> nx.Graph:
    """Entity edges (facts, SAME_AS) plus passage-entity MENTIONS edges.

    ``fact_weight`` (fact id -> weight, mean about 1) makes fact edges
    question-aware; facts without a weight count 1, as do SAME_AS links.
    """
    graph = nx.Graph()
    graph.add_nodes_from(sorted(subgraph.entities))
    weights = fact_weight or {}
    edges = sorted(
        [
            *((f.subject_id, f.object_id, weights.get(f.id, 1.0)) for f in subgraph.facts),
            *((a, b, 1.0) for a, b in subgraph.same_as),
        ]
    )
    for a, b, w in edges:
        graph.add_edge(a, b, weight=graph.get_edge_data(a, b, {}).get("weight", 0) + w)
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

    def __init__(
        self,
        graph,
        top: int = PASSAGE_TOP,
        cap: int = MENTION_CAP,
        *,
        reranker=None,
        rerank_mode: str = "off",
        dense_k: int = DENSE_K,
        reseed: bool = False,
        store=None,
        damping: float = 0.85,
        ppr_weight: float = 1.0,
        edge_power: float = 0.0,
        fact_seeds: int = 0,
        hop_expand: bool = False,
    ):
        self.graph = graph
        self.top = top
        self.cap = cap
        # rerank_mode: "off" (PPR order), "ce" (cross-encoder order over the
        # pool) or "rrf" (reciprocal-rank fusion of PPR and cross-encoder).
        self.reranker = reranker
        self.rerank_mode = rerank_mode if reranker is not None else "off"
        self.dense_k = dense_k
        self.damping = damping
        self.edge_power = edge_power
        self.fact_seeds = fact_seeds
        self.hop_expand = hop_expand and reranker is not None
        # Weight of the PPR rank against the cross-encoder rank in "rrf".
        self.ppr_weight = ppr_weight
        # Re-seeding needs the graph store's expand(); ``graph`` is that store.
        self.reseed = reseed
        self.store = store if store is not None else graph

    def rank(
        self,
        subgraph: Subgraph,
        seed_weights: Mapping[str, float],
        dense_chunks: Sequence[Chunk],
        bubbles: Sequence[str],
        question: str | None = None,
        fact_weight: Mapping[str, float] | None = None,
    ) -> tuple[Chunk, ...]:
        dense: dict[tuple[str, str], float] = {}
        dense_text: dict[tuple[str, str], Chunk] = {}
        for chunk in dense_chunks:
            key = (chunk.bubble, chunk.item_id)
            if chunk.score > dense.get(key, float("-inf")):
                dense[key] = chunk.score
            dense_text.setdefault(key, chunk)
        mentions = self._mentions(subgraph, bubbles)
        graph = passage_graph(subgraph, mentions, dense, fact_weight)
        if self.reseed:
            subgraph, seed_weights, graph = self._second_walk(
                subgraph, seed_weights, graph, dense, mentions, bubbles, fact_weight
            )
        reranking = self.rerank_mode != "off" and question
        ranked = rank_passages(graph, seed_weights, dense, damping=self.damping)[
            : RERANK_POOL if reranking else self.top
        ]
        if reranking:
            # Pool = top PPR passages plus every dense candidate (deduped).
            seen = {(b, i) for b, i, _ in ranked}
            ranked = ranked + [
                (b, i, 0.0) for (b, i) in sorted(dense, key=lambda k: -dense[k])
                if (b, i) not in seen
            ]
        if not ranked:
            return ()
        missing = [
            {"bubble": b, "item": i} for b, i, _ in ranked if (b, i) not in dense_text
        ]
        texts = {
            (row["bubble"], row["item"]): row["text"] or ""
            for row in (self.graph._run(_TEXTS, items=missing) if missing else [])
        }
        if reranking:
            ranked = self._rerank(question, ranked, dense_text, texts)
        if self.hop_expand and question and len(ranked) >= HOP_HEADS:
            ranked = self._hop(question, ranked, texts)
        chunks = []
        for bubble, item, score in ranked[: self.top]:
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

    def _mentions(self, subgraph, bubbles, ids=None):
        return [
            (row["bubble"], row["item"], row["entities"])
            for row in self.graph._run(
                _MENTIONS, ids=sorted(ids if ids is not None else subgraph.entities),
                bubbles=list(bubbles), cap=self.cap,
            )
        ]

    def _second_walk(
        self, subgraph, seed_weights, graph, dense, mentions, bubbles, fact_weight=None
    ):
        first = rank_passages(graph, seed_weights, dense, damping=self.damping)[
            :RESEED_TOP
        ]
        if not first:
            return subgraph, seed_weights, graph
        rows = self.graph._run(
            _PASSAGE_ENTITIES,
            items=[{"bubble": b, "item": i} for b, i, _ in first],
        )
        found = {(r["bubble"], r["item"]): r["entities"] for r in rows}
        total = math.fsum(score for _, _, score in first) or 1.0
        seed_total = math.fsum(max(0.0, w) for w in seed_weights.values()) or 1.0
        extra: dict[str, float] = {}
        for bubble, item, score in first:
            entities = found.get((bubble, item), [])
            for entity in entities:
                # Second-walk seeds carry the first walk's passage mass,
                # split over each passage's entities; total equal to the
                # original seed mass so neither walk dominates.
                extra[entity] = extra.get(entity, 0.0) + (
                    seed_total * (score / total) / len(entities)
                )
        if not extra:
            return subgraph, seed_weights, graph
        old_ids = set(subgraph.entities)
        new_ids = sorted(set(extra) - old_ids)
        if new_ids:
            hop = self.store.expand(
                new_ids, bubbles=list(bubbles), time_scope=None,
                max_hops=1, max_edges=RESEED_MAX_EDGES,
            )
            known = {f.id for f in subgraph.facts}
            subgraph = Subgraph(
                {**hop.entities, **subgraph.entities},
                subgraph.facts + tuple(f for f in hop.facts if f.id not in known),
                tuple(sorted(set(subgraph.same_as) | set(hop.same_as))),
            )
            mentions = mentions + self._mentions(
                subgraph, bubbles, ids=sorted(set(hop.entities) - old_ids)
            )
        weights = dict(seed_weights)
        for entity, weight in extra.items():
            if entity in subgraph.entities:
                weights[entity] = weights.get(entity, 0.0) + weight
        return subgraph, weights, passage_graph(subgraph, mentions, dense, fact_weight)

    def _hop(self, question, ranked, texts):
        """Keep the top passages; for each head, put its best-matching
        entity-linked neighbour passage (cross-encoder) right after the heads."""
        heads = ranked[:HOP_HEADS]
        rows = self.graph._run(
            _NEIGHBOR_PASSAGES,
            items=[{"bubble": b, "item": i} for b, i, _ in heads],
            cap=HOP_PER_ENTITY,
        )
        head_keys = {(b, i) for b, i, _ in heads}
        candidates: dict[str, list[tuple[str, str, str]]] = {}
        for row in rows:
            key = (row["bubble"], row["item"])
            if key in head_keys or not row["text"]:
                continue
            candidates.setdefault(row["head"], []).append((row["bubble"], row["item"], row["text"]))
        pairs, owners = [], []
        for head, items in candidates.items():
            for bubble, item, text in dict.fromkeys(items):
                pairs.append((question, text))
                owners.append((head, bubble, item, text))
        if not pairs:
            return ranked
        scores = self.reranker().predict(pairs, batch_size=32, show_progress_bar=False)
        best: dict[str, tuple[float, str, str, str]] = {}
        for (head, bubble, item, text), score in zip(owners, scores, strict=True):
            if head not in best or float(score) > best[head][0]:
                best[head] = (float(score), bubble, item, text)
        picked = []
        for _, item, _ in heads:
            if item in best:
                _, bubble, other, text = best[item]
                if (bubble, other) not in {(b, i) for b, i, _ in picked}:
                    picked.append((bubble, other, 0.0))
                    texts.setdefault((bubble, other), text)
        chosen = {(b, i) for b, i, _ in heads + picked}
        return heads + picked + [row for row in ranked[HOP_HEADS:] if (row[0], row[1]) not in chosen]

    def _rerank(self, question, ranked, dense_text, texts):
        def text(row):
            known = dense_text.get((row[0], row[1]))
            return known.text if known is not None else texts.get((row[0], row[1]), "")

        rows = [row for row in ranked if text(row)]
        if len(rows) < 2:
            return rows
        scores = self.reranker().predict(
            [(question, text(row)) for row in rows], batch_size=16,
            show_progress_bar=False,
        )
        ce_order = sorted(range(len(rows)), key=lambda i: -float(scores[i]))
        if self.rerank_mode == "ce":
            return [rows[i] for i in ce_order]
        ce_rank = {i: r for r, i in enumerate(ce_order)}
        fused = sorted(
            range(len(rows)),
            key=lambda i: -(
                self.ppr_weight / (RRF_K + i + 1) + 1 / (RRF_K + ce_rank[i] + 1)
            ),
        )
        return [rows[i] for i in fused]
