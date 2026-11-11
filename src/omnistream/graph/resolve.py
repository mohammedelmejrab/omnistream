"""Global entity resolution: embedding match, then fuzzy name match, then create."""

import re
import uuid

from rapidfuzz import fuzz, utils

from omnistream.embed import Embedder
from omnistream.models import Entity
from omnistream.store.base import GraphStore

_LEGAL_SUFFIX = re.compile(
    r"[\s,]+(?:inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc"
    r"|ag|gmbh|sa|nv)\.?\s*$",
    re.IGNORECASE,
)


def _strip_legal_suffix(name: str) -> str:
    """Drop one trailing legal-form token ("Inc.", ", Ltd"); never to empty."""
    stripped = _LEGAL_SUFFIX.sub("", name.strip())
    return stripped if stripped.strip(" ,.") else name


class EntityResolver:
    def __init__(
        self,
        store: GraphStore,
        embedder: Embedder,
        embed_threshold: float,
        fuzzy_threshold: int,
        candidate_k: int = 20,
    ):
        self._store = store
        self._embedder = embedder
        self._embed_threshold = embed_threshold
        self._fuzzy_threshold = fuzzy_threshold
        self._candidate_k = candidate_k
        self._cache: dict[tuple[str, str], Entity] = {}

    def new_batch(self) -> None:
        self._cache.clear()

    async def resolve(self, mention: str, type: str) -> Entity:
        mention = mention.strip()
        key = (mention.casefold(), type)
        if key in self._cache:
            return self._cache[key]

        [emb] = await self._embedder.embed([mention])
        candidates = await self._store.search_entities(emb, type, k=self._candidate_k)

        match = self._match(mention, type, candidates)
        if match is not None:
            known = {n.casefold() for n in (match.canonical_name, *match.aliases)}
            if mention.casefold() not in known:
                await self._store.add_alias(match.id, mention)
                match.aliases.append(mention)  # keep cached object in sync
            entity = match
        else:
            entity = await self._store.create_entity(
                Entity(
                    id=uuid.uuid4().hex,
                    canonical_name=mention,
                    type=type,
                    aliases=[],
                    embedding=emb,
                )
            )
        self._cache[key] = entity
        return entity

    def _match(
        self, mention: str, type_: str, candidates: list[tuple[Entity, float]]
    ) -> Entity | None:
        if not candidates:
            return None
        best, cosine = candidates[0]
        if cosine >= self._embed_threshold:
            return best
        best_entity, best_score = None, -1.0
        if type_ == "ORG":
            mention = _strip_legal_suffix(mention)
        for entity, _ in candidates:
            # default_process (casefold, strip punctuation) is required: without
            # it "Timothy D. Cook" vs "Timothy Cook" scores 88.9 < 90.
            names = (entity.canonical_name, *entity.aliases)
            if type_ == "ORG":
                names = tuple(_strip_legal_suffix(n) for n in names)
            score = max(
                fuzz.token_sort_ratio(mention, n, processor=utils.default_process)
                for n in names
            )
            if score > best_score:
                best_entity, best_score = entity, score
        return best_entity if best_score >= self._fuzzy_threshold else None
