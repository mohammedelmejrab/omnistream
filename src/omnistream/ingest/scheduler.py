import logging
from datetime import UTC, datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from omnistream.db import Repository
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.models import IngestResult, RawItem, Source
from omnistream.sources.api import fetch_api
from omnistream.sources.rss import fetch_rss

logger = logging.getLogger(__name__)


class IngestScheduler:
    def __init__(
        self,
        repo: Repository,
        pipeline: IngestPipeline,
        http: httpx.AsyncClient,
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        self._repo = repo
        self._pipeline = pipeline
        self._http = http
        self._scheduler = scheduler or AsyncIOScheduler()

    async def start(self) -> None:
        for source in await self._repo.list_sources():
            self.schedule_source(source)
        if not self._scheduler.running:
            self._scheduler.start()

    def schedule_source(self, source: Source) -> None:
        if source.type in ("document", "log") or not source.enabled:
            return
        job_id = f"poll:{source.id}"
        # Jobs added to an unstarted scheduler stay pending and
        # replace_existing is not applied until start, so remove explicitly.
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)
        self._scheduler.add_job(
            self.poll_source,
            trigger=IntervalTrigger(seconds=source.poll_interval),
            args=[source.id],
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    async def poll_source(self, source_id: str) -> list[IngestResult]:
        source = await self._repo.get_source(source_id)
        if source is None:
            return []
        try:
            items = await self._fetch(source)
            results = await self._pipeline.process_many(items, source)
        except Exception as exc:
            logger.exception("polling source %s failed", source_id)
            source.last_error = repr(exc)
            source.status = "error"
            await self._record(source)
            return []
        source.last_polled_at = datetime.now(UTC)
        source.last_error = None
        source.status = "ok"
        await self._record(source)
        return results

    async def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def _fetch(self, source: Source) -> list[RawItem]:
        if source.type == "rss":
            return await fetch_rss(source, self._http)
        if source.type == "api":
            return await fetch_api(source, self._http)
        return []

    async def _record(self, source: Source) -> None:
        try:
            await self._repo.upsert_source(source)
        except Exception:
            logger.exception("could not record poll state for %s", source.id)
