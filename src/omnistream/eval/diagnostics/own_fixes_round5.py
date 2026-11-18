"""Frozen eval-v2 rerank benchmark. Use --trace for single-question interventions."""

import json
import os
import shutil
import sys
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

from openai.resources.chat.completions import AsyncCompletions, Completions

from omnistream.config import Settings
from omnistream.embeddings import EmbeddingService
from omnistream.eval.diagnostics.own_fixes import fixed_routes
from omnistream.eval.diagnostics.own_fixes_round3 import forbidden
from omnistream.eval.diagnostics.run import DATA, GROUPS, IDS, SNAP, read
from omnistream.eval.metrics import retrieval_metrics
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.classic import ClassicRetriever, make_chroma_client
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm import pipeline
from omnistream.retrieval.own_algorithm.passages import PassageSource
from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever
from omnistream.retrieval.own_algorithm.rerank import local_encoder

OUT = Path("data/diagnostics/own-fixes-round5")
MODES = ("round3", "passage_specificity")


def measure(graph, embeddings, classic, frozen):
    routes = fixed_routes()
    source = PassageSource(classic, graph)
    retrievers = {
        mode + suffix: OwnRetriever(
            graph,
            embeddings,
            reranker=encoder,
            now=lambda: frozen,
            half_lives=dict(zip(GROUPS, (3, 30, 365))),
            passage_source=source if mode != "round3" else None,
            specificity_restart=mode == "passage_specificity",
        )
        for suffix, encoder in (("", None), ("+rerank", local_encoder))
        for mode in MODES
    }
    retrievers.update(
        {
            "classic": classic,
            "classic+rerank": ClassicRetriever(
                classic.client, embeddings, reranker=local_encoder
            ),
        }
    )
    trace = "--trace" in sys.argv
    if not trace:
        local_encoder().predict([("warmup", "warmup")], show_progress_bar=False)
    for question in DATA["questions"]:
        if trace and question["type"] != "single":
            continue
        raw, origin = routes[question["id"]]
        scope = raw.get("time_scope")
        if scope:
            scope = TimeScope(
                **{
                    k: datetime.fromisoformat(v) if v else None
                    for k, v in scope.items()
                }
            )
        gold = {IDS[g] for g in question["gold"]}
        for routing, bubbles in (("current", raw["bubbles"]), ("oracle", GROUPS)):
            options = {
                "bubbles": bubbles,
                "time_scope": scope,
                "excluded_bubbles": raw.get("excluded_bubbles", ()),
            }
            if trace:
                yield from trace_question(
                    question, routing, options, retrievers, gold, raw["bubbles"]
                )
                continue
            for mode, retriever in retrievers.items():
                start = perf_counter()
                if mode.startswith("classic"):
                    result = retriever.retrieve(
                        question["question"],
                        bubbles=[
                            b for b in bubbles if b not in options["excluded_bubbles"]
                        ],
                        time_scope=scope,
                    )
                    items = (c.item_id for c in result.chunks)
                else:
                    result = retriever.retrieve(question["question"], **options)
                    items = (
                        i
                        for f in result.facts
                        for i in (f.fact.item_id, *f.fact.item_ids)
                    )
                latency = (perf_counter() - start) * 1000
                ids = list(dict.fromkeys(items))
                recall = len(gold.intersection(ids)) / len(gold)
                yield dict(
                    question_id=question["id"],
                    type=question["type"],
                    routing=routing,
                    route_source=origin,
                    variant=mode,
                    latency_ms=latency,
                    recall_any=recall,
                    full_coverage=int(recall == 1),
                    **retrieval_metrics(ids, gold),
                    retrieved_item_ids=ids,
                    seed_ids=[s.id for s in result.seeds],
                )
        print(question["id"], flush=True)


