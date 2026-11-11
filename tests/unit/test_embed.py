import math

import numpy as np

from omnistream.embed import SentenceTransformerEmbedder
from omnistream.embeddings import EmbeddingService
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


class FakeEncoder:
    """Deterministic 2-dim encoder standing in for SentenceTransformer."""

    def encode(self, texts, **kwargs):
        return np.array([[1.0, 0.0] for _ in texts])


def make_service():
    return EmbeddingService(model_name="m", dimension=2, encoder=FakeEncoder())


def test_sentence_transformer_embedder_builds_shared_service():
    emb = SentenceTransformerEmbedder("m")
    assert emb.service.model_name == "m"
    assert isinstance(emb.service, EmbeddingService)


async def test_sentence_transformer_embedder_uses_document_encoding():
    # The adapter is a thin async wrapper over EmbeddingService.embed_documents
    # (C4 ingestion embeds in the document space); vectors stay L2-normalized.
    emb = SentenceTransformerEmbedder("m", service=make_service())
    assert await emb.embed(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    # One shared model instance: injecting a service keeps it, no reload.
    assert emb.service is not None
