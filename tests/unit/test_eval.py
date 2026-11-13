"""Offline C7 coverage: dataset, rankings, persistence, exports and fake live wiring."""

import csv
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.eval import run_evaluation
from omnistream.eval.dataset import load_dataset, parse_rows, validate_dataset
from omnistream.eval.metrics import (
    aggregate,
    retrieval_metrics,
    routing_metrics,
    success_criteria,
)
from omnistream.eval.report import write_report


def test_eval_dataset():
    data = load_dataset()
    validate_dataset(data)
    assert len(data["items"]) == 85
    data["questions"][0]["gold"] = ["missing"]
    with pytest.raises(AssertionError):
        validate_dataset(data)


def test_eval_ranking_metrics():
    assert retrieval_metrics(["x", "x", "a", "b"], ["a", "b"]) == {
        "recall_at_10": 1.0,
        "mrr": 0.5,
        "hits_at_1": 0.0,
    }
    assert retrieval_metrics([str(i) for i in range(11)], ["10"]) == {
        "recall_at_10": 0.0,
        "mrr": 1 / 11,
        "hits_at_1": 0.0,
    }
    assert retrieval_metrics([], ["a"])["mrr"] == 0
    assert routing_metrics(["News", "Finance"], ["News"]) == {
        "routing_recall": 1.0,
        "routing_precision": 0.5,
    }
    assert routing_metrics([], ["News"])["routing_precision"] == 0


def test_eval_rows():
    assert len(parse_rows(["all"])) == 6
    assert parse_rows(["own,classic", "own"]) == ["own", "classic"]
    with pytest.raises(ValueError):
        parse_rows(["typo"])


def test_eval_exports(tmp_path):
    results = [
        {
            "configuration": "own",
            "type": "time_sensitive",
            "correctness": 2,
            "recall_at_10": 1.0,
            "mrr": 1.0,
            "hits_at_1": 1.0,
            "routing_recall": 1.0,
            "routing_precision": 1.0,
            "citation_count": 2,
            "faithful_citations": 1,
            "latency_seconds": 2.0,
            "answer": 'quoted,"answer"\nnext line',
        }
    ]
    metrics = aggregate(results)
    assert metrics["own"]["citation_faithfulness"] == 0.5
    assert metrics["own"]["changed_fact_accuracy"] == 1.0
    paths = write_report(
        tmp_path, "demo", "stamp", metrics, results, {}, success_criteria(metrics, {})
    )
    assert "N/A" in __import__("pathlib").Path(paths[0]).read_text(encoding="utf-8")
    with open(paths[1], encoding="utf-8", newline="") as stream:
        assert next(iter(csv.DictReader(stream)))["answer"] == results[0]["answer"]
    assert all(__import__("pathlib").Path(p).exists() for p in paths)


async def test_eval_repository(tmp_path):
    repo = Repository.from_path(str(tmp_path / "state.db"))
    row = await repo.create_eval_run(snapshot="fixture", rows=["own"])
    assert row.id
    await repo.update_eval_run(
        row.id,
        status="completed",
        metrics={"own": {"correctness": 2}},
        results=[{"q": 1}],
    )
    loaded = await repo.get_eval_run(row.id)
    assert (
        loaded.snapshot == "fixture"
        and loaded.status == "completed"
        and loaded.results == [{"q": 1}]
    )
    assert len(await repo.list_eval_runs()) == 1
    with pytest.raises(ValueError):
        await repo.update_eval_run(row.id, unknown="x")
    await repo.close()