def trace_question(question, routing, options, retrievers, gold, recorded_bubbles):
    # Clamp only the PageRank vector at the input to fact scoring.
    original = pipeline.score_facts
    baseline = {}
    baseline_ranks = {}
    pool = set()
    original_fuse = pipeline.fuse_facts
    modes = [
        "round3",
        "no_confidence",
        "passage",
        "passage_specificity",
        "clamped",
        "shared_pool",
    ]
    if routing == "oracle":
        modes.append("recorded_passages")
    for mode in modes:
        mass = {}

        def fusion(candidates, *, mode=mode, **kwargs):
            if mode == "round3":
                pool.update(c.id for c in candidates)
            if mode == "no_confidence":
                candidates = [replace(c, confidence=1.0) for c in candidates]
            if mode == "shared_pool":
                candidates = [c for c in candidates if c.id in pool]
            if mode == "round3":
                all_fused = original_fuse(candidates, **{**kwargs, "top_n": None})
                baseline_ranks.update((f.fact.id, f.ranks) for f in all_fused)
                return all_fused[: kwargs["top_n"]]
            return original_fuse(candidates, **kwargs)

        def scoring(graph, ranks, query, embeddings, *, mode=mode, mass=mass):
            if mode == "round3":
                baseline.update(ranks)
            if mode == "clamped":
                ranks = baseline
            for f in graph.facts:
                mass[f.id] = (
                    ranks.get(f.subject_id, 0) + ranks.get(f.object_id, 0)
                ) / 2
            return original(graph, ranks, query, embeddings)

        retriever = retrievers[
            "round3" if mode in ("round3", "no_confidence") else "passage_specificity"
        ]

        with ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, "score_facts", scoring))
            stack.enter_context(patch.object(pipeline, "fuse_facts", fusion))
            if mode == "passage":
                stack.enter_context(
                    patch.object(retriever, "specificity_restart", False)
                )
            if mode == "recorded_passages":
                source = retriever.passage_source
                original_seeds = source.seeds
                stack.enter_context(
                    patch.object(
                        source,
                        "seeds",
                        lambda q, bs, scope, original_seeds=original_seeds: (
                            original_seeds(
                                q, [b for b in bs if b in recorded_bubbles], scope
                            )
                        ),
                    )
                )

            result = retriever.retrieve(question["question"], **options)
        facts = []
        for scored in result.facts:
            fact = scored.fact
            hit = bool(gold.intersection([fact.item_id, *fact.item_ids]))
            facts.append(
                {
                    "text": fact.text,
                    "id": fact.id,
                    "ranks": scored.ranks,
                    "gold": hit,
                    "baseline_pool": fact.id in pool,
                    "baseline_ranks": baseline_ranks.get(fact.id),
                    "baseline_mass": (
                        baseline.get(fact.subject_id, 0)
                        + baseline.get(fact.object_id, 0)
                    )
                    / 2,
                    "mass": mass[fact.id],
                }
            )
            if hit:
                break
        yield {
            "question": question["id"],
            "routing": routing,
            "variant": mode,
            "facts": facts,
            "seeds": [s.name for s in result.seeds],
        }


def summary(rows):
    """Markdown results with paired reranking overhead for each route and type."""
    variants = (
        "round3",
        "round3+rerank",
        "passage_specificity",
        "passage_specificity+rerank",
        "classic",
        "classic+rerank",
    )
    kinds = ("overall", "single", "multi_hop", "time_sensitive", "freshness")
    index = {(r["routing"], r["variant"], r["question_id"]): r for r in rows}
    expected = {
        (route, variant, q["id"])
        for route in ("current", "oracle")
        for variant in variants
        for q in DATA["questions"]
    }
    if index.keys() != expected or len(rows) != len(expected):
        raise ValueError("Incomplete or duplicated benchmark cells")
    yield "| Routes | Variant | Type | Recall-any | R@10 | Full | MRR | Hits@1 | Freshness MRR | Mean ms | Added ms |"
    yield "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    for route in ("current", "oracle"):
        for kind in kinds:
            for variant in variants:
                cells = [
                    index[route, variant, q["id"]]
                    for q in DATA["questions"]
                    if kind == "overall" or q["type"] == kind
                ]
                recall, at10, mrr, hit, ms = (
                    mean(r[key] for r in cells)
                    for key in (
                        "recall_any",
                        "recall_at_10",
                        "mrr",
                        "hits_at_1",
                        "latency_ms",
                    )
                )
                full = sum(r["full_coverage"] for r in cells)
                fresh = [r["mrr"] for r in cells if r["type"] == "freshness"]
                fmrr = f"{mean(fresh):.3f}" if fresh else "-"
                base = variant.removesuffix("+rerank")
                delta = ms - mean(
                    index[route, base, r["question_id"]]["latency_ms"] for r in cells
                )
                added = f"{delta:+.0f}" if variant != base else "-"
                yield (
                    f"| {route} | {variant} | {kind} | {recall:.3f} | {at10:.3f} | "
                    f"{full}/{len(cells)} | {mrr:.3f} | {hit:.3f} | {fmrr} | {ms:.0f} | {added} |"
                )


def main():
    out = Path(os.environ.get("OMNI_ROUND5_OUTPUT_DIR", OUT))
    if "--summary" in sys.argv:
        rows = [
            json.loads(line)
            for line in (out / "offline.jsonl").read_text().splitlines()
        ]
        print("\n".join(summary(rows)))
        return
    os.environ["HF_HUB_OFFLINE"] = "1"
    cfg = Settings(_env_file=None)
    frozen = datetime.fromisoformat(read("metadata")[0]["time"])
    out.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(Completions, "create", forbidden),
        patch.object(AsyncCompletions, "create", forbidden),
        TemporaryDirectory() as tmp,
    ):
        copied = shutil.copytree(SNAP / "chroma", Path(tmp) / "chroma")
        client = make_chroma_client(copied)
        graph = Neo4jGraphStore.from_settings(cfg)
        graph.exact_search = True
        graph.now = lambda: frozen
        embeddings = EmbeddingService(cfg)
        classic = ClassicRetriever(client, embeddings)
        try:
            with (
                out / ("trace.jsonl" if "--trace" in sys.argv else "offline.jsonl")
            ).open("w", encoding="utf-8") as journal:
                for row in measure(graph, embeddings, classic, frozen):
                    journal.write(json.dumps(row) + "\n")
                    journal.flush()
        finally:
            graph.driver.close()
            client.close()


if __name__ == "__main__":
    main()
