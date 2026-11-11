import numpy as np
import pytest

from omnistream.embeddings import (
    BGE_QUERY_INSTRUCTION,
    EmbeddingError,
    EmbeddingService,
)
from tests.conftest import DIM, HashingEncoder


def test_embed_documents_shape_dtype_and_normalisation(embedder):
    vecs = embedder.embed_documents(["Neo4j stores graphs", "Chroma stores chunks"])
    assert vecs.shape == (2, DIM)
    assert vecs.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(vecs, axis=1), 1.0, rtol=1e-5)


def test_empty_input_returns_empty_matrix(embedder, encoder):
    vecs = embedder.embed_documents([])
    assert vecs.shape == (0, DIM)
    assert encoder.calls == []


def test_blank_strings_become_zero_vectors_without_model_call(embedder, encoder):
    vecs = embedder.embed_documents(["", "   ", "real text"])
    assert not vecs[0].any() and not vecs[1].any()
    assert vecs[2].any()
    assert encoder.calls == [["real text"]]


def test_query_gets_bge_instruction_prefix(embedder, encoder):
    embedder.embed_query("who founded neo4j")
    assert encoder.calls[-1] == [BGE_QUERY_INSTRUCTION + "who founded neo4j"]


def test_query_prefix_can_be_disabled(settings, encoder):
    svc = EmbeddingService(settings, encoder=encoder, query_instruction=None)
    svc.embed_query("hello")
    assert encoder.calls[-1] == ["hello"]


def test_duplicates_are_encoded_once_and_cached(embedder, encoder):
    first = embedder.embed_documents(["a b", "a b", "c d"])
    assert encoder.calls == [["a b", "c d"]]
    np.testing.assert_array_equal(first[0], first[1])
    second = embedder.embed_documents(["c d", "e f"])
    assert encoder.calls[-1] == ["e f"]
    np.testing.assert_array_equal(first[2], second[0])


def test_query_and_document_cache_keys_are_distinct(embedder, encoder):
    embedder.embed_documents(["graph"])
    embedder.embed_query("graph")
    assert len(encoder.calls) == 2


def test_cache_is_bounded_lru(settings, encoder):
    svc = EmbeddingService(settings, encoder=encoder, cache_size=2)
    svc.embed_documents(["a"])
    svc.embed_documents(["b"])
    svc.embed_documents(["a"])  # hit, refresh "a"
    svc.embed_documents(["c"])  # evicts "b"
    calls_before = len(encoder.calls)
    svc.embed_documents(["a"])
    assert len(encoder.calls) == calls_before
    svc.embed_documents(["b"])
    assert len(encoder.calls) == calls_before + 1


def test_cache_disabled(settings, encoder):
    svc = EmbeddingService(settings, encoder=encoder, cache_size=0)
    svc.embed_documents(["x"])
    svc.embed_documents(["x"])
    assert len(encoder.calls) == 2


def test_rejects_non_string_input(embedder):
    with pytest.raises(TypeError):
        embedder.embed_documents(["ok", 3])  # type: ignore[list-item]


class _BadShape:
    def encode(self, sentences, **kwargs):
        return np.ones((len(sentences), 10))


class _NaN:
    def encode(self, sentences, **kwargs):
        return np.full((len(sentences), DIM), np.nan)


class _ZeroVector:
    def encode(self, sentences, **kwargs):
        return np.zeros((len(sentences), DIM))


@pytest.mark.parametrize("enc", [_BadShape(), _NaN()])
def test_bad_encoder_output_raises(settings, enc):
    with pytest.raises(EmbeddingError):
        EmbeddingService(settings, encoder=enc).embed_documents(["x"])


def test_zero_vector_output_does_not_divide_by_zero(settings):
    vecs = EmbeddingService(settings, encoder=_ZeroVector()).embed_documents(["x"])
    assert np.all(np.isfinite(vecs)) and not vecs.any()


def test_encoder_receives_normalise_flag(settings):
    seen = {}

    class Spy(HashingEncoder):
        def encode(self, sentences, **kwargs):
            seen.update(kwargs)
            return super().encode(sentences)

    EmbeddingService(settings, encoder=Spy(), batch_size=7).embed_documents(["x"])
    assert seen["normalize_embeddings"] is True
    assert seen["batch_size"] == 7


def test_model_is_loaded_lazily(settings, monkeypatch):
    loaded = []

    class FakeST(HashingEncoder):
        def __init__(self, name, device=None):
            super().__init__()
            loaded.append((name, device))

    import sys
    import types

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeST),
    )
    svc = EmbeddingService(settings)
    assert loaded == []
    svc.embed_documents(["x"])
    svc.embed_documents(["y"])
    assert loaded == [("BAAI/bge-small-en-v1.5", None)]


def test_semantic_ordering_with_fake_encoder(embedder):
    docs = embedder.embed_documents(["neo4j graph database", "banana bread recipe"])
    sims = embedder.cosine_similarity(embedder.embed_query("graph database"), docs)
    assert sims[0] > sims[1]


def test_cosine_similarity_edge_cases():
    q = np.array([1.0, 0.0], dtype=np.float32)
    assert EmbeddingService.cosine_similarity(q, np.zeros((0, 2))).shape == (0,)
    sims = EmbeddingService.cosine_similarity(
        q, np.array([[2.0, 0.0], [0.0, 0.0], [-1.0, 0.0]])
    )
    np.testing.assert_allclose(sims, [1.0, 0.0, -1.0])
    zero = EmbeddingService.cosine_similarity(np.zeros(2), np.array([[1.0, 0.0]]))
    np.testing.assert_allclose(zero, [0.0])


@pytest.mark.live
def test_live_bge_small_model(settings):
    svc = EmbeddingService(settings)
    docs = svc.embed_documents(
        ["Neo4j is a graph database.", "Bananas are yellow fruit."]
    )
    assert docs.shape == (2, 384)
    sims = svc.cosine_similarity(svc.embed_query("Which database stores graphs?"), docs)
    assert sims[0] > sims[1]
