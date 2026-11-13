"""Explain paired regressions without changing retrieval parameters."""

import json
from datetime import datetime
from unittest.mock import patch

from omnistream.embeddings import EmbeddingService
from omnistream.eval.diagnostics.own_fixes import OUT, fixed_routes, settings
from omnistream.eval.diagnostics.run import DATA, GROUPS, encode, read
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm import pipeline
from omnistream.retrieval.own_algorithm.seeding import Seed


def main():
    rows = [
        json.loads(line) for line in (OUT / "offline.jsonl").read_text().splitlines()
    ]
    pairs = {(r["routing"], r["question_id"], r["variant"]): r for r in rows}
    regressions = [
        r
        for r in json.loads((OUT / "paired_deltas.json").read_text())
        if r["variant"] == "F1+F2"
        and any(r[m] < 0 for m in ("recall_any", "recall_at_10", "mrr", "hits_at_1"))
    ]
    cfg = settings()
    graph = Neo4jGraphStore.from_settings(cfg)
    frozen = datetime.fromisoformat(read("metadata")[0]["time"])
    graph.now = lambda: frozen
    service = EmbeddingService(cfg)
    routes = fixed_routes()
    findings = []
    all_entities = {e.id: e for e in graph.entities_in(GROUPS)}
    try:
        for delta in regressions:
            q = next(q for q in DATA["questions"] if q["id"] == delta["question_id"])
            raw, _ = routes[q["id"]]
            groups = GROUPS if delta["routing"] == "oracle" else raw["bubbles"]
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
            row = {"delta": delta}
            expanded = []
            candidates = []
            orig_expand, orig_fuse = graph.expand, pipeline.fuse_facts

            def expand(*args, orig_expand=orig_expand, expanded=expanded, **kwargs):
                result = orig_expand(*args, **kwargs)
                expanded.extend(result.facts)
                return result

            def fusion(*args, candidates=candidates, orig_fuse=orig_fuse, **kwargs):
                candidates.extend(args[0])
                return orig_fuse(*args, **kwargs)

            n = pairs[delta["routing"], q["id"], "F1+F2"]

            def fixed_seeds(*args, seed_ids=n["seed_ids"], **kwargs):
                return [Seed(all_entities[i], 1.0, "fact") for i in seed_ids]

            with (
                patch.object(graph, "expand", expand),
                patch.object(pipeline, "seed_entities", fixed_seeds),
                patch.object(pipeline, "fuse_facts", fusion),
            ):
                result = pipeline.OwnRetriever(
                    graph,
                    service,
                    now=lambda: frozen,
                    half_lives={GROUPS[0]: 3, GROUPS[1]: 30, GROUPS[2]: 365},
                ).retrieve(q["question"], bubbles=groups, time_scope=scope)
            b = pairs[delta["routing"], q["id"], "baseline"]
            n = pairs[delta["routing"], q["id"], "F1+F2"]
            actual_ids = list(
                dict.fromkeys(
                    i
                    for sf in result.facts
                    for i in (sf.fact.item_id, *sf.fact.item_ids)
                )
            )
            assert actual_ids == n["retrieved_item_ids"], (
                "Frozen seed audit must reproduce ranking"
            )
            row["reproduces_ranking"] = True
            row["audit_mode"] = "replay captured seeds to isolate downstream ranking"
            gold = set(b["gold_item_ids"])
            lost = gold & set(b["retrieved_item_ids"]) - set(n["retrieved_item_ids"])
            expanded_items = {i for f in expanded for i in (f.item_id, *f.item_ids)}
            by_id = {f.id: f for f in expanded}
            relevance_top20 = {
                i
                for c in sorted(candidates, key=lambda c: -c.fact_score)[:20]
                for i in (by_id[c.id].item_id, *by_id[c.id].item_ids)
            }
            row.update(
                lost_items=sorted(lost),
                absent_from_expansion=sorted(lost - expanded_items),
                present_but_cut=sorted(lost & expanded_items),
                in_relevance_top20=sorted(lost & relevance_top20),
                before_rank=next(
                    (i for i, x in enumerate(b["retrieved_item_ids"], 1) if x in gold),
                    None,
                ),
                after_rank=next(
                    (i for i, x in enumerate(n["retrieved_item_ids"], 1) if x in gold),
                    None,
                ),
                seeds=[e.name for e in result.seeds],
            )
            findings.append(row)
        (OUT / "regression_audit.json").write_text(
            json.dumps(findings, default=encode, indent=2)
        )
    finally:
        graph.driver.close()


if __name__ == "__main__":
    main()
