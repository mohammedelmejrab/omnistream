from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from httpx import ASGITransport

from omnistream.api.app import create_app
from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.models import Bubble
from omnistream.router.bubbles import BubbleService
from omnistream.router.router import BubbleChoice, Router
from tests.conftest import FakeEmbedder, FakeLLM

NOW = datetime(2026, 1, 1, tzinfo=UTC)
NEWS_XML = (
    Path(__file__).parent.parent / "fixtures" / "feeds" / "news.xml"
).read_bytes()
FEED = "https://a.test/feed.xml"
DOC_TEXT = b"Alice became CEO of Acme Corp this week."


def make_env(settings: Settings | None = None):
    repo = Repository()
    fake = FakeLLM(
        {
            BubbleChoice: BubbleChoice(bubble_ids=["news"], confidence=0.9),
        }
    )
    pipe = IngestPipeline(
        repo,
        Router(fake, "m", FakeEmbedder()),
    )
    aps = AsyncIOScheduler()
    aps.start(paused=True)
    return repo, pipe, aps


@pytest.fixture
async def env():
    store, pipe, aps = make_env()
    await BubbleService(store, FakeEmbedder()).create(
        Bubble(id="news", name="News", description="news topics", updated_at=NOW)
    )
    async with httpx.AsyncClient() as http:
        sched = IngestScheduler(store, pipe, http, scheduler=aps)
        app = create_app(store, pipe, sched, FakeEmbedder())
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, store, aps
    if aps.running:
        aps.shutdown(wait=False)


async def test_create_bubble_201(env):
    client, store, _ = env
    r = await client.post("/bubbles", json={"name": "Tech News!", "description": "d"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "tech-news"
    assert len(body["description_embedding"]) == 8
    assert await store.get_bubble("tech-news") is not None


async def test_create_bubble_slug_collision_gets_suffix(env):
    client, _, _ = env
    a = await client.post("/bubbles", json={"name": "a b", "description": "d"})
    b = await client.post("/bubbles", json={"name": "a-b", "description": "d"})
    assert (a.json()["id"], b.json()["id"]) == ("a-b", "a-b-2")


async def test_create_bubble_unsluggable_name_uses_uuid(env):
    client, _, _ = env
    r = await client.post("/bubbles", json={"name": "!!!", "description": "d"})
    assert r.status_code == 201
    assert len(r.json()["id"]) == 32


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "description": "d"},
        {"name": "   ", "description": "d"},
        {"name": "n", "description": " "},
    ],
)
async def test_create_bubble_empty_422(env, payload):
    client, _, _ = env
    assert (await client.post("/bubbles", json=payload)).status_code == 422


async def test_duplicate_bubble_name_409(env):
    client, _, _ = env
    r = await client.post("/bubbles", json={"name": "  nEWS ", "description": "d"})
    assert r.status_code == 409


async def test_list_bubbles(env):
    client, _, _ = env
    r = await client.get("/bubbles")
    assert r.status_code == 200
    assert [b["id"] for b in r.json()] == ["news"]


async def test_create_source_201_and_scheduled(env):
    client, store, aps = env
    r = await client.post(
        "/sources",
        json={"type": "rss", "url": FEED, "bubble_ids": ["news"]},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert await store.get_source(sid) is not None
    assert aps.get_job(f"poll:{sid}") is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "document", "url": FEED},
        {"type": "rss", "url": FEED, "credibility": 1.5},
        {"type": "rss", "url": FEED, "poll_interval": 10},
        {"type": "api", "url": FEED},
    ],
)
async def test_create_source_validation_422(env, payload):
    client, _, _ = env
    assert (await client.post("/sources", json=payload)).status_code == 422


async def test_create_source_unknown_bubble_422(env):
    client, store, _ = env
    r = await client.post(
        "/sources", json={"type": "rss", "url": FEED, "bubble_ids": ["nope"]}
    )
    assert r.status_code == 422
    assert await store.list_sources() == []


