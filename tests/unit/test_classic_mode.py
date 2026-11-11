"""Offline Chroma checks for spec C5 classic retrieval."""

import uuid
from datetime import UTC, datetime

import chromadb
import numpy as np
import pytest
from chromadb.api.shared_system_client import SharedSystemClient
from chromadb.config import Settings as ChromaSettings

from omnistream.config import Settings
from omnistream.embeddings import EmbeddingService
from omnistream.retrieval.classic import (
    ClassicRetriever,
    add_chunks,
    collection_name,
    make_chroma_client,
)
from omnistream.retrieval.models import Chunk, TimeScope


class Encoder:
    def encode(self, sentences, **kwargs):
        result = np.zeros((len(sentences), 384))
        for i, text in enumerate(sentences):
            result[i, :2] = [1, float(text) if text.isdigit() else 0]
        return result


@pytest.fixture
def store(tmp_path, monkeypatch):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", denied)
    # Isolated persist directory: unique per test, immune to any tmp_path
    # reuse or cross-process collision on pytest's numbered roots.
    persist = tmp_path / f"chroma-{uuid.uuid4().hex}"
    persist.mkdir(parents=True, exist_ok=True)
    client = make_chroma_client(
        str(persist), settings=ChromaSettings(anonymized_telemetry=False)
    )
    embedder = EmbeddingService(
        Settings(_env_file=None, llm_api_key="test"), encoder=Encoder()
    )
    yield client, embedder
    # Release the client: stops the shared System (closing sqlite/HNSW file
    # handles, which Windows otherwise keeps locked in the tmp directory) and
    # leaves no entry in chromadb's process-wide SharedSystemClient cache.
    client.close()
    SharedSystemClient.clear_system_cache()


def chunks(bubble, start, stop):
    return [
        Chunk(
            f"c{i:02}",
            str(i),
            f"item{i}",
            bubble,
            f"https://source/{i}",
            datetime(2025, 1, 1, tzinfo=UTC),
        )
        for i in range(start, stop)
    ]


def test_global_top_ten_and_mapping(store):
    client, embedder = store
    add_chunks(client, embedder, "a", chunks("a", 0, 8))
    add_chunks(client, embedder, "b", chunks("b", 8, 16))
    retriever = ClassicRetriever(client, embedder)
    result = retriever.retrieve("query", bubbles=["b", "a"])
    assert [c.item_id for c in result.chunks] == [f"item{i}" for i in range(10)]
    assert result.chunks[0].source_url == "https://source/0"
    assert result.chunks[0].published_at == datetime(2025, 1, 1, tzinfo=UTC)
    assert {c.bubble for c in result.chunks} == {"a", "b"}
    assert len(retriever.retrieve("query", bubbles=["b"]).chunks) == 8
    assert len(retriever.retrieve("query", bubbles=["a", "b"], top_k=3).chunks) == 3


def test_missing_empty_and_scope(store):
    client, embedder = store
    retriever = ClassicRetriever(client, embedder)
    assert not retriever.retrieve("query", bubbles=["missing"]).chunks
    client.create_collection(
        collection_name("empty"),
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )
    assert not retriever.retrieve("query", bubbles=["empty"]).chunks
    add_chunks(client, embedder, "a", chunks("a", 0, 4))
    assert not retriever.retrieve("", bubbles=["a"]).chunks
    scope = TimeScope(start=datetime(2026, 1, 1))
    assert not retriever.retrieve("query", bubbles=["a"], time_scope=scope).chunks
    exact = TimeScope(datetime(2025, 1, 1), datetime(2025, 1, 1))
    assert len(retriever.retrieve("query", bubbles=["a"], time_scope=exact).chunks) == 4


def test_ties_and_validation(store):
    client, embedder = store
    items = [
        Chunk(str(i), "same", str(i), "a", None, None) for i in reversed(range(15))
    ]
    add_chunks(client, embedder, "a", items)
    retriever = ClassicRetriever(client, embedder)
    assert [c.id for c in retriever.retrieve("query", bubbles=["a"]).chunks] == sorted(
        c.id for c in items
    )[:10]
    with pytest.raises(ValueError):
        retriever.retrieve("q", bubbles=["a"], top_k=0)
    with pytest.raises(ValueError):
        add_chunks(client, embedder, "b", items)
    assert collection_name("a/b") != collection_name("a_b")


def test_many_small_collections_keep_readers(store):
    client, embedder = store
    bubbles = [f"small-{i}" for i in range(12)]
    for bubble in bubbles:
        add_chunks(client, embedder, bubble, chunks(bubble, 0, 2))
    retriever = ClassicRetriever(client, embedder)
    for _ in range(5):
        for bubble in bubbles:
            assert len(retriever.retrieve("query", bubbles=[bubble]).chunks) == 2


@pytest.mark.parametrize("failures", [1, 2])
def test_evicted_reader_refetched_once(store, failures):
    from unittest.mock import Mock

    from chromadb.errors import InternalError

    _, embedder = store
    collection = Mock(metadata={"hnsw:space": "cosine"})
    collection.count.return_value = 1
    empty = {key: [[]] for key in ("ids", "documents", "metadatas", "distances")}
    collection.query.side_effect = [
        InternalError("hnsw segment reader: Nothing found on disk")
    ] * failures + [empty]
    client = Mock()
    client.get_collection.return_value = collection
    retriever = ClassicRetriever(client, embedder)
    if failures == 2:
        with pytest.raises(RuntimeError, match="bubble 'affected' after retry"):
            retriever.retrieve("q", bubbles=["affected"])
    else:
        assert not retriever.retrieve("q", bubbles=["affected"]).chunks
    assert client.get_collection.call_count == 2
    assert collection.query.call_count == 2


def test_factory_sets_cache_before_bindings_without_global_patch(tmp_path):
    from chromadb.api.rust import RustBindingsAPI

    original_init = RustBindingsAPI.__init__
    settings = ChromaSettings(anonymized_telemetry=False)
    before = settings.model_dump()
    roomy = make_chroma_client(
        tmp_path / "roomy", hnsw_cache_size=8192, settings=settings
    )
    default = chromadb.PersistentClient(
        str(tmp_path / "default"), settings=ChromaSettings(anonymized_telemetry=False)
    )
    try:
        assert roomy._server.hnsw_cache_size == 8192
        assert default._server.hnsw_cache_size != 8192
        assert RustBindingsAPI.__init__ is original_init
        assert settings.model_dump() == before
        # Both clients are live and independent, with no shared override.
        assert roomy.heartbeat() > 0 and default.heartbeat() > 0
    finally:
        roomy.close()
        default.close()


def test_unrelated_chroma_internal_error_is_not_retried(store):
    from unittest.mock import Mock

    from chromadb.errors import InternalError

    _, embedder = store
    collection = Mock(metadata={"hnsw:space": "cosine"})
    collection.count.return_value = 1
    collection.query.side_effect = InternalError("unrelated failure")
    client = Mock()
    client.get_collection.return_value = collection
    with pytest.raises(InternalError, match="unrelated failure"):
        ClassicRetriever(client, embedder).retrieve("q", bubbles=["a"])
    assert client.get_collection.call_count == 1
    assert collection.query.call_count == 1
