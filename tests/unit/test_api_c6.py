"""C6 HTTP and template contract tests with isolated SQLite and fake services."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from omnistream.api.app import create_app
from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.db.tables import ItemRow
from omnistream.ingest.intake import Intake
from omnistream.models import Bubble, Source
from omnistream.retrieval.citations import Citation
from omnistream.router.bubbles import BubbleLifecycle
from tests.conftest import FakeChunks, FakeEmbedder, FakeLifecycleOps


class Ops(FakeLifecycleOps):
    async def bubble_graph(self, group):
        return {"nodes": [{"id": "alice", "label": "Alice", "value": 3}], "edges": []}

    async def bubble_map(self):
        return [
            {
                "from": "news",
                "to": "finance",
                "value": 1,
                "entities": [{"id": "g", "name": "Alice"}],
            }
        ]

    async def recent_episodes(self, group):
        return [
            {"id": "ep", "name": "Bulletin", "item_id": "i", "created_at": "2026-01-01"}
        ]


class Runtime:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def answer(self, question, **kwargs):
        self.calls.append((question, kwargs))
        return {
            "answer": {
                "text": "Alice leads Acme [1]. Uncertain [2].",
                "citations": [
                    Citation(1, "i", None, "Alice leads Acme", ((0, 5),)),
                    Citation(2, "i", None, "Unlocated"),
                ],
            },
            "routing": {"bubbles": ["news"], "rationale": "Pinned relevant evidence"},
            "mode": kwargs["mode"],
            "retrieval": {
                "seeds": [{"id": "alice", "name": "Alice", "bubble": "news"}],
                "facts": [
                    {
                        "fact": {
                            "id": "f",
                            "subject_id": "alice",
                            "object_id": "acme",
                            "relation": "LEADS",
                            "bubble": "news",
                            "text": "Alice leads Acme",
                        },
                        "path": ["alice", "global", "acme"],
                    }
                ],
            },
            "conflicts": [
                {
                    "relation": "LEADS",
                    "preferred_fact_id": "f",
                    "facts": [
                        {
                            "fact": {
                                "id": "f",
                                "text": "Alice leads Acme",
                                "credibility": 0.9,
                                "published_at": "2026-01-01",
                            }
                        },
                        {
                            "fact": {
                                "id": "old",
                                "text": "Bob leads Acme",
                                "credibility": 0.5,
                                "published_at": "2025-01-01",
                            }
                        },
                    ],
                }
            ],
        }

    async def close(self):
        self.closed = True


@pytest.fixture
def c6(tmp_path):
    settings = Settings(
        _env_file=None, data_dir=str(tmp_path), llm_api_key="never-store-me"
    )
    repo = Repository.from_path(str(tmp_path / "app.db"), settings=settings)
    runtime, built = Runtime(), []

    def factory(settings, repository):
        built.append(settings)
        return runtime

    scheduler = SimpleNamespace(
        schedule_source=lambda s: None,
        unschedule_source=lambda s: None,
        poll_source=AsyncMock(return_value=[]),
    )
    ops, chunks = Ops(), FakeChunks()
    lifecycle = BubbleLifecycle(repo, FakeEmbedder(), SimpleNamespace(), ops, chunks)

    async def seed():
        await repo.create_bubble(
            Bubble(
                id="news",
                name="News",
                description="Current events",
                updated_at=datetime.now(UTC),
            )
        )
        await repo.create_bubble(
            Bubble(
                id="finance",
                name="Finance",
                description="Markets",
                updated_at=datetime.now(UTC),
            )
        )
        text = tmp_path / "original.txt"
        text.write_text("Alice leads Acme. <script>alert(1)</script>", encoding="utf-8")
        await repo.create_item(
            ItemRow(id="i", source_id="source", text_path=str(text), status="unsorted")
        )

    asyncio.run(seed())

    async def evaluator(settings, repository, *, rows, snapshot):
        run = await repository.create_eval_run(snapshot=snapshot, rows=rows or ["own"])
        path = tmp_path / "result.csv"
        path.write_text("configuration,score\nown,1\n")
        await repository.update_eval_run(
            run.id,
            status="completed",
            metrics={"own": {"score": 1}},
            results=[{"question": "Who?", "score": 1}],
            csv_path=str(path),
        )

    app = create_app(
        repo,
        scheduler,
        lifecycle,
        Intake(repo, str(tmp_path), 0),
        settings,
        runtime_factory=factory,
        evaluator=evaluator,
    )
    with TestClient(app, base_url="http://localhost") as client:
        yield client, repo, runtime, built, lifecycle
    assert runtime.closed
    assert len(built) == 1
    asyncio.run(repo.close())


@pytest.mark.parametrize(
    "url",
    [
        "/ui/ask",
        "/ui/bubbles",
        "/ui/bubbles/news",
        "/ui/settings",
        "/ui/eval",
        "/ui/sources",
        "/ui/unsorted",
    ],
)
def test_ui_c6_pages(c6, url):
    client, *_ = c6
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert "OmniStream" in response.text
    assert "never-store-me" not in response.text


def test_api_query_options_and_verified_json(c6):
    client, _repo, runtime, *_ = c6
    response = client.post(
        "/query",
        json={
            "question": "Who?",
            "mode": "classic",
            "subagents": False,
            "pin": ["news"],
            "exclude": ["finance"],
        },
    )
    assert response.status_code == 200
    citations = response.json()["answer"]["citations"]
    assert [c["verified"] for c in citations] == [True, False]
    assert runtime.calls[-1][1] == {
        "mode": "classic",
        "subagents": False,
        "pin": ["news"],
        "exclude": ["finance"],
    }
    assert client.post("/query", json={"question": " "}).status_code == 422
    assert (
        client.post("/query", json={"question": "Who?", "pin": ["missing"]}).status_code
        == 422
    )
    assert (
        client.post(
            "/query", json={"question": "Who?", "pin": ["news"], "exclude": ["news"]}
        ).status_code
        == 422
    )


def test_ui_answer_citations_conflicts_and_graph(c6):
    client, *_ = c6
    response = client.post(
        "/ui/ask", data={"question": "Who?", "pin": "news", "mode": "own"}
    )
    assert response.status_code == 200
    for expected in [
        "Unverified",
        "span=0%3A5",
        "Preferred assertion",
        "Bob leads Acme",
        "Pinned relevant evidence",
        "answer-graph",
        "hop / cross-bubble",
    ]:
        assert expected in response.text


def test_api_original_and_safe_highlighting(c6):
    client, *_ = c6
    assert client.get("/items/i/text").text.startswith("Alice leads")
    for url in ["/items/i/text?span=0:5", "/ui/items/i/text?span=0:5"]:
        response = client.get(url)
        assert response.status_code == 200
        assert "<mark>Alice</mark>" in response.text
        assert "&lt;script&gt;" in response.text
        assert "<script>" not in response.text
    assert client.get("/items/missing/text").status_code == 404
    assert client.get("/ui/items/i/text?span=-1:99").status_code == 422
    assert client.get("/ui/items/i/text?span=oops").status_code == 422


def test_api_graphs_counts(c6):
    client, *_ = c6
    assert (
        client.get("/bubbles/map").json()["edges"][0]["entities"][0]["name"] == "Alice"
    )
    assert client.get("/bubbles/news/graph").json()["nodes"][0]["value"] == 3
    assert client.get("/bubbles/missing/graph").status_code == 404
    assert client.get("/bubbles/news/counts").status_code == 200
    assert client.get("/bubbles/missing/counts").status_code == 404


def test_api_settings_persist_used_and_secret_rejected(c6):
    client, repo, runtime, _built, lifecycle = c6
    values = client.get("/settings").json()
    assert "llm_api_key" not in values
    values.update(
        retrieval_mode="classic",
        llm_model="new-model",
        judge_model="judge",
        router_threshold=0.8,
        half_life_news_days=9,
    )
    assert client.put("/settings", json=values).status_code == 200
    assert client.post("/query", json={"question": "Who?"}).status_code == 200
    assert runtime.calls[-1][1]["mode"] == "classic"
    assert client.app.state.c6.provider_restart_required
    assert client.app.state.c6.settings.llm_model == "new-model"
    assert lifecycle._router._threshold == 0.8
    assert asyncio.run(repo.get_bubble("news")).half_life_days == 9
    persisted = asyncio.run(repo.all_settings())
    assert persisted == values
    assert "never-store-me" not in json.dumps(persisted)
    assert (
        client.put("/settings", json={**values, "llm_api_key": "bad"}).status_code
        == 422
    )
    assert client.post("/ui/settings", data=values).status_code == 200
    from omnistream.api.c6 import Services

    loaded = Services(repo, lifecycle, None, Settings(_env_file=None))
    asyncio.run(loaded.load())
    assert loaded.default_mode == "classic"
    assert loaded.settings.llm_model == "new-model"


def test_api_connection_capabilities(c6, monkeypatch):
    client, *_ = c6
    fake = SimpleNamespace(
        connection_test=AsyncMock(
            return_value={"json_mode": True, "function_calling": False}
        ),
        _client=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr("omnistream.llm.build_llm_client", lambda settings: fake)
    assert client.post("/settings/test", json={}).json() == {
        "json_mode": True,
        "function_calling": False,
    }
    fake._client.close.assert_awaited_once()


def test_api_eval_background_results_csv(c6):
    client, *_ = c6
    assert (
        client.post(
            "/eval/runs", json={"snapshot": "frozen", "rows": ["own"]}
        ).status_code
        == 202
    )

    # Wait for the actual background task, rather than assuming request timing.
    async def settle():
        await asyncio.gather(*client.app.state.c6.tasks)

    client.portal.call(settle)
    runs = client.get("/eval/runs").json()
    assert len(runs) == 1
    run_id = runs[0]["id"]
    assert client.get(f"/eval/runs/{run_id}").json()["status"] == "completed"
    assert "configuration,score" in client.get(f"/eval/runs/{run_id}/csv").text
    page = client.get("/ui/eval")
    assert (
        page.status_code == 200 and "Download CSV" in page.text and "Who?" in page.text
    )
    assert client.get("/eval/runs/999").status_code == 404
    assert client.get("/eval/runs/999/csv").status_code == 404
    assert client.post("/eval/runs", json={"snapshot": "../bad"}).status_code == 422


def test_api_delete_counts_lifecycle_preserves_originals_dedup(c6):
    client, repo, _runtime, _built, lifecycle = c6

    async def seed():
        await repo.upsert_source(
            Source(
                id="sole", type="rss", url="https://test.local/rss", bubble_ids=["news"]
            )
        )
        await repo.upsert_source(
            Source(
                id="shared",
                type="rss",
                url="https://test.local/rss",
                bubble_ids=["news", "finance"],
            )
        )
        await repo.mark_seen("hash", "sole")

    asyncio.run(seed())
    assert (
        client.delete(
            "/bubbles", params={"id": "news", "confirmed_counts": "{}"}
        ).status_code
        == 409
    )
    counts = client.get("/bubbles/news/counts").json()
    assert (
        client.delete(
            "/bubbles", params={"id": "news", "confirmed_counts": json.dumps(counts)}
        ).status_code
        == 204
    )
    assert asyncio.run(repo.get_bubble("news")) is None
    assert not asyncio.run(repo.get_source("sole")).enabled
    assert asyncio.run(repo.get_source("shared")).bubble_ids == ["finance"]
    assert asyncio.run(repo.has_seen("hash"))
    assert client.get("/items/i/text").status_code == 200
    assert lifecycle._ops.deleted == ["news"]


def test_api_remaining_ingestion_endpoints(c6):
    client, *_ = c6
    response = client.post(
        "/bubbles",
        json={"name": "Research", "description": "Science", "half_life_days": 365},
    )
    assert response.status_code == 201
    assert len(client.get("/bubbles").json()) == 3
    assert client.get("/bubbles/research").status_code == 200
    response = client.post(
        "/sources",
        json={"type": "rss", "url": "https://test.local/rss", "bubble_ids": ["news"]},
    )
    assert response.status_code == 201
    sid = response.json()["id"]
    assert len(client.get("/sources").json()) == 1
    assert client.patch(f"/sources/{sid}", json={"enabled": False}).status_code == 200
    assert client.post(f"/sources/{sid}/poll").status_code == 200
    assert len(client.get("/items?status=unsorted").json()) == 1
    assert (
        client.post("/items/i/assign", json={"bubble_ids": ["news"]}).status_code == 200
    )
    assert (
        client.post(
            "/documents",
            files={"file": ("notes.txt", b"Alice leads Acme. " * 20)},
            data={"bubble_ids": "news"},
        ).status_code
        == 200
    )


def test_partial_settings_validation_and_restart(c6):
    client, _, runtime, *_ = c6
    old = client.get("/settings").json()
    response = client.put("/settings", json={"router_threshold": 0.6})
    assert response.status_code == 200
    assert response.json() == {**old, "router_threshold": 0.6}
    assert client.put("/settings", json={"llm_model": "  "}).status_code == 422
    assert client.put("/settings", json={"llm_base_url": ""}).status_code == 422
    response = client.put("/settings", json={"llm_model": "new", "judge_model": ""})
    assert response.json()["judge_model"] == "new"
    assert "restart" in response.headers["x-settings-applies"]
    assert client.app.state.c6.provider_restart_required
    assert not hasattr(runtime, "llm")  # no partial provider swap
    assert "after restart" in client.get("/ui/settings").text


def test_mutations_require_same_origin_and_json(c6):
    client, *_ = c6
    for path in ["/ui/settings", "/ui/ask"]:
        assert (
            client.post(
                path, data={"llm_model": "bad"}, headers={"Origin": "https://evil.test"}
            ).status_code
            == 403
        )
    assert (
        client.put(
            "/settings",
            json={"router_threshold": 0.7},
            headers={"Origin": "https://evil.test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/settings/test", headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert client.post("/settings/test").status_code == 415
    assert client.put("/settings", data={"router_threshold": "0.7"}).status_code == 415
    assert (
        client.post(
            "/ui/settings",
            data={"router_threshold": "0.7"},
            headers={"Origin": "http://localhost"},
        ).status_code
        == 200
    )


def test_queries_overlap(c6):
    client, _, runtime, *_ = c6

    async def check():
        from omnistream.api.c6 import QueryIn

        entered = 0
        both = asyncio.Event()

        async def slow(*args, **kwargs):
            nonlocal entered
            entered += 1
            if entered == 2:
                both.set()
            await asyncio.wait_for(both.wait(), timeout=1)
            return {"ok": True}

        runtime.answer = slow
        results = await asyncio.gather(
            *(client.app.state.c6.query(QueryIn(question="Who?")) for _ in range(2))
        )
        assert results == [{"ok": True}, {"ok": True}]

    client.portal.call(check)


def test_eval_early_failure_has_record_and_log(c6, caplog):
    client, *_ = c6

    async def broken(*args, **kwargs):
        raise ValueError("invalid dataset")

    client.app.state.c6.evaluator = broken
    response = client.post("/eval/runs", json={"snapshot": "missing"})
    run_id = response.json()["run_id"]

    async def settle():
        await asyncio.gather(*client.app.state.c6.tasks)

    client.portal.call(settle)
    assert client.get(f"/eval/runs/{run_id}").json()["status"] == "failed"
    assert "failed" in caplog.text


def test_shutdown_cancels_eval_with_bounded_wait(c6):
    client, *_ = c6
    started = asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    client.app.state.c6.evaluator = slow
    response = client.post("/eval/runs", json={"snapshot": "slow"})

    async def shutdown():
        await started.wait()
        await asyncio.wait_for(client.app.state.c6.close(), timeout=3)

    client.portal.call(shutdown)
    assert (
        client.get(f"/eval/runs/{response.json()['run_id']}").json()["status"]
        == "cancelled"
    )


def test_half_lives_only_update_defaulted_bubbles(c6):
    client, repo, *_ = c6
    assert (
        client.post(
            "/bubbles",
            json={"name": "Research", "description": "Custom", "half_life_days": 365},
        ).status_code
        == 201
    )
    asyncio.run(repo.update_bubble("news", half_life_days=17))
    assert (
        client.put(
            "/settings", json={"half_life_news_days": 9, "half_life_research_days": 700}
        ).status_code
        == 200
    )
    assert asyncio.run(repo.get_bubble("news")).half_life_days == 17
    assert asyncio.run(repo.get_bubble("research")).half_life_days == 365
    asyncio.run(repo.update_bubble("finance", half_life_days=12))
    assert (
        client.put("/settings", json={"half_life_finance_days": 30}).status_code == 200
    )
    assert asyncio.run(repo.get_bubble("finance")).half_life_days == 12


def test_delete_conflict_returns_fresh_preview(c6):
    client, *_ = c6
    response = client.delete(
        "/bubbles", params={"id": "news", "confirmed_counts": "{}"}
    )
    assert response.status_code == 409
    preview = response.json()["detail"]["counts"]
    assert (
        client.delete(
            "/bubbles", params={"id": "news", "confirmed_counts": json.dumps(preview)}
        ).status_code
        == 204
    )


async def test_restart_validates_provider_overrides(tmp_path, monkeypatch):
    from omnistream.api.app import build_components

    settings = Settings(_env_file=None, data_dir=str(tmp_path), llm_model="old")
    repo = Repository.from_path(str(tmp_path / "restart.db"), settings=settings)
    await repo.set_setting("llm_model", "new")
    await repo.set_setting("judge_model", "")
    await repo.set_setting("llm_base_url", "https://provider.test/v1")
    captured = []

    def build(settings):
        captured.append(settings)
        return SimpleNamespace()

    monkeypatch.setattr("omnistream.llm.build_llm_client", build)
    try:
        components = await build_components(
            settings,
            repo=repo,
            embedder=FakeEmbedder(),
            writer=SimpleNamespace(),
            ops=Ops(),
            chunks=FakeChunks(),
            http=SimpleNamespace(),
        )
        assert captured[0].judge_model == "new"
        assert captured[0].llm_base_url == "https://provider.test/v1"
        assert components.lifecycle._router._model == "new"
    finally:
        await repo.close()


@pytest.mark.parametrize("host", ["evil.test", "evil.test:8000"])
def test_rebinding_host_rejected_on_all_routes(c6, host):
    client, *_ = c6
    response = client.get("/settings", headers={"host": host})
    assert response.status_code == 400
    assert response.json()["detail"] == (
        f"Invalid host {host!r}. Allowed: localhost, 127.0.0.1, [::1]. "
        "Set OMNI_ALLOWED_HOSTS=host1,host2 to allow more "
        "(e.g. when serving on 0.0.0.0)."
    )
    assert (
        client.post(
            "/query", json={"question": "Who?"}, headers={"host": host}
        ).status_code
        == 400
    )


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:9000", "[::1]:8000"])
def test_loopback_host_allowed(c6, host):
    client, *_ = c6
    assert client.get("/settings", headers={"host": host}).status_code == 200


def test_configured_host_allowed(monkeypatch):
    from fastapi import FastAPI

    from omnistream.api.c6 import install

    monkeypatch.setenv("OMNI_ALLOWED_HOSTS", "internal.example,other.example")
    app = FastAPI()
    install(app, SimpleNamespace())

    @app.get("/health")
    async def health():
        return {"ok": True}

    with TestClient(app, base_url="http://internal.example:8000") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health", headers={"host": "evil.test"}).status_code == 400


def test_evaluation_uses_startup_provider_after_settings_save(c6):
    client, _, _, built, *_ = c6
    captured = []

    async def evaluator(settings, repository, *, rows, snapshot, run_id):
        captured.append(settings)

    client.app.state.c6.evaluator = evaluator
    client.put("/settings", json={"llm_model": "saved-new-model"})
    client.post("/eval/runs", json={"snapshot": "frozen"})

    async def settle():
        await asyncio.gather(*client.app.state.c6.tasks)

    client.portal.call(settle)
    assert captured == [built[0]]
    assert captured[0].llm_model != "saved-new-model"
    assert (
        "queries, ingestion and evaluations after restart"
        in client.get("/settings").headers["x-settings-applies"]
    )


async def test_shutdown_late_cancellation_never_writes_closed_repo(caplog):
    from omnistream.api.c6 import EvalIn, Services

    repo = SimpleNamespace(update_eval_run=AsyncMock())
    entered, release = asyncio.Event(), asyncio.Event()

    async def evaluator(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            raise

    service = Services(repo, None, None, Settings(_env_file=None), evaluator=evaluator)
    task = asyncio.create_task(service.evaluate(EvalIn(snapshot="slow"), 1))
    service.tasks.add(task)
    service.task_runs[task] = 1
    await entered.wait()
    await service.close()
    repo.update_eval_run.assert_awaited_with(1, status="cancelled")
    repo.update_eval_run.side_effect = RuntimeError("repository closed")
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "failed" not in caplog.text
