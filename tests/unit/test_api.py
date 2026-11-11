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
from omnistream.ingest.intake import Intake
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.models import Bubble
from omnistream.router.bubbles import BubbleLifecycle, BubbleService
from omnistream.router.router import BubbleChoice, Router
from tests.conftest import FakeChunks, FakeEmbedder, FakeLifecycleOps, FakeLLM

NOW = datetime(2026, 1, 1, tzinfo=UTC)
NEWS_XML = (
    Path(__file__).parent.parent / "fixtures" / "feeds" / "news.xml"
).read_bytes()
FEED = "https://a.test/feed.xml"
DOC_TEXT = b"Alice became CEO of Acme Corp this week."


def make_env(tmp_path, settings: Settings | None = None):
    repo = Repository()
    fake = FakeLLM({BubbleChoice: BubbleChoice(bubble_ids=["news"], confidence=0.9)})
    ops, chunks = FakeLifecycleOps(), FakeChunks()
    router = Router(fake, "m", FakeEmbedder())
    lifecycle = BubbleLifecycle(repo, FakeEmbedder(), router, ops, chunks)
    intake = Intake(repo, str(tmp_path), prefilter_min_chars=0)
    aps = AsyncIOScheduler()
    aps.start(paused=True)
    return repo, lifecycle, intake, aps, ops, chunks


@pytest.fixture
async def env(tmp_path):
    store, lifecycle, intake, aps, ops, chunks = make_env(tmp_path)
    await BubbleService(store, FakeEmbedder()).create(
        Bubble(id="news", name="News", description="news topics", updated_at=NOW)
    )
    async with httpx.AsyncClient() as http:
        sched = IngestScheduler(store, http, intake, scheduler=aps)
        app = create_app(store, sched, lifecycle, intake)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            client.ops, client.chunks = ops, chunks
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
    assert all(x["status"] == "queued" for x in r.json())


async def upload(client, name="a.txt", data=DOC_TEXT, **form):
    return await client.post(
        "/documents", files={"file": (name, data, "text/plain")}, data=form
    )


async def test_upload_document_200(env):
    client, store, _ = env
    r = await upload(client, bubble_ids="news", credibility="0.9")
    assert r.status_code == 200
    assert [x["status"] for x in r.json()] == ["queued"]
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


async def test_upload_too_large_413(tmp_path):
    store, lifecycle, intake, aps, _, _ = make_env(tmp_path)
    async with httpx.AsyncClient() as http:
        sched = IngestScheduler(store, http, intake, scheduler=aps)
        app = create_app(store, sched, lifecycle, intake, Settings(max_upload_bytes=10))
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


async def test_upload_queues_parts_with_shared_original(tmp_path):
    repo, lifecycle, intake, aps, _, _ = make_env(tmp_path)
    text = ("# One\n\n" + "alpha " * 700 + "\n\n# Two\n\n" + "beta " * 700).encode()
    async with httpx.AsyncClient() as http:
        sched = IngestScheduler(repo, http, intake, scheduler=aps)
        app = create_app(repo, sched, lifecycle, intake)
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


async def test_upload_with_bubbles_sets_item_override(env):
    client, store, _ = env
    await upload(client, bubble_ids="news")
    (item,) = await store.list_items()
    assert item.bubble_ids == ["news"]


async def test_get_bubble_returns_counts(env):
    client, _store, _ = env
    await client.post(
        "/sources", json={"type": "rss", "url": FEED, "bubble_ids": ["news"]}
    )
    r = await client.get("/bubbles/news")
    assert r.status_code == 200
    assert r.json()["counts"] == {
        "episodes": 2,
        "entities": 3,
        "facts": 4,
        "chunks": 5,
        "sources": 1,
    }
    assert "description_embedding" not in r.json()
    assert (await client.get("/bubbles/nope")).status_code == 404


async def test_create_bubble_with_half_life(env):
    client, _store, _ = env
    r = await client.post(
        "/bubbles", json={"name": "Sci", "description": "d", "half_life_days": 365}
    )
    assert r.status_code == 201 and r.json()["half_life_days"] == 365


async def test_delete_bubble_cascades_and_disables_sole_sources(env):
    client, store, _aps = env
    await BubbleService(store, FakeEmbedder()).create(
        Bubble(id="fin", name="Fin", description="money", updated_at=NOW)
    )
    solo = (
        await client.post(
            "/sources", json={"type": "rss", "url": FEED, "bubble_ids": ["news"]}
        )
    ).json()["id"]
    shared = (
        await client.post(
            "/sources",
            json={"type": "rss", "url": FEED + "2", "bubble_ids": ["news", "fin"]},
        )
    ).json()["id"]
    await store.mark_seen("h", solo, "u")
    r = await client.delete("/bubbles/news")
    assert r.status_code == 204
    assert client.ops.deleted == ["news"] and client.chunks.dropped == ["news"]
    assert await store.get_bubble("news") is None
    s_solo, s_shared = await store.get_source(solo), await store.get_source(shared)
    assert not s_solo.enabled and s_solo.bubble_ids == []
    assert s_shared.enabled and s_shared.bubble_ids == ["fin"]
    assert await store.has_seen("h")
    assert (await client.delete("/bubbles/news")).status_code == 404


async def test_patch_source_disables_and_unschedules(env):
    client, _store, aps = env
    sid = (await client.post("/sources", json={"type": "rss", "url": FEED})).json()[
        "id"
    ]
    assert aps.get_job(f"poll:{sid}") is not None
    r = await client.patch(f"/sources/{sid}", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert aps.get_job(f"poll:{sid}") is None
    assert (
        await client.patch("/sources/nope", json={"enabled": True})
    ).status_code == 404


async def test_sources_mask_header_values(env):
    client, store, _ = env
    body = {
        "type": "api",
        "url": FEED,
        "api_mapping": {
            "items": "$[*]",
            "body": "$.b",
            "url": "$.u",
            "headers": {"X-Api-Key": "secret"},
        },
    }
    created = await client.post("/sources", json=body)
    assert created.json()["api_mapping"]["headers"] == {"X-Api-Key": "***"}
    listed = (await client.get("/sources")).json()
    assert listed[0]["api_mapping"]["headers"] == {"X-Api-Key": "***"}
    (stored,) = await store.list_sources()
    assert stored.api_mapping.headers == {"X-Api-Key": "secret"}


async def test_items_assign_and_text(env):
    client, store, _ = env
    await upload(client)
    (item,) = await store.list_items()
    await store.update_item(item.id, status="unsorted", bubble_ids=[])
    r = await client.get("/items", params={"status": "unsorted"})
    assert [i["id"] for i in r.json()] == [item.id]
    assert "Alice" in (await client.get(f"/items/{item.id}/text")).text
    bad = await client.post(f"/items/{item.id}/assign", json={"bubble_ids": ["zz"]})
    assert bad.status_code == 422
    ok = await client.post(f"/items/{item.id}/assign", json={"bubble_ids": ["news"]})
    assert ok.status_code == 200 and ok.json()["status"] == "queued"
    again = await client.post(f"/items/{item.id}/assign", json={"bubble_ids": ["news"]})
    assert again.status_code == 409
    assert (await client.get("/items/nope/text")).status_code == 404
