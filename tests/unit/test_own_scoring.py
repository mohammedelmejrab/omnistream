"""C5 step 4 formula and deterministic paths."""

from __future__ import annotations

import numpy as np
import pytest

from omnistream.retrieval.models import Subgraph
from omnistream.retrieval.own_algorithm.scoring import score_facts, seed_paths
from tests.unit.test_graph_memory_store import entity, fact


def test_formula_negative_zero_and_missing():
    facts = tuple(fact(str(i), "a", "b") for i in range(4))
    graph = Subgraph({i: entity(i) for i in "ab"}, facts)
    scores = score_facts(
        graph,
        {"a": 0.2, "b": 0.8},
        np.array([1.0, 0.0]),
        {"0": np.array([0.6, 0.8]), "1": np.array([-1.0, 0.0]), "2": np.zeros(2)},
    )
    assert scores == pytest.approx({"0": 0.3, "1": 0, "2": 0, "3": 0})


def test_paths_choose_nearest_seed_then_lexicographic():
    graph = Subgraph(
        {i: entity(i) for i in "abcdef"},
        (
            fact("ab", "a", "b"),
            fact("bc", "b", "c"),
            fact("cd", "c", "d"),
            fact("ef", "e", "f"),
        ),
        (("a", "d"),),
    )
    paths = seed_paths(graph, ["a"])
    assert paths == {"ab": ("a",), "bc": ("a", "b"), "cd": ("a", "d"), "ef": ()}
    assert seed_paths(graph, ["d", "a"])["cd"] == ("d",)


def test_invalid_vectors_and_pagerank():
    graph = Subgraph({i: entity(i) for i in "ab"}, (fact("f", "a", "b"),))
    with pytest.raises(ValueError):
        score_facts(graph, {"a": -1}, np.ones(2), {})
    with pytest.raises(ValueError):
        score_facts(graph, {}, np.ones(2), {"f": np.ones(3)})
