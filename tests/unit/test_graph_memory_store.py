"""Offline graph store parity checks for spec 4.3 and C5."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.retrieval.models import Entity, Fact, TimeScope
from omnistream.retrieval.protocols import GraphStore

NOW = datetime(2026, 10, 20, tzinfo=UTC)


def entity(i, bubble="news", **kwargs):
    return Entity(i, "Entity " + i, "Organization", bubble, **kwargs)


def fact(i, a, b, **kwargs):
    return Fact(
        i,
        a,
        b,
        "RELATES",
        "Fact " + i,
        kwargs.pop("bubble", "news"),
        "item-" + i,
        None,
        NOW,
        **kwargs,
    )


@pytest.fixture
def store():
    entities = [
        entity("a", aliases=("Acme",)),
        entity("b"),
        entity("c"),
        entity("d"),
        entity("af", "finance"),
        entity("f", "finance"),
    ]
    facts = [
        fact("ab", "a", "b"),
        fact("bc", "b", "c"),
        fact("cd", "c", "d"),
        fact("cross", "af", "f", bubble="finance"),
        fact("bad", "a", "d", grounded=False),
        fact("old", "a", "d", invalid_at=datetime(2020, 1, 1, tzinfo=UTC)),
    ]
    return InMemoryGraphStore(
        entities,
        facts,
        [("a", "af")],
        {"a": np.array([1.0, 0.0]), "af": np.array([1.0, 0.0])},
    )


def test_expand_filters_hops_and_cross_bubble(store):
    assert isinstance(store, GraphStore)
    graph = store.expand(["a"], bubbles=["news"], time_scope=TimeScope(NOW, NOW))
    assert [f.id for f in graph.facts] == ["ab", "bc", "cross"]
    assert graph.same_as == (("a", "af"),)
    assert "f" in graph.entities and "d" not in graph.entities
    assert [f.id for f in store.facts_about("a", NOW, NOW)] == ["ab"]
    assert {f.id for f in store.neighbors("a").facts} == {"ab", "old"}


def test_vector_top_five_inclusive_boundary():
    entities = [entity(str(i)) for i in range(8)]
    vectors = {str(i): np.array([1.0, 0.0]) for i in range(6)}
    vectors["6"] = np.array([0.5, np.sqrt(0.75)])
    vectors["7"] = np.array([0.4, np.sqrt(0.84)])
    store = InMemoryGraphStore(entities, [], entity_embeddings=vectors)
    assert len(store.seed_by_embedding(np.array([1.0, 0.0]), bubbles=["news"])) == 5
    seeds = store.seed_by_embedding(np.array([1.0, 0.0]), bubbles=["news"], top_k=10)
    assert seeds[-1][0].id == "6" and seeds[-1][1] == 0.5
    assert store.seed_by_embedding(np.array([1.0, 0.0]), bubbles=["finance"]) == []


def test_cap_is_deterministic_and_embeddings_are_copied():
    entities = [entity("a"), *[entity(str(i)) for i in range(510)]]
    facts = [fact(f"f{i:04}", "a", str(i)) for i in range(510)]
    store = InMemoryGraphStore(
        entities, list(reversed(facts)), fact_embeddings={"f0000": np.ones(2)}
    )
    graph = store.neighbors("a", 2)
    assert [f.id for f in graph.facts] == [f.id for f in facts[:500]]
    vectors = store.fact_embeddings(["f0000", "missing"])
    vectors["f0000"][0] = 0
    assert store.fact_embeddings(["f0000"])["f0000"][0] == 1


@pytest.mark.parametrize("depth", [0, 3, -1, True, 1.5])
def test_depth_validation(store, depth):
    with pytest.raises(ValueError):
        store.neighbors("a", depth)


def test_missing_seeds_and_zero_cap(store):
    assert not store.neighbors("missing").facts
    assert not store.expand(["a"], bubbles=["news"], time_scope=None, max_edges=0).facts


def test_bad_inputs():
    with pytest.raises(ValueError):
        InMemoryGraphStore([entity("a")], [fact("f", "a", "missing")])
    with pytest.raises(ValueError):
        InMemoryGraphStore([entity("a"), entity("a")], [])


@pytest.mark.parametrize(
    "valid,invalid,included",
    [
        (None, NOW, False),
        (NOW, None, True),
        (NOW, NOW, False),
        (datetime(2027, 1, 1, tzinfo=UTC), None, False),
        (datetime(2025, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC), True),
    ],
)
def test_temporal_boundary_parity(valid, invalid, included):
    store = InMemoryGraphStore(
        [entity("a"), entity("b")],
        [fact("f", "a", "b", valid_at=valid, invalid_at=invalid)],
    )
    graph = store.expand(["a"], bubbles=["news"], time_scope=TimeScope(NOW, NOW))
    assert bool(graph.facts) is included
    assert bool(store.facts_about("a", NOW, NOW)) is included


def test_global_identity_nodes_consume_a_hop():
    store = InMemoryGraphStore(
        [
            entity("a"),
            entity("global", ""),
            entity("finance", "finance"),
            entity("bank", "finance"),
        ],
        [fact("third-hop", "finance", "bank", bubble="finance")],
        [("a", "global"), ("global", "finance")],
    )
    graph = store.neighbors("a", 2)
    assert set(graph.entities) == {"a", "global", "finance"}
    assert len(graph.same_as) == 2 and not graph.facts
