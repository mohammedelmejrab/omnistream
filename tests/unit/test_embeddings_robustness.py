"""Robustness tests added after code review: overflow, validation, thread safety."""

import threading

import numpy as np
import pytest

from omnistream.embeddings import EmbeddingService
from tests.conftest import DIM, HashingEncoder


class _Huge:
    def encode(self, sentences, **kwargs):
        return np.full((len(sentences), DIM), 1e30, dtype=np.float32)


def test_huge_finite_values_normalise_without_overflow(settings):
    vecs = EmbeddingService(settings, encoder=_Huge()).embed_documents(["x"])
    np.testing.assert_allclose(np.linalg.norm(vecs, axis=1), 1.0, rtol=1e-5)


@pytest.mark.parametrize(
    "query, matrix",
    [
        (np.array([np.nan, 0.0]), np.array([[1.0, 0.0]])),
        (np.array([1.0, 0.0]), np.array([[np.inf, 0.0]])),
        (np.ones((2, 2)), np.ones((2, 2))),  # 2-D query
        (np.ones(3), np.ones((2, 2))),  # dimension mismatch
        (np.ones(2), np.ones((2, 2, 2))),  # 3-D matrix
        (np.array([np.nan, 0.0]), np.empty((0, 2))),  # bad query, empty matrix
        (np.ones(2), np.empty((0, 3))),  # empty but wrong width
        (np.ones(2), np.empty((1, 0, 2))),  # empty 3-D
    ],
)
def test_cosine_similarity_rejects_invalid_input(query, matrix):
    with pytest.raises(ValueError):
        EmbeddingService.cosine_similarity(query, matrix)


def test_cosine_similarity_extreme_magnitudes():
    sims = EmbeddingService.cosine_similarity(
        np.array([1e30, 1e30]), np.array([1e-30, 1e-30])
    )
    np.testing.assert_allclose(sims, [1.0], rtol=1e-6)


def test_known_model_dimension_mismatch_rejected(settings, encoder):
    with pytest.raises(ValueError, match="384"):
        EmbeddingService(settings, encoder=encoder, dimension=768)


def test_index_signature(embedder):
    assert embedder.index_signature == "BAAI/bge-small-en-v1.5:384"


def test_cached_vectors_are_isolated_from_callers(embedder):
    first = embedder.embed_documents(["a b"])
    first[0, :] = 42.0
    again = embedder.embed_documents(["a b"])
    np.testing.assert_allclose(np.linalg.norm(again[0]), 1.0, rtol=1e-5)


def test_cache_is_thread_safe_under_eviction_pressure(settings):
    svc = EmbeddingService(settings, encoder=HashingEncoder(), cache_size=1)
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(n: int) -> None:
        try:
            barrier.wait()
            for i in range(300):
                assert svc.embed_documents([f"w{(n + i) % 5}"]).shape == (1, DIM)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(svc._cache) <= 1


def test_cache_reads_and_writes_wait_for_the_lock(settings):
    """Deterministic check for the reviewed race: lookup/refresh and insert/evict
    are each done under the cache lock, so they cannot interleave."""
    svc = EmbeddingService(settings, encoder=HashingEncoder(), cache_size=1)
    svc.embed_documents(["old"])
    with svc._cache_lock:
        writer = threading.Thread(target=svc.embed_documents, args=(["other"],))
        reader = threading.Thread(target=svc._cache_get, args=("old",))
        writer.start()
        reader.start()
        writer.join(timeout=0.2)
        reader.join(timeout=0.2)
        assert writer.is_alive() and reader.is_alive(), (
            "cache access must block on the lock"
        )
    writer.join()
    reader.join()
    assert list(svc._cache) == ["other"]
