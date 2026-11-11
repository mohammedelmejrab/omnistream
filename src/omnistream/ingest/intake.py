"""Intake: polled/uploaded RawItems become stored, deduplicated, queued items.

Order per item: dedup (spec C2) -> pre-filter (feeds only) -> hourly cap ->
store original -> `items` row (status queued) + `jobs` row -> mark seen.
Items held back by the cap are NOT marked seen, so a later poll retries them.
"""

import logging
from datetime import UTC, datetime, timedelta

from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.ingest.normalize import content_hash, normalize_text
from omnistream.ingest.originals import store_original
from omnistream.models import RawItem, Source

logger = logging.getLogger(__name__)


class Intake:
    def __init__(
        self, repo: Repository, data_dir: str, prefilter_min_chars: int = 200
    ) -> None:
        self._repo = repo
        self._data_dir = data_dir
        self._min_chars = prefilter_min_chars
        # Closes the race where two coroutines both pass has_seen.
        self._inflight: set[str] = set()

    async def accept(
        self,
        raw_item: RawItem,
        source: Source,
        raw_bytes: bytes,
        ext: str,
        *,
        part: int | None = None,
    ) -> ItemRow | None:
        """Return the queued item, or None if dropped (duplicate/filtered/capped)."""
        text = raw_item.text
        if normalize_text(text) == "":
            return None
        h = content_hash(raw_item.url, text)
        if h in self._inflight:
            return None
        self._inflight.add(h)
        try:
            return await self._accept(raw_item, source, raw_bytes, ext, part, h)
        finally:
            self._inflight.discard(h)

    async def _accept(
        self,
        item: RawItem,
        source: Source,
        raw_bytes: bytes,
        ext: str,
        part: int | None,
        h: str,
    ) -> ItemRow | None:
        if await self._repo.has_seen(h):
            return None
        now = datetime.now(UTC)
        is_document = source.type == "document"

        # Deliberate exception 1: the pre-filter applies to feed items only.
        if not is_document and (
            len(item.text.strip()) < self._min_chars or item.published_at is None
        ):
            await self._repo.create_item(
                ItemRow(
                    id=h,
                    source_id=source.id,
                    url=item.url,
                    title=item.title,
                    published_at=item.published_at,
                    status="filtered",
                    polled_at=now,
                    deduplicated_at=now,
                )
            )
            await self._repo.mark_seen(h, source.id, item.url)
            return None

        if not is_document:
            recent = await self._repo.count_items_since(
                source.id, now - timedelta(hours=1)
            )
            if recent >= source.max_items_per_hour:
                return None  # left unseen: the next poll picks it up

        raw_path, text_path, truncated = store_original(
            self._data_dir,
            source.id,
            raw_bytes,
            ext,
            item.title,
            item.text,
            store_full_text=source.store_full_text,
            part=part,
        )
        row = await self._repo.create_item(
            ItemRow(
                id=h,
                source_id=source.id,
                bubble_ids=item.bubble_ids_override or [],
                url=item.url,
                title=item.title,
                published_at=item.published_at or (now if is_document else None),
                raw_path=str(raw_path),
                text_path=str(text_path),
                text_truncated=truncated,
                status="queued",
                polled_at=now,
                deduplicated_at=now,
            )
        )
        await self._repo.enqueue_job(row.id)
        await self._repo.mark_seen(h, source.id, item.url)
        return row
