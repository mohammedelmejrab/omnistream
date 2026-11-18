"""Bench ingestion: planning, resume, fixed metadata, id mapping (all offline).

The ingestor test exercises the REAL intake -> queue -> ItemProcessor path
with direct bubble assignment; only the graph writer, LLM and embedder are
replaced with fakes, so no provider or Neo4j is ever touched.
"""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.eval.bench import ingest as bench_ingest
from omnistream.eval.bench.datasets import load_benchmark
from omnistream.eval.bench.ingest import (
    FIXED_CREDIBILITY,
    FIXED_PUBLISHED_AT,
    BenchIngestor,
    bench_manifest_path,
    default_bench_snapshot,
    load_bench_manifest,
    plan_ingest,
    run_bench_ingest_cli,
)

MUSIQUE_CORPUS = [
    {"title": "Alpha", "text": "Alpha text one."},
    {"title": "Beta", "text": "Beta text with odd whitespace."},
    {"title": "Gamma", "text": "Different gamma text."},
    {"title": "Delta", "text": "Delta text A."},
]

MUSIQUE = [
    {
        "id": "2hop__1_2",
        "paragraphs": [
            {
                "idx": 0,
                "title": "Alpha",
                "paragraph_text": "Alpha text one.",
                "is_supporting": False,
            },
            {
                "idx": 1,
                "title": "Beta",
                "paragraph_text": "Beta text  with odd whitespace.",
                "is_supporting": True,
            },
            {
                "idx": 2,
                "title": "Gamma",
                "paragraph_text": "Gamma gold text.",
                "is_supporting": True,
            },
        ],
        "question": "What is the Beta value?",
        "question_decomposition": [],
        "answer": "yes",
        "answer_aliases": [],
        "answerable": True,
    }
]


def _write_bench(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "musique.json").write_text(json.dumps(MUSIQUE), encoding="utf-8")
    (root / "musique_corpus.json").write_text(
        json.dumps(MUSIQUE_CORPUS), encoding="utf-8"
    )
    return root


def _benchmark(root, corpus="slice"):
    return load_benchmark("musique", root=root, corpus=corpus)


def test_plan_ingest_counts_resume_and_limit(tmp_path):
    _write_bench(tmp_path)
    bench = _benchmark(tmp_path)
    plan = plan_ingest(bench, None)
    assert plan.total == 3  # slice: Alpha (context), Beta, Gamma (gold)
    assert plan.written == 0 and plan.pending == ["musique-0", "musique-1", "musique-2"]
    assert plan.selected == plan.pending

    manifest = {
        "passages": {
            "musique-0": {"status": "written", "runtime_id": "a"},
            "musique-1": {"status": "failed", "runtime_id": "b"},
            # musique-2: interrupted mid-write, no status yet.
            "musique-2": {"runtime_id": "c"},
        }
    }
    plan = plan_ingest(bench, manifest)
    assert plan.written == 1
    assert plan.skipped == 1
    assert plan.pending == ["musique-2"]  # re-run through intake dedup
    assert plan.selected == ["musique-2"]

    plan = plan_ingest(bench, manifest, limit_passages=0)
    assert plan.selected == []
    fresh = plan_ingest(bench, None, limit_passages=2)
    assert fresh.selected == ["musique-0", "musique-1"]


def test_fixed_metadata_and_default_snapshot_name():
    assert FIXED_PUBLISHED_AT == "2026-01-01T00:00:00Z"
    assert FIXED_CREDIBILITY == 0.8
    assert default_bench_snapshot("musique", 100, 0) == "bench-musique-n100-s0"
    assert default_bench_snapshot("2wiki", None, 3) == "bench-2wiki-nall-s3"


