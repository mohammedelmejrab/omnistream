"""Offline tests for HippoRAG 2-style passage nodes in the own retriever."""

from datetime import UTC, datetime

from omnistream.retrieval.models import Chunk, Entity, Fact, RetrievalResult, Subgraph
from omnistream.retrieval.own_algorithm.passage_nodes import (
    PassageNodes,
    passage_graph,
    rank_passages,
)


def _entity(i):
    return Entity(id=i, name=i.upper(), type="Person", bubble="b")


def _fact(fid, s, o, item="x"):
    return Fact(
        id=fid, subject_id=s, object_id=o, relation="R", text=f"{s} R {o}",
        item_id=item, bubble="b", source_url=None, published_at=NOW,
    )


NOW = datetime(2026, 1, 1, tzinfo=UTC)

SUB = Subgraph(
    entities={i: _entity(i) for i in ("a", "b", "c", "d")},
    facts=(_fact("f1", "a", "b"), _fact("f2", "b", "c")),
)


def test_passage_graph_links_passages_to_subgraph_entities_only():
    graph = passage_graph(
        SUB,
        [("b", "p1", ["a", "zzz"]), ("b", "p2", ["c", "d"])],
        {("b", "p3"): 0.5},
    )
    assert set(graph.neighbors("passage::b::p1")) == {"a"}
    assert set(graph.neighbors("passage::b::p2")) == {"c", "d"}
    assert "passage::b::p3" in graph  # dense-only passage is still a node


def test_rank_passages_prefers_passages_near_seeds():
    graph = passage_graph(
        SUB, [("b", "near", ["a"]), ("b", "far", ["d"])], {}
    )
    ranked = rank_passages(graph, {"a": 1.0}, {})
    assert [item for _, item, _ in ranked][:2] == ["near", "far"]


def test_dense_restart_breaks_ties_between_unlinked_passages():
    graph = passage_graph(SUB, [], {("b", "p1"): 0.2, ("b", "p2"): 0.9})
    ranked = rank_passages(graph, {"a": 1.0}, {("b", "p1"): 0.2, ("b", "p2"): 0.9})
    assert [item for _, item, _ in ranked] == ["p2", "p1"]


def test_rank_passages_without_restart_mass_is_empty():
    graph = passage_graph(SUB, [], {})
    assert rank_passages(graph, {}, {}) == []


class FakeGraph:
    def __init__(self, mentions, texts):
        self.mentions, self.texts, self.calls = mentions, texts, []

    def _run(self, query, **params):
        self.calls.append(params)
        if "items" in params:
            return [
                {"item": it["item"], "bubble": it["bubble"], "text": self.texts.get(it["item"])}
                for it in params["items"]
            ]
        return self.mentions


def test_passage_nodes_returns_chunks_with_graph_text_for_non_dense_passages():
    graph = FakeGraph(
        [{"bubble": "b", "item": "p1", "entities": ["a"]},
         {"bubble": "b", "item": "p2", "entities": ["c"]}],
        {"p1": "passage one text"},
    )
    dense = [Chunk("c2", "dense text two", "p2", "b", None, None, 0.8)]
    chunks = PassageNodes(graph, top=2).rank(SUB, {"a": 1.0}, dense, ["b"])
    assert [c.item_id for c in chunks] == ["p1", "p2"]
    assert chunks[0].text == "passage one text"  # read from the Episodic node
    assert chunks[1].text == "dense text two"  # dense chunk text reused
    assert graph.calls[0]["bubbles"] == ["b"]


def test_chunks_first_changes_item_order():
    fact = _fact("f1", "a", "b", item="fact-item")
    chunk = Chunk("c", "t", "chunk-item", "b", None, None, 1.0)
    from omnistream.retrieval.models import ScoredFact

    scored = (ScoredFact(fact, 1.0, ("a",), {}),)
    assert RetrievalResult("own", facts=scored, chunks=(chunk,)).item_ids == (
        "fact-item", "chunk-item",
    )
    assert RetrievalResult(
        "own", facts=scored, chunks=(chunk,), chunks_first=True
    ).item_ids == ("chunk-item", "fact-item")


def test_hop_expansion_puts_best_neighbour_after_heads():
    class Graph:
        def _run(self, query, **params):
            return [
                {"head": "h1", "item": "n_bad", "bubble": "b", "text": "unrelated"},
                {"head": "h1", "item": "n_good", "bubble": "b", "text": "director bio"},
                {"head": "h2", "item": "n2", "bubble": "b", "text": "second director"},
            ]

    class Encoder:
        def predict(self, pairs, **_):
            return [2.0 if "director" in text else 0.0 for _, text in pairs]

    nodes = PassageNodes(Graph(), reranker=lambda: Encoder(), rerank_mode="rrf", hop_expand=True)
    ranked = [("b", "h1", 0.5), ("b", "h2", 0.4), ("b", "x", 0.3), ("b", "y", 0.2)]
    texts = {}
    out = nodes._hop("who directed", ranked, texts)
    assert [item for _, item, _ in out] == ["h1", "h2", "n_good", "n2", "x", "y"]
    assert texts[("b", "n_good")] == "director bio"
