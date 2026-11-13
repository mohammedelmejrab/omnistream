"""Offline regression for completed snapshots containing router misses."""

import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from omnistream.config import Settings
from omnistream.eval import measure_freshness
from omnistream.eval.metrics import ingestion_outcomes, ingestion_routing_metrics
from omnistream.eval.report import write_report
from omnistream.eval.snapshot import SnapshotBuilder, item_digest, save


@pytest.mark.parametrize(
    "bad",
    [None, "failed", "queued", "missing", "job_failed", "job_queued", "job_missing"],
)
async def test_completed_unsorted_snapshot_freezes_without_ingestion(
    tmp_path, monkeypatch, bad
):
    data = {
        "version": "2-real",
        "items": [{"id": str(i), "freshness": i >= 71} for i in range(76)],
    }
    entries = {
        str(i): {
            "runtime_id": str(i),
            "status": "written" if i < 74 else "unsorted",
            "bubbles": [],
            "route_confidence": 1 if i < 74 else [0.1, 0.45][i - 74],
        }
        for i in range(76)
    }
    stored = [
        NS(id=k, status=e["status"], route_confidence=e["route_confidence"])
        for k, e in entries.items()
    ]
    jobs = [NS(item_id=k, state="done") for k in entries]
    if bad == "missing":
        stored.pop()
    elif bad == "job_missing":
        jobs.pop()
    elif bad and bad.startswith("job_"):
        jobs[-1].state = bad.removeprefix("job_")
    elif bad:
        entries["75"]["status"] = stored[-1].status = bad
    repo = NS(
        list_items=AsyncMock(return_value=stored),
        list_jobs=AsyncMock(return_value=jobs),
    )
    monkeypatch.setattr(
        "omnistream.eval.snapshot.SentenceTransformerEmbedder", lambda _: None
    )
    verify = AsyncMock()
    monkeypatch.setattr(
        "omnistream.eval.snapshot.verify_item_store", lambda *args: item_digest(data)
    )
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    builder = SnapshotBuilder(settings, repo, data, "resume", AsyncMock())
    builder.manifest.update(
        items=entries, freshness={str(i): {} for i in range(71, 76)}
    )
    save(builder.manifest_path, builder.manifest)
    builder = SnapshotBuilder(settings, repo, data, "resume", AsyncMock())
    builder.ingest = verify
    if bad:
        with pytest.raises(ValueError, match="incomplete"):
            await builder.verify_frozen()
        return
    assert await builder.verify_frozen()
    await builder.base()
    await measure_freshness(builder, data, None, None)
    verify.assert_not_awaited()
    manifest = json.loads(builder.manifest_path.read_text())
    assert manifest["frozen"]
    assert manifest["unsorted_item_ids"] == {
        "74": {"route_confidence": 0.1},
        "75": {"route_confidence": 0.45},
    }
    assert await builder.verify_frozen()


def test_unsorted_metrics_and_report(tmp_path):
    entries = {
        "a": {"status": "written", "bubbles": ["r"]},
        "b": {"status": "unsorted", "bubbles": ["r"], "route_confidence": 0.1},
        "c": {"status": "unsorted", "bubbles": [], "route_confidence": 0.45},
    }
    items = [{"id": key, "bubbles": ["Research"]} for key in entries]
    routing = ingestion_routing_metrics(items, entries, {"Research": "r"})
    assert routing["ingestion_routing_accuracy"] == 1 / 3
    assert routing["ingestion_primary_label_recall"] == 1 / 3
    assert routing["ingestion_wrong_routing_rate"] == 2 / 3
    outcomes = ingestion_outcomes(
        entries,
        [
            {"id": "rq-d-008", "gold": ["b"], "acceptable_evidence": ["c"]},
            {"id": "other", "gold": ["a"]},
        ],
    )
    assert outcomes["ingestion_unsorted_count"] == 2
    assert outcomes["ingestion_unsorted_item_ids"]["b"]["gold_question_ids"] == [
        "rq-d-008"
    ]
    assert outcomes["ingestion_unsorted_item_ids"]["c"][
        "acceptable_evidence_question_ids"
    ] == ["rq-d-008"]
    report, *_ = write_report(tmp_path, "test", "stamp", {}, [], outcomes, {})
    text = Path(report).read_text(encoding="utf-8")
    assert "1 written, 2 unsorted; gold items unsorted: 1 (rq-d-008)" in text
    assert '"route_confidence": 0.45' in text
