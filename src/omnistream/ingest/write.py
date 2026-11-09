from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from omnistream.models import Fact, RawItem, Source
from omnistream.store.base import GraphStore


def utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class FactWriter:
    """Writes facts with provenance, corroboration and time-aware supersession."""

    def __init__(
        self, store: GraphStore, clock: Callable[[], datetime] = utcnow
    ) -> None:
        self._store = store
        self._clock = clock

    async def write(
        self,
        subject_id: str,
        relation: str,
        object_id: str,
        exclusive: bool,
        valid_from: datetime | None,
        bubble_id: str,
        item: RawItem,
        item_hash: str,
        source: Source,
    ) -> Literal["created", "merged", "superseded"]:
        vf = _aware(valid_from or item.published_at or self._clock())
        active = await self._store.find_active_facts(bubble_id, subject_id, relation)

        same = next((a for a in active if a.object_id == object_id), None)
        if same is not None:
            if item_hash not in same.evidence_hashes:
                same.evidence_hashes = [*same.evidence_hashes, item_hash]
                same.source_count += 1
                same.credibility = max(same.credibility, source.credibility)
                await self._store.update_fact(same)
            return "merged"

        status: Literal["VERIFIED", "HISTORICAL"] = "VERIFIED"
        valid_to: datetime | None = None
        historicized = 0
        if exclusive:
            older = [a for a in active if a.valid_from <= vf]
            newer = [a for a in active if a.valid_from > vf]
            if newer:
                if await self._already_stored_late(
                    bubble_id, subject_id, relation, object_id, item_hash
                ):
                    return "merged"
                status = "HISTORICAL"
                valid_to = min(a.valid_from for a in newer)
            for a in older:
                a.valid_to = vf
                a.status = "HISTORICAL"
                await self._store.update_fact(a)
                historicized += 1

        await self._store.create_fact(
            Fact(
                id=uuid4().hex,
                subject_id=subject_id,
                relation=relation,
                object_id=object_id,
                bubble_id=bubble_id,
                source_id=source.id,
                source_url=item.url,
                credibility=source.credibility,
                source_count=1,
                evidence_hashes=[item_hash],
                valid_from=vf,
                valid_to=valid_to,
                status=status,
                ingested_at=self._clock(),
            )
        )
        return "superseded" if historicized else "created"

    async def _already_stored_late(
        self,
        bubble_id: str,
        subject_id: str,
        relation: str,
        object_id: str,
        item_hash: str,
    ) -> bool:
        return any(
            f.status == "HISTORICAL"
            and f.subject_id == subject_id
            and f.relation == relation
            and f.object_id == object_id
            and item_hash in f.evidence_hashes
            for f in await self._store.list_facts(bubble_id)
        )