async def test_eval_run_with_fakes(tmp_path, monkeypatch):
    import omnistream.eval.judge as judging
    import omnistream.eval.snapshot as snap
    from omnistream.eval import audit, resources
    from omnistream.retrieval import runtime

    monkeypatch.chdir(tmp_path)
    data = load_dataset()

    class Builder:
        def __init__(self, settings, repo, dataset, name, progress):
            self.path = tmp_path / "snapshots" / name
            self.path.mkdir(parents=True, exist_ok=True)
            self.manifest_path = self.path / "manifest.json"
            self.groups = {
                n: name + "-" + n.lower() for n in ("News", "Finance", "Research")
            }
            self.manifest = {
                "dataset": "eval-v1",
                "items": {
                    i["id"]: {
                        "runtime_id": i["id"],
                        "status": "written",
                        "bubbles": [self.groups[b] for b in i["bubbles"]],
                    }
                    for i in dataset["items"]
                },
                "freshness": {
                    i["id"]: {"answerable_lag_seconds": 1, "write_lag_seconds": 0.5}
                    for i in dataset["items"]
                    if i["freshness"]
                },
            }
            self.local_settings = settings
            self.embedder = NS(service=None)

        async def initialize(self):
            pass

        async def base(self):
            pass

        async def close(self):
            pass

    class Judge:
        def __init__(self, settings):
            pass

        async def correctness(self, q, answer):
            return {"score": 2, "rationale": "fake"}

        async def citations(self, *args):
            return 0, 0, []

        async def contamination(self, q):
            return {"answer": "unknown", "score": 0, "rationale": "fake"}

        async def close(self):
            pass

    class Runtime:
        async def answer(self, question, **kwargs):
            q = next(q for q in data["questions"] if q["question"] == question)
            return NS(
                answer=NS(
                    text=q["reference_answer"], citations=[], invalid_citations=[]
                ),
                retrieval=NS(facts=[], chunks=[NS(item_id=i) for i in q["gold"]]),
                multi_hop=None,
                routing=NS(
                    bubbles=["fixture-" + b.lower() for b in q["expected_bubbles"]]
                ),
            )

        async def close(self):
            pass

    async def sample(self):
        self.app_peak = 100
        self.peak = 200
        self.container_peak = 100

    monkeypatch.setattr(snap, "SnapshotBuilder", Builder)
    monkeypatch.setattr(judging, "Judge", Judge)
    monkeypatch.setattr(
        audit,
        "audit_graph",
        AsyncMock(
            return_value={
                "duplicate_entity_rate": 0,
                "ungrounded_entity_rate": 0,
                "audit_sample_size": 100,
            }
        ),
    )
    monkeypatch.setattr(runtime, "build_query_runtime", lambda *a, **k: Runtime())
    monkeypatch.setattr(resources.MemorySampler, "sample", sample)
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    repo = Repository.from_path(str(tmp_path / "main.db"))
    summary = await run_evaluation(
        settings, repo, rows=["classic"], snapshot="fixture", progress=lambda _: None
    )
    assert summary.status == "completed", summary.global_metrics
    assert len(summary.results) == 60
    assert summary.metrics["classic"]["recall_at_10"] == 1
    assert summary.metrics["classic"]["correctness"] == 2
    assert (await repo.get_eval_run(summary.id)).status == "completed"
    assert summary.global_metrics["ingestion_routing_accuracy"] == 1
    resumed = await run_evaluation(
        settings,
        repo,
        rows=["classic"],
        snapshot="fixture",
        resume="latest",
        progress=lambda _: None,
    )
    assert resumed.id == summary.id and len(resumed.results) == 60
    assert resumed.results == summary.results
    answers = (
        tmp_path / "snapshots" / "fixture" / "runs" / str(summary.id) / "answers.jsonl"
    )
    lines = answers.read_text(encoding="utf-8").splitlines()
    answers.write_text("\n".join(lines[:-1]) + '\n{"partial":', encoding="utf-8")
    recovered = await run_evaluation(
        settings,
        repo,
        rows=["classic"],
        snapshot="fixture",
        resume="latest",
        progress=lambda _: None,
    )
    assert len(recovered.results) == 60
    assert recovered.results[:-1] == summary.results[:-1]
    assert (
        len({(r["configuration"], r["question_id"]) for r in recovered.results}) == 60
    )
    # A failed checkpoint pair is retried once on explicit resume.
    retry_rows = recovered.results.copy()
    retry_rows[0] = {
        **retry_rows[0],
        "judgement_errors": {"correctness": "malformed"},
        "correctness": None,
    }
    answers.write_text(
        "".join(json.dumps(r) + "\n" for r in retry_rows), encoding="utf-8"
    )
    retried = await run_evaluation(
        settings,
        repo,
        rows=["classic"],
        snapshot="fixture",
        resume="latest",
        progress=lambda _: None,
    )
    retried_pair = next(
        r for r in retried.results if r["question_id"] == retry_rows[0]["question_id"]
    )
    assert retried_pair["resume_retry"] and retried_pair["correctness"] == 2
    retried_pair["judgement_errors"] = {"correctness": "malformed again"}
    answers.write_text(
        "".join(json.dumps(r) + "\n" for r in retried.results), encoding="utf-8"
    )
    twice = await run_evaluation(
        settings,
        repo,
        rows=["classic"],
        snapshot="fixture",
        resume="latest",
        progress=lambda _: None,
    )
    assert twice.results == retried.results
    # Repeated credit failures must stop new calls and remain retryable on every resume.
    calls = []

    async def broke(self, *args, **kwargs):
        calls.append(args)
        raise RuntimeError("APIStatusError: Error code: 402 - Insufficient credits")

    monkeypatch.setattr(Runtime, "answer", broke)
    answers.write_text("", encoding="utf-8")
    for _ in range(2):
        calls.clear()
        invalid = await run_evaluation(
            settings,
            repo,
            rows=["classic"],
            snapshot="fixture",
            resume="latest",
            progress=lambda _: None,
        )
        assert 1 <= len(calls) <= 2
        assert invalid.status == "invalid"
        assert len(invalid.results) == 60
        assert invalid.metrics["classic"]["unmeasured"] == 60
        assert invalid.metrics["classic"]["correctness"] is None
        assert (await repo.get_eval_run(invalid.id)).status == "invalid"
        assert "INVALID RUN" in __import__("pathlib").Path(
            invalid.report_path
        ).read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="question selection"):
        await run_evaluation(
            settings,
            repo,
            rows=["classic"],
            snapshot="fixture",
            resume="latest",
            limit=3,
        )
    await repo.close()


