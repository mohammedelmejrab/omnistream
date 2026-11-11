"""Parameterised Cypher adapter tests: never contacts Neo4j (spec 13.3)."""

from __future__ import annotations

import numpy as np
import pytest

from omnistream.config import Settings
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.protocols import GraphStore
from tests.unit.test_graph_memory_store import NOW


class Driver:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []
        self.databases = []

    def session(self, **kwargs):
        self.databases.append(kwargs)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        return next(self.responses)


NODE = {
    "uuid": "a",
    "name": "Acme",
    "type": "Organization",
    "group_id": "news",
    "aliases": ["ACME"],
}
OTHER = {"uuid": "b", "name": "Bank", "group_id": "finance"}
EDGE = {
    "uuid": "f",
    "name": "FUNDS",
    "fact": "Acme funds Bank",
    "group_id": "finance",
    "item_id": "item",
    "published_at": NOW.isoformat(),
    "valid_at": NOW,
    "grounded": True,
    "confidence": 0.8,
    "credibility": 0.9,
    "source_count": 2,
}


def test_seed_parameters_mapping_and_entities():
    malicious = "news' OR true //"
    index = "index' malicious"
    driver = Driver([{"e": NODE, "score": 0.5}], [{"e": NODE}])
    store = Neo4jGraphStore(driver, database="test-db", entity_index_name=index)
    assert isinstance(store, GraphStore)
    result = store.seed_by_embedding(np.array([1.0, 0.0]), bubbles=[malicious])
    assert result[0][0].aliases == ("ACME",) and result[0][1] == 0.5
    query, params = driver.calls[0]
    assert malicious not in query and index not in query
    assert "2.0 * index_score - 1.0 AS score" in query
    assert "db.index.vector.queryNodes" in query and "score >= $min_cosine" in query
    assert "node.group_id IN $bubbles" in query and "LIMIT $top_k" in query
    assert params == {
        "index_name": index,
        "embedding": [1.0, 0.0],
        "bubbles": [malicious],
        "min_cosine": 0.5,
        "top_k": 5,
    }
    assert store.entities_in(["news"])[0].id == "a"
    assert driver.databases == [{"database": "test-db"}] * 2


def test_expand_query_bounds_filters_mapping_and_identity():
    driver = Driver(
        [
            {
                "entities": [NODE, OTHER, NODE],
                "facts": [{"fact": EDGE, "subject": "a", "object": "b"}],
                "same_as": [["a", "b"], ["b", "a"]],
            }
        ],
        [],
    )
    graph = Neo4jGraphStore(driver).expand(
        ["a"], bubbles=["news"], time_scope=TimeScope(NOW, NOW)
    )
    assert set(graph.entities) == {"a", "b"} and graph.same_as == (("a", "b"),)
    fact = graph.facts[0]
    assert (fact.id, fact.subject_id, fact.object_id, fact.text) == (
        "f",
        "a",
        "b",
        "Acme funds Bank",
    )
    assert (
        fact.published_at == NOW and fact.confidence == 0.8 and fact.source_count == 2
    )
    query, params = driver.calls[0]
    assert "*0..4" not in query and "UNION" in query and "SAME_AS" in query
    assert driver.calls[1][1]["seed_ids"] == ["b"]
    assert (
        "grounded = true" in query
        and "r.valid_at <= $end" in query
        and "r.invalid_at > $start" in query
    )
    assert "LIMIT $max_edges" in query
    assert params == {
        "seed_ids": ["a"],
        "known_fact_ids": [],
        "excluded_bubbles": [],
        "max_edges": 500,
        "now": None,
        "start": NOW,
        "end": NOW,
    }
    assert "NOT coalesce(target.group_id" in query


def test_neighbors_facts_and_embeddings():
    driver = Driver(
        [{"entities": [NODE], "facts": [], "same_as": []}],
        [{"r": EDGE, "subject": "a", "object": "b"}],
        [{"id": "f", "embedding": [1.0, 0.0]}],
    )
    store = Neo4jGraphStore(driver)
    assert not store.neighbors("a", 1).facts
    assert len(driver.calls) == 1
    assert store.facts_about("a", NOW, NOW)[0].relation == "FUNDS"
    query, params = driver.calls[1]
    assert params == {
        "entity_id": "a",
        "excluded_bubbles": [],
        "now": None,
        "start": NOW,
        "end": NOW,
    }
    assert "grounded = true" in query and "r.invalid_at > $start" in query
    assert np.array_equal(store.fact_embeddings(["f"])["f"], [1.0, 0.0])
    assert driver.calls[2][1] == {"fact_ids": ["f"]}


@pytest.mark.parametrize("depth", [0, 3, True, 1.5])
def test_invalid_depth_never_opens_session(depth):
    driver = Driver()
    with pytest.raises(ValueError):
        Neo4jGraphStore(driver).neighbors("a", depth)
    assert not driver.calls


def test_from_settings_uses_injected_factory(monkeypatch):
    driver = Driver()
    calls = []

    def factory(uri, **kwargs):
        calls.append((uri, kwargs))
        return driver

    monkeypatch.setattr("neo4j.GraphDatabase.driver", factory)
    settings = Settings(
        _env_file=None,
        neo4j_uri="bolt://offline",
        neo4j_user="test",
        neo4j_password="fake",
    )
    assert Neo4jGraphStore.from_settings(settings).driver is driver
    assert calls == [("bolt://offline", {"auth": ("test", "fake")})]


def test_invalid_seed_and_empty_bubbles_never_run():
    driver = Driver()
    store = Neo4jGraphStore(driver)
    assert store.seed_by_embedding(np.ones(2), bubbles=[]) == []
    with pytest.raises(ValueError):
        store.seed_by_embedding(np.ones(2), bubbles=["news"], top_k=-1)
    with pytest.raises(ValueError):
        store.seed_by_embedding(np.array([float("nan")]), bubbles=["news"])
    assert not driver.calls


@pytest.mark.parametrize("dimension", [None, 8, 384])
def test_reader_index_dimension_check(dimension):
    rows = (
        []
        if dimension is None
        else [{"options": {"indexConfig": {"vector.dimensions": dimension}}}]
    )
    driver = Driver([], rows, [])
    if dimension == 384:
        Neo4jGraphStore(driver).ensure_schema(384)
        assert "awaitIndex" in driver.calls[-1][0]
    else:
        with pytest.raises(ValueError, match="expected 384"):
            Neo4jGraphStore(driver).ensure_schema(384)
    assert "SHOW INDEXES" in driver.calls[1][0]