async def test_bench_ingestor_fixed_assignment_resume_and_mapping(
    tmp_path, monkeypatch
):
    from tests.conftest import FakeEmbedder

    _write_bench(tmp_path)
    bench = _benchmark(tmp_path)
    settings = Settings(_env_file=None, data_dir=str(tmp_path))

    class FakeClient:
        async def close(self):
            pass

    class FakeLLM:
        def __init__(self, settings):
            self._client = FakeClient()

    class FakeGraphiti:
        async def close(self):
            pass

    writer = bench_ingest  # module under test

    class FakeWriter:
        def __init__(self):
            self.written = []
            self._graphiti = FakeGraphiti()
            self.chunks = NS(_client=NS(close=lambda: None))

        async def write(self, item, text, bubble_ids, source):
            self.written.append(
                {
                    "item_id": item.id,
                    "text": text,
                    "bubbles": tuple(bubble_ids),
                    "credibility": source.credibility,
                    "published_at": item.published_at.isoformat(),
                }
            )

    async def fake_build_graph_writer(settings, repo, embedder, llm):
        return fake.writer

    fake = NS(writer=FakeWriter())
    monkeypatch.setattr(writer, "SentenceTransformerEmbedder", lambda name: FakeEmbedder())
    monkeypatch.setattr(writer, "build_llm_client", lambda settings: FakeLLM(settings))
    monkeypatch.setattr(writer, "build_graph_writer", fake_build_graph_writer)

    directory = tmp_path / "snapshots" / "bench-demo"
    repo = Repository.from_path(str(directory / "state.db"), settings=settings)
    ingestor = BenchIngestor(
        settings, repo, bench, "bench-demo", n=None, seed=0, corpus="slice"
    )
    await ingestor.initialize()
    summary = await ingestor.run(limit_passages=1)
    assert summary["passages_written"] == 1 and summary["passages_total"] == 3

    # Fixed assignment: routed by override, not by the LLM router.
    stored = await repo.list_items()
    assert len(stored) == 1
    row = stored[0]
    assert row.status == "written"
    assert row.bubble_ids == ["bench-demo"]
    assert row.route_confidence == 1.0
    assert row.published_at is not None
    published = (
        row.published_at.replace(tzinfo=None)
        if row.published_at.tzinfo
        else row.published_at
    )
    assert published.isoformat().startswith("2026-01-01T00:00:00")
    source = await repo.get_source(row.source_id)
    assert source.credibility == FIXED_CREDIBILITY
    assert "musique-0" in source.id and "musique-0" in source.url
    assert Path(row.text_path).read_text(encoding="utf-8") == (
        "Alpha\nAlpha text one."
    )
    assert fake.writer.written[0]["bubbles"] == ("bench-demo",)
    assert fake.writer.written[0]["credibility"] == FIXED_CREDIBILITY

    manifest = load_bench_manifest(directory)
    assert manifest["group_id"] == "bench-demo"
    assert manifest["published_at"] == FIXED_PUBLISHED_AT
    assert manifest["question_ids"] == [q.id for q in bench.questions]
    assert set(manifest["passages"]) == {"musique-0"}
    assert manifest["passages"]["musique-0"]["status"] == "written"
    assert manifest["passages"]["musique-0"]["runtime_id"] == row.id

    # Resume: the written passage is skipped, the other two are ingested.
    await ingestor.run()
    assert len(fake.writer.written) == 3
    manifest = load_bench_manifest(directory)
    assert [manifest["passages"][p]["status"] for p in manifest["passages"]] == [
        "written",
        "written",
        "written",
    ]
    calls_before = len(fake.writer.written)
    summary = await ingestor.run()
    assert len(fake.writer.written) == calls_before
    assert summary["passages_written"] == 3 and summary["passages_pending"] == 0

    await ingestor.close()
    await repo.close()

    # A different sampling cannot silently reuse the same snapshot.
    repo = Repository.from_path(str(directory / "state.db"), settings=settings)
    with pytest.raises(ValueError):
        BenchIngestor(
            settings, repo, bench, "bench-demo", n=None, seed=1, corpus="slice"
        )
    await repo.close()


async def test_bench_ingest_cli_dry_run_makes_no_calls(tmp_path, capsys):
    _write_bench(tmp_path)
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    args = NS(
        dataset="musique",
        n=None,
        seed=0,
        corpus="slice",
        snapshot="bench-demo",
        limit_passages=None,
        dry_run=True,
        bench_root=str(tmp_path),
    )
    assert await run_bench_ingest_cli(settings, args) == 0
    out = capsys.readouterr().out
    assert "DRY RUN bench-demo" in out
    assert "corpus passages: 3" in out
    assert "this run would ingest: all 3 pending passage(s)" in out
    # Nothing was created: no manifest, no database.
    assert not (tmp_path / "snapshots" / "bench-demo" / "state.db").exists()
    assert not bench_manifest_path(tmp_path / "snapshots" / "bench-demo").exists()


async def test_bench_ingest_cli_dry_run_reports_existing_progress(tmp_path, capsys):
    _write_bench(tmp_path)
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    directory = tmp_path / "snapshots" / "bench-demo"
    directory.mkdir(parents=True)
    bench_ingest.save_bench_manifest(
        bench_manifest_path(directory),
        {
            "kind": "bench-ingest",
            "dataset": "musique",
            "n": None,
            "seed": 0,
            "corpus": "slice",
            "group_id": "bench-demo",
            "passages": {p.id: {"status": "written"} for p in _benchmark(tmp_path).passages[:2]},
        },
    )
    args = NS(
        dataset="musique",
        n=None,
        seed=0,
        corpus="slice",
        snapshot="bench-demo",
        limit_passages=1,
        dry_run=True,
        bench_root=str(tmp_path),
    )
    await run_bench_ingest_cli(settings, args)
    out = capsys.readouterr().out
    assert "already written: 2" in out
    assert "pending: 1" in out
    assert "this run would ingest: 1 passage(s)" in out
