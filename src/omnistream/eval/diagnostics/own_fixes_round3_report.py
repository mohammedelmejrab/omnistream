"""Render round-three paired measurements without changing retrieval defaults."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean, median

OUT = Path("data/diagnostics/own-fixes-round3")
METRICS = ("recall_any", "recall_at_10", "full_coverage", "mrr", "hits_at_1")


def main():
    rows = [
        json.loads(line) for line in (OUT / "offline.jsonl").read_text().splitlines()
    ]
    index = {(r["variant"], r["question_id"], r["routing"]): r for r in rows}
    variants = ("baseline", "round1", "round2", "round3")
    lines = [
        "# Own retrieval fixes, round 3",
        "",
        "Measured 2026-11-13 on `feat/c5-integration`, round-two reference `646beb6`. No commits, web search, paid LLM calls, `.env` access, application graph writes or snapshot writes. Local embeddings only; OpenAI completion SDK calls are blocked during measurement. Integration schema writes target disposable testcontainers databases.",
        "",
        "## Controls and headline",
        "",
        "All 60 eval-v2 questions, recorded routes and all-bubble routes, exact search, frozen E0 clock. Recorded routes remain the 35 E0 own decisions plus 25 E2 repeat-0 decisions. All-bubble routing retains the recorded time scope and exclusions. The concurrently implemented event-relative router is not rerun: this keeps routing fixed for the retrieval comparison. Unbounded history is tested independently. No answer correctness claim is made.",
        "",
        "Baseline, round 1 and round 2 are freshly remeasured using frozen source fixtures and the round-two store (including its former lexical prefilter). Baseline/round-one seeds, restart and fusion retain their historical behavior; identity deduplication uses the round-two harness contract. Round-three paths use the changed store/seeds/versions. Baseline/round-one/round-two aggregates reproduce the round-two exact table. All metrics credit existing item_ids provenance, without treating suppressed versions as retrieved evidence. Recall-any is mean fraction of gold items found anywhere; full is count with all gold items.",
        "",
        f"{len(rows)} cells: four headline variants, two predeclared generic-weight sensitivities (0.25, 1.0), and two mechanism counterfactuals; each has 60 questions × two routing policies. Default 0.5 was declared before measurement and remains unchanged.",
        "",
        "| Routing | Variant | Recall-any | R@10 | Full | MRR | Hits@1 | Freshness MRR |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    def table_row(route, v):
        selected = [r for r in rows if r["variant"] == v and r["routing"] == route]
        fresh = [r for r in selected if r["type"] == "freshness"]
        return f"| {route} | {v} | {mean(r['recall_any'] for r in selected):.3f} | {mean(r['recall_at_10'] for r in selected):.3f} | {sum(r['full_coverage'] for r in selected)}/{len(selected)} | {mean(r['mrr'] for r in selected):.3f} | {mean(r['hits_at_1'] for r in selected):.3f} | {mean(r['mrr'] for r in fresh):.3f} |"

    for route in ("current", "oracle"):
        lines.extend(table_row(route, v) for v in variants)
    lines += [
        "",
        "Recorded-route full coverage improves 39 -> 42 and R@10 .772 -> .831; all-bubble full coverage declines 38 -> 37 despite higher R@10 (.772 -> .800). Freshness MRR stays at 1.000 for both routing policies. No constants were tuned in response to these outcomes.",
        "",
        "## General mechanisms",
        "",
        "1. Name candidates use an online Entity name FULLTEXT index, discovered read-only. Installed Graphiti 0.31.2 graph_queries.py defines `node_name_and_summary`; SHOW INDEXES confirms it exists over name/summary/group_id. Content words exclude a fixed English stopword/legal-suffix list; terms are tokenized, Lucene-escaped and name-field quoted, and the complete query is passed as a parameter. Candidates are ranked by index score and bounded after bubble filtering. With no index, all bubble candidates are ranked by whole content-word overlap, then fuzzy WRatio, then textual ties; no UUID-first truncation. The fallback is intentionally linear; the online index avoids the CONTAINS population scan. Aliases remain available in fallback and final fuzzy matching, while Graphiti indexes canonical names.",
        "",
        "2. Version collapse requires the same bubble, directed local endpoints and normalized relation, plus identical normalized text or fact-text cosine >= .95. Different digit/amount/quarter/date tokens or spelled month names prevent collapse unless explicit invalid_at/expired_at <= newer.valid_at proves replacement. Global identities never cross bubble boundaries. Local endpoint keys deliberately prefer retention over collapsing ingestion duplicates. Families use deterministic newest-first ordering and require compatibility with every member, preventing first-member and transitive-bridge effects. Point/current scopes keep representatives; all interval scopes, including TimeScope(None, None), retain every overlapping assertion. Other assertions remain untouched; no extra recency demotion was needed. Temporal filtering already removes invalidated older CEOs under now and retains both under unbounded history.",
        "",
        "3. Every positive top-10 fact match may seed endpoints, including Concept/untyped/unknown endpoints. Each source (vector, fuzzy, fact) uses reciprocal dense rank 1/(1 + number of distinct higher scores) within the query before cross-source selection. Generic fact endpoints multiply their normalized fact score by the declared 0.5 default. Thus cosine and fuzzy magnitudes no longer compete directly. Names retain five distinct identities; all sources share ten total identities. Half the total capacity (ceiling for odd budgets) is reserved for the strongest distinct fact-derived identities, with remaining slots filled by the combined normalized ranking. Duplicate identities take maximum score. This rank scale and symmetric reservation are structural choices, not eval-tuned constants.",
        "",
        "4. Incompatible/offline/missing vector indexes select exact server-side cosine; incompatible schema/metric emits a warning instead of raising during retrieval. Explicit writer/schema dimension validation remains strict. Both entity and fact ANN paths refill at 5k/15k/25k and warn/fall back to exact when fewer than k survive. Read-only SHOW PROCEDURES on Neo4j 5.26.33 confirms queryNodes/queryRelationships accept only (indexName, numberOfNearestNeighbours, query), with no filter parameter. Signatures and index inventory are retained in schema.json. No unsupported in-index filter was introduced.",
        "",
        "## By-type tables",
        "",
        "| Routing | Variant | Type | n | Recall-any | R@10 | Full | MRR | Hits@1 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for route in ("current", "oracle"):
        for v in variants:
            for kind in ("single", "multi_hop", "time_sensitive", "freshness"):
                selected = [
                    r
                    for r in rows
                    if r["variant"] == v and r["routing"] == route and r["type"] == kind
                ]
                lines.append(
                    f"| {route} | {v} | {kind} | {len(selected)} | {mean(r['recall_any'] for r in selected):.3f} | {mean(r['recall_at_10'] for r in selected):.3f} | {sum(r['full_coverage'] for r in selected)}/{len(selected)} | {mean(r['mrr'] for r in selected):.3f} | {mean(r['hits_at_1'] for r in selected):.3f} |"
                )
    lines += [
        "",
        "## Sensitivity and counterfactuals",
        "",
        "| Routing | Variant | Recall-any | R@10 | Full | MRR | Hits@1 | Freshness MRR |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for route in ("current", "oracle"):
        lines.extend(
            table_row(route, v)
            for v in (
                "generic025",
                "round3",
                "generic100",
                "seed_only",
                "versions_only",
            )
        )
    lines += [
        "",
        "`seed_only` uses new name retrieval/seeding and old version grouping; `versions_only` uses old names/seeding with new version grouping. Both retain weighted PPR/current fusion. They separate seeding and grouping effects; interactions can still affect ranks. Sensitivities are reported without changing the default.",
        "",
        "## Every regression versus round 2",
        "",
        "A regression is any requested metric loss, even when another metric improves. Reasons below distinguish gold-item loss before expansion, suppression, and final top-20 truncation using captured expansion/representative IDs. Rank-only losses report changed seed identity count and the two controlled counterfactual MRRs; they are evidence of ranking competition, not a claim of unique causal attribution. Each MRR pair is seed-only / versions-only (round-two MRR is also shown).",
        "",
        "| Routing | Question | ?Recall | ?R@10 | ?Full | ?MRR | ?H@1 | Reason / diagnostic |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    regressions = []
    for r in rows:
        if r["variant"] != "round3":
            continue
        b = index["round2", r["question_id"], r["routing"]]
        delta = {m: r[m] - b[m] for m in METRICS}
        if not any(d < 0 for d in delta.values()):
            continue
        lost = set(b["retrieved_item_ids"]) & set(r["gold_item_ids"]) - set(
            r["retrieved_item_ids"]
        )
        reason = []
        for gold in sorted(lost):
            reason.append(
                gold
                + ": "
                + (
                    "not expanded after seed changes"
                    if gold not in r.get("expanded_item_ids", [])
                    else "removed by version grouping"
                    if gold not in r.get("representative_item_ids", [])
                    else "outside final top20"
                )
            )
        changed = len(set(b["seed_ids"]) ^ set(r["seed_ids"]))
        one = index["seed_only", r["question_id"], r["routing"]]
        two = index["versions_only", r["question_id"], r["routing"]]
        reason.append(
            f"seed symmetric difference {changed}; MRR old {b['mrr']:.3f}, counterfactuals {one['mrr']:.3f}/{two['mrr']:.3f}"
        )
        if not lost:
            reason.insert(
                0,
                "gold retained; ranking competition (R@10 losses reflect displacement below rank 10)",
            )
        reason = "; ".join(reason)
        regressions.append(
            dict(
                question_id=r["question_id"],
                routing=r["routing"],
                **delta,
                reason=reason,
            )
        )
        lines.append(
            f"| {r['routing']} | {r['question_id']} | {delta['recall_any']:+.3f} | {delta['recall_at_10']:+.3f} | {delta['full_coverage']:+d} | {delta['mrr']:+.3f} | {delta['hits_at_1']:+.3f} | {reason} |"
        )
    (OUT / "regressions_round2.json").write_text(json.dumps(regressions, indent=2))
    replay = json.loads((OUT / "replays.json").read_text())
    lines += [
        "",
        f"{len(regressions)} regression cells: "
        + ", ".join(
            f"{n} {route}"
            for route, n in Counter(r["routing"] for r in regressions).items()
        )
        + ". Signed deltas for every variant/reference are in paired_deltas.json.",
        "",
        "## Determinism, timing and validation",
        "",
        f"Independent replay with the graph query cache disabled: **{sum(r['changed'] for r in replay)}/{len(replay)} changed** across seed IDs, ranked fact IDs and ranked item IDs. Local query embedding inference remains cached; graph retrieval is independently reread.",
        "",
        "| Exact path | n | Mean ms | Median ms |",
        "|---|---:|---:|---:|",
    ]
    times = json.loads((OUT / "fact_timings.json").read_text())
    for path in ("fact_exact", "name_fulltext", "name_exact"):
        values = [r["seconds"] * 1000 for r in times if r["path"] == path]
        if values:
            lines.append(
                f"| {path} | {len(values)} | {mean(values):.2f} | {median(values):.2f} |"
            )
    lines += [
        "",
        "Times are 60 uncached recorded-route queries per search operation, with local embeddings precomputed. Name timing includes schema discovery. This small synthetic graph and concurrently active database do not establish large-corpus latency or ANN quality. Raw paths/times: fact_timings.json.",
        "",
    ]
    for name in ("offline-tests-final.txt", "integration-tests.txt"):
        raw = (OUT / name).read_bytes()
        contents = raw.decode("utf-16" if raw.startswith(b"\xff\xfe") else "utf-8")
        result = [
            line
            for line in contents.splitlines()
            if " passed" in line or " failed" in line
        ]
        lines.append(
            f"- `{name}`: " + (" / ".join(result) if result else "still running")
        )
    lines += [
        "",
        "Added general tests cover common-word name survival beyond 300 distractors, Lucene literal escaping/parameterization, co-existing quarterly/tranche/month facts despite identical embeddings, same-relation near-identical collapse, cross-bubble retention, input permutations, invalidated CEO now versus unbounded scope, generic endpoint reduction, source-scale independence/fact quota, incompatible-index warning, and ANN-shortfall exact fallback. Integration executes actual fulltext/schema/fallback queries in isolated Neo4j. Existing round-two tests were updated where they asserted the rejected over-merge or silent underfill contracts.",
        "",
        "All sources/replays/metrics are in `src/omnistream/eval/diagnostics/own_fixes_round3*.py` and `data/diagnostics/own-fixes-round3/`. Source fixture own_fixes_round2_sources.json comes from git show 646beb6. Diagnostics are retrieval-only and use synthetic eval-v2; real-data dev validation remains outstanding. OpenCode-owned router/QA/runtime/modes/tools files were not edited by this implementation agent; the full suite includes concurrent event-relative changes.",
    ]
    Path("docs/diagnostics/own-fixes-round3.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
