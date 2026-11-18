"""Unit tests for the in-memory GlobalEntityStore lookup (ingestion item 2b)."""

import numpy as np

from omnistream.graph.memory_store import InMemoryGlobalEntityStore


def emb(*vals):
    return np.asarray(vals, dtype=float)


async def test_memory_store_find_by_name_casefolded():
    store = InMemoryGlobalEntityStore()
    await store.create_global_entity("g1", "Aldervane Transit", "Organization", emb(1, 0))
    found = await store.find_global_entity("alDERVANE transit", "Organization")
    assert found is not None and found.uuid == "g1"


async def test_memory_store_find_by_alias():
    store = InMemoryGlobalEntityStore()
    await store.create_global_entity("g1", "Aldervane Transit", "Organization", emb(1, 0))
    await store.add_global_alias("g1", "AVT")
    found = await store.find_global_entity("avt", "Organization")
    assert found is not None and found.uuid == "g1"


async def test_memory_store_type_compatibility():
    store = InMemoryGlobalEntityStore()
    await store.create_global_entity("g1", "Aldervane Transit", "Organization", emb(1, 0))
    assert await store.find_global_entity("Aldervane Transit", "Person") is None
    assert (await store.find_global_entity("Aldervane Transit", "Entity")).uuid == "g1"


async def test_memory_store_ambiguous_returns_none():
    store = InMemoryGlobalEntityStore()
    await store.create_global_entity("g1", "AVT", "Organization", emb(1, 0))
    await store.create_global_entity("g2", "AVT", "Organization", emb(0, 1))
    assert await store.find_global_entity("AVT", "Organization") is None


async def test_memory_store_used_by_linker_end_to_end():
    from omnistream.graph.linker import GlobalEntityLinker
    from tests.conftest import FakeEmbedder

    store = InMemoryGlobalEntityStore()
    l = GlobalEntityLinker(store, FakeEmbedder(), 0.88, 90)
    pairs = [("Aldervane Transit", "AVT")]
    a = await l.link("e1", "Aldervane Transit", "Organization", alias_pairs=pairs)
    b = await l.link("e2", "AVT", "Organization", alias_pairs=pairs)
    assert a == b
