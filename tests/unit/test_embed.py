import math
import sys
import types

from omnistream.embed import SentenceTransformerEmbedder
from tests.conftest import FakeEmbedder


def norm(v):
    return math.sqrt(sum(x * x for x in v))


async def test_fake_embedder_is_deterministic_and_normalized():
    e = FakeEmbedder(dim=8)
    a, b = await e.embed(["hello", "hello"])
    assert a == b
    assert len(a) == 8
    assert math.isclose(norm(a), 1.0, rel_tol=1e-9)
    (c,) = await e.embed(["other"])
    assert c != a


async def test_fake_embedder_table_is_casefolded_and_normalized():
    e = FakeEmbedder(table={"Foo": [3.0, 4.0]})
    (v,) = await e.embed(["FOO"])
    assert v == [0.6, 0.8]


async def test_sentence_transformer_embedder_uses_normalized_encode(monkeypatch):
    import numpy as np

    calls = {}

    class FakeModel:
        def __init__(self, name):
            calls["name"] = name

        def encode(self, texts, normalize_embeddings):
            calls["norm"] = normalize_embeddings
            return np.array([[1.0, 0.0] for _ in texts])

    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)
    emb = SentenceTransformerEmbedder("m")
    assert await emb.embed(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    assert calls == {"name": "m", "norm": True}
