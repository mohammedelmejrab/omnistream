"""General mechanism tests; no eval-v2 names, labels, or gold-derived settings."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.retrieval.models import Entity, TimeScope
from omnistream.retrieval.own_algorithm.fact_fusion import FactCandidate, fuse_facts
from omnistream.retrieval.own_algorithm.seeding import is_named_entity, seed_entities
from tests.unit.test_graph_memory_store import NOW, fact


@pytest.mark.parametrize(
    "name,kind,expected",
    [
        ("office supplies", "Concept", False),
        ("Arc Labs", "Organization", True),
        ("A Generic Type", "Generic", False),
        ("DNA", "Concept", False),
        ("123 widgets", "Product", True),
    ],
)
def test_generic_guard(name, kind, expected):
    assert is_named_entity(Entity("e", name, kind, "news")) is expected


def test_name_budget_refills_after_identity_and_generic_filtering():
    entities = [
        Entity(str(i), "Arc Labs", "Organization", "news", "same") for i in range(7)
    ]
    entities += [Entity("g", "office supplies", "Concept", "news")]
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


def test_rounding_drops_noise_and_weights_are_explicit():
    candidates = [
        FactCandidate("a", 0.9, NOW, "news", 0.92),
        FactCandidate("b", 0.1, NOW - timedelta(days=10), "news", 0.920000001),
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


@pytest.mark.parametrize(
    "name",
    [
        "eBay",
        "iPhone",
        "arXiv",
        "x86",
        "adidas",
        "bitcoin",
        "mRNA",
        "pH",
        "ffmpeg",
        "??",
        "???????",
    ],
)
def test_named_type_is_independent_of_script_and_case(name):
    assert is_named_entity(Entity("e", name, "Product", "news"))


@pytest.mark.parametrize(
    "name", ["Research Funding Agreement", "the Chief Scientist", "CEO"]
)
def test_generic_typed_phrase_does_not_seed(name):
    assert not is_named_entity(Entity("e", name, "Concept", "news", global_id="linked"))


def test_rare_corroboration_signal_survives():
    candidates = [FactCandidate(str(i), 0.5, NOW, "news", 0.92) for i in range(99)]
    candidates.append(FactCandidate("rare", 0.5, NOW, "news", 0.99))
    out = fuse_facts(candidates, now=NOW)
    assert out[0].fact.id == "rare"
    assert all("confidence" in f.ranks for f in out)


def test_seed_cap_and_fact_endpoint_eligibility():
    entities = [Entity(str(i), "widget", "Product", "news") for i in range(20)]
    entities.append(Entity("generic", "CEO", "Concept", "news"))
    facts = [fact(str(i), str(i), "generic") for i in range(20)]
    store = InMemoryGraphStore(
        entities,
        facts,
        fact_embeddings={f.id: np.ones(2) for f in facts},
        now=lambda: NOW,
    )
    seeds = seed_entities("unrelated", np.ones(2), store, bubbles=["news"], max_seeds=5)
    assert len(seeds) == 5
    assert "generic" not in {s.entity.id for s in seeds}


def test_weighted_restart_and_zero_fallback():
    from omnistream.retrieval.models import Subgraph
    from omnistream.retrieval.own_algorithm.pagerank import personalized_pagerank

    graph = Subgraph({i: Entity(i, i, "Product", "news") for i in ("a", "b")}, ())
    ranks = personalized_pagerank(graph, ["a", "b"], seed_weights={"a": 0.9, "b": 0.1})
    assert ranks["a"] == pytest.approx(0.9)
    assert personalized_pagerank(graph, ["a", "b"], seed_weights={})[
        "a"
    ] == pytest.approx(0.5)


def test_versions_current_point_and_interval_and_identity():
    from omnistream.retrieval.models import Subgraph
    from omnistream.retrieval.own_algorithm.versions import fact_versions

    entities = {
        i: Entity(i, i, "Product", "news", global_id=g)
        for i, g in [("a", "A"), ("copy", "A"), ("b", "B")]
    }
    old = replace(
        fact("old", "a", "b"),
        published_at=NOW - timedelta(days=10),
        valid_at=NOW - timedelta(days=10),
    )
    new = replace(fact("new", "copy", "b"), published_at=NOW, valid_at=NOW)
    unrelated = replace(new, id="other", relation="different relation")
    graph = Subgraph(entities, (old, new, unrelated))
    groups = fact_versions(graph, {}, scope=None, now=NOW)
    assert {g.representative.id for g in groups} == {"new", "old", "other"}
    assert {f.id for g in groups for f in g.versions} == {"new", "old", "other"}
    past = NOW - timedelta(days=5)
    assert [
        g.representative.id
        for g in fact_versions(graph, {}, scope=TimeScope(past, past), now=NOW)
    ] == ["old"]
    assert (
        len(
            fact_versions(
                graph, {}, scope=TimeScope(NOW - timedelta(days=20), NOW), now=NOW
            )
        )
        == 3
    )


def test_versions_paraphrase_threshold():
    from omnistream.retrieval.models import Subgraph
    from omnistream.retrieval.own_algorithm.versions import fact_versions

    entities = {i: Entity(i, i, "Product", "news") for i in ("a", "b")}
    a = replace(
        fact("a", "a", "b"), relation="works with", published_at=NOW - timedelta(days=1)
    )
    b = replace(
        a, id="b", relation="works_with", text="A distinct paraphrase", published_at=NOW
    )
    graph = Subgraph(entities, (a, b))
    assert (
        len(
            fact_versions(
                graph,
                {"a": np.array([1.0, 0]), "b": np.array([1.0, 0])},
                scope=None,
                now=NOW,
            )
        )
        == 1
    )
    assert (
        len(
            fact_versions(
                graph,
                {"a": np.array([1.0, 0]), "b": np.array([0.0, 1])},
                scope=None,
                now=NOW,
            )
        )
        == 2
    )
