"""Regression coverage for independently reviewed v2 evaluation semantics."""

import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from omnistream.eval import evidence_ids, score_question
from omnistream.eval.calibration import agreement
from omnistream.eval.dataset import load_dataset, validate_dataset
from omnistream.eval.judge import Judge, claim_groups
from omnistream.eval.metrics import aggregate


def test_eval_v2_validation():
    data = load_dataset("eval-v2")
    assert len(data["items"]) == 90
    validate_dataset(data)
    q = next(q for q in data["questions"] if q["type"] == "multi_hop")
    q["gold"] = [q["gold"][0]]
    with pytest.raises(AssertionError):
        validate_dataset(data)


def test_eval_claims_decimals_abbreviations_and_citation_unions():
    assert claim_groups(
        "Dr. Okonkwo-Rand secured 8.5 million [1]. The lab built a membrane [2][5][6]."
    ) == [
        ("Dr. Okonkwo-Rand secured 8.5 million .", [1]),
        ("The lab built a membrane .", [2, 5, 6]),
    ]
    groups = claim_groups(
        "Dr. Okonkwo-Rand secured 8.5 million. [1] A second claim [2]."
    )
    assert len(groups) == 2 and "8.5 million" in groups[0][0]
    assert all(c.strip(" .!?") for c, ns in groups)
    assert claim_groups(" [1]") == []
    assert claim_groups("5 million [1]") == [("5 million", [1])]


async def test_eval_citation_union_and_external_union():
    judge = Judge.__new__(Judge)
    payloads = []

    class Client:
        def chat_json(self, messages, **kwargs):
            payload = json.loads(messages[1]["content"])
            payloads.append(payload)
            assert (
                "Source A" in payload["original_text"]
                and "Source B" in payload["original_text"]
            )
            assert "[" not in payload["claim"]
            return {"supported": True}

    judge.client = Client()
    cites = [(1, "a", (), ""), (2, "b", (), "")]
    assert (
        await judge.citations(
            "A and B [1][2].", cites, {"a": "Source A", "b": "Source B"}
        )
    )[:2] == (2, 2)
    assert (
        await judge.citations("A and B.", cites, {"a": "Source A", "b": "Source B"})
    )[:2] == (2, 2)
    assert len(payloads) == 2


