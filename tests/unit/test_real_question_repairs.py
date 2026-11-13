"""Offline regressions for repaired real-v2 evidence and scoring policy."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from omnistream.eval.dataset import load_dataset
from omnistream.eval.metrics import retrieval_metrics
from tests.unit import test_eval_real

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def corpus(tmp_path):
    return test_eval_real.corpus.__wrapped__(tmp_path)


def test_acceptable_evidence_changes_rank_but_not_gold_recall():
    assert retrieval_metrics(["alternative", "noise", "gold"], ["gold"], ["alternative"]) == {
        "recall_at_10": 1.0, "mrr": 1.0, "hits_at_1": 1.0,
    }
    assert retrieval_metrics(["alternative"], ["gold"], ["alternative"]) == {
        "recall_at_10": 0.0, "mrr": 1.0, "hits_at_1": 1.0,
    }


def test_loader_retains_exclusion_audit_and_filters_scored_questions(corpus):
    root, path, data = corpus
    excluded = dict(data["questions"][0], id="excluded", type="single", gold=["e"],
                    evidence=[{"item_id": "e", "quote": "This"}],
                    exclude_from_scoring=True, exclusion_reason="Invalid probe")
    data["questions"].append(excluded)
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_dataset("real-v2", split="dev", background=0, root=root)
    assert [q["id"] for q in loaded["questions"]] == ["dev"]
    assert loaded["excluded_questions"] == [excluded]
    assert "e" in loaded["selected_item_ids"]
    assert loaded["questions"][0]["acceptable_evidence"] == ["d"]


@pytest.mark.parametrize("change,match", [
    ("gold", "distinct from gold"),
    ("distractor", "cannot be a distractor"),
    ("unknown", "question item"),
    ("cross_split", "gold versus evidence overlap"),
    ("reason", "exclusion_reason"),
    ("date", "requires exclude_from_scoring"),
])
def test_loader_rejects_invalid_repair_annotations(corpus, change, match):
    root, path, data = corpus
    q = data["questions"][0]
    if change == "gold":
        q["acceptable_evidence"] = ["a"]
    elif change == "distractor":
        q["acceptable_evidence"] = ["c"]
    elif change == "unknown":
        q["acceptable_evidence"] = ["missing"]
    elif change == "cross_split":
        q["acceptable_evidence"] = ["b"]
    elif change == "reason":
        q["exclude_from_scoring"] = True
        q["exclusion_reason"] = "   "
    else:
        q["date_order_unavailable"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_dataset("real-v2", split="dev", background=0, root=root)


def test_actual_repaired_corpus_scored_counts_and_exclusions():
    from collections import Counter

    for split, expected in [("dev", [8, 6, 6, 4]), ("test", [15, 17, 13, 10])]:
        loaded = load_dataset("real-v2", split=split, background=0)
        counts = Counter(q["type"] for q in loaded["questions"])
        assert [counts[t] for t in ["single", "multi_hop", "time_sensitive", "freshness"]] == expected
        assert all(q["exclusion_reason"] for q in loaded["excluded_questions"])
        assert all(not q.get("exclude_from_scoring") for q in loaded["questions"])
        assert all(set(q.get("acceptable_evidence", [])) <= set(loaded["selected_item_ids"])
                   for q in loaded["questions"])


@pytest.mark.parametrize("change,error", [
    ("gold", "acceptable_evidence overlaps gold"),
    ("unknown", "id not in manifest"),
    ("reason", "excluded question needs exclusion_reason"),
    ("overlap", "split_overlap organisation not found"),
])
def test_validator_rejects_invalid_new_fields(tmp_path, monkeypatch, capsys, change, error):
    module = runpy.run_path(str(ROOT / "scripts/realdata/check_questions.py"))
    data = json.loads((ROOT / "src/omnistream/eval/corpus/real-v2-questions.json").read_text(encoding="utf-8"))
    q = data["questions"][0]
    if change == "gold":
        q["acceptable_evidence"] = [q["gold"][0]]
    elif change == "unknown":
        q["acceptable_evidence"] = ["missing"]
    elif change == "reason":
        q.update(exclude_from_scoring=True, exclusion_reason="")
    else:
        q["split_overlap"] = [{"item": q["gold"][0], "other_split_org": "NoSuchOrganisation123"}]
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    module["main"].__globals__["QFILE"] = path
    monkeypatch.setattr(sys, "argv", ["check_questions.py"])
    assert module["main"]() == 1
    assert error in capsys.readouterr().out