def test_eval_cli_wiring(monkeypatch):
    from omnistream import cli

    called = {}

    async def evaluate(settings, rows, snapshot, rebuild):
        called.update(rows=rows, snapshot=snapshot, rebuild=rebuild)
        return 0

    monkeypatch.setattr(cli, "evaluate", evaluate)
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    assert (
        cli.main(
            ["eval", "--rows", "own,classic", "--snapshot", "fixture", "--rebuild"]
        )
        == 0
    )
    assert called == {"rows": "own,classic", "snapshot": "fixture", "rebuild": True}


def test_eval_source_contract():
    from omnistream.models import ApiMapping, Source

    source = Source(
        id="eval-example",
        type="api",
        poll_interval=900,
        api_mapping=ApiMapping(items="$[*]", body="$.text", url="$.url"),
    )
    assert source.bubble_ids == []


def test_eval_success_criteria_require_freshness_and_audit():
    checks = success_criteria(
        {},
        {
            "freshness_answerable_count": 9,
            "freshness_max_lag_seconds": None,
            "audit_sample_size": 99,
        },
    )
    assert checks["freshness max answerable lag seconds"]["status"] == "FAIL"
    assert checks["entity audit sample size"]["status"] == "FAIL"


async def test_eval_migrates_existing_database(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE eval_runs (id INTEGER PRIMARY KEY, config VARCHAR NOT NULL, scores JSON NOT NULL, created_at DATETIME NOT NULL)"
        )
        connection.execute(
            "INSERT INTO eval_runs VALUES (1, 'classic', '{}', '2026-01-01 00:00:00')"
        )
    repo = Repository.from_path(str(path))
    row = await repo.get_eval_run(1)
    assert row.config == "classic" and row.rows == [] and row.results == []
    await repo.close()


def test_eval_provider_usage_missing_cost_is_not_zero():
    from omnistream.eval.resources import UsageMeter, stage

    meter = UsageMeter()
    token = stage.set("classic")
    try:
        meter.record(NS(usage=NS(total_tokens=100, model_extra={"cost": 0.001})))
        assert meter.summary()["classic"]["cost_usd"] == 0.001
        meter.record(NS(usage=NS(total_tokens=20, model_extra={})))
        assert meter.summary()["classic"]["tokens"] == 120
        assert meter.summary()["classic"]["cost_usd"] is None
    finally:
        stage.reset(token)


async def test_eval_judge_missing_source_counts_unfaithful():
    from omnistream.eval.judge import Judge

    judge = Judge.__new__(Judge)
    faithful, count, details = await judge.citations(
        "Claim [1]", [(1, "missing", (), "text")], {}, [2]
    )
    assert faithful == 0 and count == 2
    assert all(not d["supported"] for d in details)


async def test_eval_judge_uses_original_when_span_missing():
    from omnistream.eval.judge import Judge

    judge = Judge.__new__(Judge)

    class Client:
        def chat_json(self, messages, **kwargs):
            payload = json.loads(messages[1]["content"])
            assert (
                payload["original_text"] == "Taren is CEO."
                and not payload["verified_spans"]
            )
            return {"supported": True, "rationale": "original supports claim"}

    judge.client = Client()
    faithful, count, _ = await judge.citations(
        "Taren is CEO [1]", [(1, "i", (), "")], {"i": "Taren is CEO."}
    )
    assert faithful == 1 and count == 1


