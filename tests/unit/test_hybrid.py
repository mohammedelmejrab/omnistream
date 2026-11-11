from itertools import pairwise

import pytest

from omnistream.retrieval import BM25Index, HybridRetriever
from omnistream.retrieval.sparse import tokenize

CORPUS = {
    "c1": "Neo4j is a graph database used to store entities and relations.",
    "c2": "Chroma is an embedded vector store for text chunks.",
    "c3": "Personalized PageRank scores graph nodes relative to seed entities.",
    "c4": "Banana bread needs ripe bananas, flour and sugar.",
    "c5": "Reciprocal rank fusion merges ranked lists from several retrievers.",
}


@pytest.fixture
def retriever(settings, embedder):
    r = HybridRetriever(embedder, settings=settings)
    r.add(CORPUS)
    return r


# ------------------------------------------------------------------- BM25
def test_tokenize():
    assert tokenize("Neo4j, GRAPH-db!") == ["neo4j", "graph", "db"]


def test_bm25_ranks_keyword_matches():
    idx = BM25Index(CORPUS)
    results = idx.search("graph database")
    assert results[0][0] == "c1"
    assert {doc for doc, _ in results} == {"c1", "c3"}


def test_bm25_edge_cases():
    assert BM25Index().search("anything") == []
    idx = BM25Index(CORPUS)
    assert idx.search("") == []
    assert idx.search("zzz unknown") == []
    assert idx.search("graph", top_k=0) == []
    assert len(idx.search("graph", top_k=1)) == 1


def test_bm25_reindexing_document_updates_df():
    idx = BM25Index({"a": "graph graph", "b": "graph"})
    idx.add({"a": "banana"})
    assert len(idx) == 2
    assert [d for d, _ in idx.search("graph")] == ["b"]
    assert [d for d, _ in idx.search("banana")] == ["a"]


# ----------------------------------------------------------------- hybrid
def test_empty_retriever_returns_nothing(settings, embedder):
    r = HybridRetriever(embedder, settings=settings)
    assert len(r) == 0
    assert r.search("graph") == []


def test_dense_search_orders_by_similarity(retriever):
    results = retriever.dense_search("graph database entities", top_k=3)
    assert results[0][0] == "c1"
    assert all(a[1] >= b[1] for a, b in pairwise(results))


def test_hybrid_combines_both_retrievers(retriever):
    results = retriever.search("graph database", top_k=3)
    assert results[0].id == "c1"
    assert results[0].dense_rank == 1 and results[0].sparse_rank == 1
    assert results[0].text == CORPUS["c1"]
    assert all(a.score >= b.score for a, b in pairwise(results))


def test_item_found_by_only_one_retriever_keeps_none_rank(settings, embedder):
    r = HybridRetriever(embedder, settings=settings, min_dense_similarity=0.99)
    r.add(CORPUS)
    results = r.search("bananas flour")
    assert results[0].id == "c4"
    assert results[0].dense_rank is None
    assert results[0].sparse_rank == 1


def test_irrelevant_query_returns_empty(retriever):
    assert retriever.search("quantum chromodynamics") == []


def test_top_k_respected(retriever):
    assert len(retriever.search("graph store chunks entities", top_k=2)) == 2


def test_add_updates_existing_chunk(retriever):
    retriever.add({"c4": "Neo4j graph database graph"})
    assert len(retriever) == 5
    ids = [c.id for c in retriever.search("graph database", top_k=5)]
    assert "c4" in ids
    assert not retriever.search("banana")


def test_uses_rrf_k(settings, embedder):
    r = HybridRetriever(embedder, settings=settings, rrf_k=10)
    r.add({"a": "graph"})
    res = r.search("graph")
    assert res[0].score == pytest.approx(2 / 11)
