"""Offline round-three ablations; read-only graph, local embeddings, no LLM."""

from __future__ import annotations

import json
import os
import sys
import types
from datetime import datetime
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from openai.resources.chat.completions import AsyncCompletions, Completions

from omnistream.embeddings import EmbeddingService
from omnistream.eval.diagnostics.own_fixes import fixed_routes, load_baseline, settings
from omnistream.eval.diagnostics.run import DATA, GROUPS, IDS, encode, read
from omnistream.eval.metrics import retrieval_metrics
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm import fact_fusion, pagerank, pipeline, seeding
from omnistream.retrieval.own_algorithm.versions import fact_versions

OUT = Path("data/diagnostics/own-fixes-round3")
METRICS = ("recall_any", "recall_at_10", "full_coverage", "mrr", "hits_at_1")
VARIANTS = (
    "baseline",
    "round1",
    "round2",
    "round3",
    "generic025",
    "generic100",
    "seed_only",
    "versions_only",
)


def module(name, source):
    m = types.ModuleType("_round2_" + name)
    sys.modules[m.__name__] = m
    exec(compile(source, "round1:" + name, "exec"), m.__dict__)  # noqa: S102 - frozen local sources
    return m


def forbidden(*a, **kw):
    raise AssertionError("No paid calls in offline measurement")