def test_eval_evidence_includes_subagent_reads_and_fact_provenance():
    from omnistream.eval import evidence_ids

    result = NS(
        retrieval=NS(
            facts=[NS(fact=NS(item_id="a", item_ids=("a", "b")))],
            chunks=[NS(item_id="c")],
        ),
        multi_hop=NS(findings=[NS(item_ids=("d", "a"))]),
    )
    assert evidence_ids(result) == ["a", "b", "c", "d"]


def test_eval_external_embedding_adapter_stays_local():
    import numpy as np

    from omnistream.eval.external import LocalEmbedding

    class Service:
        model_name = "local-test"

        def embed_documents(self, texts):
            return np.array([[1.0, 0.0] for _ in texts])

        def embed_query(self, text):
            return np.array([0.0, 1.0])

    embedding = LocalEmbedding(Service())
    assert embedding.get_text_embedding("x") == [1.0, 0.0]
    assert embedding.get_query_embedding("x") == [0.0, 1.0]


async def test_eval_snapshot_real_queue_and_automatic_routing(tmp_path):
    from omnistream.eval.snapshot import SnapshotBuilder
    from omnistream.ingest.intake import Intake
    from omnistream.ingest.pipeline import ItemProcessor
    from omnistream.ingest.queue import WorkerPool

    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    repo = Repository.from_path(str(tmp_path / "isolated.db"))
    builder = SnapshotBuilder(settings, repo, load_dataset(), "sample", AsyncMock())
    router = NS(
        route=AsyncMock(
            return_value=NS(unsorted=False, bubble_ids=["sample-news"], confidence=0.95)
        )
    )
    writer = NS(write=AsyncMock())
    builder.intake = Intake(repo, str(builder.path), 200)
    builder.pool = WorkerPool(
        repo,
        ItemProcessor(repo, router, writer).process_item,
        max_attempts=3,
        backoff_base=0,
    )
    item = load_dataset()["items"][0]
    first = await builder.ingest(item)
    second = await builder.ingest(item)
    assert first.id == second.id and first.status == "written"
    assert router.route.await_count == 1 and writer.write.await_count == 1
    source = await repo.get_source(first.source_id)
    assert source.bubble_ids == []
    assert source.poll_interval == settings.poll_interval_minutes * 60
    assert source.poll_interval >= 60
    assert (await repo.list_jobs())[0].state == "done"
    assert first.polled_at and first.routed_at and first.written_at
    await repo.close()


async def test_snapshot_freeze_verifies_database_and_never_ingests(
    tmp_path, monkeypatch
):
    from omnistream.eval.snapshot import SnapshotBuilder, item_digest, save

    monkeypatch.setattr(
        "omnistream.eval.snapshot.verify_item_store",
        lambda path, manifest, dataset: item_digest(dataset),
    )

    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    data = load_dataset()
    repo = NS(
        list_items=AsyncMock(return_value=[]), list_jobs=AsyncMock(return_value=[])
    )
    builder = SnapshotBuilder(settings, repo, data, "freeze", AsyncMock())
    builder.manifest["items"] = {
        i["id"]: {"runtime_id": i["id"], "status": "written"} for i in data["items"]
    }
    with pytest.raises(ValueError, match="incomplete"):
        await builder.verify_frozen()
    repo.list_items.return_value = [
        NS(id=i["id"], status="written") for i in data["items"]
    ]
    repo.list_jobs.return_value = [
        NS(item_id=i["id"], state="done") for i in data["items"]
    ]
    assert await builder.verify_frozen()
    with pytest.raises(ValueError, match="frozen"):
        await builder.ingest(data["items"][0])
    builder.manifest["item_content_sha256"] = "changed"
    save(builder.manifest_path, builder.manifest)
    with pytest.raises(ValueError, match="dataset changed"):
        SnapshotBuilder(settings, repo, data, "freeze", AsyncMock())


def test_graph_reader_only_uses_graphiti_fact_embedding():
    from pathlib import Path

    from omnistream.graph import neo4j_store

    source = Path(neo4j_store.__file__).read_text()
    assert "r.embedding" not in source
    assert "r.fact_embedding AS embedding" in source
