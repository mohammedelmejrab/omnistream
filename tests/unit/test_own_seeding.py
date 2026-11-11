"""C5 step 1 seeding checks."""

from __future__ import annotations

import numpy as np
import pytest

from omnistream.graph.memory_store import InMemoryGraphStore
from omnistream.retrieval.models import Entity
from omnistream.retrieval.own_algorithm.seeding import seed_entities


def test_alias_merge_case_and_short_name():
    entities = [
        Entity("a", "Corporation", "Organization", "news", aliases=("ACME",)),
        Entity("b", "Acme Holdings", "Organization", "news"),
        Entity("c", "AI", "Concept", "news"),
        Entity("d", "Acme", "Organization", "finance"),
    ]
    store = InMemoryGraphStore(
        entities, [], entity_embeddings={"a": np.array([1.0, 0.0])}
    )
    seeds = seed_entities(
        "What did acme and AI do?", np.array([1.0, 0.0]), store, bubbles=["news"]
    )
    assert [(s.entity.id, s.source) for s in seeds] == [("a", "both")]
    fuzzy = seed_entities("ACME HOLDINGS", np.zeros(2), store, bubbles=["news"])
    assert [(s.entity.id, s.source) for s in fuzzy] == [("a", "fuzzy"), ("b", "fuzzy")]


def test_empty_and_validation():
    store = InMemoryGraphStore([], [])
    assert seed_entities("", np.ones(2), store, bubbles=[]) == []
    with pytest.raises(ValueError):
        seed_entities("", np.ones(2), store, bubbles=[], fuzzy_threshold=101)


@pytest.mark.parametrize(
    "name,question", [("Apple", "pineapple sales"), ("Meta", "metadata tools")]
)
def test_fuzzy_rejects_matches_inside_words(name, question):
    store = InMemoryGraphStore([Entity("e", name, "Organization", "news")], [])
    assert seed_entities(question, np.zeros(2), store, bubbles=["news"]) == []


@pytest.mark.parametrize(
    "name,question",
    [
        ("Microsoft", "What did Microsft announce?"),
        ("European Central Bank", "The EUROPEAN CENTRAL BANK, today?"),
    ],
)
def test_fuzzy_preserves_typos_and_multiword_names(name, question):
    store = InMemoryGraphStore([Entity("e", name, "Organization", "news")], [])
    assert [
        s.entity.id
        for s in seed_entities(question, np.zeros(2), store, bubbles=["news"])
    ] == ["e"]
