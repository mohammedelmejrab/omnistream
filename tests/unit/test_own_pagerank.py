"""C5 step 3 PageRank reference checks."""

from __future__ import annotations

import networkx as nx
import pytest

from omnistream.retrieval.models import Subgraph
from omnistream.retrieval.own_algorithm.pagerank import personalized_pagerank
from tests.unit.test_graph_memory_store import entity, fact


def test_weighted_pagerank_matches_reference():
    graph = Subgraph(
        {i: entity(i) for i in "abcd"},
        (fact("1", "a", "b"), fact("2", "a", "b"), fact("3", "b", "c")),
        (("c", "d"),),
    )
    reference = nx.Graph()
    reference.add_edge("a", "b", weight=2)
    reference.add_edge("b", "c", weight=1)
    reference.add_edge("c", "d", weight=1)
    expected = nx.pagerank(
        reference,
        alpha=0.85,
        personalization={"a": 1, "b": 0, "c": 0, "d": 0},
        max_iter=1000,
        tol=1e-12,
    )
    result = personalized_pagerank(graph, ["a", "absent"])
    assert result == pytest.approx(expected)
    assert sum(result.values()) == pytest.approx(1)


def test_empty_isolated_and_absent():
    assert personalized_pagerank(Subgraph({}, ()), []) == {}
    graph = Subgraph({i: entity(i) for i in "ab"}, ())
    assert personalized_pagerank(graph, ["a"]) == pytest.approx({"a": 1, "b": 0})
    assert personalized_pagerank(graph, ["a", "b"]) == pytest.approx(
        {"a": 0.5, "b": 0.5}
    )
    with pytest.raises(ValueError):
        personalized_pagerank(graph, ["missing"])


@pytest.mark.parametrize("damping", [-1, 1, float("nan")])
def test_damping_validation(damping):
    with pytest.raises(ValueError):
        personalized_pagerank(Subgraph({}, ()), [], damping=damping)
