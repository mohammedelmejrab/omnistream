import math

from omnistream.models import Bubble, Entity, Fact, Source


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


class InMemoryStore:
    """Dict-backed GraphStore. Stores and returns deep copies."""

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}
        self._bubbles: dict[str, Bubble] = {}
        self._sources: dict[str, Source] = {}
        self._entities: dict[str, Entity] = {}
        self._facts: dict[str, Fact] = {}

    async def has_seen(self, item_hash: str) -> bool:
        return item_hash in self._seen

    async def mark_seen(self, item_hash: str, source_id: str) -> None:
        self._seen.setdefault(item_hash, source_id)

    async def create_bubble(self, b: Bubble) -> Bubble:
        self._bubbles[b.id] = b.model_copy(deep=True)
        return b.model_copy(deep=True)

    async def get_bubble(self, id: str) -> Bubble | None:
        b = self._bubbles.get(id)
        return b.model_copy(deep=True) if b else None

    async def list_bubbles(self) -> list[Bubble]:
        return [b.model_copy(deep=True) for b in self._bubbles.values()]

    async def upsert_source(self, s: Source) -> Source:
        self._sources[s.id] = s.model_copy(deep=True)
        return s.model_copy(deep=True)

    async def get_source(self, id: str) -> Source | None:
        s = self._sources.get(id)
        return s.model_copy(deep=True) if s else None

    async def list_sources(self) -> list[Source]:
        return [s.model_copy(deep=True) for s in self._sources.values()]

    async def create_entity(self, e: Entity) -> Entity:
        self._entities[e.id] = e.model_copy(deep=True)
        return e.model_copy(deep=True)

    async def add_alias(self, entity_id: str, alias: str) -> None:
        entity = self._entities.get(entity_id)
        if entity is None:
            raise KeyError(entity_id)
        known = {entity.canonical_name.casefold()} | {
            a.casefold() for a in entity.aliases
        }
        if alias.casefold() not in known:
            entity.aliases.append(alias)

    async def get_entity(self, id: str) -> Entity | None:
        e = self._entities.get(id)
        return e.model_copy(deep=True) if e else None

    async def search_entities(
        self, embedding: list[float], type: str, k: int
    ) -> list[tuple[Entity, float]]:
        if k <= 0:
            return []
        scored = [
            (e.model_copy(deep=True), _cosine(embedding, e.embedding))
            for e in self._entities.values()
            if e.type == type
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]

    async def create_fact(self, f: Fact) -> Fact:
        self._facts[f.id] = f.model_copy(deep=True)
        return f.model_copy(deep=True)

    async def update_fact(self, f: Fact) -> Fact:
        if f.id not in self._facts:
            raise KeyError(f.id)
        self._facts[f.id] = f.model_copy(deep=True)
        return f.model_copy(deep=True)

    async def find_active_facts(
        self, bubble_id: str, subject_id: str, relation: str
    ) -> list[Fact]:
        return [
            f.model_copy(deep=True)
            for f in self._facts.values()
            if f.bubble_id == bubble_id
            and f.subject_id == subject_id
            and f.relation == relation
            and f.status == "VERIFIED"
        ]

    async def list_facts(self, bubble_id: str) -> list[Fact]:
        return [
            f.model_copy(deep=True)
            for f in self._facts.values()
            if f.bubble_id == bubble_id
        ]
