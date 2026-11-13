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
