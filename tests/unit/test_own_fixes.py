"""General mechanism tests; no eval-v2 names, labels, or gold-derived settings."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.models import Entity, TimeScope
from omnistream.retrieval.own_algorithm.fact_fusion import FactCandidate, fuse_facts
from omnistream.retrieval.own_algorithm.seeding import is_named_entity, seed_entities
from tests.unit.test_graph_memory_store import NOW, fact


@pytest.mark.parametrize(
    "name,kind,expected",
    [
        ("laboratory equipment", "Product", False),
        ("Arc Labs", "Organization", True),
        ("A Generic Type", "Generic", False),
        ("DNA", "Concept", True),
        ("123 equipment", "Product", False),
    ],
)
def test_generic_guard(name, kind, expected):
    assert is_named_entity(Entity("e", name, kind, "news")) is expected


def test_name_budget_refills_after_identity_and_generic_filtering():
    entities = [
        Entity(str(i), "Arc Labs", "Organization", "news", "same") for i in range(7)
    ]
    entities += [Entity("g", "equipment", "Product", "news")]
    entities += [
        Entity("u" + str(i), "Named " + str(i), "Organization", "news")
        for i in range(4)
    ]
    store = InMemoryGraphStore(
        entities, [], entity_embeddings={e.id: np.array([1.0, 0.0]) for e in entities}
    )
    seeds = seed_entities("unrelated", np.array([1.0, 0.0]), store, bubbles=["news"])
    assert len(seeds) == 5
    assert len({s.entity.global_id or s.entity.id for s in seeds}) == 5
    assert "g" not in {s.entity.id for s in seeds}


def test_fact_seeds_work_without_named_query_or_entity_vectors():
    entities = [
        Entity("a", "equipment", "Product", "news"),
        Entity("b", "division", "Organization", "news"),
    ]
    store = InMemoryGraphStore(
        entities,
        [fact("f", "a", "b")],
        fact_embeddings={"f": np.array([1.0, 0.0])},
        now=lambda: NOW,
    )
    seeds = seed_entities(
        "Which was recalled?", np.array([1.0, 0.0]), store, bubbles=["news"]
    )
    assert {s.entity.id for s in seeds} == {"a", "b"}
    assert all(s.source == "fact" and s.score == 1 for s in seeds)
    assert not seed_entities("Which?", np.array([1.0, 0.0]), store, bubbles=["finance"])


def test_fact_seeds_respect_grounding_validity_and_top_k():
    entities = [Entity(str(i), "generic", "Concept", "news") for i in range(6)]
    facts = [
        replace(fact("past", "0", "1"), invalid_at=NOW - timedelta(days=1)),
        replace(fact("bad", "2", "3"), grounded=False),
        replace(fact("ok", "4", "5"), valid_at=NOW),
    ]
    store = InMemoryGraphStore(
        entities,
        facts,
        fact_embeddings={f.id: np.array([1.0, 0.0]) for f in facts},
        now=lambda: NOW,
    )
    assert {
        e.id
        for e, _ in store.seed_by_fact_embedding(
            np.array([1.0, 0.0]), bubbles=["news"], top_k=1
        )
    } == {"4", "5"}
    scope = TimeScope(NOW - timedelta(days=3), NOW - timedelta(days=2))
    assert {
        e.id
        for e, _ in store.seed_by_fact_embedding(
            np.array([1.0, 0.0]), bubbles=["news"], time_scope=scope
        )
    } == {"0", "1"}
    assert (
        store.seed_by_fact_embedding(np.array([1.0, 0.0]), bubbles=["news"], top_k=0)
        == []
    )


def test_near_constant_auxiliary_signals_drop_and_weights_are_explicit():
    candidates = [
        FactCandidate("a", 0.9, NOW, "news", 0.92),
        FactCandidate("b", 0.1, NOW - timedelta(days=10), "news", 0.921),
    ]
    out = fuse_facts(candidates, now=NOW)
    assert all("confidence" not in x.ranks for x in out)
    assert out[0].fact.id == "a"
    assert out[0].score == pytest.approx(2 / 61 + 1 / 61)
    legacy = fuse_facts(candidates, now=NOW, relevance_weight=1, drop_constant=False)
    assert all("confidence" in x.ranks for x in legacy)
    assert fuse_facts(candidates, now=NOW, relevance_weight=3)[
        0
    ].score == pytest.approx(3 / 61 + 1 / 61)


def test_constant_signals_cannot_break_relevance_ties():
    candidates = [FactCandidate(i, 0.5, NOW, "news", 0.92) for i in ("b", "a")]
    out = fuse_facts(candidates, now=NOW)
    assert all(x.ranks == {"fact_score": 1} for x in out)
    assert out[0].score == out[1].score


@pytest.mark.parametrize("indexed", [False, True])
def test_neo4j_fact_seed_read_only_index_and_fallback(indexed):
    store = Neo4jGraphStore(None, now=lambda: NOW)
    calls = []

    def run(query, **params):
        calls.append((query, params))
        if query.startswith("SHOW"):
            return [{"name": "existing_vector"}] if indexed else []
        return [
            {
                "id": "f",
                "subject": "a",
                "object": "b",
                "score": 0.8,
                "embedding": [0.8, 0.6],
            }
        ]

    store._run = run
    store.entities_in = lambda bubbles: [
        Entity("a", "Arc", "Product", "news"),
        Entity("b", "B", "Product", "news"),
    ]
    result = store.seed_by_fact_embedding(np.array([1.0, 0.0]), bubbles=["news"])
    assert [e.id for e, _ in result] == ["a", "b"]
    assert all(score == pytest.approx(0.8) for _, score in result)
    assert all("CREATE" not in q and "SET " not in q for q, _ in calls)
    assert "r.grounded = true" in calls[-1][0]
    assert calls[-1][1]["now"] == NOW
    assert ("queryRelationships" in calls[-1][0]) is indexed
