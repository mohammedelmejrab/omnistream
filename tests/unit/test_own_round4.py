"""Passage seeding controls using local fakes."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.retrieval.models import Chunk, Entity, TimeScope
from omnistream.retrieval.own_algorithm.passages import PassageSource
from omnistream.retrieval.own_algorithm.seeding import Seed, seed_entities


def test_ranked_chunks_map_by_bubble_and_item_and_drop_concepts():
    classic, graph = Mock(), Mock()
    chunks = [
        Chunk(str(i), "text", "same-item", b, None, None)
        for i, b in enumerate(("a", "b"))
    ]
    classic.retrieve.return_value.chunks = chunks
    graph._run.return_value = [
        {
            "entity": {"uuid": t, "group_id": "a", "name": t, "labels": [t]},
            "score": 0.375,
        }
        for t in ("Person", "Concept")
    ]
    scope = TimeScope()
    found = PassageSource(classic, graph).seeds("query", ["a", "b"], scope)
    classic.retrieve.assert_called_once_with(
        "query", bubbles=["a", "b"], time_scope=scope, top_k=5
    )
    assert graph._run.call_args.kwargs["passages"] == [
        {"bubble": "a", "item": "same-item", "rank": 1},
        {"bubble": "b", "item": "same-item", "rank": 2},
    ]
    assert [(s.entity.id, s.score, s.source) for s in found] == [
        ("Person", 0.375, "passage")
    ]


def test_empty_passages_do_not_query_graph():
    graph = Mock()
    classic = Mock()
    classic.retrieve.return_value = SimpleNamespace(chunks=[])
    assert PassageSource(classic, graph).seeds("query", [], None) == []
    graph._run.assert_not_called()


def test_specificity_scales_restart_without_removing_unmentioned_seeds():
    seeds = [Seed(Entity(i, i, "Person", "a"), 0.5, "fact") for i in ("many", "zero")]
    graph = Mock()
    graph._run.return_value = [{"id": "many", "frequency": 4}]
    assert PassageSource(None, graph).restart_weights(seeds) == {
        "many": 0.125,
        "zero": 0.5,
    }


def test_passages_share_identity_cap_and_refill():
    entities = [Entity(str(i), str(i), "Person", "a", str(i // 2)) for i in range(12)]
    passage = [Seed(e, 1 / (i + 1), "passage") for i, e in enumerate(entities)]
    result = seed_entities(
        "query",
        np.ones(2),
        InMemoryGraphStore([], []),
        bubbles=["a"],
        passage_seeds=passage,
        max_seeds=4,
    )
    assert [s.entity.id for s in result] == ["0", "2", "4", "6"]
