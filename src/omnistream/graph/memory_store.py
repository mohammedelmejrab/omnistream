"""Deterministic NetworkX graph store (spec 4.3, C5 steps 1-2)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime

import networkx as nx
import numpy as np

from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.models import Entity, Fact, Subgraph, TimeScope, fact_in_scope


def _bounds(max_hops: int, max_edges: int) -> None:
    if (
        isinstance(max_hops, bool)
        or not isinstance(max_hops, int)
        or not 1 <= max_hops <= 2
    ):
        raise ValueError("max_hops must be 1 or 2")
    if isinstance(max_edges, bool) or not isinstance(max_edges, int) or max_edges < 0:
        raise ValueError("max_edges must be a non-negative integer")


def _seed_bounds(top_k: int, min_cosine: float) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise ValueError("top_k must be a non-negative integer")
    if not math.isfinite(min_cosine) or not -1 <= min_cosine <= 1:
        raise ValueError("min_cosine must be within [-1, 1]")


class InMemoryGraphStore:
    """Immutable-input offline equivalent of the bounded Cypher store.

    Bubbles restrict seeds; SAME_AS traversal can reach other bubbles. Only
    grounded, temporally overlapping facts are traversable. Each relationship,
    including SAME_AS, consumes one hop; the cap counts facts only.
    """

    def __init__(
        self,
        entities: Sequence[Entity],
        facts: Sequence[Fact],
        same_as: Sequence[tuple[str, str]] = (),
        entity_embeddings: Mapping[str, np.ndarray] | None = None,
        fact_embeddings: Mapping[str, np.ndarray] | None = None,
        *,
        now=None,
    ) -> None:
        self.now = now
        self._entities = {e.id: e for e in entities}
        self._facts = {f.id: f for f in facts}
        if len(self._entities) != len(entities) or len(self._facts) != len(facts):
            raise ValueError("entity and fact ids must be unique")
        self._same_as = tuple(sorted({tuple(sorted(pair)) for pair in same_as}))
        for a, b in [*((f.subject_id, f.object_id) for f in facts), *self._same_as]:
            if a not in self._entities or b not in self._entities:
                raise ValueError("edge endpoints must exist in entities")
        self._entity_embeddings = {
            k: np.asarray(v).copy() for k, v in (entity_embeddings or {}).items()
        }
        self._fact_embeddings = {
            k: np.asarray(v).copy() for k, v in (fact_embeddings or {}).items()
        }

    def entities_in(self, bubbles: Sequence[str]) -> list[Entity]:
        return sorted(
            (e for e in self._entities.values() if e.bubble in bubbles),
            key=lambda e: e.id,
        )

    def name_candidates(
        self, question: str, *, bubbles: Sequence[str], limit: int = 100
    ) -> list[Entity]:
        """Bound fuzzy matching by token overlap, independent of entity casing."""
        import re

        tokens = re.findall(r"\w+", question.casefold())
        return [
            e
            for e in self.entities_in(bubbles)
            if any(
                token[:3] in (e.name + " " + " ".join(e.aliases)).casefold()
                for token in tokens
                if len(token) >= 3
            )
        ][:limit]

    def seed_by_embedding(
        self,
        embedding: np.ndarray,
        *,
        bubbles: Sequence[str],
        top_k: int = 5,
        min_cosine: float = 0.5,
    ) -> list[tuple[Entity, float]]:
        _seed_bounds(top_k, min_cosine)
        candidates = [
            e for e in self.entities_in(bubbles) if e.id in self._entity_embeddings
        ]
        vectors = [self._entity_embeddings[e.id] for e in candidates]
        scores = EmbeddingService.cosine_similarity(embedding, vectors)
        found = [(e, float(s)) for e, s in zip(candidates, scores) if s >= min_cosine]
        return sorted(found, key=lambda row: (-row[1], row[0].id))[:top_k]

    def seed_by_fact_embedding(
        self,
        embedding: np.ndarray,
        *,
        bubbles: Sequence[str],
        top_k: int = 10,
        time_scope: TimeScope | None = None,
    ) -> list[tuple[Entity, float]]:
        """Exact read-only cosine over eligible fact text vectors, then endpoints."""
        _seed_bounds(top_k, -1)
        facts = [
            f
            for f in self._facts.values()
            if f.bubble in bubbles
            and f.grounded
            and fact_in_scope(f, time_scope, now=self.now)
            and f.id in self._fact_embeddings
        ]
        scores = EmbeddingService.cosine_similarity(
            embedding, [self._fact_embeddings[f.id] for f in facts]
        )
        ranked = sorted(zip(facts, scores), key=lambda x: (-float(x[1]), x[0].id))[
            :top_k
        ]
        return [
            (self._entities[i], float(score))
            for f, score in ranked
            for i in (f.subject_id, f.object_id)
            if self._entities[i].bubble in bubbles
        ]

    def expand(
        self,
        seed_ids: Sequence[str],
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None,
        max_hops: int = 2,
        max_edges: int = 500,
        excluded_bubbles: Sequence[str] = (),
    ) -> Subgraph:
        _bounds(max_hops, max_edges)
        facts = [
            f
            for f in self._facts.values()
            if f.grounded
            and fact_in_scope(f, time_scope, now=self.now)
            and f.bubble not in excluded_bubbles
            and self._entities[f.subject_id].bubble not in excluded_bubbles
            and self._entities[f.object_id].bubble not in excluded_bubbles
        ]
        graph = nx.Graph()
        allowed = {
            i for i, e in self._entities.items() if e.bubble not in excluded_bubbles
        }
        same_as = [(a, b) for a, b in self._same_as if a in allowed and b in allowed]
        graph.add_nodes_from(allowed)
        graph.add_edges_from((f.subject_id, f.object_id) for f in facts)
        graph.add_edges_from(same_as)
        seeds = sorted(set(seed_ids) & allowed)
        distances = (
            nx.multi_source_dijkstra_path_length(
                graph, seeds, cutoff=max_hops, weight=None
            )
            if seeds
            else {}
        )
        selected = [
            f
            for f in facts
            if min(
                distances.get(f.subject_id, math.inf),
                distances.get(f.object_id, math.inf),
            )
            < max_hops
        ]
        selected.sort(
            key=lambda f: (
                min(distances[f.subject_id], distances[f.object_id]) + 1,
                f.id,
            )
        )
        links = tuple(
            (a, b)
            for a, b in same_as
            if min(distances.get(a, math.inf), distances.get(b, math.inf)) < max_hops
        )
        return Subgraph(
            {i: self._entities[i] for i in sorted(distances)},
            tuple(selected[:max_edges]),
            links,
        )

    def neighbors(
        self, entity_id: str, depth: int = 1, *, excluded_bubbles: Sequence[str] = ()
    ) -> Subgraph:
        _bounds(depth, 500)
        return self.expand(
            [entity_id],
            bubbles=(),
            time_scope=None,
            max_hops=depth,
            excluded_bubbles=excluded_bubbles,
        )

    def facts_about(
        self,
        entity_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        excluded_bubbles: Sequence[str] = (),
    ) -> list[Fact]:
        scope = TimeScope(start, end) if start is not None or end is not None else None
        return sorted(
            (
                f
                for f in self._facts.values()
                if entity_id in (f.subject_id, f.object_id)
                and f.bubble not in excluded_bubbles
                and f.grounded
                and fact_in_scope(f, scope, now=self.now)
            ),
            key=lambda f: f.id,
        )

    def fact_embeddings(self, fact_ids: Sequence[str]) -> dict[str, np.ndarray]:
        return {
            i: self._fact_embeddings[i].copy()
            for i in fact_ids
            if i in self._fact_embeddings
        }
