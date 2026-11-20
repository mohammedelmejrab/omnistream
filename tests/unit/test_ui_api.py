"""HTTP contract for the React app's API (spec 12, 13, 14 API tests)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from omnistream.api import ui_api
from omnistream.api.app import create_app
from omnistream.api.c6 import Services
from omnistream.api.ui_api import MessageIn, UIServices, _event_stream
from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.db.tables import ChatRow, ItemRow, MessageRow, RunRow, RunStepRow
from omnistream.ingest.intake import Intake
from omnistream.models import Bubble
from omnistream.router.bubbles import BubbleLifecycle
from tests.conftest import FakeChunks, FakeEmbedder
from tests.unit.ui_support import (
    FakeChat,
    FakeDispatcher,
    FakeRetriever,
    FakeRouter,
    FakeRuntime,
    GraphOps,
    fake_scheduler,
)

KEY = "sk-live-secret-a7f2"


async def seed(repo: Repository) -> None:
    now = datetime.now(UTC)
    for bubble_id, name in (("news", "News"), ("finance", "Finance")):
        await repo.create_bubble(
            Bubble(id=bubble_id, name=name, description=f"{name} desk", updated_at=now)
        )
    await repo.create_item(
        ItemRow(id="i1", source_id="src", url="https://example.test/i1", title="Item one", status="written")
    )


def make_app(
    tmp_path: Path,
    runtime,
    *,
    env_key: str = "",
    web_dist: Path | None = None,
    bubbles: bool = True,
    factory=None,
):
    settings = Settings(_env_file=None, llm_api_key=env_key)
    repo = Repository.from_path(str(tmp_path / "omni.db"), settings=settings)
    if bubbles:
        asyncio.run(seed(repo))
    lifecycle = BubbleLifecycle(repo, FakeEmbedder(), SimpleNamespace(), GraphOps(), FakeChunks())
    app = create_app(
        repo,
        fake_scheduler(),
        lifecycle,
        Intake(repo, str(tmp_path), 0),
        settings,
        runtime_factory=factory or (lambda _settings, _repo: runtime),
        web_dist=web_dist or tmp_path / "no-dist",
    )
    return app, repo


@contextmanager
def running_app(tmp_path: Path, runtime=None, **kwargs) -> Iterator[tuple[TestClient, Repository, object]]:
    runtime = runtime or FakeRuntime()
    app, repo = make_app(tmp_path, runtime, **kwargs)
    with TestClient(app, base_url="http://localhost") as client:
        yield client, repo, runtime
    asyncio.run(repo.close())


def set_key(client: TestClient, key: str = KEY) -> None:
    response = client.put(
        "/api/settings/provider",
        json={"api_key": key, "base_url": "https://example.test/v1", "model": "test-model"},
    )
    assert response.status_code == 200, response.text


def new_chat(client: TestClient, title: str | None = None) -> str:
    response = client.post("/api/chats", json={"title": title} if title else None)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(client: TestClient, chat_id: str, content: str = "Who leads Acme?", mode: str = "normal", bubbles=("news",)):
    return client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": content, "mode": mode, "bubble_ids": list(bubbles)},
    )


def wait_for_run(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running" or time.monotonic() > deadline:
            return run
        time.sleep(0.02)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if line and not line.startswith(":")]
        if not lines:
            continue
        name = next(line[len("event: "):] for line in lines if line.startswith("event: "))
        data = next(json.loads(line[len("data: "):]) for line in lines if line.startswith("data: "))
        events.append((name, data))
    return events


# ------------------------------------------------------------------ chats


def test_chat_lifecycle_and_unknown_ids_are_404(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        chat_id = new_chat(client, "Energy")
        assert client.get("/api/chats").json()[0]["title"] == "Energy"

        renamed = client.patch(f"/api/chats/{chat_id}", json={"title": "EU energy"})
        assert renamed.status_code == 200 and renamed.json()["title"] == "EU energy"
        assert client.patch(f"/api/chats/{chat_id}", json={"title": "  "}).status_code == 422

        detail = client.get(f"/api/chats/{chat_id}").json()
        assert detail["messages"] == []
        for method, url in [
            ("GET", "/api/chats/unknown"),
            ("PATCH", "/api/chats/unknown"),
            ("DELETE", "/api/chats/unknown"),
            ("POST", "/api/chats/unknown/messages"),
        ]:
            kwargs = {"json": {"title": "x"}} if method == "PATCH" else {}
            if method == "POST":
                kwargs = {"json": {"content": "hi"}}
            assert client.request(method, url, **kwargs).status_code == 404, url

        assert client.delete(f"/api/chats/{chat_id}").status_code == 204
        assert client.get(f"/api/chats/{chat_id}").status_code == 404


def test_question_limit_and_blank_question_are_validated(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        set_key(client)
        chat_id = new_chat(client)
        assert send(client, chat_id, "x" * 20001).status_code == 422
        assert send(client, chat_id, "   ").status_code == 422
        accepted = send(client, chat_id, "x" * 20000)
        assert accepted.status_code == 202, accepted.text
        wait_for_run(client, accepted.json()["run_id"])


def test_sending_needs_a_key_and_known_bubbles(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        chat_id = new_chat(client)
        response = send(client, chat_id)
        assert response.status_code == 409
        assert "provider key" in response.json()["detail"]
        set_key(client)
        assert send(client, chat_id, bubbles=("missing",)).status_code == 422


def test_sending_without_any_bubble_says_so(tmp_path):
    with running_app(tmp_path, bubbles=False) as (client, _repo, _runtime):
        set_key(client)
        chat_id = new_chat(client)
        response = send(client, chat_id, bubbles=())
        assert response.status_code == 409
        assert "no bubbles" in response.json()["detail"]


# ------------------------------------------------------------ normal runs


def test_normal_run_persists_steps_and_replay_matches_the_live_stream(tmp_path):
    with running_app(tmp_path) as (client, _repo, runtime):
        set_key(client)
        chat_id = new_chat(client)
        sent = send(client, chat_id, "Who leads Acme?")
        assert sent.status_code == 202
        run_id = sent.json()["run_id"]
        run = wait_for_run(client, run_id)

        assert run["status"] == "ok"
        assert run["answer"].startswith("Alice leads Acme")
        assert run["question"] == "Who leads Acme?"
        assert runtime.dispatcher.calls == 1  # Normal: the own pipeline runs once

        steps = client.get(f"/api/runs/{run_id}/steps").json()
        assert [s["kind"] for s in steps] == ["route", "retrieve", "seed", "score", "answer"]
        assert all(s["status"] == "ok" for s in steps)
        assert steps[1]["parent_step_id"] == steps[0]["id"]
        assert steps[2]["parent_step_id"] == steps[1]["id"]  # seed under retrieve
        assert steps[3]["parent_step_id"] == steps[1]["id"]  # score under retrieve
        assert steps[4]["parent_step_id"] == steps[1]["id"]  # answer after retrieve
        assert steps[4]["summary"]["citation_count"] == 1
        assert steps[4]["citations"] == [
            {"number": 1, "item_id": "i1", "url": "https://example.test/i1", "title": "Item one"}
        ]

        with client.stream("GET", f"/api/runs/{run_id}/events") as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            events = parse_sse(response.read().decode())
        names = [name for name, _ in events]
        assert names[0] == "run" and names[-1] == "done"
        assert events[-1][1] == {"run_id": run_id, "status": "ok"}
        replayed = [data for name, data in events if name == "step"]
        assert replayed == steps  # replay from storage matches the stored steps exactly

        chat = client.get(f"/api/chats/{chat_id}").json()
        assert chat["chat"]["title"] == "Who leads Acme?"
        assistant = chat["messages"][1]
        assert assistant["role"] == "assistant" and assistant["run_id"] == run_id
        assert assistant["content"] == run["answer"]
        assert chat["messages"][0]["content"] == "Who leads Acme?"


def test_agentic_run_records_subagent_join_and_answer(tmp_path):
    with running_app(tmp_path) as (client, _repo, runtime):
        set_key(client)
        chat_id = new_chat(client)
        run_id = send(client, chat_id, mode="agentic", bubbles=("news", "finance")).json()["run_id"]
        run = wait_for_run(client, run_id)

        assert run["mode"] == "agentic" and run["status"] == "ok"
        steps = client.get(f"/api/runs/{run_id}/steps").json()
        subagents = [s for s in steps if s["kind"] == "subagent"]
        assert sorted(s["bubble"] for s in subagents) == ["finance", "news"]
        assert {s["kind"] for s in steps} >= {"route", "subagent", "retrieve", "join", "answer"}
        assert runtime.dispatcher.calls == 0  # subagents retrieve through their own tool loop
        chat = client.get(f"/api/chats/{chat_id}").json()
        assert chat["chat"]["mode"] == "agentic"
        assert chat["messages"][1]["mode"] == "agentic"


def test_failed_provider_call_is_a_failed_run_without_the_key(tmp_path):
    class ExplodingChat(FakeChat):
        def chat(self, messages, **kwargs):
            raise RuntimeError(f"401 unauthorized for key {KEY}")

    runtime = FakeRuntime(llm=ExplodingChat())
    with running_app(tmp_path, runtime) as (client, _repo, _runtime):
        set_key(client)
        chat_id = new_chat(client)
        run_id = send(client, chat_id).json()["run_id"]
        run = wait_for_run(client, run_id)

        assert run["status"] == "failed"
        assert "[redacted]" in run["error"]
        everything = json.dumps([run, client.get(f"/api/runs/{run_id}/steps").json(), client.get(f"/api/chats/{chat_id}").json()])
        assert KEY not in everything
        assert "This answer failed" in client.get(f"/api/chats/{chat_id}").json()["messages"][1]["content"]


def test_empty_answer_is_a_failed_run(tmp_path):
    runtime = FakeRuntime(llm=FakeChat(text="   "))
    with running_app(tmp_path, runtime) as (client, _repo, _runtime):
        set_key(client)
        chat_id = new_chat(client)
        run = wait_for_run(client, send(client, chat_id).json()["run_id"])
        assert run["status"] == "failed"
        assert run["error"] == "The model returned no answer."


def test_no_relevant_sources_is_recorded_on_the_retrieve_step(tmp_path):
    class EmptyRetriever(FakeRetriever):
        def retrieve(self, question, **kwargs):
            from omnistream.retrieval.models import RetrievalResult

            return RetrievalResult(mode="own")

    runtime = FakeRuntime(dispatcher=FakeDispatcher(EmptyRetriever()))
    with running_app(tmp_path, runtime) as (client, _repo, _runtime):
        set_key(client)
        chat_id = new_chat(client)
        run_id = send(client, chat_id).json()["run_id"]
        wait_for_run(client, run_id)
        retrieve = next(s for s in client.get(f"/api/runs/{run_id}/steps").json() if s["kind"] == "retrieve")
        assert retrieve["summary"]["no_relevant_sources"] is True


# ------------------------------------------------------- cancel and delete


def _blocked_runtime():
    gate, started = threading.Event(), threading.Event()
    runtime = FakeRuntime(
        router=FakeRouter(), dispatcher=FakeDispatcher(FakeRetriever(gate=gate, started=started))
    )
    return runtime, gate, started


def test_cancel_stops_the_run_and_keeps_the_finished_steps(tmp_path):
    runtime, gate, started = _blocked_runtime()
    with running_app(tmp_path, runtime) as (client, _repo, _runtime):
        set_key(client)
        chat_id = new_chat(client)
        run_id = send(client, chat_id).json()["run_id"]
        assert started.wait(5)

        response = client.post(f"/api/runs/{run_id}/cancel")
        gate.set()
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

        steps = client.get(f"/api/runs/{run_id}/steps").json()
        assert [(s["kind"], s["status"]) for s in steps] == [("route", "ok"), ("retrieve", "cancelled")]
        assistant = client.get(f"/api/chats/{chat_id}").json()["messages"][1]
        assert assistant["content"] == "Stopped"
        assert client.post("/api/runs/unknown/cancel").status_code == 404


def test_deleting_a_chat_during_a_live_run_cancels_it_and_keeps_the_trace(tmp_path):
    runtime, gate, started = _blocked_runtime()
    with running_app(tmp_path, runtime) as (client, _repo, _runtime):
        set_key(client)
        chat_id = new_chat(client)
        run_id = send(client, chat_id).json()["run_id"]
        assert started.wait(5)

        assert client.delete(f"/api/chats/{chat_id}").status_code == 204
        gate.set()

        assert client.get(f"/api/chats/{chat_id}").status_code == 404
        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "cancelled" and run["chat_id"] == chat_id
        kinds = [(s["kind"], s["status"]) for s in client.get(f"/api/runs/{run_id}/steps").json()]
        assert kinds == [("route", "ok"), ("retrieve", "cancelled")]


async def test_live_stream_announces_running_then_finished_steps_in_order(tmp_path):
    gate, started = threading.Event(), threading.Event()
    runtime = FakeRuntime(dispatcher=FakeDispatcher(FakeRetriever(gate=gate, started=started)))
    settings = Settings(_env_file=None, llm_api_key=KEY)
    repo = Repository.from_path(str(tmp_path / "live.db"), settings=settings)
    await seed(repo)
    lifecycle = BubbleLifecycle(repo, FakeEmbedder(), SimpleNamespace(), GraphOps(), FakeChunks())
    scheduler = fake_scheduler()
    services = Services(repo, lifecycle, scheduler, settings, lambda _s, _r: runtime)
    await services.load()
    ui = UIServices(repo, services, scheduler, web_dist=tmp_path)
    await ui.startup()
    try:
        await repo.create_chat(ChatRow(id="c1", title="New chat"))
        sent = await ui.send_message("c1", MessageIn(content="Who?", mode="normal", bubble_ids=["news"]))

        stream = _event_stream(ui, sent.run_id)
        seen: list[tuple[str, str, str]] = []  # (event, kind, status)
        while True:
            chunk = await asyncio.wait_for(stream.__anext__(), 5)
            name, data = parse_sse(chunk)[0]
            if name == "step":
                seen.append((name, data["kind"], data["status"]))
                if data["kind"] == "retrieve" and data["status"] == "running":
                    gate.set()  # release the blocked retrieval only once the client saw it running
            else:
                seen.append((name, "", data.get("status", "")))
            if name == "done":
                break
        await stream.aclose()

        assert seen[0][0] == "run"
        assert seen[-1] == ("done", "", "ok")
        position = {item: index for index, item in enumerate(seen)}
        assert position[("step", "retrieve", "running")] < position[("step", "retrieve", "ok")]
        assert position[("step", "route", "ok")] < position[("step", "retrieve", "running")]
        assert position[("step", "retrieve", "ok")] < position[("step", "answer", "ok")]
        assert position[("run", "", "ok")] < position[("done", "", "ok")]
        stored = await ui.step_snapshot(sent.run_id)
        assert [(s["kind"], s["status"]) for s in stored] == [
            ("route", "ok"), ("retrieve", "ok"), ("seed", "ok"), ("score", "ok"), ("answer", "ok"),
        ]
    finally:
        await ui.shutdown()
        await repo.close()


# ------------------------------------------------------- startup and retention


def test_changing_the_provider_mid_run_keeps_the_old_runtime_until_that_run_ends(tmp_path):
    gate, started = threading.Event(), threading.Event()
    placeholder = FakeRuntime()  # built at startup; replaced when the key is saved
    first = FakeRuntime(dispatcher=FakeDispatcher(FakeRetriever(gate=gate, started=started)))
    second = FakeRuntime()
    built = iter([placeholder, first, second])
    with running_app(tmp_path, placeholder, factory=lambda _s, _r: next(built)) as (client, _repo, _runtime):
        set_key(client)
        chat_id = new_chat(client)
        run_id = send(client, chat_id).json()["run_id"]
        assert started.wait(5)

        changed = client.put(
            "/api/settings/provider",
            json={"base_url": "https://example.test/v2", "model": "other-model"},
        )
        assert changed.status_code == 200
        assert first.closed is False  # the in-flight run still uses it

        gate.set()
        assert wait_for_run(client, run_id)["status"] == "ok"
        deadline = time.monotonic() + 5
        while not first.closed and time.monotonic() < deadline:
            time.sleep(0.02)
        assert first.closed is True

        second_run = wait_for_run(client, send(client, chat_id, "Again?").json()["run_id"])
        assert second_run["status"] == "ok"
        assert second.dispatcher.calls == 1  # the next message uses the new runtime


def test_a_run_left_running_is_interrupted_on_startup(tmp_path):
    app, repo = make_app(tmp_path, FakeRuntime())

    async def leftovers():
        now = datetime.now(UTC)
        await repo.create_chat(ChatRow(id="c", title="Old", created_at=now, updated_at=now))
        await repo.create_run(RunRow(id="stale", chat_id="c", mode="normal", started_at=now))
        await repo.add_message(MessageRow(id="a", chat_id="c", role="assistant", content="", run_id="stale"))
        repo.save_step(RunStepRow(id="s1", run_id="stale", seq=1, kind="route", status="ok", started_at=now))

    asyncio.run(leftovers())
    with TestClient(app, base_url="http://localhost") as client:
        run = client.get("/api/runs/stale").json()
        assert run["status"] == "interrupted"
        assert run["error"] == "Interrupted when OmniStream restarted"
        assert client.get("/api/chats/c").json()["messages"][0]["content"] == "Interrupted when OmniStream restarted"
        assert [s["kind"] for s in client.get("/api/runs/stale/steps").json()] == ["route"]
    asyncio.run(repo.close())


def test_traces_older_than_thirty_days_are_purged_on_startup_and_answer_410(tmp_path):
    app, repo = make_app(tmp_path, FakeRuntime())
    old = datetime.now(UTC) - timedelta(days=31)

    async def leftovers():
        await repo.create_chat(ChatRow(id="c", title="Old"))
        await repo.create_run(RunRow(id="ancient", chat_id="c", mode="normal", status="ok", started_at=old))
        await repo.add_message(MessageRow(id="a", chat_id="c", role="assistant", content="kept", run_id="ancient"))
        repo.save_step(RunStepRow(id="s-old", run_id="ancient", seq=1, kind="route", started_at=old, status="ok"))

    asyncio.run(leftovers())
    with TestClient(app, base_url="http://localhost") as client:
        assert asyncio.run(repo.list_steps("ancient")) == []  # purged at startup
        for url in ("/api/runs/ancient", "/api/runs/ancient/steps", "/api/runs/ancient/events"):
            response = client.get(url)
            assert response.status_code == 410, url
            assert response.json()["detail"] == "Trace no longer available"
        assert client.get("/api/chats/c").json()["messages"][0]["content"] == "kept"
    asyncio.run(repo.close())


def test_unknown_run_is_404_everywhere(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        assert client.get("/api/runs/nope").status_code == 404
        assert client.get("/api/runs/nope/steps").status_code == 404
        assert client.get("/api/runs/nope/events").status_code == 404


# ------------------------------------------------------------- provider


def test_provider_key_is_write_only_and_the_saved_key_wins_over_the_environment(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        initial = client.get("/api/settings/provider").json()
        assert initial == {"key_set": False, "key_hint": None, "key_source": None,
                           "base_url": initial["base_url"], "model": initial["model"]}

        saved = client.put(
            "/api/settings/provider",
            json={"api_key": KEY, "base_url": "https://example.test/v1", "model": "test-model"},
        )
        assert saved.json() == {"key_set": True, "key_hint": "a7f2", "key_source": "ui",
                                "base_url": "https://example.test/v1", "model": "test-model"}
        responses = [saved.text, client.get("/api/settings/provider").text]
        assert all(KEY not in text and "live-secret" not in text for text in responses)

        keep = client.put(
            "/api/settings/provider",
            json={"base_url": "https://example.test/v2", "model": "other"},
        )
        assert keep.json()["key_hint"] == "a7f2"  # omitting the key keeps it

        cleared = client.delete("/api/settings/provider/key")
        assert cleared.json()["key_set"] is False
        assert KEY not in cleared.text


def test_environment_key_is_the_fallback_and_is_never_shown(tmp_path):
    env_key = "env-key-z9y8"
    with running_app(tmp_path, env_key=env_key) as (client, _repo, _runtime):
        body = client.get("/api/settings/provider").json()
        assert body["key_set"] is True and body["key_source"] == "env" and body["key_hint"] is None
        assert env_key not in client.get("/api/settings/provider").text

        set_key(client)
        assert client.get("/api/settings/provider").json()["key_source"] == "ui"
        after_clear = client.delete("/api/settings/provider/key").json()
        assert after_clear["key_source"] == "env"
        assert env_key not in json.dumps(after_clear)


def test_saved_key_survives_a_restart_and_reaches_the_runtime(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        set_key(client)
    app, repo = make_app(tmp_path, FakeRuntime(), bubbles=False)
    with TestClient(app, base_url="http://localhost") as client:
        body = client.get("/api/settings/provider").json()
        assert body["key_set"] is True and body["key_source"] == "ui" and body["key_hint"] == "a7f2"
        assert body["base_url"] == "https://example.test/v1"
        assert KEY not in client.get("/api/settings/provider").text
    asyncio.run(repo.close())


def test_test_connection_reports_success_and_failure_without_secrets(tmp_path, monkeypatch):
    calls = []

    async def probe(settings, key):
        calls.append((settings.llm_base_url, settings.llm_model, key))
        if key.endswith("bad"):
            return False, "The provider rejected the API key."
        return True, "Connected. The model replied."

    monkeypatch.setattr(ui_api, "_probe_provider", probe)
    with running_app(tmp_path) as (client, _repo, _runtime):
        assert client.post("/api/settings/provider/test").json() == {
            "ok": False, "message": "No API key is configured.",
        }
        set_key(client)
        ok = client.post("/api/settings/provider/test")
        assert ok.json()["ok"] is True
        assert calls[-1] == ("https://example.test/v1", "test-model", KEY)
        assert KEY not in ok.text

        set_key(client, "sk-other-key-bad")
        failed = client.post("/api/settings/provider/test")
        assert failed.json() == {"ok": False, "message": "The provider rejected the API key."}
        assert "sk-other" not in failed.text


def test_provider_validation_rejects_bad_urls_and_blank_keys(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        base = {"base_url": "https://example.test/v1", "model": "m"}
        assert client.put("/api/settings/provider", json={**base, "base_url": "ftp://x"}).status_code == 422
        assert client.put("/api/settings/provider", json={**base, "model": " "}).status_code == 422
        assert client.put("/api/settings/provider", json={**base, "api_key": ""}).status_code == 422


# ----------------------------------------------------------------- graph


def test_graph_endpoint_filters_by_bubble_and_pages(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        news = client.get("/api/graph", params={"bubble": "news"}).json()
        assert news["total"] == 2
        assert {n["bubble"] for n in news["nodes"]} == {"news"}
        assert news["edges"] == [
            {"id": "news-r1", "source": "news-alice", "target": "news-acme", "label": "LEADS"}
        ]

        everything = client.get("/api/graph").json()
        assert everything["total"] == 4

        page = client.get("/api/graph", params={"limit": 1, "offset": 1}).json()
        assert len(page["nodes"]) == 1 and page["total"] == 4
        assert page["edges"] == []  # edges only join nodes on the same page

        assert client.get("/api/graph", params={"bubble": "nope"}).status_code == 404
        assert client.get("/api/graph", params={"limit": 0}).status_code == 422


# ------------------------------------------------------------- sources


def test_sources_are_reachable_under_api_and_can_be_deleted(tmp_path):
    with running_app(tmp_path) as (client, _repo, _runtime):
        assert client.get("/api/sources").json() == []
        created = client.post(
            "/api/sources",
            json={"type": "rss", "url": "https://example.test/feed.xml", "bubble_ids": ["news"]},
        )
        assert created.status_code == 201
        source_id = created.json()["id"]
        patched = client.patch(f"/api/sources/{source_id}", json={"enabled": False})
        assert patched.status_code == 200 and patched.json()["enabled"] is False
        assert client.delete(f"/api/sources/{source_id}").status_code == 204
        assert client.get("/api/sources").json() == []
        assert client.delete(f"/api/sources/{source_id}").status_code == 404


# ------------------------------------------------------------- /app


def test_web_app_is_served_with_spa_fallback_and_no_path_escape(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the build", encoding="utf-8")
    with running_app(tmp_path, web_dist=dist) as (client, _repo, _runtime):
        assert "id=root" in client.get("/app").text
        assert "id=root" in client.get("/app/chat/abc123").text  # client-side route
        assert client.get("/app/assets/app.js").text == "console.log(1)"
        assert client.get("/app/assets/missing.js").status_code == 404
        assert client.get("/app/..%2Fsecret.txt").status_code == 404
        assert "outside the build" not in client.get("/app/..%2Fsecret.txt").text


def test_web_app_explains_when_the_build_is_missing(tmp_path):
    with running_app(tmp_path, web_dist=tmp_path / "absent") as (client, _repo, _runtime):
        response = client.get("/app")
        assert response.status_code == 503
        assert "npm run build" in response.text


async def test_a_run_cancelled_before_it_starts_is_still_finalised(tmp_path):
    settings = Settings(_env_file=None, llm_api_key=KEY)
    repo = Repository.from_path(str(tmp_path / "early.db"), settings=settings)
    await seed(repo)
    runtime = FakeRuntime()
    lifecycle = BubbleLifecycle(repo, FakeEmbedder(), SimpleNamespace(), GraphOps(), FakeChunks())
    scheduler = fake_scheduler()
    services = Services(repo, lifecycle, scheduler, settings, lambda _s, _r: runtime)
    await services.load()
    ui = UIServices(repo, services, scheduler, web_dist=tmp_path)
    await ui.startup()
    try:
        await repo.create_chat(ChatRow(id="c1", title="New chat"))
        sent = await ui.send_message("c1", MessageIn(content="Who?", mode="normal", bubble_ids=["news"]))
        ui.active[sent.run_id].task.cancel()  # no await in between: the task has not started yet
        await asyncio.sleep(0.05)

        run = await repo.get_run(sent.run_id)
        assert run.status == "cancelled"
        assert run.finished_at is not None
        assert sent.run_id not in ui.active
        messages = await repo.list_messages("c1")
        assert messages[-1].content == "Stopped"
    finally:
        await ui.shutdown()
        await repo.close()