def main():
    OUT.mkdir(exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    sources = json.loads(Path(__file__).with_name("own_fixes_round1.json").read_text())
    r1 = {
        n: module(n, sources[n + ".py"]) for n in ("seeding", "pagerank", "fact_fusion")
    }
    base_seed, base_fusion = load_baseline()
    frozen_sources = json.loads(
        Path(__file__).with_name("own_fixes_round2_sources.json").read_text()
    )
    r2 = {
        Path(path).stem: module("round2_" + Path(path).stem, source)
        for path, source in frozen_sources.items()
    }
    cfg = settings()
    frozen = datetime.fromisoformat(read("metadata")[0]["time"])
    graph = Neo4jGraphStore.from_settings(cfg)
    graph.exact_search = True
    graph.now = lambda: frozen
    legacy = r2["neo4j_store"].Neo4jGraphStore(
        graph.driver, exact_search=True, now=lambda: frozen
    )
    emb = EmbeddingService(cfg)
    # Cache local inference only; query cache is disabled during independent replays.
    embed = emb.embed_query
    vectors = {}
    emb.embed_query = lambda text: (
        vectors.setdefault(text, embed(text)) if text not in vectors else vectors[text]
    )
    raw_run = graph._run
    cache = {}
    cached_enabled = True

    def run(query, **kw):
        key = (query, json.dumps(kw, default=encode, sort_keys=True))
        if not cached_enabled:
            return raw_run(query, **kw)
        if key not in cache:
            cache[key] = raw_run(query, **kw)
        return cache[key]

    graph._run = run
    legacy._run = run
    routes = fixed_routes()

    def retrieve(q, routing, variant):
        raw, source = routes[q["id"]]
        groups = GROUPS if routing == "oracle" else raw["bubbles"]
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

        def seeds(question, query, store, **kwargs):
            if variant in ("round2", "versions_only"):
                return r2["seeding"].seed_entities(question, query, store, **kwargs)
            if variant in ("round3", "generic025", "generic100", "seed_only"):
                return seeding.seed_entities(
                    question,
                    query,
                    store,
                    generic_fact_weight={"generic025": 0.25, "generic100": 1.0}.get(
                        variant, 0.5
                    ),
                    **kwargs,
                )
            if variant == "baseline":
                kwargs.pop("time_scope", None)
                found = base_seed.seed_entities(question, query, store, **kwargs)
            elif variant == "name":
                with patch.object(
                    r1["seeding"], "is_named_entity", seeding.is_named_entity
                ):
                    found = r1["seeding"].seed_entities(
                        question, query, store, **kwargs
                    )
                found = [s for s in found if seeding.is_named_entity(s.entity)]
            else:
                found = r1["seeding"].seed_entities(question, query, store, **kwargs)
            unique = {}
            for s in found:
                unique.setdefault(s.entity.global_id or s.entity.id, s)
            found = list(unique.values())
            return found[:10] if variant == "cap_weight" else found

        def pr(graph, ids, **kwargs):
            if variant in (
                "round2",
                "seed_only",
                "versions_only",
                "round3",
                "generic025",
                "generic100",
                "cap_weight",
            ):
                return pagerank.personalized_pagerank(graph, ids, **kwargs)
            kwargs.pop("seed_weights", None)
            return r1["pagerank"].personalized_pagerank(graph, ids, **kwargs)

        fusion = (
            base_fusion.fuse_facts
            if variant == "baseline"
            else fact_fusion.fuse_facts
            if variant
            in (
                "round2",
                "round3",
                "generic025",
                "generic100",
                "seed_only",
                "versions_only",
            )
            else r1["fact_fusion"].fuse_facts
        )
        versions = (
            fact_versions
            if variant in ("round3", "generic025", "generic100", "versions_only")
            else lambda graph, *a, **kw: [
                types.SimpleNamespace(representative=f, versions=(f,))
                for f in graph.facts
            ]
        )
        if variant in ("round2", "seed_only"):
            versions = r2["versions"].fact_versions
        retriever = pipeline.OwnRetriever(
            legacy
            if variant in ("baseline", "round1", "round2", "versions_only")
            else graph,
            emb,
            now=lambda: frozen,
            half_lives=dict(zip(GROUPS, (3, 30, 365))),
        )
        version_fn = versions
        captured = {}

        def capture_versions(subgraph, *args, **kwargs):
            groups = version_fn(subgraph, *args, **kwargs)
            captured["expanded_item_ids"] = sorted(
                {i for f in subgraph.facts for i in (f.item_id, *f.item_ids)}
            )
            captured["representative_item_ids"] = sorted(
                {
                    i
                    for g in groups
                    for i in (g.representative.item_id, *g.representative.item_ids)
                }
            )
            return groups

        with (
            patch.object(pipeline, "seed_entities", seeds),
            patch.object(pipeline, "personalized_pagerank", pr),
            patch.object(pipeline, "fuse_facts", fusion),
            patch.object(pipeline, "fact_versions", capture_versions),
        ):
            result = retriever.retrieve(
                q["question"],
                bubbles=groups,
                time_scope=scope,
                excluded_bubbles=raw.get("excluded_bubbles", ()),
            )
        ids = list(
            dict.fromkeys(
                i for f in result.facts for i in (f.fact.item_id, *f.fact.item_ids)
            )
        )
        gold = [IDS[g] for g in q["gold"]]
        recall = len(set(ids) & set(gold)) / len(gold)
        return dict(
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
            fact_ids=[f.fact.id for f in result.facts],
            **captured,
        )

    rows = []
    (OUT / "offline.jsonl").write_text("")
    try:
        with (
            patch.object(Completions, "create", forbidden),
            patch.object(AsyncCompletions, "create", forbidden),
        ):
            for q in DATA["questions"]:
                for routing in ("current", "oracle"):
                    for variant in VARIANTS:
                        row = retrieve(q, routing, variant)
                        rows.append(row)
                        with (OUT / "offline.jsonl").open("a") as f:
                            f.write(json.dumps(row) + "\n")
                print(q["id"], "done", flush=True)
            # The same 44 regression cells as the first round, independently reread.
            keys = {
                (d["question_id"], d["routing"])
                for d in json.loads(
                    Path("data/diagnostics/own-fixes/paired_deltas.json").read_text()
                )
                if d["variant"] == "F1+F2"
                and any(
                    d[m] < 0 for m in ("recall_any", "recall_at_10", "mrr", "hits_at_1")
                )
            }
            expected = {
                (r["question_id"], r["routing"]): r
                for r in rows
                if r["variant"] == "round3"
            }
            cached_enabled = False
            replays = []
            for qid, routing in sorted(keys):
                q = next(q for q in DATA["questions"] if q["id"] == qid)
                fresh = retrieve(q, routing, "round3")
                old = expected[qid, routing]
                replays.append(
                    dict(  # noqa: C408
                        question_id=qid,
                        routing=routing,
                        changed=any(
                            fresh[k] != old[k]
                            for k in ("seed_ids", "fact_ids", "retrieved_item_ids")
                        ),
                        fresh=fresh,
                    )
                )
            (OUT / "replays.json").write_text(json.dumps(replays, indent=2))
            # Warm server timing, uncached, both paths, identical query/routing mix.
            times = []
            for exact in (True,):
                graph.exact_search = exact
                for q in DATA["questions"]:
                    groups = routes[q["id"]][0]["bubbles"]
                    before = len(graph.search_paths)
                    graph.seed_by_fact_embedding(
                        emb.embed_query(q["question"]), bubbles=groups
                    )
                    graph.name_candidates(q["question"], bubbles=groups)
                    times.extend(
                        dict(entry, question_id=q["id"], routing="current")
                        for entry in graph.search_paths[before:]
                    )
            (OUT / "fact_timings.json").write_text(json.dumps(times, indent=2))
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
                        **{
                            m: sum(r[m] for r in selected)
                            if m == "full_coverage"
                            else mean(r[m] for r in selected)
                            for m in METRICS
                        },
                    )
                )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    comparisons = []
    for reference in ("baseline", "round1", "round2"):
        before = {
            (r["question_id"], r["routing"]): r
            for r in rows
            if r["variant"] == reference
        }
        for r in rows:
            if r["variant"] == reference:
                continue
            b = before[r["question_id"], r["routing"]]
            comparisons.append(
                {k: r[k] for k in ("question_id", "routing", "variant", "type")}
                | dict(reference=reference, **{m: r[m] - b[m] for m in METRICS})
            )
    (OUT / "paired_deltas.json").write_text(json.dumps(comparisons, indent=2))
    print(
        "complete",
        len(rows),
        "cells; replays",
        len(replays),
        "changed",
        sum(r["changed"] for r in replays),
        flush=True,
    )


if __name__ == "__main__":
    main()
