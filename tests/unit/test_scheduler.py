from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from omnistream.db import Repository
from omnistream.graph.extract import Extractor
from omnistream.graph.resolve import EntityResolver
from omnistream.graph.write import FactWriter
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.models import Bubble, Extraction, Source
from omnistream.router.bubbles import BubbleService
from omnistream.router.router import BubbleChoice, Router
from omnistream.store.memory import InMemoryStore
from tests.conftest import FakeEmbedder, FakeLLM

NOW = datetime(2026, 1, 1, tzinfo=UTC)
NEWS_XML = (
    Path(__file__).parent.parent / "fixtures" / "feeds" / "news.xml"
).read_bytes()
URL_A = "https://a.test/feed.xml"
URL_B = "https://b.test/feed.xml"


def rss(id: str, url: str, poll_interval: int = 300) -> Source:
    return Source(id=id, type="rss", url=url, poll_interval=poll_interval)


@pytest.fixture
async def env():
    store = InMemoryStore()
    repo = Repository()
    await BubbleService(repo, FakeEmbedder()).create(
        Bubble(id="news", name="news", description="news topics", updated_at=NOW)
    )
    fake = FakeLLM(
        {
            BubbleChoice: BubbleChoice(bubble_ids=["news"], confidence=0.9),
            Extraction: Extraction(triples=[]),
        }
    )
    pipe = IngestPipeline(
        repo,
        Router(fake, "m", FakeEmbedder()),
        Extractor(fake, "m"),
        EntityResolver(store, FakeEmbedder(), 0.9, 90),
        FactWriter(store, clock=lambda: NOW),
        grounding_threshold=85,
    )
    aps = AsyncIOScheduler()
    aps.start(paused=True)
    async with httpx.AsyncClient() as http:
        yield repo, IngestScheduler(repo, pipe, http, scheduler=aps), aps
    if aps.running:
        aps.shutdown(wait=False)


@respx.mock
async def test_poll_rss_source_ingests_items(env):
    store, sched, _ = env
    await store.upsert_source(rss("a", URL_A))
    respx.get(URL_A).respond(200, content=NEWS_XML)
    results = await sched.poll_source("a")
    assert len(results) == 3
    assert all(r.status == "ingested" for r in results)
    src = await store.get_source("a")
    assert src.last_polled_at is not None
    assert src.last_error is None


@respx.mock
async def test_second_poll_reports_duplicates(env):
    store, sched, _ = env
    await store.upsert_source(rss("a", URL_A))
    respx.get(URL_A).respond(200, content=NEWS_XML)
    await sched.poll_source("a")
    results = await sched.poll_source("a")
    assert len(results) == 3
    assert all(r.status == "duplicate" for r in results)


@respx.mock
async def test_failing_source_does_not_block_others(env):
    store, sched, _ = env
    await store.upsert_source(rss("a", URL_A))
    await store.upsert_source(rss("b", URL_B))
    respx.get(URL_A).respond(500)
    respx.get(URL_B).respond(200, content=NEWS_XML)
    assert await sched.poll_source("a") == []
    results_b = await sched.poll_source("b")
    assert len(results_b) == 3
    assert all(r.status == "ingested" for r in results_b)
    assert (await store.get_source("a")).last_error
    assert (await store.get_source("b")).last_error is None


@respx.mock
async def test_transport_error_is_recorded(env):
    store, sched, _ = env
    await store.upsert_source(rss("a", URL_A))
    respx.get(URL_A).mock(side_effect=httpx.ConnectError("boom"))
    assert await sched.poll_source("a") == []
    assert "boom" in (await store.get_source("a")).last_error


async def test_unknown_source_returns_empty(env):
    _, sched, _ = env
    assert await sched.poll_source("nope") == []


async def test_schedule_source_registers_interval_job(env):
    _, sched, aps = env
    sched.schedule_source(rss("a", URL_A, poll_interval=120))
    job = aps.get_job("poll:a")
    assert job is not None
    assert job.trigger.interval == timedelta(seconds=120)
    assert job.max_instances == 1
    assert job.coalesce is True


async def test_rescheduling_replaces_job(env):
    _, sched, aps = env
    sched.schedule_source(rss("a", URL_A, poll_interval=120))
    sched.schedule_source(rss("a", URL_A, poll_interval=240))
    jobs = aps.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].trigger.interval == timedelta(seconds=240)


async def test_rescheduling_replaces_job_on_unstarted_scheduler(env):
    _, sched, _ = env
    aps = AsyncIOScheduler()
    sched._scheduler = aps
    sched.schedule_source(rss("a", URL_A, poll_interval=120))
    sched.schedule_source(rss("a", URL_A, poll_interval=240))
    jobs = aps.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].trigger.interval == timedelta(seconds=240)


async def test_document_sources_not_scheduled(env):
    _, sched, aps = env
    sched.schedule_source(Source(id="d", type="document", url=None))
    assert aps.get_jobs() == []


async def test_start_schedules_non_document_sources(env):
    store, sched, aps = env
    await store.upsert_source(rss("a", URL_A))
    await store.upsert_source(Source(id="d", type="document", url=None))
    await sched.start()
    assert [j.id for j in aps.get_jobs()] == ["poll:a"]
    await sched.shutdown()


@respx.mock
async def test_poll_with_intake_queues_items_and_repoll_adds_none(tmp_path):
    from omnistream.ingest.intake import Intake

    repo = Repository()
    await repo.upsert_source(rss("a", URL_A))
    respx.get(URL_A).respond(200, content=NEWS_XML)
    aps = AsyncIOScheduler()
    async with httpx.AsyncClient() as http:
        sched = IngestScheduler(
            repo, None, http, scheduler=aps, intake=Intake(repo, str(tmp_path), 1)
        )
        first = await sched.poll_source("a")
        second = await sched.poll_source("a")
    assert len(first) == 3 and all(r.status == "queued" for r in first)
    assert second == []
    items = await repo.list_items(status="queued")
    assert len(items) == 3 and len(await repo.list_jobs()) == 3
    assert all(Path(i.raw_path).exists() and Path(i.text_path).exists() for i in items)


async def test_poll_disabled_source_does_nothing(env):
    repo, sched, _ = env
    s = rss("a", URL_A)
    s.enabled = False
    await repo.upsert_source(s)
    assert await sched.poll_source("a") == []
    assert (await repo.get_source("a")).last_polled_at is None


@respx.mock
async def test_poll_failure_backs_off_to_4x_and_resets(env):
    repo, sched, _ = env
    s = rss("a", URL_A)
    await repo.upsert_source(s)
    sched.schedule_source(s)
    respx.get(URL_A).respond(500)
    for expected in (2, 4, 4):
        await sched.poll_source("a")
        assert (
            sched.current_interval("a", s.poll_interval) == s.poll_interval * expected
        )
    stored = await repo.get_source("a")
    assert stored.status == "error" and stored.last_error
    respx.get(URL_A).respond(200, content=NEWS_XML)
    await sched.poll_source("a")
    assert sched.current_interval("a", s.poll_interval) == s.poll_interval
    assert (await repo.get_source("a")).status == "ok"
