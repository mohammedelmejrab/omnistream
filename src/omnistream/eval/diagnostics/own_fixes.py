"""Read-only, LLM-blocked paired own-mode ablations on the frozen eval-v2 graph.

Baseline sources are captured before implementation in baseline_sources.json.
No threshold optimization: declared sensitivity runs use fixed nearby defaults.
"""

from __future__ import annotations

import json
import os
import types
from datetime import datetime
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from openai.resources.chat.completions import AsyncCompletions, Completions

from omnistream.config import Settings
from omnistream.embeddings import EmbeddingService
from omnistream.eval.diagnostics.run import (
    DATA,
    GROUPS,
    IDS,
    encode,
    primary_answers,
    read,
)
from omnistream.eval.metrics import retrieval_metrics
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm import fact_fusion, pipeline, seeding

OUT = Path("data/diagnostics/own-fixes")
VARIANTS = {
    "baseline": (False, False, 10, 1, 0.01),
    "F1": (True, False, 10, 1, 0.01),
    "F2": (False, True, 10, 2, 0.01),
    "F1+F2": (True, True, 10, 2, 0.01),
    "fact-k5": (True, True, 5, 2, 0.01),
    "fact-k15": (True, True, 15, 2, 0.01),
    "weight1": (True, True, 10, 1, 0.01),
    "weight3": (True, True, 10, 3, 0.01),
    "cv005": (True, True, 10, 2, 0.005),
    "cv02": (True, True, 10, 2, 0.02),
}


def load_baseline():
    sources = json.loads(
        Path(__file__).with_name("own_fixes_baseline.json").read_text()
    )
    modules = []
    import sys

    for name in ("seeding", "fact_fusion"):
        module = types.ModuleType("_own_baseline_" + name)
        sys.modules[module.__name__] = module
        exec(  # noqa: S102 - execute only the captured local baseline
            compile(sources[name + ".py"], "baseline:" + name, "exec"), module.__dict__
        )
        modules.append(module)
    return modules


def fixed_routes():
    e0 = {
        r["question_id"]: (r["routing"], "E0 own")
        for r in primary_answers()
        if r["experiment"] == "E0" and r["configuration"] == "own" and "routing" in r
    }
    for r in read("routes"):
        if r["repeat"] == 0:
            e0.setdefault(
                r["question_id"], (r["decision"], "E2 repeat0 (E0 own absent)")
            )
    return e0


