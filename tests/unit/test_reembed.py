from pathlib import Path

import numpy as np
import pytest

from omnistream.graph.reembed import chroma_inventory, rewrite_chroma
from omnistream.retrieval.classic import ClassicRetriever, make_chroma_client


class Encoder:
    index_signature = "test-model:1024"

    def embed_documents(self, texts):
        return np.tile([1.0] + [0.0] * 1023, (len(texts), 1))

    def embed_query(self, text):
        return self.embed_documents([text])[0]


def test_chroma_reembed_preserves_data_and_recovers_from_interrupted_staging(
    tmp_path: Path,
    monkeypatch,
):
    path = tmp_path / "chroma"
    client = make_chroma_client(path)
    try:
        collection = client.create_collection(
            "bubble_news",
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )
        collection.add(
            ids=["chunk1"],
            documents=["Stored chunk"],
            embeddings=[[1.0, 0.0]],
            metadatas=[{"item_id": "item1", "chunk": 0}],
            uris=["urn:chunk:1"],
        )
    finally:
        client.close()

    def fail(texts):
        raise RuntimeError("encoder interrupted")

    encoder = Encoder()
    with monkeypatch.context() as patch:
        patch.setattr(encoder, "embed_documents", fail)
        with pytest.raises(RuntimeError, match="encoder interrupted"):
            rewrite_chroma(path, encoder, [])
    assert (
        next(r for r in chroma_inventory(path) if r["name"] == "bubble_news")[
            "dimension"
        ]
        == 2
    )

    assert rewrite_chroma(path, encoder, []) == {"bubble_news": 1}
    assert rewrite_chroma(path, encoder, []) == {}
    assert chroma_inventory(path) == [
        {
            "name": "bubble_news",
            "dimension": 1024,
            "count": 1,
            "signature": encoder.index_signature,
        }
    ]
    client = make_chroma_client(path)
    try:
        collection = client.get_collection("bubble_news", embedding_function=None)
        stored = collection.get(include=["documents", "metadatas", "uris"])
        assert stored["ids"] == ["chunk1"]
        assert stored["documents"] == ["Stored chunk"]
        assert stored["metadatas"] == [{"item_id": "item1", "chunk": 0}]
        assert stored["uris"] == ["urn:chunk:1"]
        result = ClassicRetriever(client, encoder).retrieve("query", bubbles=["news"])
        assert result.chunks[0].item_id == "item1"
    finally:
        client.close()
