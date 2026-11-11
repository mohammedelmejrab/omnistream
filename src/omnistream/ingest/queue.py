"""SQLite-backed job queue consumed by N asyncio workers (spec §4.2).

Jobs are claimed atomically via the Repository. A failed attempt (including an
``LLMError`` after the client exhausted its own 429 retries) is re-queued with
exponential backoff; after ``max_attempts`` the job and its item are marked
``failed`` with the error recorded. Items are never deleted.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from omnistream.config import Settings
from omnistream.db import Repository

logger = logging.getLogger(__name__)

_settings = Settings()


class WorkerPool:
    def __init__(
        self,
        repo: Repository,
        process_item: Callable[[str], Awaitable[None]],
        workers: int = _settings.queue_workers,
        max_attempts: int = 5,
        backoff_base: float = 30.0,
        idle_sleep: float = 0.5,
    ) -> None:
        self._repo = repo
        self._process = process_item
        self._n = workers
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._idle = idle_sleep
        self._tasks: list[asyncio.Task[None]] = []

    def backoff(self, attempts: int) -> timedelta:
        return timedelta(seconds=self._backoff_base * 2 ** (attempts - 1))

    async def start(self) -> None:
        if self._tasks:
            return
        n = await self._repo.requeue_running_jobs()
        if n:
            logger.warning("re-queued %d job(s) left running after a crash", n)
        self._tasks = [asyncio.create_task(self._loop()) for _ in range(self._n)]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _loop(self) -> None:
        while True:
            try:
                if not await self.run_once():
                    await asyncio.sleep(self._idle)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("worker loop error")
                await asyncio.sleep(self._idle)

    async def run_once(self) -> bool:
        """Claim and process one job. Returns False when nothing was available."""
        job = await self._repo.claim_job()
        if job is None:
            return False
        try:
            await self._process(job.item_id)
        except asyncio.CancelledError:
            # Shutdown mid-job: leave it claimable rather than stuck running.
            await asyncio.shield(self._repo.finish_job(job.id, "queued"))
            raise
        except Exception as exc:  # noqa: BLE001 - any failure is retried/recorded
            await self._on_failure(job.id, job.item_id, job.attempts, exc)
        else:
            await self._repo.finish_job(job.id, "done")
        return True

    async def _on_failure(
        self, job_id: int, item_id: str, attempts: int, exc: Exception
    ) -> None:
        err = f"{type(exc).__name__}: {exc}"
        if attempts >= self._max_attempts:
            logger.error("item %s failed after %d attempts: %s", item_id, attempts, err)
            await self._repo.finish_job(job_id, "failed")
            await self._repo.update_item(item_id, status="failed", error=err)
            return
        logger.warning(
            "item %s attempt %d failed (%s); retrying", item_id, attempts, err
        )
        await self._repo.finish_job(job_id, "queued", retry_in=self.backoff(attempts))
        await self._repo.update_item(item_id, error=err)
