"""Ingest orchestration: dedup, route, extract, ground, resolve, write, mark seen."""

import logging

from omnistream.graph.extract import Extractor
from omnistream.graph.grounding import ground_extraction
from omnistream.graph.resolve import EntityResolver
from omnistream.graph.write import FactWriter
from omnistream.ingest.normalize import content_hash, normalize_text
from omnistream.models import IngestResult, RawItem, Source
from omnistream.router.route import Router
from omnistream.store.base import GraphStore

logger = logging.getLogger(__name__)


class IngestPipeline:
    def __init__(
        self,
        store: GraphStore,
        router: Router,
        extractor: Extractor,
        resolver: EntityResolver,
        writer: FactWriter,
        grounding_threshold: int,
    ) -> None:
        self._store = store
        self._router = router
        self._extractor = extractor
        self._resolver = resolver
        self._writer = writer
        self._threshold = grounding_threshold
        self._inflight: set[str] = set()

    async def process(self, item: RawItem, source: Source) -> IngestResult:
        h = content_hash(item.url, item.text)
        if normalize_text(item.text) == "":
            return IngestResult(status="empty", item_hash=h)

        # No await between the in-flight check and the add: closes the race
        # where two coroutines both pass has_seen before either registers.
        if h in self._inflight:
            return IngestResult(status="duplicate", item_hash=h)
        self._inflight.add(h)
        try:
            if await self._store.has_seen(h):
                return IngestResult(status="duplicate", item_hash=h)
            try:
                return await self._run(item, source, h)
            except Exception as exc:
                logger.exception("ingest failed for %s", item.url)
                return IngestResult(status="failed", item_hash=h, error=repr(exc))
        finally:
            self._inflight.discard(h)

    async def _run(self, item: RawItem, source: Source, h: str) -> IngestResult:
        bubbles = await self._router.route(
            item, source, await self._store.list_bubbles()
        )
        if not bubbles:
            return IngestResult(status="unrouted", item_hash=h)

        extraction = await self._extractor.extract(item)
        kept, dropped = ground_extraction(
            extraction, f"{item.title}\n{item.text}", self._threshold
        )

        self._resolver.new_batch()
        created = merged = superseded = 0
        for t in kept.triples:
            subject = await self._resolver.resolve(t.subject, t.subject_type)
            obj = await self._resolver.resolve(t.object, t.object_type)
            for bubble_id in bubbles:
                outcome = await self._writer.write(
                    subject.id,
                    t.relation,
                    obj.id,
                    t.exclusive,
                    t.valid_from,
                    bubble_id,
                    item,
                    h,
                    source,
                )
                if outcome == "merged":
                    merged += 1
                else:
                    created += 1
                    if outcome == "superseded":
                        superseded += 1

        await self._store.mark_seen(h, source.id)
        return IngestResult(
            status="ingested",
            item_hash=h,
            bubble_ids=bubbles,
            facts_created=created,
            facts_merged=merged,
            facts_superseded=superseded,
            dropped_ungrounded=dropped,
        )

    async def process_many(
        self, items: list[RawItem], source: Source
    ) -> list[IngestResult]:
        return [await self.process(i, source) for i in items]
