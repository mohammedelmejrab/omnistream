"""Render the measured progress report from durable offline artifacts."""

import json
from pathlib import Path

from omnistream.eval.diagnostics.own_fixes import OUT


def main():
    summaries = json.loads((OUT / "summary.json").read_text())
    deltas = json.loads((OUT / "paired_deltas.json").read_text())
    audits = json.loads((OUT / "regression_audit.json").read_text())
    lines = [
        "# Own retrieval fixes: eval-v2 progress report",
        "",
        "Measured 2026-11-13 on `feat/c5-integration`. **Implementation and offline measurement complete; answer-level measurement blocked by missing credentials.** No answer correctness gain is claimed.",
        "",
        "## Changes and rationale",
        "",
        "- **F1 / P1:** add question-to-fact-text vector search (ten facts), seed both eligible endpoint entities using each fact cosine, then deduplicate GlobalEntity identities. Name-vector candidates are filtered by the simple proper-name guard and deduplicated **before** taking five distinct identities; fuzzy matches remain available outside that budget. Generic names can still be fact seeds or expansion nodes.",
        "- Guard: names must contain at least one token starting with an uppercase Unicode letter; explicit `Generic`, `GenericEntity`, `generic_type` types are excluded. `Concept` is not automatically generic. This casing heuristic misses lowercase proper names and admits title-cased common phrases; it is intentionally simple and is not a named-entity model. It removes 124/300 original name top-five slots under current routes, and 52/100 on multi-hop (106/300, 52/100 with all bubbles). Diagnosis used a broader manual generic classification (56/100); these counts are not interchangeable.",
        "- Ten fact matches is twice the five-name budget, allowing event descriptions to supply both endpoints. No gold labels or question-specific names enter the implementation. Five and fifteen are reported as sensitivity, without changing the ten-fact default.",
        "- **F2 / P2:** weighted RRF, relevance:recency:confidence **2:1:1**. Relevance receives twice each auxiliary signal's vote. Drop auxiliary rankings with fewer than two distinct values or coefficient of variation below **0.01** (population SD / absolute mean). One percent means negligible relative dispersion; 0.005 and 0.02 are sensitivity checks. Relevance remains as a deterministic fallback even when constant.",
        "- **Spec deviation:** C5 step 1 now includes fact-text seeding and a generic-name guard. Step 5 changes equal RRF to weighted RRF and removes uninformative auxiliary signals; it remains RRF of fact relevance, recency and corroboration. The existing RRF implementation already assigns equal ranks to exact ties. Thus exactly constant confidence did not invent arbitrary tie order; near-constant auxiliary values and recency competing with relevance are the actionable mechanisms.",
        "- Expansion remains two hops / 500 facts; PPR damping 0.85, fusion k=60, returned facts 20, validity filtering and answer/judge definitions are unchanged. **BM25 not implemented** to keep the two-fix scope tight; no marginal lexical effect is claimed.",
        "",
        "See [diagnosis P1/P2 and E3/E4](eval-v2-diagnosis.md) and [Finding 4 and fix plan](../IMPROVEMENT_LOG.md).",
        "",
        "## Index and measurement controls",
        "",
        "Read-only `SHOW INDEXES` found an existing ONLINE `fact_embedding` VECTOR RELATIONSHIP index on `RELATES_TO.fact_embedding`; production uses `db.index.vector.queryRelationships` and converts Neo4j's normalized score to cosine. If absent, it computes exact Python cosine over eligible group fact embeddings. Graphiti 0.31.2's `graph_queries.py` creates `edge_name_and_fact` fulltext and relationship range indexes; its standard index helpers do not provision a fact vector index. No index creation was needed or performed. Both branches have unit coverage.",
        "",
        "To prevent other bubbles or invalid facts consuming a seed budget, the index query requests all indexed relationship candidates before filtering groups/time/grounding and taking ten. This and the exact fallback are linear; **this is not a scalable filtered-ANN implementation**. Endpoint lookup also scans selected-group entities. Future scale work needs filtered ANN/oversampling with explicit recall guarantees; this report makes no latency improvement claim.",
        "",
        "All 60 authored eval-v2 questions were evaluated under current recorded routes and all three bubbles, ten predeclared configurations each: **1,200 cells**, no LLM calls. All-bubble routing is an intervention, not a minimal relevant subset. Query scope and exclusions are reused; clock frozen to E0 metadata `2026-11-12T23:49:17.370617+00:00`. Runtime item IDs include corroborating provenance, deduplicated in retrieval order; Recall@10, MRR and Hits@1 use the harness functions. Recall-any is per-question gold-item coverage at any returned rank; full coverage counts questions retrieving every gold item. Means are macro averages.",
        "",
        "**Routing qualification:** E0 own answer/routes exist for the 20 multi-hop + 15 time-sensitive questions only. These 35 reuse exactly E0 own decisions and scopes. The other 25 reuse recorded E2 repeat-0 current-model decisions from `routes.jsonl`, explicitly tagged per cell. They cannot honestly be labelled E0 own decisions. The reproduced baseline matches all four E0 retrieval metrics on **35/35** comparable questions. No live rerouting was done.",
        "",
        "The first exact-fallback pilot was stopped after discovery of the available index and is kept separately as `exact-fallback-pilot.jsonl`; the final table uses only the completed indexed run. Original implementation sources are frozen in `src/omnistream/eval/diagnostics/own_fixes_baseline.json`. The baseline differs only in seeding/fusion; the original pipeline's identity dedup behavior is preserved.",
        "",
        "## Offline ablations",
        "",
        "Current routes carry the E0/E2 qualification above. All values below are measured; full is count/n.",
        "",
    ]
    for routing in ("current", "oracle"):
        lines += [
            "### "
            + (
                "Recorded current routing"
                if routing == "current"
                else "All-bubble routing"
            ),
            "",
            "| Variant | Type | n | Recall-any | Recall@10 | Full | MRR | Hits@1 |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for r in summaries:
            if r["routing"] == routing and r["variant"] in (
                "baseline",
                "F1",
                "F2",
                "F1+F2",
            ):
                lines.append(
                    f"| {r['variant']} | {r['type']} | {r['n']} | {r['recall_any']:.3f} | {r['recall_at_10']:.3f} | {r['full_coverage']}/{r['n']} | {r['mrr']:.3f} | {r['hits_at_1']:.3f} |"
                )
        lines.append("")
    lines += [
        "F1 alone helps multi-hop coverage but reduces time-sensitive coverage. F2 alone improves time-sensitive retrieval substantially and does not improve multi-hop full coverage. Their combination improves current multi-hop full coverage from 1 to 6 and time-sensitive from 6 to 12. Across all 60 current-route questions, Recall-any is 0.644 -> 0.803 and full coverage 29 -> 42; Hits@1 falls 0.267 -> 0.200. Recall gains do not imply answer gains.",
        "",
        "## Sensitivity (declared defaults retained)",
        "",
        "Each sensitivity changes one parameter of F1+F2. The table shows all questions and multi-hop; the linked summary JSON contains every question type and all metrics for every setting. No search or threshold selection followed these results.",
        "",
        "| Routing | Setting | Type | Recall-any | Recall@10 | Full | MRR | Hits@1 |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in summaries:
        if r["variant"] in (
            "F1+F2",
            "fact-k5",
            "fact-k15",
            "weight1",
            "weight3",
            "cv005",
            "cv02",
        ) and r["type"] in ("all", "multi_hop"):
            lines.append(
                f"| {r['routing']} | {r['variant']} | {r['type']} | {r['recall_any']:.3f} | {r['recall_at_10']:.3f} | {r['full_coverage']}/{r['n']} | {r['mrr']:.3f} | {r['hits_at_1']:.3f} |"
            )
    lines += [
        "",
        "`weight1` = 1:1:1, `weight3` = 3:1:1; confidence/recency dropping stays enabled. Default fact-k10 has 6/20 current multi-hop full coverage versus 1/20 at k5 and 4/20 at k15: sensitivity to candidate distribution remains substantial. This is a limitation, not evidence of a generally optimal k10. CV sensitivity leaves the headline multi-hop metrics unchanged.",
        "",
        "## Regressions and paired evidence",
        "",
        "Reproducibility caveat: a fresh follow-up replay of the 44 regression cells changed seed sets/ranked items in 6 cells (q14 current/all-bubble, q17 all-bubble, q29 all-bubble, q47 current/all-bubble). Root cause has not been isolated; approximate-index results and numerical sensitivity are possible contributors, not established causes. The main table remains the original single paired pass, without cherry-picking a replay. `fresh_replay_audit.json` preserves these checks. To explain that pass accurately, the downstream audit reuses its recorded seed IDs and asserts exact reproduction of ranked item IDs. This isolates ranking/expansion; it does not establish deterministic end-to-end seeding.",
        "",
        "Every per-question metric delta against baseline is retained in `data/diagnostics/own-fixes/paired_deltas.json` (1,080 paired rows); all ranked item IDs and seed IDs are in `offline.jsonl`. The following lists **every** F1+F2 question worsening on at least one requested metric. delta R and delta R10 are recall changes; the first-gold rank uses item rank, not fact rank. Losing one gold item while gaining another can leave delta R=0.",
        "",
        "| Routing | Question | delta R | delta R10 | First gold rank before -> after | Explanation |",
        "|---|---|---:|---:|---|---|",
    ]
    for a in audits:
        d = a["delta"]
        explanation = "First relevant item moved lower after added fact seeds changed PPR/candidate competition."
        if a["lost_items"]:
            explanation = f"{len(a['present_but_cut'])} previously returned gold item(s) remain in expansion but miss fused top20; {len(a['in_relevance_top20'])} remain in relevance top20."
        if a["absent_from_expansion"]:
            explanation += f" {len(a['absent_from_expansion'])} absent from expansion."
        lines.append(
            f"| {d['routing']} | {d['question_id']} | {d['recall_any']:+.3f} | {d['recall_at_10']:+.3f} | {a['before_rank']} -> {a['after_rank']} | {explanation} |"
        )
    lines += [
        "",
        "All lost gold items in the regression audit are still in the expanded candidates. Ranking/PPR dilution and residual fusion competition remain material limitations. Freshness still covers 10/10 questions, but MRR falls 0.858 -> 0.475 and Hits@1 0.8 -> 0.3. Current multi-hop recall losses are q17, q25, q38, q43; q18 loses Recall@10. All-bubble q23 and q34 additionally lose full coverage. No gold-specific repair or reranking override was added.",
        "",
        "Other ablation variants with any recall or ranking regression against baseline:",
        "",
        "| Routing | Variant | Questions worse on any metric |",
        "|---|---|---|",
    ]
    for routing in ("current", "oracle"):
        for variant in ("F1", "F2"):
            ids = sorted(
                {
                    r["question_id"]
                    for r in deltas
                    if r["routing"] == routing
                    and r["variant"] == variant
                    and any(
                        r[m] < 0
                        for m in ("recall_any", "recall_at_10", "mrr", "hits_at_1")
                    )
                }
            )
            lines.append(f"| {routing} | {variant} | {', '.join(ids) or 'none'} |")
    lines += [
        "",
        "## Answer-level correctness and spend",
        "",
        "**NOT MEASURED: 0/35 answers or judges, USD 0.00, zero tokens.** `LLM_API_KEY` is absent from this process environment. A private `request_secret` (`delivery=file`, 60-second timeout) timed out without delivery; `.env` was never opened. No provider failure is scored as an incorrect answer. The USD 0.60 budget was not approached; no request was sent. Own+subagents was intentionally not evaluated offline.",
        "",
        "| Configuration | Model | Multi-hop fully correct / n | Mean (0-2) | Time-sensitive fully correct / n | Mean (0-2) | Cost in this task |",
        "|---|---|---|---:|---|---:|---:|",
        "| E0 own | deepseek/deepseek-v4.1-flash-1017 | 1/20 | 0.100 | 10/15 | 1.333 | historical baseline |",
        "| E0 classic | same | 4/20 | 0.400 | 11/15 | 1.467 | historical baseline |",
        "| F1+F2 own | requested same model | UNMEASURED (n=0/20) | unmeasured | UNMEASURED (n=0/15) | unmeasured | $0.00 |",
        "",
        "The parallel reasoning-control change is present in the working tree (`Settings.llm_reasoning` default `off`, judge default `off`). **There were no calls, so reasoning was neither observed on nor observed off.** A resumed run must explicitly record its actual settings, provider prompt/completion/reasoning tokens, cumulative provider cost, and stop before $0.60. It must use the harness's existing answer and correctness judge paths (`deepseek/deepseek-chat`) without metric changes; it must not substitute the E0 answers or infer correctness from recall.",
        "",
        "## Validation, artifacts and limitations",
        "",
        "- `.venv\\Scripts\\python.exe -m pytest -q`: **1080 passed, 1 skipped, 21 deselected in 99.04s**. The shared checkout includes parallel changes, so the count exceeds the supplied 1021 baseline. New tests cover fact-vector seeds, temporal/grounding/group restrictions, generic guard, post-dedup refill, near-constant dropping, weighted fusion, and index/fallback read-only queries. Existing fusion/protocol/pipeline tests were updated for the explicit new contracts.",
        "- Ruff checks passed for all changed implementation, tests and measurement modules. Initial expected-contract failures were fixed and the complete suite rerun; a new temporal test fixture was corrected to set a valid-at boundary rather than assuming publication implied validity.",
        "- Snapshot integrity: **107/107 recorded E0 snapshot file hashes unchanged** (`integrity.json`). Neo4j use was read-only; no DDL or graph mutation. No commits, no modifications to the protected parallel implementation files, and no `.env` access.",
        "- Reproduce offline: `.venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.own_fixes`; the cell log is resumable, with saved original baseline sources. For regression detail run `-m omnistream.eval.diagnostics.own_fixes_audit`; render this report with `-m omnistream.eval.diagnostics.own_fixes_report`. Set `HF_HUB_OFFLINE=1` to require cached local model weights.",
        "- Artifacts: `data/diagnostics/own-fixes/{offline.jsonl,summary.json,paired_deltas.json,regression_audit.json,indices.json,integrity.json,answer_status.json}`. Primary metrics are direct JSON calculations, not copied estimates.",
        "- **Synthetic eval-v2 only; graph built by the old deepseek-chat model. Not measured on real data.** The current task explicitly requested these mechanisms and eval-v2 measurements; defaults were declared from the diagnosis, not selected using real-test or eval-v2 score search. The real-data dev validation required by the improvement plan remains outstanding. No real-data test split was used. The planned 35 answer-level questions remain unmeasured and would still be a limited sample once completed.",
        "- Seeding expands candidate reach but uniform-seed PPR can dilute previously useful anchors; score-based restart weighting and historical/event-relative scope changes were outside scope. Casing, alias linkage, graph extraction defects, validity filtering and residual relevance/recency competition remain limitations. This is a measured improvement with regressions, not a claim that P1/P2 or multi-hop answering are solved.",
        "",
    ]
    Path("docs/diagnostics/own-fixes-eval-v2.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