async def test_list_sources(env):
    client, _, _ = env
    await client.post("/sources", json={"type": "rss", "url": FEED})
    r = await client.get("/sources")
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_poll_unknown_source_404(env):
    client, _, _ = env
    assert (await client.post("/sources/nope/poll")).status_code == 404


@respx.mock
async def test_poll_source_200(env):
    client, _, _ = env
    sid = (await client.post("/sources", json={"type": "rss", "url": FEED})).json()[
        "id"
    ]
    respx.get(FEED).respond(200, content=NEWS_XML)
    r = await client.post(f"/sources/{sid}/poll")
    assert r.status_code == 200
    assert len(r.json()) == 3
    assert all(x["status"] == "ingested" for x in r.json())


async def upload(client, name="a.txt", data=DOC_TEXT, **form):
    return await client.post(
        "/documents", files={"file": (name, data, "text/plain")}, data=form
    )


async def test_upload_document_200(env):
    client, store, _ = env
    r = await upload(client, bubble_ids="news", credibility="0.9")
    assert r.status_code == 200
    assert [x["status"] for x in r.json()] == ["ingested"]
    (src,) = await store.list_sources()
    assert src.type == "document"
    assert src.credibility == 0.9
    assert src.bubble_ids == ["news"]


async def test_upload_without_bubbles_leaves_router_to_decide(env):
    client, store, _ = env
    assert (await upload(client)).status_code == 200
    (src,) = await store.list_sources()
    assert src.bubble_ids == []


async def test_upload_same_document_twice_second_all_duplicate(env):
    client, _, _ = env
    await upload(client)
    r = await upload(client)
    assert r.status_code == 200
    assert all(x["status"] == "duplicate" for x in r.json())


async def test_upload_too_large_413():
    store, pipe, aps = make_env()
    async with httpx.AsyncClient() as http:
        sched = IngestScheduler(store, pipe, http, scheduler=aps)
        app = create_app(
            store, pipe, sched, FakeEmbedder(), Settings(max_upload_bytes=10)
        )
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await upload(client)
    aps.shutdown(wait=False)
    assert r.status_code == 413
    assert await store.list_sources() == []


async def test_upload_unsupported_415(env):
    client, store, _ = env
    assert (await upload(client, name="a.exe")).status_code == 415
    assert await store.list_sources() == []


async def test_upload_corrupt_pdf_422(env):
    client, store, _ = env
    assert (await upload(client, name="a.pdf", data=b"not a pdf")).status_code == 422
    assert await store.list_sources() == []


async def test_upload_unknown_bubble_422(env):
    client, store, _ = env
    r = await upload(client, bubble_ids="news, nope")
    assert r.status_code == 422
    assert await store.list_sources() == []


async def test_upload_bad_credibility_422(env):
    client, _, _ = env
    assert (await upload(client, credibility="2")).status_code == 422


async def test_upload_via_intake_queues_parts_with_shared_original(tmp_path):
    from omnistream.ingest.intake import Intake

    repo, pipe, aps = make_env()
    intake = Intake(repo, str(tmp_path))
    text = ("# One\n\n" + "alpha " * 700 + "\n\n# Two\n\n" + "beta " * 700).encode()
    async with httpx.AsyncClient() as http:
        sched = IngestScheduler(repo, pipe, http, scheduler=aps, intake=intake)
        app = create_app(repo, pipe, sched, FakeEmbedder(), intake=intake)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r1 = await upload(client, name="doc.md", data=text)
            r2 = await upload(client, name="doc.md", data=text)
    aps.shutdown(wait=False)
    assert [x["status"] for x in r1.json()] == ["queued", "queued"]
    assert [x["status"] for x in r2.json()] == ["duplicate", "duplicate"]
    a, b = await repo.list_items(status="queued")
    assert a.raw_path == b.raw_path and a.text_path != b.text_path
    assert Path(a.raw_path).read_bytes() == text
    assert len(await repo.list_jobs()) == 2
