"""Offline real-corpus and split binding regressions."""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from omnistream.eval.dataset import load_dataset
from omnistream.eval.snapshot import bound_dataset


@pytest.fixture
def corpus(tmp_path):
    base = tmp_path / "src/omnistream/eval"
    (base / "real").mkdir(parents=True)
    (base / "corpus").mkdir()
    texts = tmp_path / "data/real/real-v2"
    texts.mkdir(parents=True)
    rows = []
    for item_id in "abcdefghi":
        (texts / f"{item_id}.txt").write_text("Real fixture text " * 30)
        rows.append(
            {
                "id": item_id,
                "title": item_id,
                "source": "fixture",
                "url": f"https://example.org/{item_id}",
                "published_at": "2026-11-01T00:00:00+00:00",
                "text_path": f"data/real/real-v2/{item_id}.txt",
            }
        )
    (base / "real/real-v2-manifest.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows)
    )
    questions = []
    for split, item_id in (("dev", "a"), ("test", "b")):
        questions.append(
            {
                "id": split,
                "split": split,
                "type": "freshness",
                "question": "What?",
                "reference_answer": "This",
                "key_facts": ["This"],
                "gold": [item_id],
                "expected_bubbles": ["News"],
                "evidence": [{"item_id": item_id, "quote": "This"}],
                "distractors": ["c"],
                "acceptable_evidence": ["d"],
                "time_scope": None,
                "alias_bridge": False,
                "surface_forms": [],
                "notes": "",
            }
        )
    annotations = {
        "version": "real-v2-q1",
        "corpus": "real-v2",
        "split_assignment": {},
        "freshness_item_ids": {"dev": ["a"], "test": ["b"]},
        "questions": questions,
        "routing_labels": [
            {"item_id": "a", "routing_labels": ["News"], "reason": "annotation"}
        ],
    }
    path = base / "corpus/real-v2-questions.json"
    path.write_text(json.dumps(annotations))
    return tmp_path, path, annotations


def test_real_selection_and_holdback(corpus):
    root, _, _ = corpus
    dev = load_dataset("real-v2", split="dev", background=2, root=root)
    assert dev == load_dataset("real-v2", split="dev", background=2, root=root)
    assert len(dev["items"]) == 5
    assert "b" not in dev["selected_item_ids"]
    assert {i["id"] for i in dev["items"] if i["freshness"]} == {"a"}
    assert all(i["bubbles"] == [] for i in dev["items"])
    assert dev["questions"][0]["acceptable_evidence"] == ["d"]
    test = load_dataset("real-v2", split="test", background=100, root=root)
    assert "a" not in test["selected_item_ids"]
    assert all(q["split"] == "test" for q in test["questions"])


@pytest.mark.parametrize(
    "change,match",
    [
        ("overlap", "gold overlap"),
        ("gold", "question item"),
        ("freshness", "freshness item"),
        ("distractor", "question item"),
    ],
)
def test_real_validation(corpus, change, match):
    root, path, data = corpus
    if change == "overlap":
        data["questions"][0]["gold"].append("b")
    elif change == "freshness":
        data["freshness_item_ids"]["dev"].append("missing")
    elif change == "distractor":
        data["questions"][0]["distractors"].append("missing")
    else:
        data["questions"][0]["gold"].append("missing")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=match):
        load_dataset("real-v2", split="dev", root=root)


def test_real_requires_split(corpus):
    with pytest.raises(ValueError, match="requires --split"):
        load_dataset("real-v2", root=corpus[0])


def test_snapshot_split_binding(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"dataset": "real-v2", "split": "dev", "background": 40})
    )
    monkeypatch.setattr("omnistream.eval.dataset.load_dataset", lambda *a, **kw: kw)
    assert bound_dataset(tmp_path) == {"split": "dev", "background": 40}
    with pytest.raises(ValueError, match="split.*conflicts"):
        bound_dataset(tmp_path, split="test")
    with pytest.raises(ValueError, match="background.*conflicts"):
        bound_dataset(tmp_path, background=60)


