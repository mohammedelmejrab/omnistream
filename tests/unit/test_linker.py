from omnistream.graph.aliases import types_compatible
from omnistream.graph.linker import GlobalCandidate, GlobalEntityLinker
from tests.conftest import FakeEmbedder


class FakeGlobalStore:
    def __init__(self, candidates=()):
        self.candidates = list(candidates)
        self.created: list[tuple] = []
        self.aliases: list[tuple] = []
        self.links: list[tuple] = []
        self._globals = {c.uuid: c for c in self.candidates}

    async def existing_global_entity(self, entity_uuid):
        return next((g for e, g in self.links if e == entity_uuid), None)

    async def nearest_global_entities(self, embedding, type, k):
        return [c for c in self.candidates if c.type == type][:k]

    async def create_global_entity(self, uuid, name, type, embedding):
        self.created.append((uuid, name, type))
        self._globals[uuid] = GlobalCandidate(uuid, name, type)

    async def add_global_alias(self, uuid, alias):
        self.aliases.append((uuid, alias))
        if uuid in self._globals and alias not in self._globals[uuid].aliases:
            self._globals[uuid].aliases.append(alias)

    async def link_same_as(self, entity_uuid, global_uuid):
        self.links.append((entity_uuid, global_uuid))

    async def find_global_entity(self, name, type):
        key = name.strip().casefold()
        matches = [
            g
            for g in self._globals.values()
            if key
            in {g.name.strip().casefold(), *(a.strip().casefold() for a in g.aliases)}
            and types_compatible(g.type, type)
        ]
        return matches[0] if len(matches) == 1 else None


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


# --- source-evidenced alias resolution (ingestion item 2b) -------------------

PAIR = [("Aldervane Transit", "AVT")]


async def test_alias_resolution_short_links_to_existing_full_global():
    store = FakeGlobalStore()
    l = linker(store)
    # Full name linked first (creates the GlobalEntity).
    full_gid = await l.link("e-full", "Aldervane Transit", "Organization")
    # Short form linked second: resolves by exact name lookup, same global.
    short_gid = await l.link("e-short", "AVT", "Organization", alias_pairs=PAIR)
    assert short_gid == full_gid
    assert ("e-short", full_gid) in store.links
    assert ("AVT" in store._globals[full_gid].aliases)


async def test_alias_resolution_full_links_to_existing_short_global():
    store = FakeGlobalStore()
    l = linker(store)
    # Short form linked first (creates the GlobalEntity).
    short_gid = await l.link("e-short", "AVT", "Organization", alias_pairs=PAIR)
    # Full name linked second: resolves the short global, adds full as alias.
    full_gid = await l.link("e-full", "Aldervane Transit", "Organization", alias_pairs=PAIR)
    assert full_gid == short_gid
    assert "Aldervane Transit" in store._globals[short_gid].aliases


async def test_alias_resolution_order_independent_same_global():
    store = FakeGlobalStore()
    first = await linker(store).link("e1", "AVT", "Organization", alias_pairs=PAIR)
    second = await linker(store).link("e2", "Aldervane Transit", "Organization", alias_pairs=PAIR)
    assert first == second


async def test_alias_resolution_does_not_embed():
    # Even with zero embedding candidates, the source-stated pair resolves.
    store = FakeGlobalStore()
    l = linker(store)
    a = await l.link("e1", "Aldervane Transit", "Organization", alias_pairs=PAIR)
    b = await l.link("e2", "AVT", "Organization", alias_pairs=PAIR)
    assert a == b


async def test_alias_resolution_refused_on_number_token():
    store = FakeGlobalStore()
    l = linker(store)
    pairs = [("Dovetail Quay 9", "DQ9")]
    first = await l.link("e1", "Dovetail Quay 9", "Organization", alias_pairs=pairs)
    second = await l.link("e2", "Dovetail Quay 10", "Organization", alias_pairs=pairs)
    assert first != second


async def test_no_alias_merge_without_source_evidence():
    # No alias_pairs: a pure acronym-initials match must not merge.
    store = FakeGlobalStore()
    l = linker(store)
    first = await l.link("e1", "Aldervane Transit", "Organization")
    second = await l.link("e2", "AVT", "Organization")
    assert first != second


async def test_find_global_entity_type_conflict_returns_none():
    store = FakeGlobalStore([GlobalCandidate("g1", "Aldervane Transit", "Organization")])
    assert await store.find_global_entity("Aldervane Transit", "Person") is None
    assert (await store.find_global_entity("Aldervane Transit", "Organization")).uuid == "g1"
    # Untyped lookup side is compatible.
    assert (await store.find_global_entity("Aldervane Transit", "Entity")).uuid == "g1"


async def test_find_global_entity_ambiguous_returns_none():
    store = FakeGlobalStore(
        [
            GlobalCandidate("g1", "AVT", "Organization", ["Aldervane Transit"]),
            GlobalCandidate("g2", "AVT", "Organization", ["Aldervane Transit"]),
        ]
    )
    assert await store.find_global_entity("Aldervane Transit", "Organization") is None

