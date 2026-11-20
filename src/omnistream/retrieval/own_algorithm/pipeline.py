"""Bounded typed fact/name seeds, weighted PPR, version representatives and RRF.

Extends C5 steps 1, 3 and 5; restart remains at seeds, weighted by evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.models import RetrievalResult, ScoredFact, TimeScope
from omnistream.retrieval.own_algorithm.fact_fusion import FactCandidate, fuse_facts
from omnistream.retrieval.own_algorithm.pagerank import personalized_pagerank
from omnistream.retrieval.own_algorithm.rerank import WINDOW, rerank
from omnistream.retrieval.own_algorithm.scoring import score_facts, seed_paths
from omnistream.retrieval.own_algorithm.seeding import seed_entities
from omnistream.retrieval.own_algorithm.versions import fact_versions
from omnistream.retrieval.protocols import GraphStore


def edge_weights(query, embeddings, power: float) -> dict[str, float] | None:
    """Question-aware fact-edge weights: max(cos, 0) ** power, mean-normalised.

    ``power`` 0 disables weighting (all fact edges count 1).
    """
    if not power or not embeddings:
        return None
    import numpy as np

    q = np.asarray(query, dtype=float)
    q = q / (np.linalg.norm(q) or 1.0)
    raw = {}
    for fact_id, vector in embeddings.items():
        v = np.asarray(vector, dtype=float)
        cos = float(q @ v / (np.linalg.norm(v) or 1.0))
        raw[fact_id] = max(cos, 0.0) ** power + 1e-6
    mean = sum(raw.values()) / len(raw)
    return {fact_id: w / mean for fact_id, w in raw.items()}


class OwnRetriever:
    """Bounded graph retrieval with injectable clock and local embeddings."""

    def __init__(
        self,
        store: GraphStore,
        embedder: EmbeddingService,
        *,
        now: Callable[[], datetime] | None = None,
        half_lives: Mapping[str, float] | None = None,
        top_k: int = 20,
        k: int = 60,
        reranker=None,
        passage_source=None,
        specificity_restart: bool = False,
        passage_nodes=None,
    ) -> None:
        self._validate_top_k(top_k)
        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            raise ValueError("k must be a non-negative integer")
        self.store, self.embedder = store, embedder
        self.now = now or (lambda: datetime.now(UTC))
        self.half_lives = half_lives if half_lives is not None else {}
        self.reranker = reranker
        self.passage_source = passage_source
        self.specificity_restart = specificity_restart
        if passage_nodes is not None and passage_source is None:
            raise ValueError("passage_nodes requires a passage_source")
        self.passage_nodes = passage_nodes
        self.top_k, self.k = top_k, k

    @staticmethod
    def _validate_top_k(value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("top_k must be a non-negative integer")

    def retrieve(
        self,
        question: str,
        *,
        bubbles: Sequence[str],
        time_scope: TimeScope | None = None,
        excluded_bubbles: Sequence[str] = (),
        top_k: int | None = None,
    ) -> RetrievalResult:
        self.last_version_groups = []
        limit = self.top_k if top_k is None else top_k
        self._validate_top_k(limit)
        if not limit:
            return RetrievalResult(mode="own")
        query = self.embedder.embed_query(question)
        allowed = [b for b in bubbles if b not in excluded_bubbles]
        options = {}
        dense_chunks: tuple = ()
        if self.passage_nodes is not None:
            from omnistream.retrieval.own_algorithm.passage_nodes import (
                DENSE_K,
                PASSAGE_TOP,
            )

            dense_chunks = tuple(
                self.passage_source.dense(
                    question, allowed, time_scope,
                    getattr(self.passage_nodes, "dense_k", DENSE_K),
                )
            )
            fallback = RetrievalResult(
                mode="own", chunks=dense_chunks[:PASSAGE_TOP], chunks_first=True
            )
        else:
            fallback = RetrievalResult(mode="own")
        if self.passage_source is not None:
            options["passage_seeds"] = self.passage_source.seeds(
                question, allowed, time_scope,
                **({"chunks": dense_chunks} if dense_chunks else {}),
            )
        seeds = seed_entities(
            question,
            query,
            self.store,
            bubbles=allowed,
            **options,
            time_scope=time_scope,
        )
        if not seeds:
            return fallback
        ids = [s.entity.id for s in seeds]
        graph = self.store.expand(
            ids,
            bubbles=bubbles,
            time_scope=time_scope,
            **({"excluded_bubbles": excluded_bubbles} if excluded_bubbles else {}),
        )
        if not graph.facts:
            return RetrievalResult(
                mode="own",
                seeds=tuple(s.entity for s in seeds),
                chunks=fallback.chunks,
                chunks_first=fallback.chunks_first,
            )
        weights = {s.entity.id: max(0.0, s.score) for s in seeds}
        if self.specificity_restart and self.passage_source is not None:
            weights = self.passage_source.restart_weights(seeds)
        ranks = personalized_pagerank(graph, ids, seed_weights=weights)
        embeddings = self.store.fact_embeddings([f.id for f in graph.facts])
        missing = [f for f in graph.facts if f.id not in embeddings]
        if missing:
            embeddings.update(
                zip(
                    (f.id for f in missing),
                    self.embedder.embed_documents([f.text for f in missing]),
                )
            )
        scores = score_facts(graph, ranks, query, embeddings)
        paths = seed_paths(graph, ids)
        facts = {f.id: f for f in graph.facts}
        self.last_version_groups = fact_versions(
            graph, embeddings, scope=time_scope, now=self.now()
        )
        representatives = [g.representative for g in self.last_version_groups]
        candidates = [
            FactCandidate(
                f.id, scores[f.id], f.published_at, f.bubble, f.confidence, paths[f.id]
            )
            for f in representatives
        ]
        fused = fuse_facts(
            candidates,
            now=self.now(),
            half_lives=self.half_lives,
            k=self.k,
            top_n=max(limit, WINDOW) if self.reranker else limit,
        )
        if self.reranker:
            fused = rerank(
                question, fused, lambda f: facts[f.fact.id].text, self.reranker
            )[:limit]
        passages: tuple = ()
        if self.passage_nodes is not None:
            top_facts = getattr(self.passage_nodes, "fact_seeds", 0)
            if top_facts:
                # HippoRAG 2-style query-to-triple seeding: endpoints of the
                # best (reranked) facts join the restart set, rank-weighted,
                # with total mass equal to the entity seeds'.
                weights = dict(weights)
                total = sum(max(0.0, w) for w in weights.values()) or 1.0
                chosen = fused[:top_facts]
                norm = sum(1 / (r + 1) for r in range(len(chosen))) or 1.0
                for r, entry in enumerate(chosen):
                    fact = facts[entry.fact.id]
                    share = total * (1 / (r + 1)) / norm / 2
                    for entity in (fact.subject_id, fact.object_id):
                        weights[entity] = weights.get(entity, 0.0) + share
            passages = self.passage_nodes.rank(
                graph, weights, dense_chunks, allowed, question=question,
                fact_weight=edge_weights(
                    query, embeddings, getattr(self.passage_nodes, "edge_power", 0)
                ),
            )
            if not passages:
                passages = fallback.chunks
        return RetrievalResult(
            mode="own",
            seeds=tuple(s.entity for s in seeds),
            facts=tuple(
                ScoredFact(facts[f.fact.id], f.score, f.fact.path, f.ranks)
                for f in fused
            ),
            chunks=passages,
            chunks_first=self.passage_nodes is not None,
        )