def test_cli_real_options(monkeypatch):
    from omnistream import cli

    evaluate = AsyncMock(return_value=0)
    monkeypatch.setattr(cli, "evaluate", evaluate)
    assert (
        cli.main(
            [
                "eval",
                "--rows",
                "classic",
                "--snapshot",
                "real-v2-dev",
                "--dataset",
                "real-v2",
                "--split",
                "dev",
                "--background",
                "40",
            ]
        )
        == 0
    )
    assert evaluate.call_args.kwargs == {
        "dataset_name": "real-v2",
        "split": "dev",
        "background": 40,
    }


async def test_real_freshness_base_holdback(corpus, tmp_path):
    from omnistream.config import Settings
    from omnistream.eval.snapshot import SnapshotBuilder

    data = load_dataset("real-v2", split="dev", background=0, root=corpus[0])
    builder = SnapshotBuilder(
        Settings(_env_file=None, data_dir=str(tmp_path)),
        SimpleNamespace(),
        data,
        "real-test",
        AsyncMock(),
    )
    builder.ingest = AsyncMock()
    await builder.base()
    assert {c.args[0]["id"] for c in builder.ingest.call_args_list} == {"c", "d"}
    assert builder.manifest["dataset"] == "real-v2"
    assert builder.manifest["selected_item_ids"] == data["selected_item_ids"]


def test_real_text_integrity_and_path(corpus):
    root, _, _ = corpus
    path = root / "src/omnistream/eval/real/real-v2-manifest.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["sha256"] = "bad"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_dataset("real-v2", split="dev", root=root)
    rows[0]["text_path"] = "../outside.txt"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError, match="outside local corpus"):
        load_dataset("real-v2", split="dev", root=root)


def test_probe_selection_and_budget_guard():
    probe = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "scripts/realdata/ingestion_costprobe.py"
        )
    )
    manifest = (
        Path(__file__).resolve().parents[2]
        / "src/omnistream/eval/real/real-v2-manifest.jsonl"
    )
    rows = [
        json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()
    ]
    selected = probe["sample"](rows)
    assert selected == probe["sample"](rows)
    assert len(selected) == 10
    assert [
        sum(i["bubble_hint"] == b for i in selected)
        for b in ("news", "finance", "research")
    ] == [3, 3, 4]
    assert sum(": exhibit " in i["title"] for i in selected) >= 2
    assert sum("blog" in i["source"] and i["word_count"] >= 1500 for i in selected) >= 2
    meter = probe["BudgetMeter"]()
    args = {
        "model": "deepseek/deepseek-v4.1-flash-1017",
        "messages": [],
        "max_tokens": 8192,
    }
    reserve = meter.reserve(args)
    assert meter.pending == reserve
    response = SimpleNamespace(usage=SimpleNamespace(model_extra={"cost": 0.001}))
    meter.settle(reserve, response)
    assert meter.charged == 0.001 and meter.pending == 0
    meter.charged = 0.549
    with pytest.raises(RuntimeError, match="budget guard"):
        meter.reserve(args)
    with pytest.raises(RuntimeError, match="without output limit"):
        meter.reserve({"model": args["model"]})


def test_usage_meter_records_prompt_completion():
    from omnistream.eval.resources import UsageMeter

    meter = UsageMeter()
    meter.record(
        SimpleNamespace(
            usage=SimpleNamespace(
                total_tokens=30,
                prompt_tokens=20,
                completion_tokens=10,
                model_extra={"cost": 0.002},
            )
        )
    )
    usage = next(iter(meter.summary().values()))
    assert usage["prompt_tokens"] == 20 and usage["completion_tokens"] == 10
    assert usage["calls"] == 1 and usage["cost_usd"] == 0.002


def test_real_reports_freshness_without_scored_question(corpus):
    root, path, annotations = corpus
    excluded = annotations["questions"][0]
    excluded["exclude_from_scoring"] = True
    excluded["exclusion_reason"] = "No reliable answer"
    scored = dict(excluded, id="scored", type="single", gold=["e"],
                  exclude_from_scoring=False)
    annotations["questions"].append(scored)
    path.write_text(json.dumps(annotations))
    data = load_dataset("real-v2", split="dev", root=root)
    assert data["freshness_items_without_scored_question"] == ["a"]
    assert "a" in data["selected_item_ids"]
    assert [q["id"] for q in data["questions"]] == ["scored"]