def settings():
    os.environ["NEO4J_PASSWORD"] = (
        Path(
            "C:/Users/mehme/AppData/Local/Temp/claude/803928835945f44b/3875a788-004a-4920-9803-352914729589/scratchpad/neo4j_pw.txt"
        )
        .read_text()
        .strip()
    )
    return Settings(_env_file=None)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    old_seed, old_fusion = load_baseline()
    cfg = settings()
    frozen = datetime.fromisoformat(read("metadata")[0]["time"])
    graph = Neo4jGraphStore.from_settings(cfg)
    graph.now = lambda: frozen
    embedder = EmbeddingService(cfg)
    # Cache identical read queries across ablations; all results share one clock.
    run = graph._run
    cache = {}

    def cached(query, **kwargs):
        key = query, json.dumps(kwargs, default=encode, sort_keys=True)
        if key not in cache:
            cache[key] = run(query, **kwargs)
        return cache[key]

    graph._run = cached

    def forbidden(*args, **kwargs):
        raise AssertionError("LLM calls forbidden in offline ablation")

    routes = fixed_routes()
    rows = (
        [json.loads(line) for line in (OUT / "offline.jsonl").read_text().splitlines()]
        if (OUT / "offline.jsonl").exists()
        else []
    )
    done = {(r["question_id"], r["routing"], r["variant"]) for r in rows}
    try:
        indices = graph._run(
            "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state RETURN *"
        )
        (OUT / "indices.json").write_text(
            json.dumps([dict(r) for r in indices], default=encode, indent=2)
        )
        with (
            patch.object(Completions, "create", forbidden),
            patch.object(AsyncCompletions, "create", forbidden),
        ):
            for q in DATA["questions"]:
                raw, source = routes[q["id"]]
                scope = raw.get("time_scope")
                scope = (
                    TimeScope(
                        **{
                            k: datetime.fromisoformat(v) if v else None
                            for k, v in scope.items()
                        }
                    )
                    if scope
                    else None
                )
                for routing, groups in (
                    ("current", raw["bubbles"]),
                    ("oracle", GROUPS),
                ):
                    for variant, (f1, f2, fact_k, weight, cv) in VARIANTS.items():
                        if (q["id"], routing, variant) in done:
                            continue
                        stats = {}

                        def seeds(
                            question,
                            query,
                            store,
                            *,
                            f1=f1,
                            groups=groups,
                            stats=stats,
                            fact_k=fact_k,
                            **kwargs,
                        ):
                            if not f1:
                                kwargs.pop("time_scope", None)
                                found = old_seed.seed_entities(
                                    question, query, store, **kwargs
                                )
                            else:
                                entities = store.entities_in(groups)
                                raw_seeds = store.seed_by_embedding(
                                    query, bubbles=groups, top_k=5, min_cosine=0.5
                                )
                                stats["generic_removed_from_original_top5"] = sum(
                                    not seeding.is_named_entity(e) for e, _ in raw_seeds
                                )
                                stats["generic_entities"] = sum(
                                    not seeding.is_named_entity(e) for e in entities
                                )
                                found = seeding.seed_entities(
                                    question, query, store, fact_top_k=fact_k, **kwargs
                                )
                            return found

                        def fusion(*args, f2=f2, weight=weight, cv=cv, **kwargs):
                            return (
                                fact_fusion.fuse_facts(
                                    *args, relevance_weight=weight, min_cv=cv, **kwargs
                                )
                                if f2
                                else old_fusion.fuse_facts(*args, **kwargs)
                            )

                        retriever = pipeline.OwnRetriever(
                            graph,
                            embedder,
                            now=lambda: frozen,
                            half_lives={GROUPS[0]: 3, GROUPS[1]: 30, GROUPS[2]: 365},
                        )
                        with (
                            patch.object(pipeline, "seed_entities", seeds),
                            patch.object(pipeline, "fuse_facts", fusion),
                        ):
                            result = retriever.retrieve(
                                q["question"],
                                bubbles=groups,
                                time_scope=scope,
                                excluded_bubbles=raw.get("excluded_bubbles", ()),
                            )
                        ids = list(
                            dict.fromkeys(
                                i
                                for sf in result.facts
                                for i in (sf.fact.item_id, *sf.fact.item_ids)
                            )
                        )
                        gold = [IDS[g] for g in q["gold"]]
                        recall = len(set(ids) & set(gold)) / len(gold)
                        row = dict(
                            question_id=q["id"],
                            type=q["type"],
                            routing=routing,
                            route_source=source,
                            variant=variant,
                            recall_any=recall,
                            full_coverage=int(recall == 1),
                            **retrieval_metrics(ids, gold),
                            retrieved_item_ids=ids,
                            gold_item_ids=gold,
                            seed_ids=[e.id for e in result.seeds],
                            stats=stats,
                        )
                        rows.append(row)
                        with (OUT / "offline.jsonl").open("a") as file:
                            file.write(json.dumps(row) + "\n")
                print(q["id"], "complete", flush=True)
    finally:
        graph.driver.close()
    summary = []
    for routing in ("current", "oracle"):
        for variant in VARIANTS:
            for kind in ("all", "single", "multi_hop", "time_sensitive", "freshness"):
                selected = [
                    r
                    for r in rows
                    if r["routing"] == routing
                    and r["variant"] == variant
                    and (kind == "all" or r["type"] == kind)
                ]
                summary.append(
                    dict(
                        routing=routing,
                        variant=variant,
                        type=kind,
                        n=len(selected),
                        full_coverage=sum(r["full_coverage"] for r in selected),
                        **{
                            m: mean(r[m] for r in selected)
                            for m in ("recall_any", "recall_at_10", "mrr", "hits_at_1")
                        },
                    )
                )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    base = {
        (r["routing"], r["question_id"]): r for r in rows if r["variant"] == "baseline"
    }
    deltas = []
    for r in rows:
        if r["variant"] == "baseline":
            continue
        b = base[r["routing"], r["question_id"]]
        deltas.append(
            {k: r[k] for k in ("routing", "variant", "question_id", "type")}
            | {
                m: r[m] - b[m]
                for m in (
                    "recall_any",
                    "recall_at_10",
                    "full_coverage",
                    "mrr",
                    "hits_at_1",
                )
            }
        )
    (OUT / "paired_deltas.json").write_text(json.dumps(deltas, indent=2))


if __name__ == "__main__":
    main()
