from omnistream.graph.linker import GlobalCandidate, GlobalEntityLinker
from tests.conftest import FakeEmbedder


class FakeGlobalStore:
    def __init__(self, candidates=()):
        self.candidates = list(candidates)
        self.created: list[tuple] = []
        self.aliases: list[tuple] = []
        self.links: list[tuple] = []

    async def existing_global_entity(self, entity_uuid):
        return next((g for e, g in self.links if e == entity_uuid), None)

    async def nearest_global_entities(self, embedding, type, k):
        return [c for c in self.candidates if c.type == type][:k]

    async def create_global_entity(self, uuid, name, type, embedding):
        self.created.append((uuid, name, type))

    async def add_global_alias(self, uuid, alias):
        self.aliases.append((uuid, alias))

    async def link_same_as(self, entity_uuid, global_uuid):
        self.links.append((entity_uuid, global_uuid))


def linker(store):
    return GlobalEntityLinker(store, FakeEmbedder(), 0.88, 90)


async def test_creates_new_global_when_none_close():
    store = FakeGlobalStore([GlobalCandidate("g1", "Zebra", "Person", cosine=0.2)])
    gid = await linker(store).link("e1", "Alice Smith", "Person")
    assert store.created[0][1:] == ("Alice Smith", "Person")
    assert store.links == [("e1", gid)] and gid != "g1"


async def test_cosine_match_same_type_links_and_adds_alias():
    store = FakeGlobalStore([GlobalCandidate("g1", "Tim Cook", "Person", cosine=0.9)])
    gid = await linker(store).link("e1", "Timothy Cook", "Person")
    assert gid == "g1" and not store.created
    assert store.aliases == [("g1", "Timothy Cook")]


async def test_cosine_below_threshold_falls_to_fuzzy():
    store = FakeGlobalStore(
        [GlobalCandidate("g1", "Timothy Cook", "Person", cosine=0.5)]
    )
    gid = await linker(store).link("e1", "Timothy D. Cook", "Person")
    assert gid == "g1"


async def test_fuzzy_below_threshold_creates():
    store = FakeGlobalStore([GlobalCandidate("g1", "Tim Cook", "Person", cosine=0.5)])
    await linker(store).link("e1", "Jane Doe", "Person")
    assert len(store.created) == 1


async def test_organization_legal_suffix_ignored():
    store = FakeGlobalStore(
        [GlobalCandidate("g1", "Apple Inc.", "Organization", cosine=0.3)]
    )
    assert await linker(store).link("e1", "Apple", "Organization") == "g1"


async def test_suffix_not_stripped_for_other_types():
    store = FakeGlobalStore(
        [GlobalCandidate("g1", "Apple Inc.", "Product", cosine=0.3)]
    )
    await linker(store).link("e1", "Apple", "Product")
    assert len(store.created) == 1


async def test_no_alias_when_disabled_or_known():
    store = FakeGlobalStore(
        [GlobalCandidate("g1", "Tim Cook", "Person", ["TC"], cosine=0.95)]
    )
    await linker(store).link("e1", "Hallucinated", "Person", add_alias=False)
    await linker(store).link("e2", "tc", "Person")
    assert store.aliases == []


async def test_retry_reuses_existing_link_even_without_search_candidates():
    store = FakeGlobalStore()
    first = await linker(store).link("e1", "Alice Smith", "Person")
    assert await linker(store).link("e1", "Alice Smith", "Person") == first
    assert len(store.created) == len(store.links) == 1
