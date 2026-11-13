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
    assert len(retriever.retrieve("query", bubbles=["a"], time_scope=scope).chunks) == 4
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


def test_reporting_lag_and_unknown_dates_never_remove_similarity_candidates(store):
    client, embedder = store
    day = datetime(2026, 2, 7, tzinfo=UTC)
    items = [
        Chunk(
            "report",
            "same",
            "reported-next-day",
            "news",
            None,
            datetime(2026, 2, 8, tzinfo=UTC),
        ),
        Chunk("unknown", "same", "undated", "news", None, None),
        Chunk(
            "later",
            "same",
            "reported-next-year",
            "news",
            None,
            datetime(2027, 2, 8, tzinfo=UTC),
        ),
    ]
    add_chunks(client, embedder, "news", items)
    result = ClassicRetriever(client, embedder).retrieve(
        "query",
        bubbles=["news"],
        time_scope=TimeScope(day, datetime(2026, 2, 7, 23, 59, 59, tzinfo=UTC)),
    )
    assert result.chunks[0].item_id == "reported-next-day"
    assert set(result.item_ids) == {c.item_id for c in items}


@pytest.mark.parametrize("point", [False, True])
def test_cutoff_excludes_later_report_before_similarity_top_k(store, point):
    client, embedder = store
    add_chunks(
        client,
        embedder,
        "news",
        [
            Chunk("a-later", "same", "later", "news", None, datetime(2026, 3, 1)),
            Chunk(
                "z-contemporary", "same", "then", "news", None, datetime(2025, 12, 31)
            ),
        ],
    )
    retriever = ClassicRetriever(client, embedder)
    scope = TimeScope(datetime(2026, 1, 1) if point else None, datetime(2026, 1, 1))
    assert retriever.retrieve("q", bubbles=["news"], time_scope=scope).item_ids == (
        "then",
    )
    # Cutoff filtering happens before selecting top-k.
    assert retriever.retrieve(
        "q", bubbles=["news"], time_scope=scope, top_k=1
    ).item_ids == ("then",)


def test_unbounded_scope_applies_no_cutoff(store):
    """Event-relative any-time scopes must not cut by publication date."""
    client, embedder = store
    add_chunks(
        client,
        embedder,
        "news",
        [
            Chunk("later", "same", "later", "news", None, datetime(2026, 3, 1)),
            Chunk("older", "same", "older", "news", None, datetime(2025, 1, 1)),
        ],
    )
    retriever = ClassicRetriever(client, embedder)
    any_time = retriever.retrieve(
        "q", bubbles=["news"], time_scope=TimeScope(None, None)
    )
    assert set(any_time.item_ids) == {"later", "older"}
    # A point scope still cuts the later publication.
    cutoff = TimeScope(datetime(2026, 1, 1), datetime(2026, 1, 1))
    assert retriever.retrieve("q", bubbles=["news"], time_scope=cutoff).item_ids == (
        "older",
    )


def test_cutoff_answer_uses_old_report_and_now_uses_new(store):
    from omnistream.retrieval.citations import AnswerContext, generate_answer

    client, embedder = store
    add_chunks(
        client,
        embedder,
        "news",
        [
            Chunk(
                "old",
                "Ada leads X",
                "old",
                "news",
                None,
                datetime(2025, 1, 1, tzinfo=UTC),
            ),
            Chunk(
                "new",
                "Bea leads X",
                "new",
                "news",
                None,
                datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ],
    )
    retriever = ClassicRetriever(client, embedder)
    cutoff = datetime(2025, 6, 1, 23, 59, 59, 999999, tzinfo=UTC)
    scope = TimeScope(cutoff, cutoff)
    past = retriever.retrieve("leader", bubbles=["news"], time_scope=scope)
    current = retriever.retrieve("leader", bubbles=["news"])
    assert past.item_ids == ("old",)
    assert set(current.item_ids) == {"old", "new"}

    class LLM:
        def chat(self, messages):
            self.system = messages[0]["content"]
            return messages[1]["content"]

    llm = LLM()
    context = AnswerContext(text=past.chunks[0].text, citations=())
    answer = generate_answer(llm, "leader", context, time_scope=scope)
    assert "Ada leads X" in answer.text and "Bea" not in answer.text
    assert "Answer as of 2025-06-01" in llm.system
    assert "prefer the most recent statement on or before it" in llm.system
    generate_answer(llm, "leader", context)
    assert "prefer the most recent statement valid now" in llm.system
