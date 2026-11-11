"""End-to-end own retriever: spec C5 steps 1-5."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.models import RetrievalResult, ScoredFact, TimeScope
from omnistream.retrieval.own_algorithm.fact_fusion import FactCandidate, fuse_facts
from omnistream.retrieval.own_algorithm.pagerank import personalized_pagerank
from omnistream.retrieval.own_algorithm.scoring import score_facts, seed_paths
from omnistream.retrieval.own_algorithm.seeding import seed_entities
from omnistream.retrieval.protocols import GraphStore


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
    ) -> None:
        self._validate_top_k(top_k)
        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            raise ValueError("k must be a non-negative integer")
        self.store, self.embedder = store, embedder
        self.now = now or (lambda: datetime.now(UTC))
        self.half_lives = half_lives if half_lives is not None else {}
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
        limit = self.top_k if top_k is None else top_k
        self._validate_top_k(limit)
        if not limit:
            return RetrievalResult(mode="own")
        query = self.embedder.embed_query(question)
        seeds = seed_entities(question, query, self.store, bubbles=bubbles)
        if not seeds:
            return RetrievalResult(mode="own")
        # One seed per real-world identity: seeding both bubble-local copies
        # hides the SAME_AS path and spends the seed budget on duplicates.
        identities = set()
        unique_seeds = []
        for seed in seeds:
            identity = seed.entity.global_id or seed.entity.id
            if identity not in identities:
                identities.add(identity)
                unique_seeds.append(seed)
        seeds = unique_seeds
        ids = [s.entity.id for s in seeds]
        graph = self.store.expand(
            ids,
            bubbles=bubbles,
            time_scope=time_scope,
            **({"excluded_bubbles": excluded_bubbles} if excluded_bubbles else {}),
        )
        if not graph.facts:
            return RetrievalResult(mode="own", seeds=tuple(s.entity for s in seeds))
        ranks = personalized_pagerank(graph, ids)
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
        candidates = [
            FactCandidate(
                f.id, scores[f.id], f.published_at, f.bubble, f.confidence, paths[f.id]
            )
            for f in graph.facts
        ]
        fused = fuse_facts(
            candidates,
            now=self.now(),
            half_lives=self.half_lives,
            k=self.k,
            top_n=limit,
        )
        return RetrievalResult(
            mode="own",
            seeds=tuple(s.entity for s in seeds),
            facts=tuple(
                ScoredFact(facts[f.fact.id], f.score, f.fact.path, f.ranks)
                for f in fused
            ),
        )