async def test_eval_judge_retries_malformed_and_coerces_score():
    judge = Judge.__new__(Judge)

    class Client:
        calls = 0

        def chat_json(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise json.JSONDecodeError("bad", "", 0)
            if self.calls == 2:
                return {"score": "wrong"}
            return {"score": "2", "rationale": "correct"}

    judge.client = Client()
    assert (await judge.correctness({"question": "q", "reference_answer": "a"}, "a"))[
        "score"
    ] == 2
    assert judge.client.calls == 3


async def test_eval_judgement_failures_preserve_retrieval_and_other_judgement():
    q = {
        "id": "q",
        "question": "q",
        "type": "time_sensitive",
        "expected_bubbles": ["News"],
        "reference_answer": "a",
    }
    judge = NS(
        correctness=AsyncMock(side_effect=ValueError("bad json")),
        citations=AsyncMock(return_value=(1, 1, [])),
    )
    row = await score_question(
        "own", q, "a", ["a"], ["News"], [], [], {}, judge, ["a"], 1
    )
    assert row["correctness"] is None
    assert (
        row["recall_at_10"]
        == row["routing_recall"]
        == row["citation_faithfulness"]
        == 1
    )
    metrics = aggregate([row])["own"]
    assert metrics["correctness"] is None and metrics["changed_fact_accuracy"] is None
    assert metrics["correctness_errors"] == 1 and metrics["faithfulness_errors"] == 0
    judge.correctness = AsyncMock(return_value={"score": 2})
    judge.citations = AsyncMock(side_effect=ValueError("bad json"))
    row = await score_question(
        "own", q, "a", ["a"], ["News"], [], [], {}, judge, ["a"], 1
    )
    assert row["correctness"] == 2 and row["citation_faithfulness"] is None
    assert aggregate([row])["own"]["citation_faithfulness"] is None


def test_eval_subagent_ranking_round_robin_before_cutoff():
    def finding(bubble, ids):
        return NS(
            bubble=bubble,
            facts=[NS(item_id=i, item_ids=(i,)) for i in ids],
            chunks=[],
            item_ids=ids,
        )

    result = NS(
        multi_hop=NS(
            findings=[
                finding("A", [f"a{i}" for i in range(20)]),
                finding("B", ["b0", "b1"]),
            ]
        ),
        retrieval=None,
    )
    assert evidence_ids(result)[:5] == ["a0", "b0", "a1", "b1", "a2"]
    assert len(evidence_ids(result)) == 22


def test_eval_macro_micro_zero_citation_and_calibration_kappa():
    rows = [
        {
            "configuration": "own",
            "type": "single",
            "citation_count": n,
            "faithful_citations": f,
        }
        for n, f in [(0, 0), (1, 1), (9, 0)]
    ]
    m = aggregate(rows)["own"]
    assert m["citation_faithfulness"] == pytest.approx(1 / 3)
    assert m["citation_faithfulness_micro"] == 0.1
    assert (
        agreement([{"human_score": "", "judge_score": 2}])["status"]
        == "pending human labels"
    )
    r = agreement(
        [{"human_score": a, "judge_score": b} for a, b in [(0, 0), (1, 1), (2, 1)]]
    )
    assert r["exact_agreement"] == pytest.approx(2 / 3)
    assert r["cohens_kappa"] == pytest.approx(0.5)


async def test_eval_judge_retries_llm_json_wrapper_error():
    from omnistream.llm import LLMError

    judge = Judge.__new__(Judge)

    class Client:
        calls = 0

        def chat_json(self, *args, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise LLMError("response is not valid JSON")
            return {"score": "2"}

    judge.client = Client()
    assert (await judge.correctness({"question": "q", "reference_answer": "a"}, "a"))[
        "score"
    ] == 2
    assert judge.client.calls == 3


def test_eval_v2_rejects_named_shortcut_and_same_bubble_gold():
    data = load_dataset("eval-v2")
    q = next(q for q in data["questions"] if q["type"] == "multi_hop")
    q["question"] += " Anchorforge"
    for item in data["items"]:
        if item["id"] in q["gold"]:
            item["text"] += " Anchorforge"
    with pytest.raises(AssertionError):
        validate_dataset(data)
    data = load_dataset("eval-v2")
    q = next(q for q in data["questions"] if q["type"] == "multi_hop")
    q["gold"] = ["0-leader", "0-recall"]
    with pytest.raises(AssertionError):
        validate_dataset(data)


def test_eval_calibration_export_is_v2_stratified_and_blinded(tmp_path):
    from collections import Counter

    from omnistream.eval.calibration import calibration_report, export_sample

    run = tmp_path / "runs" / "8"
    run.mkdir(parents=True)
    questions = load_dataset("eval-v2")["questions"]
    rows = [
        {
            "configuration": ["classic", "own", "own+subagents"][i % 3],
            "question_id": q["id"],
            "type": q["type"],
            "answer": q["reference_answer"],
            "correctness": i % 3,
        }
        for i, q in enumerate(questions)
    ]
    (run / "answers.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    dest = tmp_path / "labels.jsonl"
    assert export_sample(run.parent, dest) == 30
    labels = list(map(json.loads, dest.read_text().splitlines()))
    keys = list(
        map(json.loads, dest.with_suffix(".key.jsonl").read_text().splitlines())
    )
    assert Counter(k["judge_score"] for k in keys) == {0: 10, 1: 10, 2: 10}
    assert len({k["configuration"] for k in keys}) == 3
    assert len({k["type"] for k in keys}) == 4
    assert all(
        "judge_score" not in r
        and "configuration" not in r
        and "source_checkpoint" not in r
        for r in labels
    )
    assert calibration_report(dest) == {
        "status": "pending human labels",
        "n": 30,
        "labelled": 0,
    }
    lookup = {k["sample_id"]: k["judge_score"] for k in keys}
    for row in labels:
        row["human_score"] = lookup[row["sample_id"]]
    dest.write_text("".join(json.dumps(r) + "\n" for r in labels))
    assert calibration_report(dest)["cohens_kappa"] == 1
    dest.unlink()
    (run / "answers.jsonl").write_text(json.dumps(rows[0]))
    with pytest.raises(ValueError, match="found 1"):
        export_sample(run.parent, dest)


def test_eval_v2_reference_and_acceptable_evidence():
    from omnistream.eval.metrics import retrieval_metrics

    data = load_dataset("eval-v2")
    for q in data["questions"]:
        if q["id"] in ("v2-q48", "v2-q53", "v2-q58"):
            assert "(" in q["reference_answer"]
            assert len(q["key_fact_alternatives"][0]) == 2
        if q.get("acceptable_evidence"):
            m = retrieval_metrics(
                q["acceptable_evidence"] + q["gold"],
                q["gold"],
                q["acceptable_evidence"],
            )
            assert m == {"recall_at_10": 1, "mrr": 1, "hits_at_1": 1}
            assert (
                retrieval_metrics(
                    q["acceptable_evidence"], q["gold"], q["acceptable_evidence"]
                )["recall_at_10"]
                == 0
            )


def test_eval_failed_judgements_make_dependent_checks_unmeasured():
    from omnistream.eval.metrics import success_criteria

    rows = [
        {
            "configuration": c,
            "type": "multi_hop",
            "correctness": 2,
            "citation_count": 1,
            "faithful_citations": 1,
        }
        for c in ("own+subagents", "classic", "external")
    ]
    rows += [
        {
            "configuration": "classic",
            "type": "time_sensitive",
            "correctness": None,
            "citation_count": None,
            "judgement_errors": {"correctness": "failed", "faithfulness": "failed"},
        }
    ]
    metrics = aggregate(rows)
    checks = success_criteria(metrics, {})
    assert checks["classic: citation faithfulness"]["status"] == "UNMEASURED"
    assert checks["classic: citation faithfulness"]["value"] == 1
    assert (
        checks["Full system multi-hop correctness gain vs classic"]["status"]
        == "UNMEASURED"
    )
    assert (
        checks["Full system multi-hop correctness gain vs classic"]["failed_judgements"]
        == 1
    )
    assert (
        checks["Full system multi-hop correctness gain vs external"]["status"] == "FAIL"
    )


def test_eval_ingestion_routing_keeps_original_labels():
    from omnistream.eval.metrics import ingestion_routing_metrics

    items = [
        {"id": "0-study", "bubbles": ["Research"]},
        {"id": "1-study", "bubbles": ["Research"]},
    ]
    entries = {"0-study": {"bubbles": ["r", "f"]}, "1-study": {"bubbles": ["f"]}}
    m = ingestion_routing_metrics(items, entries, {"Research": "r"})
    assert m["ingestion_routing_accuracy"] == 0
    assert m["ingestion_primary_label_recall"] == 0.5
    assert m["ingestion_over_assignment_rate"] == 1
    assert m["ingestion_wrong_routing_rate"] == 0.5
    assert m["ingestion_over_assignments_by_category"]["study"] == {
        "items": 2,
        "over_assignments": 2,
    }
    assert items[0]["bubbles"] == ["Research"]


def test_eval_manifest_binding_and_content_integrity(tmp_path):
    import copy
    import sqlite3

    from omnistream.eval.snapshot import (
        bound_dataset,
        item_digest,
        migrate_manifest,
        save,
        verify_item_store,
    )

    dataset = load_dataset("eval-v2")
    original = item_digest(dataset)
    dataset["questions"][0]["reference_answer"] = "Corrected answer"
    assert item_digest(dataset) == original
    renamed = tmp_path / "renamed-v2"
    renamed.mkdir()
    manifest = {
        "dataset_sha256": "736b8035ebb4a9ebf1386bf33e76956a11cde470c575671a9fee51b2bb78634a"
    }
    save(renamed / "manifest.json", manifest)
    assert bound_dataset(renamed)["version"].startswith("2")
    with pytest.raises(ValueError, match="conflicts"):
        bound_dataset(renamed, "eval-v1")
    changed = copy.deepcopy(dataset)
    changed["items"][0]["bubbles"] = ["Finance"]
    with pytest.raises(ValueError, match="Legacy item content"):
        migrate_manifest(renamed, changed)
    assert json.loads((renamed / "manifest.json").read_text()) == manifest
    # Miniature read-only store covers every field actually persisted by intake.
    item = dataset["items"][0]
    text = renamed / "raw.txt"
    text.write_text(item["text"], encoding="utf-8")
    with sqlite3.connect(renamed / "state.db") as db:
        db.execute(
            "CREATE TABLE items (id, source_id, url, title, published_at, bubble_ids, text_path, raw_path)"
        )
        db.execute("CREATE TABLE sources (id, url, credibility)")
        source = renamed.name + "-" + item["id"]
        db.execute(
            "INSERT INTO sources VALUES (?, ?, ?)",
            (source, item["url"], item["credibility"]),
        )
        db.execute(
            "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "runtime",
                source,
                item["url"] + "?snapshot=" + renamed.name,
                item["title"],
                item["published_at"],
                '["assigned"]',
                str(text),
                str(text),
            ),
        )
    mini = {"items": [item]}
    manifest = {
        "items": {item["id"]: {"runtime_id": "runtime", "bubbles": ["assigned"]}},
        "freshness": {},
    }
    assert verify_item_store(renamed, manifest, mini) == item_digest(mini)
    text.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="content mismatch"):
        verify_item_store(renamed, manifest, mini)


def test_eval_new_named_v2_snapshot_records_dataset(tmp_path):
    from omnistream.config import Settings
    from omnistream.eval.snapshot import SnapshotBuilder

    data = load_dataset("eval-v2")
    builder = SnapshotBuilder(
        Settings(_env_file=None, data_dir=str(tmp_path)),
        NS(),
        data,
        "custom-v2",
        AsyncMock(),
    )
    assert builder.manifest["dataset"] == "eval-v2"
    assert builder.manifest["item_content_sha256"]
