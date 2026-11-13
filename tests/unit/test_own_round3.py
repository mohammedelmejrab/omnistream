"""Round-three general retrieval regressions, independent of evaluation gold."""

from dataclasses import replace
from datetime import timedelta
from itertools import permutations

import numpy as np
import pytest

from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.graph.name_search import escape_lucene, lucene_query
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.models import Entity, Subgraph, TimeScope
from omnistream.retrieval.own_algorithm.seeding import seed_entities
from omnistream.retrieval.own_algorithm.versions import fact_versions
from tests.unit.test_graph_memory_store import NOW, fact
from tests.unit.test_neo4j_store import NODE, OTHER, Driver


def test_common_words_cannot_push_real_name_beyond_cap():
    entities = [
        Entity(str(i), "The Computer Incorporated", "Organization", "news")
        for i in range(300)
    ]
    target = Entity("zzz", "Aster Labs", "Organization", "news")
    store = InMemoryGraphStore([*entities, target], [])
    assert store.name_candidates(
        "What is the company Aster Labs in the inc com?", bubbles=["news"], limit=1
    ) == [target]


def test_lucene_literals():
    assert escape_lucene('a+b:c*(x)"\\') == 'a\\+b\\:c\\*\\(x\\)\\"\\\\'
    assert (
        lucene_query("the OR name:* (Aster) AND inc") == 'name:"aster" OR name:"name"'
    )


@pytest.mark.parametrize(
    "texts",
    [
        ("reported Q1 2024 results", "reported Q2 2024 results"),
        ("bought 10 million shares", "bought 20 million shares"),
        ("met in January", "met in February"),
    ],
)
def test_numeric_and_date_facts_coexist_even_with_identical_embeddings(texts):
    a = replace(fact("a", "s", "o"), text=texts[0])
    b = replace(a, id="b", text=texts[1], published_at=NOW - timedelta(days=1))
    graph = Subgraph({}, (a, b))
    for facts in permutations(graph.facts):
        result = fact_versions(
            replace(graph, facts=facts),
            {"a": np.ones(2), "b": np.ones(2)},
            scope=None,
            now=NOW,
        )
        assert len(result) == 2


def test_supersession_now_and_unbounded_before_question():
    old = replace(
        fact("old", "s", "o"),
        text="A served as CEO",
        valid_at=NOW - timedelta(days=10),
        invalid_at=NOW,
    )
    new = replace(old, id="new", text="B served as CEO", valid_at=NOW, invalid_at=None)
    graph = Subgraph({}, (old, new))
    assert [
        g.representative.id for g in fact_versions(graph, {}, scope=None, now=NOW)
    ] == ["new"]
    assert len(fact_versions(graph, {}, scope=TimeScope(), now=NOW)) == 2


def test_cross_bubble_never_merges_and_input_order_is_irrelevant():
    a = replace(fact("a", "s", "o"), text="They collaborate")
    b = replace(a, id="b", bubble="finance")
    c = replace(a, id="c", published_at=NOW - timedelta(days=1))
    outcomes = []
    for facts in permutations((a, b, c)):
        groups = fact_versions(Subgraph({}, facts), {}, scope=None, now=NOW)
        outcomes.append(
            [(g.representative.id, tuple(f.id for f in g.versions)) for g in groups]
        )
    assert all(o == outcomes[0] for o in outcomes)
    assert len(outcomes[0]) == 2


def test_generic_fact_endpoints_seed_at_declared_reduction():
    entities = [Entity(i, i, "Concept", "news") for i in ("s", "o")]
    store = InMemoryGraphStore(
        entities,
        [fact("f", "s", "o")],
        fact_embeddings={"f": np.ones(2)},
        now=lambda: NOW,
    )
    seeds = seed_entities("unrelated", np.ones(2), store, bubbles=["news"])
    assert len(seeds) == 2
    assert all(s.score == 0.5 and s.source == "fact" for s in seeds)


def test_fact_ann_shortfall_falls_back_to_exact_and_logs(caplog):
    rows = [{"id": "f", "subject": "a", "object": "b", "score": 0.8}]
    driver = Driver([], [], [], rows, [{"e": NODE}, {"e": OTHER}])
    store = Neo4jGraphStore(driver)
    store._cosine_index = lambda *a: True
    assert (
        len(
            store.seed_by_fact_embedding(
                np.ones(2), bubbles=["news", "finance"], top_k=2
            )
        )
        == 2
    )
    assert "shortfall" in caplog.text
    assert "vector.similarity.cosine" in driver.calls[3][0]
    assert store.search_paths[-1]["path"] == "fact_exact_ann_shortfall"


def test_incompatible_index_falls_back_with_warning(caplog):
    driver = Driver(
        [
            {
                "labelsOrTypes": ["Wrong"],
                "properties": ["embedding"],
                "options": {"indexConfig": {"vector.similarity_function": "euclidean"}},
                "state": "ONLINE",
            }
        ],
        [],
    )
    store = Neo4jGraphStore(driver)
    assert store.seed_by_embedding(np.ones(2), bubbles=["news"]) == []
    assert "incompatible" in caplog.text
    assert "vector.similarity.cosine" in driver.calls[-1][0]


def test_fact_quota_and_scores_are_independent_of_source_magnitude():
    class Store:
        def name_candidates(self, *args, **kwargs):
            return []

        def seed_by_embedding(self, *args, **kwargs):
            return [
                (Entity("n" + str(i), "named", "Product", "news"), 0.99 - i * 0.001)
                for i in range(5)
            ]

        def seed_by_fact_embedding(self, *args, **kwargs):
            return [
                (
                    Entity("f" + str(i), "fact endpoint", "Product", "news"),
                    0.1 - i * 0.001,
                )
                for i in range(5)
            ]

    seeds = seed_entities(
        "unrelated", np.ones(2), Store(), bubbles=["news"], max_seeds=4
    )
    assert sum(s.source == "fact" for s in seeds) >= 2
    by_id = {s.entity.id: s.score for s in seeds}
    assert by_id["f0"] == by_id["n0"] == 1


def test_fulltext_query_uses_parameters_and_rank_order():
    driver = Driver([{"name": "node_name_and_summary"}], [{"e": NODE}])
    store = Neo4jGraphStore(driver)
    assert (
        store.name_candidates("the Acme OR name:*", bubbles=["news"], limit=3)[0].id
        == "a"
    )
    query, params = driver.calls[-1]
    assert params["lexical_query"] == 'name:"acme" OR name:"name"'
    assert "ORDER BY score DESC" in query and "LIMIT $limit" in query
    assert params["limit"] == 3
