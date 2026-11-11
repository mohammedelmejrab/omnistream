from pathlib import Path

import httpx
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from httpx import ASGITransport

import omnistream.ui as ui_pkg
from omnistream.api.app import create_app
from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.ingest.intake import Intake
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.models import ApiMapping, Source
from omnistream.router.bubbles import BubbleLifecycle, BubbleService
from omnistream.router.router import BubbleChoice, Router
from tests.conftest import FakeChunks, FakeEmbedder, FakeLifecycleOps, FakeLLM
from tests.unit.test_api import NOW, Bubble

SECRET = "Bearer sekret-token-123"


@pytest.fixture
async def ui(tmp_path):
    repo = Repository()
    llm = FakeLLM({BubbleChoice: BubbleChoice(bubble_ids=["news"], confidence=0.9)})
    lifecycle = BubbleLifecycle(
        repo, FakeEmbedder(), Router(llm, "m", FakeEmbedder()),
        FakeLifecycleOps(), FakeChunks(),
    )  # fmt: skip
    intake = Intake(repo, str(tmp_path), prefilter_min_chars=0)
    aps = AsyncIOScheduler()
    aps.start(paused=True)
    await BubbleService(repo, FakeEmbedder()).create(
        Bubble(id="news", name="News", description="d", updated_at=NOW)
    )
    async with httpx.AsyncClient() as http:
        sched = IngestScheduler(repo, http, intake, scheduler=aps)
        app = create_app(repo, sched, lifecycle, intake)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, repo
    aps.shutdown(wait=False)


def test_htmx_vendored():
    f = Path(ui_pkg.__file__).parent / "static" / "htmx.min.js"
    assert f.exists() and f.stat().st_size > 10_000


async def test_htmx_served(ui):
    client, _ = ui
    r = await client.get("/ui/static/htmx.min.js")
    assert r.status_code == 200 and "htmx" in r.text


async def test_sources_page_renders_without_secrets(ui):
    client, repo = ui
    await repo.upsert_source(
        Source(
            id="a", type="api", url="https://x.test/api",
            api_mapping=ApiMapping(
                items="$.a[*]", body="$.b", url="$.u", headers={"Authorization": SECRET}
            ),
        )
    )  # fmt: skip
    r = await client.get("/ui/sources")
    assert r.status_code == 200
    assert "https://x.test/api" in r.text and "Poll now" in r.text
    assert "map_items" in r.text and "map_headers" in r.text
    assert SECRET not in r.text and "sekret" not in r.text


async def test_add_toggle_poll_source(ui):
    client, repo = ui
    r = await client.post(
        "/ui/sources",
        data={"type": "rss", "url": "https://a.test/f.xml", "bubble_ids": "news"},
    )
    assert r.status_code == 200 and "https://a.test/f.xml" in r.text
    (src,) = await repo.list_sources()
    assert src.bubble_ids == ["news"]
    r = await client.post(f"/ui/sources/{src.id}/toggle")
    assert not (await repo.get_source(src.id)).enabled
    assert "Enable" in r.text


async def test_add_api_source_with_headers_hidden(ui):
    client, repo = ui
    r = await client.post(
        "/ui/sources",
        data={
            "type": "api", "url": "https://x.test/api", "map_items": "$.a[*]",
            "map_body": "$.b", "map_url": "$.u",
            "map_headers": f"Authorization: {SECRET}",
        },
    )  # fmt: skip
    (src,) = await repo.list_sources()
    assert src.api_mapping.headers == {"Authorization": SECRET}
    assert SECRET not in r.text


async def test_add_invalid_source_shows_error(ui):
    client, repo = ui
    r = await client.post("/ui/sources", data={"type": "api", "url": "https://x.test"})
    assert "Invalid source" in r.text and await repo.list_sources() == []


async def test_unsorted_page_and_assign(ui, tmp_path):
    client, repo = ui
    text = tmp_path / "t.txt"
    text.write_text("Some body snippet about nothing in particular")
    await repo.create_item(
        ItemRow(id="i1", source_id="s", title="Odd item", status="unsorted",
                route_confidence=0.31, text_path=str(text))
    )  # fmt: skip
    r = await client.get("/ui/unsorted")
    assert r.status_code == 200
    assert "Odd item" in r.text and "Some body snippet" in r.text and "0.31" in r.text
    r = await client.post("/ui/items/i1/assign", data={"bubble_ids": "news"})
    assert r.status_code == 200 and "No unsorted items" in r.text
    row = await repo.get_item("i1")
    assert row.status == "queued" and row.bubble_ids == ["news"]


async def test_assign_requires_known_bubble(ui):
    client, repo = ui
    await repo.create_item(ItemRow(id="i2", source_id="s", status="unsorted"))
    r = await client.post("/ui/items/i2/assign", data={"bubble_ids": "nope"})
    assert "existing bubble" in r.text
    assert (await repo.get_item("i2")).status == "unsorted"
