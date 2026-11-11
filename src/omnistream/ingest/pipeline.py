"""Legacy direct ingest path, reduced to dedup + routing.

Graph writing moved to `omnistream.graph.writer.GraphWriter`; Task 7 replaces this
module with the queue-driven `process_item` pipeline.
"""

import logging

from omnistream.db import Repository
from omnistream.ingest.normalize import content_hash, normalize_text
from omnistream.models import IngestResult, RawItem, Source
from omnistream.router.router import Router

logger = logging.getLogger(__name__)


class IngestPipeline:
    def __init__(self, repo: Repository, router: Router) -> None:
        self._repo = repo
        self._router = router
        self._inflight: set[str] = set()

    async def process(self, item: RawItem, source: Source) -> IngestResult:
        h = content_hash(item.url, item.text)
        if normalize_text(item.text) == "":
            return IngestResult(status="empty", item_hash=h)
        if h in self._inflight:
            return IngestResult(status="duplicate", item_hash=h)
        self._inflight.add(h)
        try:
            if await self._repo.has_seen(h):
                return IngestResult(status="duplicate", item_hash=h)
            try:
                decision = await self._router.route(
                    item, source, await self._repo.list_bubbles()
                )
                if decision.unsorted or not decision.bubble_ids:
                    return IngestResult(status="unrouted", item_hash=h)
                await self._repo.mark_seen(h, source.id, item.url)
                return IngestResult(
                    status="ingested", item_hash=h, bubble_ids=decision.bubble_ids
                )
            except Exception as exc:
                logger.exception("ingest failed for %s", item.url)
                return IngestResult(status="failed", item_hash=h, error=repr(exc))
        finally:
            self._inflight.discard(h)

    async def process_many(
        self, items: list[RawItem], source: Source
    ) -> list[IngestResult]:
        return [await self.process(i, source) for i in items]
