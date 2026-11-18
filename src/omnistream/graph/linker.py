"""GlobalEntity linking (spec C4): cosine >= 0.88 same type, else fuzzy >= 90, else new.

Each per-bubble Entity node gets `(:Entity)-[:SAME_AS]->(:GlobalEntity)` so the
same real-world entity is recognised across bubbles.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from rapidfuzz import fuzz, utils

from omnistream.embed import Embedder
from omnistream.graph.aliases import name_key, names_differ_by_number

ORG_TYPE = "Organization"

_LEGAL_SUFFIX = re.compile(
    r"[\s,]+(?:inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc"
    r"|ag|gmbh|sa|nv)\.?\s*$",
    re.IGNORECASE,
)


def _strip_legal_suffix(name: str) -> str:
    """Drop one trailing legal-form token ("Inc.", ", Ltd"); never to empty."""
    stripped = _LEGAL_SUFFIX.sub("", name.strip())
    return stripped if stripped.strip(" ,.") else name


@dataclass
class GlobalCandidate:
    uuid: str
    name: str
    type: str
    aliases: list[str] = field(default_factory=list)
    cosine: float = 0.0


class GlobalEntityStore(Protocol):
    async def existing_global_entity(self, entity_uuid: str) -> str | None: ...

    async def nearest_global_entities(
        self, embedding: list[float], type: str, k: int
    ) -> list[GlobalCandidate]:
        """Same-type GlobalEntities by descending cosine (true cosine, -1..1)."""
        ...

    async def create_global_entity(
        self, uuid: str, name: str, type: str, embedding: list[float]
    ) -> None: ...

    async def add_global_alias(self, uuid: str, alias: str) -> None: ...

    async def link_same_as(self, entity_uuid: str, global_uuid: str) -> None: ...

    async def find_global_entity(
        self, name: str, type: str
    ) -> GlobalCandidate | None:
        """Exact casefolded match on a GlobalEntity's name or an alias, same type
        (or either side untyped/unknown).  Returns None when there is no match or
        when the match is ambiguous (more than one distinct GlobalEntity)."""
        ...


class GlobalEntityLinker:
    def __init__(
        self,
        store: GlobalEntityStore,
        embedder: Embedder,
        embed_threshold: float,
        fuzzy_threshold: int,
        candidate_k: int = 20,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._embed_threshold = embed_threshold
        self._fuzzy_threshold = fuzzy_threshold
        self._candidate_k = candidate_k

    async def link(
        self,
        entity_uuid: str,
        name: str,
        type: str,
        embedding: list[float] | None = None,
        add_alias: bool = True,
        alias_pairs: list[tuple[str, str]] | None = None,
    ) -> str:
        """Link an Entity node to its GlobalEntity (creating one); returns its uuid.

        ``alias_pairs`` are ``(full, short)`` pairs extracted from the *same*
        source item/episode text.  When ``name`` equals one side of a pair and the
        other side already has a GlobalEntity, the entity is linked to that same
        GlobalEntity instead of relying on embedding/fuzzy matching.  This is
        order-independent: whichever side of the pair is linked first creates the
        GlobalEntity, and the second side resolves it by exact name lookup.
        """
        existing = await self._store.existing_global_entity(entity_uuid)
        if existing is not None:
            return existing
        name = name.strip()
        # 1. Source-evidenced alias resolution (stronger than embedding).
        alias_match = await self._resolve_alias(name, type, alias_pairs or ())
        if alias_match is not None:
            await self._adopt(name, alias_match, add_alias)
            await self._store.link_same_as(entity_uuid, alias_match.uuid)
            return alias_match.uuid
        # 2. Embedding / fuzzy match, else create.
        if embedding is None:
            [embedding] = await self._embedder.embed([name])
        candidates = await self._store.nearest_global_entities(
            embedding, type, self._candidate_k
        )
        match = self._match(name, type, candidates)
        if match is None:
            global_uuid = uuid.uuid4().hex
            await self._store.create_global_entity(global_uuid, name, type, embedding)
        else:
            global_uuid = match.uuid
            await self._adopt(name, match, add_alias)
        await self._store.link_same_as(entity_uuid, global_uuid)
        return global_uuid

    async def _adopt(self, name: str, match: GlobalCandidate, add_alias: bool) -> None:
        """Record ``name`` as an alias of ``match``'s GlobalEntity when unknown."""
        known = {n.casefold() for n in (match.name, *match.aliases)}
        if add_alias and name.casefold() not in known:
            await self._store.add_global_alias(match.uuid, name)

    async def _resolve_alias(
        self, name: str, type_: str, alias_pairs: list[tuple[str, str]]
    ) -> GlobalCandidate | None:
        """Find the GlobalEntity for the *other* side of a source-stated pair.

        Refuses to merge when the two names differ by a number token, and relies
        on the store's ``find_global_entity`` to refuse ambiguous/type-mismatched
        lookups (returning None).
        """
        key = name_key(name)
        for full, short in alias_pairs:
            if key == name_key(full):
                other = short
            elif key == name_key(short):
                other = full
            else:
                continue
            if names_differ_by_number(name, other):
                continue
            candidate = await self._store.find_global_entity(other, type_)
            if candidate is not None:
                return candidate
        return None

    def _match(
        self, mention: str, type_: str, candidates: list[GlobalCandidate]
    ) -> GlobalCandidate | None:
        if not candidates:
            return None
        best = candidates[0]
        if best.cosine >= self._embed_threshold:
            return best
        if type_ == ORG_TYPE:
            mention = _strip_legal_suffix(mention)
        best_candidate, best_score = None, -1.0
        for cand in candidates:
            # default_process (casefold, strip punctuation) is required: without
            # it "Timothy D. Cook" vs "Timothy Cook" scores 88.9 < 90.
            names = (cand.name, *cand.aliases)
            if type_ == ORG_TYPE:
                names = tuple(_strip_legal_suffix(n) for n in names)
            score = max(
                fuzz.token_sort_ratio(mention, n, processor=utils.default_process)
                for n in names
            )
            if score > best_score:
                best_candidate, best_score = cand, score
        return best_candidate if best_score >= self._fuzzy_threshold else None
