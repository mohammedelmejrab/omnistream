"""Queue-driven item processing (spec §4.2): route, then write to the graph.

`ItemProcessor.process_item(item_id)` is what the WorkerPool calls. Exceptions
(including `LLMError`) propagate so the pool retries the job with backoff.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from omnistream.db import Repository
from omnistream.models import RawItem

logger = logging.getLogger(__name__)


class ItemProcessor:
    def __init__(self, repo: Repository, router, writer) -> None:
        self._repo = repo
        self._router = router
        self._writer = writer

    async def process_item(self, item_id: str) -> None:
        item = await self._repo.get_item(item_id)
        if item is None:
            logger.warning("job for unknown item %s", item_id)
            return
        source = await self._repo.get_source(item.source_id)
        if source is None:
            raise RuntimeError(f"item {item_id}: unknown source {item.source_id}")
        text = Path(item.text_path).read_text(encoding="utf-8")

        if item.bubble_ids:  # upload override / manual assignment bypasses the router
            bubble_ids = list(item.bubble_ids)
            changes = {"status": "routed", "routed_at": datetime.now(UTC)}
            if item.status != "routed":  # a retry keeps the confidence from routing
                changes["route_confidence"] = 1.0
            await self._repo.update_item(item_id, **changes)
        else:
            raw = RawItem(
                source_id=source.id,
                url=item.url,
                title=item.title,
                text=text,
                published_at=item.published_at,
            )
            decision = await self._router.route(
                raw, source, await self._repo.list_bubbles()
            )
            status = (
                "unsorted" if decision.unsorted or not decision.bubble_ids else "routed"
            )
            await self._repo.update_item(
                item_id,
                status=status,
                route_confidence=decision.confidence,
                routed_at=datetime.now(UTC),
                bubble_ids=decision.bubble_ids if status == "routed" else [],
            )
            if status == "unsorted":
                return
            bubble_ids = decision.bubble_ids

        written = list(item.written_bubble_ids or [])
        for bubble_id in bubble_ids:
            if bubble_id in written:  # finished before a failed attempt
                continue
            await self._writer.write(item, text, [bubble_id], source)
            written.append(bubble_id)
            await self._repo.update_item(item_id, written_bubble_ids=list(written))
        now = datetime.now(UTC)
        await self._repo.update_item(
            item_id, status="written", extracted_at=now, written_at=now, error=None
        )
