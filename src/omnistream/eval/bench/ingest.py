"""Bench ingestion: benchmark passages loaded directly into the retrievers' indexes.

Design (docs/eval/GRAPHRAG_EVAL_PLAN.md sections 8 and 8b):

* All sampled questions' passages form ONE shared corpus, ingested into ONE
  dedicated bubble (``Bench``) whose ``group_id`` equals the snapshot name, so
  Graphiti episodes, Chroma chunks and graph facts all live in a single
  group and bubble routing is never a confound.
* The LLM bubble router is bypassed entirely: items enter intake with
  ``bubble_ids_override`` (the existing fixed-assignment path in
  ``ingest/pipeline.py``), which also records ``route_confidence`` 1.0.
* Every passage gets the SAME fixed ``published_at`` and credibility, so the
  recency and confidence RRF signals are constant and drop out of fact fusion
  (``retrieval/own_algorithm/fact_fusion.drop_constant``).
* Item text is ``title + "\\n" + text`` (the corpus doc form the gold mapping
  uses), and the bench passage id survives in the source id and the snapshot
  mapping, so any retrieved fact/chunk maps back to its passage.
* Resumable: passages recorded as written in ``bench_manifest.json`` are
  skipped; a passage interrupted mid-write has no status yet and is simply
  re-run (intake dedup returns the existing item).
* Usage metering: the shared ``eval.resources.UsageMeter`` records tokens and
  cost per ``bench_ingestion:<passage_id>`` stage, stored in the manifest.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from omnistream.embed import SentenceTransformerEmbedder
from omnistream.graph.writer import build_graph_writer
from omnistream.ingest.intake import Intake
from omnistream.ingest.pipeline import ItemProcessor
from omnistream.ingest.queue import WorkerPool
from omnistream.llm import build_llm_client
from omnistream.models import ApiMapping, Bubble, RawItem, Source
from omnistream.router.bubbles import BubbleService

from .datasets import DATASET_ALIASES, DATASET_FILES, Benchmark, load_benchmark

BENCH_BUBBLE_NAME = "Bench"
BENCH_BUBBLE_DESCRIPTION = (
    "Benchmark corpus of HippoRAG passages (MuSiQue, 2WikiMultiHopQA or "
    "HotpotQA) loaded directly for retrieval evaluation. Every passage shares "
    "one fixed timestamp and credibility, so recency and confidence ranking "
    "signals stay constant and drop out."
)
FIXED_PUBLISHED_AT = "2026-01-01T00:00:00Z"
FIXED_CREDIBILITY = 0.8
BENCH_MANIFEST_NAME = "bench_manifest.json"


def default_bench_snapshot(dataset: str, n: int | None, seed: int) -> str:
    return f"bench-{dataset}-n{n if n is not None else 'all'}-s{seed}"


def bench_dataset(name: str) -> str:
    canonical = DATASET_ALIASES.get(name, name)
    if canonical not in DATASET_FILES:
        raise ValueError(
            f"unknown benchmark dataset {name!r}; expected one of "
            + ", ".join(sorted(set(DATASET_FILES) | set(DATASET_ALIASES)))
        )
    return canonical


def _parse_published_at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def bench_manifest_path(snapshot_dir: str | Path) -> Path:
    return Path(snapshot_dir) / BENCH_MANIFEST_NAME


def load_bench_manifest(snapshot_dir: str | Path) -> dict | None:
    path = bench_manifest_path(snapshot_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_bench_manifest(path: str | Path, manifest: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temp.replace(path)


@dataclass
class BenchIngestPlan:
    """Pure planning output: nothing here touches the DB or any provider."""

    total: int
    written: int
    skipped: int
    pending: list[str]
    selected: list[str]


def plan_ingest(
    benchmark: Benchmark, manifest: dict | None, limit_passages: int | None = None
) -> BenchIngestPlan:
    """Decide which passages still need ingestion.

    ``written`` passages are skipped; entries recorded as ``failed`` or
    ``unsorted`` are skipped and counted (re-ingestion needs a new snapshot);
    entries without a status (interrupted mid-write) stay pending and are
    safely re-run through intake dedup. ``limit_passages`` bounds the number
    of NEW passages ingested by this invocation, so a 30-passage cost probe
    followed by a full run (or by ``--limit-passages 50``) resumes cleanly.
    """
    entries = (manifest or {}).get("passages", {})
    written: list[str] = []
    skipped: list[str] = []
    pending: list[str] = []
    for passage in benchmark.passages:
        status = entries.get(passage.id, {}).get("status")
        if status == "written":
            written.append(passage.id)
        elif status in ("unsorted", "failed"):
            skipped.append(passage.id)
        else:
            pending.append(passage.id)
    selected = pending if limit_passages is None else pending[:limit_passages]
    return BenchIngestPlan(
        total=len(benchmark.passages),
        written=len(written),
        skipped=len(skipped),
        pending=pending,
        selected=selected,
    )


def passage_text(passage) -> str:
    """Corpus doc form used by the gold mapping: title + newline + text."""
    return passage.title + "\n" + passage.text


async def _print_progress(message: str) -> None:
    print(message, flush=True)


class BenchIngestor:
    """Build a bench snapshot directory through the real ingestion machinery.

    The snapshot directory mirrors a regular snapshot: ``state.db``, ``raw/``,
    ``chroma/`` and Graphiti episodes under the bubble ``group_id``; only the
    routing step is replaced by fixed direct assignment.
    """

    def __init__(
        self,
        settings,
        repo,
        benchmark: Benchmark,
        snapshot: str,
        *,
        n: int | None,
        seed: int,
        corpus: str,
        group_id: str | None = None,
        published_at: str = FIXED_PUBLISHED_AT,
        credibility: float = FIXED_CREDIBILITY,
        progress=None,
    ) -> None:
        from omnistream.eval.snapshot import snapshot_path

        self.settings, self.repo = settings, repo
        self.benchmark, self.name = benchmark, snapshot
        self.n, self.seed, self.corpus = n, seed, corpus
        self.progress = progress or _print_progress
        self.path = snapshot_path(settings, snapshot)
        self.path.mkdir(parents=True, exist_ok=True)
        self.manifest_path = bench_manifest_path(self.path)
        self.group_id = group_id or snapshot
        self.published_at = _parse_published_at(published_at)
        self.credibility = credibility
        self.passage_by_id = {p.id: p for p in benchmark.passages}
        self.local_settings = settings.model_copy(
            update={"data_dir": str(self.path), "llm_max_concurrency": 2}
        )
        self.manifest = load_bench_manifest(self.path) or self._fresh_manifest()
        if not self.manifest_path.exists():
            # Persist the binding immediately so an interrupted first run still
            # leaves a resumable, verifiable manifest behind.
            save_bench_manifest(self.manifest_path, self.manifest)
        for key, expected in (
            ("dataset", benchmark.name),
            ("n", n),
            ("seed", seed),
            ("corpus", corpus),
            ("group_id", self.group_id),
        ):
            if self.manifest.get(key) != expected:
                raise ValueError(
                    f"bench snapshot binding mismatch for {key}: "
                    f"manifest={self.manifest.get(key)!r} requested={expected!r}; "
                    "use a new --snapshot name"
                )
        self.meter = None
        self.writer = None
        self.llm = None
        self.embedder = SentenceTransformerEmbedder(settings)

    def _fresh_manifest(self) -> dict:
        return {
            "kind": "bench-ingest",
            "dataset": self.benchmark.name,
            "n": self.n,
            "seed": self.seed,
            "corpus": self.corpus,
            "question_ids": [q.id for q in self.benchmark.questions],
            "question_count": len(self.benchmark.questions),
            "unmatched_gold": self.benchmark.unmatched_gold,
            "passage_count": len(self.benchmark.passages),
            "group_id": self.group_id,
            "bubble_name": BENCH_BUBBLE_NAME,
            "published_at": FIXED_PUBLISHED_AT,
            "credibility": self.credibility,
            "construction_started_at": time.time(),
            "passages": {},
        }

    async def initialize(self) -> None:
        """Create the Bench bubble and the real writer/processor/queue wiring."""
        service = BubbleService(self.repo, self.embedder)
        if await self.repo.get_bubble(self.group_id) is None:
            await service.create(
                Bubble(
                    id=self.group_id,
                    name=BENCH_BUBBLE_NAME,
                    description=BENCH_BUBBLE_DESCRIPTION,
                    half_life_days=365,
                )
            )
        self.llm = build_llm_client(self.local_settings)
        self.writer = await build_graph_writer(
            self.local_settings, self.repo, self.embedder, self.llm
        )
        # The router is never used: bench items always carry bubble_ids_override.
        processor = ItemProcessor(self.repo, None, self.writer)
        self.pool = WorkerPool(
            self.repo, processor.process_item, workers=1, max_attempts=3, backoff_base=1
        )
        # No pre-filter: benchmark paragraphs may be shorter than the feed limit.
        self.intake = Intake(self.repo, str(self.path), 0)

    def source_for(self, passage) -> Source:
        return Source(
            id=f"{self.group_id}--{passage.id}",
            type="api",
            url=f"bench://{self.benchmark.name}/{passage.id}",
            credibility=self.credibility,
            api_mapping=ApiMapping(
                items="$[*]", body="$.text", url="$.url", date="$.published_at"
            ),
            bubble_ids=[],
            poll_interval=self.settings.poll_interval_minutes * 60,
            # One-shot bulk load must never hit the hourly cap.
            max_items_per_hour=1_000_000,
        )

    async def ingest_passage(self, passage) -> dict:
        from ..resources import stage

        entry = self.manifest["passages"].get(passage.id)
        if entry and entry.get("status") in ("written", "unsorted", "failed"):
            return entry
        stage_token = stage.set("bench_ingestion:" + passage.id)
        source = self.source_for(passage)
        await self.repo.upsert_source(source)
        text = passage_text(passage)
        raw = RawItem(
            source_id=source.id,
            url=source.url + "?snapshot=" + self.name,
            title=passage.title,
            text=text,
            published_at=self.published_at,
            # Direct assignment: intake stores these and ItemProcessor
            # bypasses the router with route_confidence 1.0.
            bubble_ids_override=[self.group_id],
        )
        start = time.time()
        row = await self.intake.accept(raw, source, text.encode(), "txt")
        if row is None:
            candidates = [
                r for r in await self.repo.list_items() if r.source_id == source.id
            ]
            if not candidates:
                raise RuntimeError("deduplicated item has no record")
            row = candidates[0]
        self.manifest["passages"][passage.id] = {
            "runtime_id": row.id,
            "source_id": source.id,
            "injected_at": start,
        }
        save_bench_manifest(self.manifest_path, self.manifest)
        await self.repo.requeue_running_jobs()
        for _ in range(300):
            await self.pool.run_once()
            jobs = [j for j in await self.repo.list_jobs() if j.item_id == row.id]
            if jobs[-1].state in ("done", "failed"):
                break
            await asyncio.sleep(0.5)
        stored = await self.repo.get_item(row.id)
        entry = self.manifest["passages"][passage.id]
        entry.update(
            status=stored.status,
            bubbles=stored.bubble_ids,
            route_confidence=stored.route_confidence,
            write_lag_seconds=time.time() - start
            if stored.status == "written"
            else None,
        )
        if getattr(self, "meter", None):
            entry["usage"] = self.meter.summary().get("bench_ingestion:" + passage.id)
        save_bench_manifest(self.manifest_path, self.manifest)
        stage.reset(stage_token)
        return entry

    def running_usage(self) -> dict:
        if not getattr(self, "meter", None):
            return {"tokens": 0, "cost_usd": 0.0, "calls": 0}
        values = list(self.meter.summary().values())
        cost = (
            sum(v["cost_usd"] for v in values)
            if values and all(v["cost_usd"] is not None for v in values)
            else None
        )
        return {
            "tokens": sum(v["tokens"] for v in values),
            "cost_usd": cost,
            "calls": sum(v["calls"] for v in values),
        }

    async def run(self, limit_passages: int | None = None) -> dict:
        plan = plan_ingest(self.benchmark, self.manifest, limit_passages)
        total = len(plan.selected)
        await self.progress(
            f"Bench ingest {self.name}: {plan.written} already written, "
            f"{plan.skipped} skipped, ingesting {total} of {len(plan.pending)} pending"
        )
        for index, passage_id in enumerate(plan.selected, 1):
            passage = self.passage_by_id[passage_id]
            entry = await self.ingest_passage(passage)
            usage = self.running_usage()
            cost = usage["cost_usd"]
            await self.progress(
                f"[{index}/{total}] {passage_id}: {entry.get('status')} | "
                f"running total: {usage['tokens']} tokens, "
                + (
                    f"${cost:.4f}"
                    if cost is not None
                    else "cost not reported by provider"
                )
            )
        final = plan_ingest(self.benchmark, self.manifest, None)
        usage = self.running_usage()
        cost = usage["cost_usd"]
        summary = {
            "snapshot": self.name,
            "group_id": self.group_id,
            "passages_total": final.total,
            "passages_written": final.written,
            "passages_skipped": final.skipped,
            "passages_pending": len(final.pending),
            "usage": usage,
        }
        await self.progress(
            f"Bench ingest complete: {final.written}/{final.total} written, "
            f"{len(final.pending)} pending | total {usage['tokens']} tokens, "
            + (f"${cost:.4f}" if cost is not None else "cost not reported")
        )
        return summary

    async def close(self) -> None:
        if self.writer is not None:
            await self.writer._graphiti.close()
            await asyncio.to_thread(self.writer.chunks._client.close)
        if self.llm is not None:
            await self.llm._client.close()


async def run_bench_ingest_cli(settings, args) -> int:
    """``omni eval bench-ingest`` entry: plan, then ingest into the snapshot."""
    dataset = bench_dataset(args.dataset)
    snapshot = args.snapshot or default_bench_snapshot(dataset, args.n, args.seed)
    corpus = args.corpus or "slice"
    benchmark = load_benchmark(
        dataset,
        root=Path(args.bench_root),
        n=args.n,
        seed=args.seed,
        corpus=corpus,
    )
    from omnistream.eval.snapshot import snapshot_path

    directory = snapshot_path(settings, snapshot)
    manifest = load_bench_manifest(directory)
    plan = plan_ingest(benchmark, manifest, args.limit_passages)
    if args.dry_run:
        print(
            f"DRY RUN {snapshot}: dataset={dataset} n={args.n} seed={args.seed} "
            f"corpus={corpus}"
        )
        print(
            f"questions: {len(benchmark.questions)}; corpus passages: {plan.total}; "
            f"unmatched gold docs: {benchmark.unmatched_gold}"
        )
        print(
            f"already written: {plan.written}; skipped (failed/unsorted): "
            f"{plan.skipped}; pending: {len(plan.pending)}"
        )
        print(
            "this run would ingest: "
            + (
                f"{len(plan.selected)} passage(s)"
                if args.limit_passages is not None
                else f"all {len(plan.pending)} pending passage(s)"
            )
            + " (no LLM calls were made)"
        )
        return 0

    from omnistream.db import Repository

    repo = Repository.from_path(str(directory / "state.db"), settings=settings)
    ingestor = BenchIngestor(
        settings,
        repo,
        benchmark,
        snapshot,
        n=args.n,
        seed=args.seed,
        corpus=corpus,
    )
    from ..resources import UsageMeter

    try:
        with UsageMeter() as meter:
            ingestor.meter = meter
            await ingestor.initialize()
            await ingestor.run(limit_passages=args.limit_passages)
    finally:
        await ingestor.close()
        await repo.close()
    return 0
