"""The React app's endpoint contract, checked against the real FastAPI app (spec 12, 8, 9)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import respx

from tests.unit.test_ui_api import KEY, running_app
from tests.unit.ui_support import FakeRuntime

FEED = "https://a.test/feed.xml"


def _feed(*entries: tuple[str, datetime]) -> bytes:
    items = "".join(
        f"<item><title>{title}</title><link>https://a.test/{i}</link>"
        f"<description>Body text for {title} with some words.</description>"
        f"<pubDate>{format_datetime(when)}</pubDate></item>"
        for i, (title, when) in enumerate(entries)
    )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>'
        f"{items}</channel></rss>"
    ).encode()


# ----------------------------------------------------------- /api aliases


def test_api_bubbles_lists_the_seeded_bubbles(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        response = client.get("/api/bubbles")
        assert response.status_code == 200
        assert {b["id"] for b in response.json()} == {"news", "finance"}


def test_api_documents_accepts_multipart_and_rejects_unknown_bubbles(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        ok = client.post(
            "/api/documents",
            files={"file": ("note.txt", b"Alice became CEO of Acme Corp.", "text/plain")},
            data={"bubble_ids": "news", "credibility": "0.9"},
        )
        assert ok.status_code == 200
        assert isinstance(ok.json(), list) and ok.json()

        bad = client.post(
            "/api/documents",
            files={"file": ("note.txt", b"text", "text/plain")},
            data={"bubble_ids": "nope"},
        )
        assert bad.status_code == 422


def test_api_documents_maps_unsupported_files_to_415(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        response = client.post(
            "/api/documents",
            files={"file": ("photo.png", b"\x89PNG", "image/png")},
            data={"bubble_ids": "news"},
        )
        assert response.status_code == 415


def test_provider_test_returns_ok_and_message(tmp_path):
    with running_app(tmp_path, env_key=KEY) as (client, _repo, _runtime):
        app_ui = client.app.state.ui

        async def probe(settings, key):
            assert key == KEY
            return False, "The provider rejected the API key."

        app_ui._probe = probe
        response = client.post("/api/settings/provider/test")
        assert response.status_code == 200
        assert response.json() == {"ok": False, "message": "The provider rejected the API key."}


def test_chat_detail_is_chat_and_messages_and_send_returns_run_id(tmp_path):
    with running_app(tmp_path, FakeRuntime(), env_key=KEY) as (client, _repo, _runtime):
        chat = client.post("/api/chats", json={"title": "Hi"}).json()
        sent = client.post(
            f"/api/chats/{chat['id']}/messages",
            json={"content": "Who leads Acme?", "mode": "normal", "bubble_ids": ["news"]},
        )
        assert sent.status_code == 202
        assert sent.json()["run_id"]

        detail = client.get(f"/api/chats/{chat['id']}").json()
        assert set(detail) == {"chat", "messages"}
        assert detail["chat"]["id"] == chat["id"]
        assert [m["role"] for m in detail["messages"]][:1] == ["user"]
        assert client.get("/api/chats/unknown").status_code == 404


# ------------------------------------------------------------- sources


def test_adding_an_existing_url_is_409_with_the_existing_source(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        first = client.post("/api/sources", json={"type": "rss", "url": FEED})
        assert first.status_code == 201
        again = client.post("/api/sources", json={"type": "rss", "url": FEED + "/"})
        assert again.status_code == 409
        assert again.json()["source_id"] == first.json()["id"]
        assert len(client.get("/api/sources").json()) == 1


def test_the_plain_sources_route_keeps_its_existing_behaviour(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        client.post("/sources", json={"type": "rss", "url": FEED})
        assert client.post("/sources", json={"type": "rss", "url": FEED}).status_code == 201


def test_backfill_days_is_accepted_stored_and_validated(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        created = client.post(
            "/api/sources", json={"type": "rss", "url": FEED, "backfill_days": 7}
        )
        assert created.status_code == 201
        assert created.json()["backfill_days"] == 7
        listed = client.get("/api/sources").json()
        assert listed[0]["backfill_days"] == 7
        zero = client.post(
            "/api/sources", json={"type": "rss", "url": "https://b.test/f.xml", "backfill_days": 0}
        )
        assert zero.status_code == 422


@respx.mock
def test_source_test_returns_first_items_and_stores_nothing(tmp_path):
    now = datetime.now(UTC)
    respx.get(FEED).respond(
        200, content=_feed(("Fresh one", now), ("Fresh two", now - timedelta(hours=1)))
    )
    with running_app(tmp_path) as (client, _repo, _runtime):
        response = client.post("/api/sources/test", json={"type": "rss", "url": FEED})
        assert response.status_code == 200
        items = response.json()["items"]
        assert [i["title"] for i in items] == ["Fresh one", "Fresh two"]
        assert all(i["url"].startswith("https://a.test/") for i in items)
        assert client.get("/api/sources").json() == []


@respx.mock
def test_source_test_applies_backfill_days(tmp_path):
    now = datetime.now(UTC)
    respx.get(FEED).respond(
        200, content=_feed(("Recent", now), ("Last year", now - timedelta(days=400)))
    )
    with running_app(tmp_path) as (client, _repo, _runtime):
        response = client.post(
            "/api/sources/test", json={"type": "rss", "url": FEED, "backfill_days": 30}
        )
        assert [i["title"] for i in response.json()["items"]] == ["Recent"]


@respx.mock
def test_source_test_failure_is_a_readable_422_and_stores_nothing(tmp_path):
    respx.get(FEED).respond(500)
    with running_app(tmp_path) as (client, _repo, _runtime):
        response = client.post("/api/sources/test", json={"type": "rss", "url": FEED})
        assert response.status_code == 422
        assert "HTTP 500" in response.json()["detail"]
        assert client.get("/api/sources").json() == []


def test_source_test_rejects_an_invalid_body(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        response = client.post("/api/sources/test", json={"type": "api", "url": FEED})
        assert response.status_code == 422  # api sources need a mapping


def test_apply_backfill_keeps_recent_and_undated_items_only():
    from omnistream.models import RawItem
    from omnistream.sources.rss import apply_backfill

    now = datetime(2026, 11, 18, tzinfo=UTC)
    items = [
        RawItem(source_id="s", url="u1", title="new", text="t", published_at=now - timedelta(days=2)),
        RawItem(source_id="s", url="u2", title="old", text="t", published_at=now - timedelta(days=90)),
        RawItem(source_id="s", url="u3", title="undated", text="t", published_at=None),
    ]
    assert [i.title for i in apply_backfill(items, 7, now)] == ["new", "undated"]
    assert apply_backfill(items, None, now) == items  # no setting, nothing dropped
