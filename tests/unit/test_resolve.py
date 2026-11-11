import math
import uuid

from omnistream.graph.resolve import EntityResolver
from omnistream.models import Entity
from omnistream.store.memory import InMemoryStore
from tests.conftest import DIM, FakeEmbedder


def _e(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def _at_cosine(c: float) -> list[float]:
    """Unit vector with cosine `c` against e0."""
    v = [0.0] * DIM
    v[0] = c
    v[1] = math.sqrt(1 - c * c)
    return v


TABLE = {
    "Apple Inc.": _e(0),
    "Apple": _at_cosine(0.95),
    "Timothy Cook": _e(2),
    "Timothy D. Cook": [0.0, 0.0, 0.8, 0.6, 0.0, 0.0, 0.0, 0.0],
    "NewCo": _e(4),
}


async def _seed(store: InMemoryStore, name: str, type_: str) -> Entity:
    emb = (await FakeEmbedder(TABLE).embed([name]))[0]
    return await store.create_entity(
        Entity(
            id=uuid.uuid4().hex,
            canonical_name=name,
            type=type_,
            aliases=[],
            embedding=emb,
        )
    )


def _resolver(store: InMemoryStore) -> EntityResolver:
    return EntityResolver(
        store, FakeEmbedder(TABLE), embed_threshold=0.9, fuzzy_threshold=90
    )


async def test_embedding_match_reuses_entity_and_adds_alias():
    store = InMemoryStore()
    apple = await _seed(store, "Apple Inc.", "ORG")
    got = await _resolver(store).resolve("Apple", "ORG")
    assert got.id == apple.id
    assert "Apple" in (await store.get_entity(apple.id)).aliases


async def test_fuzzy_fallback_when_embedding_below_threshold():
    store = InMemoryStore()
    cook = await _seed(store, "Timothy Cook", "PERSON")
    got = await _resolver(store).resolve("Timothy D. Cook", "PERSON")
    assert got.id == cook.id
    assert "Timothy D. Cook" in (await store.get_entity(cook.id)).aliases


async def test_creates_new_entity_when_no_match():
    store = InMemoryStore()
    await _seed(store, "Apple Inc.", "ORG")
    got = await _resolver(store).resolve("NewCo", "ORG")
    assert got.canonical_name == "NewCo"
    assert (await store.get_entity(got.id)).aliases == []
    assert len(store._entities) == 2


async def test_type_mismatch_creates_new_entity():
    store = InMemoryStore()
    apple = await _seed(store, "Apple Inc.", "ORG")
    got = await _resolver(store).resolve("Apple Inc.", "PRODUCT")
    assert got.id != apple.id
    assert got.type == "PRODUCT"
    assert len(store._entities) == 2


async def test_same_mention_twice_in_batch_creates_one_entity():
    store = InMemoryStore()
    r = _resolver(store)
    a = await r.resolve("NewCo", "ORG")
    b = await r.resolve("newco ", "ORG")
    assert a.id == b.id
    assert len(store._entities) == 1


async def test_new_batch_clears_cache():
    store = InMemoryStore()
    r = _resolver(store)
    a = await r.resolve("NewCo", "ORG")
    r.new_batch()
    b = await r.resolve("NewCo", "ORG")
    assert a.id == b.id  # found again via the store, not duplicated
    assert len(store._entities) == 1


async def test_no_alias_added_when_mention_equals_canonical_casefolded():
    store = InMemoryStore()
    apple = await _seed(store, "Apple Inc.", "ORG")
    got = await _resolver(store).resolve("apple inc.", "ORG")
    assert got.id == apple.id
    assert (await store.get_entity(apple.id)).aliases == []


async def test_cross_bubble_entity_shared():
    store = InMemoryStore()
    r = _resolver(store)
    first = await r.resolve("NewCo", "ORG")  # item from bubble A
    r.new_batch()
    second = await r.resolve("NewCo", "ORG")  # item from bubble B
    assert first.id == second.id


LOW_TABLE = {**TABLE, "Apple": _at_cosine(0.70), "Apple Inc.": _e(0)}


def _low_resolver(store: InMemoryStore) -> EntityResolver:
    return EntityResolver(
        store, FakeEmbedder(LOW_TABLE), embed_threshold=0.9, fuzzy_threshold=90
    )


async def test_org_legal_suffix_ignored_in_fuzzy_match():
    store = InMemoryStore()
    apple = await _seed(store, "Apple Inc.", "ORG")
    got = await _low_resolver(store).resolve("Apple", "ORG")
    assert got.id == apple.id
    assert "Apple" in (await store.get_entity(apple.id)).aliases


async def test_legal_suffix_not_stripped_for_non_org():
    store = InMemoryStore()
    apple = await _seed(store, "Apple Inc.", "PRODUCT")
    got = await _low_resolver(store).resolve("Apple", "PRODUCT")
    assert got.id != apple.id
    assert len(store._entities) == 2
