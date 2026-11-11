import asyncio
from datetime import timedelta

from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.ingest.queue import WorkerPool
from omnistream.llm import LLMError


async def _seed(repo, n=1):
    for i in range(n):
        await repo.create_item(ItemRow(id=f"i{i}", source_id="s"))
        await repo.enqueue_job(f"i{i}")


async def test_claim_exclusive_under_concurrency(tmp_path):
    repo = Repository.from_path(str(tmp_path / "q.db"))
    await _seed(repo, 5)
    got = await asyncio.gather(*[repo.claim_job() for _ in range(12)])
    ids = [j.id for j in got if j]
    assert len(ids) == 5 and len(set(ids)) == 5


async def test_success_marks_done():
    repo = Repository()
    await _seed(repo)
    seen = []

    async def proc(item_id):
        seen.append(item_id)

    pool = WorkerPool(repo, proc)
    assert await pool.run_once() and not await pool.run_once()
    assert seen == ["i0"] and len(await repo.list_jobs("done")) == 1


async def test_llm_error_retries_with_backoff_item_not_lost():
    repo = Repository()
    await _seed(repo)

    async def proc(item_id):
        raise LLMError("429 retries exhausted")

    pool = WorkerPool(repo, proc, backoff_base=60)
    await pool.run_once()
    job = (await repo.list_jobs())[0]
    assert job.state == "queued" and job.attempts == 1
    assert await repo.claim_job() is None  # backing off
    item = await repo.get_item("i0")
    assert item.status == "queued" and "LLMError" in item.error


def test_backoff_is_exponential():
    pool = WorkerPool(None, None, backoff_base=10)
    assert [pool.backoff(a) for a in (1, 2, 3)] == [
        timedelta(seconds=10),
        timedelta(seconds=20),
        timedelta(seconds=40),
    ]


async def test_fails_after_five_attempts_item_kept():
    repo = Repository()
    await _seed(repo)

    async def proc(item_id):
        raise LLMError("boom")

    pool = WorkerPool(repo, proc, backoff_base=0)
    for _ in range(5):
        assert await pool.run_once()
    assert not await pool.run_once()
    assert (await repo.list_jobs())[0].state == "failed"
    item = await repo.get_item("i0")
    assert item.status == "failed" and "boom" in item.error


async def test_running_jobs_reclaimed_on_start_and_processed(tmp_path):
    repo = Repository.from_path(str(tmp_path / "q.db"))
    await _seed(repo)
    assert await repo.claim_job() is not None  # simulate crash mid-job
    done = asyncio.Event()

    async def proc(item_id):
        done.set()

    pool = WorkerPool(repo, proc, workers=2, idle_sleep=0.01)
    await pool.start()
    try:
        await asyncio.wait_for(done.wait(), 2)
    finally:
        await pool.stop()
