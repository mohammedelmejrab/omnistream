from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from omnistream.ingest.extract import Extractor
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.ingest.resolve import EntityResolver
from omnistream.ingest.route import BubbleChoice, Router
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.ingest.write import FactWriter
from omnistream.models import Bubble, Extraction, Source
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
    await store.create_bubble(
        Bubble(id="news", name="news", description="news topics", updated_at=NOW)
    )
    fake = FakeLLM(
        {
            BubbleChoice: BubbleChoice(bubble_ids=["news"]),
            Extraction: Extraction(triples=[]),
        }
    )
    pipe = IngestPipeline(
        store,
        Router(fake, "m"),
        Extractor(fake, "m"),
        EntityResolver(store, FakeEmbedder(), 0.9, 90),
        FactWriter(store, clock=lambda: NOW),
        grounding_threshold=85,
    )
    aps = AsyncIOScheduler()
    aps.start(paused=True)
    async with httpx.AsyncClient() as http:
        yield store, IngestScheduler(store, pipe, http, scheduler=aps), aps
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
