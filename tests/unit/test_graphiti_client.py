import pytest

from omnistream.graph.graphiti_client import (
    ENTITY_TYPES,
    BgeEmbedderClient,
    LocalCrossEncoder,
)
from tests.conftest import FakeEmbedder


def test_entity_types_are_the_spec_set():
    assert list(ENTITY_TYPES) == [
        "Person",
        "Organization",
        "Location",
        "Product",
        "Event",
        "Concept",
        "FinancialInstrument",
        "Publication",
    ]
    assert all(t.__doc__ for t in ENTITY_TYPES.values())


async def test_embedder_adapter_str_list_and_batch():
    emb = FakeEmbedder({"a": [1, 0, 0, 0, 0, 0, 0, 0]})
    client = BgeEmbedderClient(emb)
    assert (await client.create("a"))[0] == 1.0
    assert await client.create(["a", "b"]) == await client.create("a")
    batch = await client.create_batch(["a", "b"])
    assert len(batch) == 2 and len(batch[0]) == 8


async def test_embedder_adapter_rejects_token_ids():
    with pytest.raises(TypeError):
        await BgeEmbedderClient(FakeEmbedder()).create([1, 2, 3])


async def test_cross_encoder_ranks_by_cosine_desc():
    emb = FakeEmbedder(
        {
            "q": [1, 0, 0, 0, 0, 0, 0, 0],
            "near": [1, 0.1, 0, 0, 0, 0, 0, 0],
            "far": [0, 1, 0, 0, 0, 0, 0, 0],
        }
    )
    ranked = await LocalCrossEncoder(emb).rank("q", ["far", "near"])
    assert [p for p, _ in ranked] == ["near", "far"]
    assert ranked[0][1] > ranked[1][1]
    assert await LocalCrossEncoder(emb).rank("q", []) == []
