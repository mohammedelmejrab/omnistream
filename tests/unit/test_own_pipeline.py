"""Offline end-to-end own retrieval (spec C5, 13.3)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from omnistream.config import Settings
from omnistream.embeddings import EmbeddingService
from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm.fact_fusion import FactCandidate, fuse_facts
from omnistream.retrieval.own_algorithm.pagerank import personalized_pagerank
from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever
from omnistream.retrieval.protocols import Retriever
from tests.unit.test_graph_memory_store import NOW, entity, fact, store  # noqa: F401 - store is a pytest fixture


class Encoder:
    def __init__(self):
        self.inputs = []

    def encode(self, sentences, **kwargs):
        self.inputs.extend(sentences)
        return np.tile([1.0, 0.0], (len(sentences), 1))


def embedder():
    encoder = Encoder()
    settings = Settings(_env_file=None, embedding_model="offline-test", embedding_dim=2)
    return EmbeddingService(settings, encoder=encoder), encoder


def test_pipeline_filters_and_fallback(store):  # noqa: F811 - pytest fixture param
    service, encoder = embedder()
    retriever = OwnRetriever(store, service, now=lambda: NOW)
    assert isinstance(retriever, Retriever)
    result = retriever.retrieve(
        "Acme", bubbles=["news"], time_scope=TimeScope(NOW, NOW)
    )
    assert result.mode == "own"
    assert {r.fact.id for r in result.facts} == {"ab", "bc", "cross"}
    assert all(
        r.path and "fact_score" in r.ranks and "confidence" not in r.ranks
        for r in result.facts
    )
    assert any("Fact cross" == text for text in encoder.inputs)
    assert result == retriever.retrieve(
        "Acme", bubbles=["news"], time_scope=TimeScope(NOW, NOW)
    )
    assert len(retriever.retrieve("Acme", bubbles=["news"], top_k=1).facts) == 1


def test_top_twenty_order_matches_fusion():
    service, encoder = embedder()
    entities = [entity("seed"), *[entity(str(i)) for i in range(25)]]
    facts = [
        replace(fact(f"{i:02}", "seed", str(i)), confidence=i / 25) for i in range(25)
    ]
    built = InMemoryGraphStore(
        entities,
        facts,
        entity_embeddings={"seed": np.array([1.0, 0.0])},
        fact_embeddings={f.id: np.array([1.0, 0.0]) for f in facts},
    )
    retriever = OwnRetriever(built, service, now=lambda: NOW)
    result = retriever.retrieve("question", bubbles=["news"])
    assert len(result.facts) == 20
    graph = built.neighbors("seed", 2)
    pr = personalized_pagerank(graph, [e.id for e in result.seeds])
    expected = fuse_facts(
        [
            FactCandidate(
                f.id, (pr["seed"] + pr[f.object_id]) / 2, NOW, "news", f.confidence
            )
            for f in facts
        ],
        now=NOW,
    )
    assert [r.fact.id for r in result.facts] == [r.fact.id for r in expected]
    assert result == retriever.retrieve("question", bubbles=["news"])
    assert len(encoder.inputs) == 1  # persisted fact vectors avoid document embedding


def test_empty_and_validation():
    service, _ = embedder()
    retriever = OwnRetriever(InMemoryGraphStore([], []), service, now=lambda: NOW)
    assert not retriever.retrieve("none", bubbles=["news"]).facts
    assert not retriever.retrieve("none", bubbles=[], top_k=0).facts
    with pytest.raises(ValueError):
        retriever.retrieve("none", bubbles=[], top_k=-1)
    with pytest.raises(ValueError):
        OwnRetriever(retriever.store, service, k=-1)


def test_shared_identity_seeds_preserve_cross_bubble_bridge():
    from omnistream.retrieval.models import Entity

    service, _ = embedder()
    entities = [
        Entity("a", "Pelvoria Institute", "Organization", "finance", "global-p"),
        Entity("b", "Pelvoria Institute", "Organization", "research", "global-p"),
        Entity("c", "Zorvanta Labs", "Organization", "finance"),
        Entity("d", "Nuvex Prism", "Product", "research"),
    ]
    graph = InMemoryGraphStore(
        entities,
        [
            replace(fact("funds", "c", "a"), bubble="finance"),
            replace(fact("developed", "b", "d"), bubble="research"),
        ],
        same_as=[("a", "b")],
    )
    result = OwnRetriever(graph, service, now=lambda: NOW).retrieve(
        "Pelvoria Institute", bubbles=["finance", "research"]
    )
    assert len(result.seeds) == 1
    assert {f.fact.id for f in result.facts} == {"funds", "developed"}
    assert any(
        frozenset((a, b)) == {"a", "b"}
        for f in result.facts
        for a, b in zip(f.path, f.path[1:])
    )


def test_changed_facts_follow_validity_not_report_publication():
    from datetime import UTC, datetime

    service, _ = embedder()
    boundary = datetime(2025, 2, 7, tzinfo=UTC)
    report = datetime(2025, 2, 8, tzinfo=UTC)
    old = replace(
        fact("old", "a", "b"),
        published_at=report,
        valid_at=datetime(2025, 1, 1, tzinfo=UTC),
        invalid_at=boundary,
        expired_at=report,
    )
    current = replace(fact("new", "a", "b"), published_at=report, valid_at=boundary)
    graph = InMemoryGraphStore(
        [entity("a"), entity("b")],
        [old, current],
        entity_embeddings={"a": np.array([1.0, 0.0])},
    )
    retriever = OwnRetriever(graph, service)
    historical = datetime(2025, 2, 6, 23, 59, 59, tzinfo=UTC)
    assert {
        f.fact.id
        for f in retriever.retrieve(
            "Entity a", bubbles=["news"], time_scope=TimeScope(historical, historical)
        ).facts
    } == {"old"}
    assert {
        f.fact.id
        for f in retriever.retrieve(
            "Entity a", bubbles=["news"], time_scope=TimeScope(boundary, boundary)
        ).facts
    } == {"new"}
    assert {
        f.fact.id for f in retriever.retrieve("Entity a", bubbles=["news"]).facts
    } == {"new"}
