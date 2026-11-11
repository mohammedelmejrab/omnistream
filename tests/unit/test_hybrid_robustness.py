"""Hybrid/BM25 tests added after code review: exact maths, atomicity, concurrency."""

import ast
import math
import os
import subprocess
import sys
import threading

import numpy as np
import pytest

from omnistream.config import PROJECT_ROOT
from omnistream.embeddings import EmbeddingService
from omnistream.retrieval import BM25Index, HybridRetriever


# ------------------------------------------------------------------- BM25
def test_bm25_numeric_scores_match_hand_calculation():
    idx = BM25Index({"a": "x y y", "b": "x z z z z z"}, k1=1.5, b=0.75)
    avg = (3 + 6) / 2
    idf_x = math.log(1 + (2 - 2 + 0.5) / (2 + 0.5))
    idf_y = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))

    def term(idf, f, length):
        return idf * f * 2.5 / (f + 1.5 * (1 - 0.75 + 0.75 * length / avg))

    got = dict(idx.search("x y"))
    assert got["a"] == pytest.approx(term(idf_x, 1, 3) + term(idf_y, 2, 3), rel=1e-12)
    assert got["b"] == pytest.approx(term(idf_x, 1, 6), rel=1e-12)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k1": -1},
        {"k1": math.nan},
        {"k1": math.inf},
        {"b": 1.5},
        {"b": -0.1},
        {"b": math.nan},
    ],
)
def test_bm25_invalid_parameters_rejected(kwargs):
    with pytest.raises(ValueError):
        BM25Index(**kwargs)


def test_bm25_boundary_parameters_work():
    assert BM25Index({"a": "x"}, k1=0, b=0).search("x")[0][0] == "a"
    assert BM25Index({"a": "x"}, k1=1.2, b=1).search("x")[0][0] == "a"


def test_bm25_rejects_non_string_without_partial_update():
    idx = BM25Index({"a": "old"})
    with pytest.raises(TypeError):
        idx.add({"a": "new", "b": None})  # type: ignore[dict-item]
    assert [d for d, _ in idx.search("old")] == ["a"]
    assert idx.search("new") == []


def test_bm25_ties_identical_across_hash_seeds():
    code = (
        "from omnistream.retrieval.sparse import BM25Index\n"
        "i = BM25Index({'a': 'x y y z z z z z', 'b': 'x x x x x y y z'})\n"
        "print(repr(i.search('x y z')))\n"
    )
    outputs = set()
    for seed in ("0", "1", "2", "3", "42"):
        env = {
            **os.environ,
            "PYTHONHASHSEED": seed,
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        }
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.add(result.stdout)
    assert len(outputs) == 1
    ranked = ast.literal_eval(outputs.pop())
    assert ranked[0][1] == ranked[1][1]  # exact tie...
    assert [d for d, _ in ranked] == ["a", "b"]  # ...broken by id


# ----------------------------------------------------------------- hybrid
def test_rrf_k_comes_from_settings(settings, embedder):
    r = HybridRetriever(embedder, settings=settings.model_copy(update={"rrf_k": 7}))
    assert r.rrf_k == 7
    r.add({"a": "graph"})
    assert r.search("graph")[0].score == pytest.approx(2 / 8)


def test_explicit_rrf_k_overrides_settings(settings, embedder):
    assert HybridRetriever(embedder, settings=settings, rrf_k=3).rrf_k == 3


def test_min_dense_similarity_is_inclusive(settings, encoder):
    svc = EmbeddingService(settings, encoder=encoder, query_instruction=None)
    r = HybridRetriever(svc, settings=settings, min_dense_similarity=0.5)
    r.add(
        {
            "full": "x",
            "high": "x y",
            "exact": "x a b c",
            "low": "x a b c d e f g h",
            "none": "z",
        }
    )
    got = dict(r.dense_search("x"))
    assert got["exact"] == pytest.approx(0.5, abs=1e-6)  # 1 / sqrt(4)
    assert set(got) == {"full", "high", "exact"}


def test_default_threshold_excludes_zero_similarity(settings, embedder):
    r = HybridRetriever(embedder, settings=settings)
    r.add({"a": "graph", "b": "banana"})
    assert [d for d, _ in r.dense_search("graph")] == ["a"]


def test_weights_change_the_winner_when_retrievers_disagree(
    settings, embedder, monkeypatch
):
    r = HybridRetriever(embedder, settings=settings)
    r.add({"d": "dense favourite", "s": "sparse favourite"})
    monkeypatch.setattr(r, "dense_search", lambda q, k: [("d", 0.9), ("s", 0.1)])
    monkeypatch.setattr(r, "sparse_search", lambda q, k: [("s", 9.0), ("d", 1.0)])
    r.weights = {"dense": 1.0, "sparse": 1.0}
    equal = r.search("q")
    assert equal[0].score == equal[1].score
    assert [c.id for c in equal] == ["d", "s"]  # exact tie -> first appearance
    r.weights = {"dense": 1.0, "sparse": 2.0}
    assert r.search("q")[0].id == "s"
    r.weights = {"dense": 2.0, "sparse": 1.0}
    assert r.search("q")[0].id == "d"


def test_empty_index_search_does_not_touch_encoder(settings):
    class Exploding:
        def encode(self, sentences, **kwargs):
            raise RuntimeError("encoder must not be called")

    r = HybridRetriever(
        EmbeddingService(settings, encoder=Exploding()), settings=settings
    )
    assert r.dense_search("anything") == []
    assert r.search("anything") == []


def test_failed_add_leaves_index_unchanged(settings, embedder):
    r = HybridRetriever(embedder, settings=settings)
    r.add({"a": "old text"})
    with pytest.raises(TypeError):
        r.add({"a": "new text", "b": None})  # type: ignore[dict-item]
    assert len(r) == 1
    hit = r.search("old text")[0]
    assert (hit.id, hit.text) == ("a", "old text")
    assert r.search("new") == []


def test_encoder_failure_leaves_index_unchanged(settings):
    class Flaky:
        fail = False

        def encode(self, sentences, **kwargs):
            if self.fail:
                raise RuntimeError("boom")
            return np.eye(384, dtype=np.float32)[: len(sentences)]

    enc = Flaky()
    r = HybridRetriever(EmbeddingService(settings, encoder=enc), settings=settings)
    r.add({"a": "alpha"})
    enc.fail = True
    with pytest.raises(RuntimeError):
        r.add({"a": "beta", "b": "gamma"})
    assert len(r) == 1
    assert r.sparse_search("alpha")[0][0] == "a"
    assert r.sparse_search("beta") == []


def test_concurrent_adds_of_same_id_do_not_duplicate(settings, embedder):
    r = HybridRetriever(embedder, settings=settings)
    barrier = threading.Barrier(16)
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            barrier.wait()
            r.add({"a": "graph"})
            r.add({f"c{i}": f"chunk {i}"})
            r.search("graph")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(r) == 17
    assert len(r._ids) == len(set(r._ids)) == r._matrix.shape[0] == len(r._row)
