"""Retrieval-only development check for the own retriever (no LLM calls).

Scores passage R@2/R@5 and all-recall AR@2/AR@5 (HippoRAG 1 Tables 2 and 6)
on DEVELOPMENT questions of a full-corpus bench snapshot: a seeded sample of
the released questions that excludes every question of that snapshot's test
run, so tuning never sees test questions.

    python scripts/dev_retrieval.py --dataset 2wiki --n 100 [--tag name]

Retriever settings come from the environment (OMNI_OWN_*), as in bench-qa.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.eval import evidence_ids
from omnistream.eval.bench.datasets import load_benchmark
from omnistream.eval.bench.qa import passage_ids
from omnistream.retrieval.runtime import build_query_runtime

ROOT = Path(__file__).resolve().parents[1]


def dev_questions(dataset: str, snapshot_dir: Path, n: int, seed: int):
    bench = load_benchmark(dataset, root=ROOT / "data/bench/hipporag", corpus="full")
    test_ids: set[str] = set()
    for meta in (snapshot_dir / "bench_runs").glob("*/metadata.json"):
        test_ids.update(json.loads(meta.read_text(encoding="utf-8"))["question_ids"])
    pool = [q for q in bench.questions if q.id not in test_ids]
    picked = random.Random(seed).sample(pool, min(n, len(pool)))
    return bench, picked, len(test_ids)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag", default="current")
    ap.add_argument(
        "--split", choices=("dev", "test"), default="dev",
        help="test = the 200 questions of the snapshot's test run (final check only)",
    )
    args = ap.parse_args()

    snapshot = f"bench-{args.dataset}-n200-full-oie"
    snapshot_dir = ROOT / "data/snapshots" / snapshot
    manifest = json.loads((snapshot_dir / "bench_manifest.json").read_text(encoding="utf-8"))
    mapping = {e["runtime_id"]: pid for pid, e in manifest["passages"].items()}
    group = manifest["group_id"]
    bench, questions, n_test = dev_questions(args.dataset, snapshot_dir, args.n, args.seed)
    if args.split == "test":
        ids = []
        for meta in sorted((snapshot_dir / "bench_runs").glob("*/metadata.json")):
            ids = json.loads(meta.read_text(encoding="utf-8"))["question_ids"]
        by_id = {q.id: q for q in bench.questions}
        questions = [by_id[i] for i in ids]

    settings = Settings().model_copy(update={"data_dir": str(snapshot_dir)})
    repo = Repository.from_path(str(snapshot_dir / "state.db"), settings=settings)
    runtime = build_query_runtime(settings, repo)
    own = runtime.dispatcher.retrievers["own"]

    rows = []
    started = time.perf_counter()
    for q in questions:
        result = own.retrieve(q.question, bubbles=[group])
        ranked = passage_ids(evidence_ids(SimpleNamespace(retrieval=result, multi_hop=None)), mapping)
        gold = set(q.gold_passage_ids) if hasattr(q, "gold_passage_ids") else set(q.supporting_ids)
        row = {"id": q.id, "top5": ranked[:5], "gold": sorted(gold)}
        for k in (2, 5):
            top = set(ranked[:k])
            row[f"R@{k}"] = len(gold & top) / len(gold) if gold else 0.0
            row[f"AR@{k}"] = float(gold <= top) if gold else 0.0
        rows.append(row)
    elapsed = time.perf_counter() - started

    summary = {k: round(100 * statistics.fmean(r[k] for r in rows), 1)
               for k in ("R@2", "R@5", "AR@2", "AR@5")}
    out = {"dataset": args.dataset, "tag": args.tag, "split": args.split,
           "n": len(rows), "seed": args.seed,
           "excluded_test_questions": n_test, "summary": summary,
           "seconds_per_question": round(elapsed / max(1, len(rows)), 2),
           "ircot_failures": getattr(own, "failures", None),
           "ircot_steps": getattr(own, "steps", None), "rows": rows}
    folder = "dev" if args.split == "dev" else "test-retrieval"
    dest = ROOT / "docs/eval/bench" / folder / f"{args.dataset}-{args.tag}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(args.dataset, args.tag, summary, f"{out['seconds_per_question']}s/q",
          f"ircot_failures={out['ircot_failures']} steps={out['ircot_steps']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