async def test_partial_snapshot_resumes_written_freshness_and_freezes(tmp_path, monkeypatch):
    from omnistream.config import Settings
    from omnistream.eval import measure_freshness
    from omnistream.eval.snapshot import SnapshotBuilder, item_digest, save

    # 69 base + 3 freshness items were written; only two probes were checkpointed.
    data = {
        "version": "2-real", "corpus": "real-v2",
        "items": [{"id": str(i), "freshness": i >= 69,
                   "published_at": "2026-11-01"} for i in range(74)],
        "questions": [{"gold": [str(i)], "question": str(i)} for i in (69, 70, 72, 73)],
    }
    stored = {str(i): SimpleNamespace(id=str(i), status="written") for i in range(72)}
    repo = SimpleNamespace(
        get_item=AsyncMock(side_effect=lambda key: stored.get(key)),
        list_items=AsyncMock(side_effect=lambda: list(stored.values())),
        list_jobs=AsyncMock(side_effect=lambda: [
            SimpleNamespace(item_id=key, state="done") for key in stored]),
    )
    monkeypatch.setattr("omnistream.eval.snapshot.SentenceTransformerEmbedder", lambda _: None)
    monkeypatch.setattr("omnistream.eval.snapshot.verify_item_store",
                        lambda *args: item_digest(data))
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    builder = SnapshotBuilder(settings, repo, data, "real-v2-dev", AsyncMock())
    builder.manifest["items"] = {
        key: {"runtime_id": key, "status": "written", "injected_at": 1,
              "write_lag_seconds": 2} for key in stored
    }
    recorded = {key: {"write_lag_seconds": 2, "answerable_lag_seconds": 3}
                for key in ("69", "70")}
    builder.manifest["freshness"] = recorded.copy()
    save(builder.manifest_path, builder.manifest)
    builder = SnapshotBuilder(settings, repo, data, "real-v2-dev", AsyncMock())
    assert not await builder.verify_frozen()
    # Exercise the real ingest resume guard: no intake or worker exists for old items.
    await builder.base()
    assert await builder.ingest(data["items"][71]) is stored["71"]
    original_ingest = builder.ingest
    newly_ingested = []

    async def ingest(item):
        key = item["id"]
        if key in stored:
            return await original_ingest(item)
        newly_ingested.append(key)
        stored[key] = SimpleNamespace(id=key, status="written")
        builder.manifest["items"][key] = {
            "runtime_id": key, "status": "written", "injected_at": 1,
            "write_lag_seconds": 2,
        }
        return stored[key]

    builder.ingest = ingest
    runtime = SimpleNamespace(answer=AsyncMock(side_effect=lambda question, **kwargs:
        SimpleNamespace(answer=SimpleNamespace(text="answer"), multi_hop=None,
                        retrieval=None)))
    judge = SimpleNamespace(correctness=AsyncMock(return_value={"score": 2}))
    monkeypatch.setattr("omnistream.eval.evidence_ids", lambda result: ["72", "73"])
    await measure_freshness(builder, data, runtime, judge)
    assert newly_ingested == ["72", "73"]
    assert builder.manifest["freshness"]["69"] == recorded["69"]
    assert builder.manifest["freshness"]["70"] == recorded["70"]
    assert builder.manifest["freshness"]["71"] == {
        "write_lag_seconds": 2, "answerable_lag_seconds": None,
        "probes": [], "probe_skipped": "no scored question",
    }
    assert runtime.answer.await_count == judge.correctness.await_count == 2
    assert await builder.verify_frozen()
    assert json.loads(builder.manifest_path.read_text())["frozen"] is True
    await measure_freshness(builder, data, runtime, judge)
    assert runtime.answer.await_count == 2
    # A crash after the last write must not freeze ahead of its missing probe.
    builder.manifest["frozen"] = False
    del builder.manifest["freshness"]["73"]
    assert not await builder.verify_frozen()
    await measure_freshness(builder, data, runtime, judge)
    assert newly_ingested == ["72", "73"]
    assert runtime.answer.await_count == 3
    assert await builder.verify_frozen()
