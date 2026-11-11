from datetime import UTC, datetime

import chromadb

from omnistream.graph.chunks import ChunkStore, collection_name
from tests.conftest import FakeEmbedder

PARA = ("word " * 100).strip()  # ~130 estimated tokens
TEXT = "\n\n".join([PARA] * 4)


async def test_chunks_land_in_per_bubble_cosine_collection(tmp_path):
    store = ChunkStore(str(tmp_path), FakeEmbedder(), chunk_tokens=300)
    when = datetime(2026, 1, 2, tzinfo=UTC)
    n = await store.add("news", "item1", TEXT, "https://x.test/a", when)
    assert n == 2
    col = chromadb.PersistentClient(path=str(tmp_path / "chroma")).get_collection(
        collection_name("news")
    )
    assert collection_name("news") == "bubble_news"
    assert col.metadata["hnsw:space"] == "cosine"
    got = col.get(include=["metadatas"])
    assert len(got["ids"]) == 2
    assert all(m["item_id"] == "item1" for m in got["metadatas"])
    assert got["metadatas"][0]["source_url"] == "https://x.test/a"
    assert got["metadatas"][0]["published_at"] == when.isoformat()


async def test_rewrite_is_idempotent_and_collections_are_separate(tmp_path):
    store = ChunkStore(str(tmp_path), FakeEmbedder(), chunk_tokens=300)
    await store.add("news", "i1", TEXT, "u", None)
    await store.add("news", "i1", TEXT, "u", None)
    await store.add("finance", "i1", TEXT, "u", None)
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    assert client.get_collection("bubble_news").count() == 2
    assert client.get_collection("bubble_finance").count() == 2


async def test_empty_text_adds_nothing(tmp_path):
    store = ChunkStore(str(tmp_path), FakeEmbedder(), chunk_tokens=300)
    assert await store.add("news", "i1", "  ", "u", None) == 0


async def test_count_and_drop(tmp_path):
    store = ChunkStore(str(tmp_path), FakeEmbedder(), chunk_tokens=300)
    assert await store.count("news") == 0
    await store.drop("news")  # missing collection is fine
    await store.add("news", "item1", TEXT, "u", None)
    assert await store.count("news") == 2
    await store.drop("news")
    assert await store.count("news") == 0
