"""Render round-two measurements without changing or selecting parameters."""

import hashlib
import json
from pathlib import Path
from statistics import mean, median

from omnistream.eval.diagnostics.own_fixes_round2 import METRICS, OUT
from omnistream.eval.diagnostics.run import read


def main():
    summary = json.loads((OUT / "summary.json").read_text())
    deltas = json.loads((OUT / "paired_deltas.json").read_text())
    rows = [json.loads(s) for s in (OUT / "offline.jsonl").read_text().splitlines()]
    replays = json.loads((OUT / "replays.json").read_text())
    signals = json.loads((OUT / "entity_signals.json").read_text())
    generic = {
        r["id"]
        for r in json.loads(
            Path("data/diagnostics/eval-v2/generic_entities.json").read_text()
        )["entities"]
    }
    historical = [
        json.loads(s)
        for s in Path("data/diagnostics/own-fixes/offline.jsonl")
        .read_text()
        .splitlines()
    ]
    historical_deltas = []
    for ref, variant in [("baseline", "baseline"), ("round1", "F1+F2")]:
        before = {
            (r["question_id"], r["routing"]): r
            for r in historical
            if r["variant"] == variant
        }
        for r in rows:
            if r["variant"] == "round2":
                b = before[r["question_id"], r["routing"]]
                historical_deltas.append(
                    {k: r[k] for k in ("question_id", "routing", "type")}
                    | {"reference": ref, **{m: r[m] - b[m] for m in METRICS}}
                )
    (OUT / "historical_deltas.json").write_text(json.dumps(historical_deltas, indent=2))
    hashes = read("metadata")[0]["snapshot_hashes"]
    checked = {p: h for p, h in hashes.items() if not p.endswith(("-shm", "-wal"))}
    missing = [p for p in checked if not (Path("data/snapshots/eval-v2") / p).exists()]
    changed = [
        p
        for p, h in checked.items()
        if p not in missing
        and hashlib.sha256(
            (Path("data/snapshots/eval-v2") / p).read_bytes()
        ).hexdigest()
        != h
    ]
    integrity = dict(  # noqa: C408
        files_checked=len(checked),
        changed=changed,
        missing=missing,
        ignored_ephemeral=[p for p in hashes if p not in checked],
        unchanged=not changed and not missing,
    )
    (OUT / "integrity.json").write_text(json.dumps(integrity, indent=2))
    lines = [
        "# Own retrieval fixes, round 2",
        "",
        "Measured 2026-11-13 on `feat/c5-integration`, with round-1 sources frozen from `cbba2e7`. No commits, paid calls, answer generation, web search, snapshot writes, or mutations of the application Neo4j graph. Schema writes in tests target a separate testcontainers database only.",
        "",
        "## Result and measurement controls",
        "",
        "All 60 questions, recorded and all-bubble routes, nine configurations: **1,080 paired exact-path cells**. Recorded routes retain the first-round qualification: 35 E0 own decisions, 25 E2 repeat-0 decisions; all-bubble routing retains each recorded time scope/exclusion. The clock is frozen to E0 metadata. Gold evidence and metric functions are unchanged. Recall-any is mean gold-item coverage at any returned rank, not a binary hit. Full coverage is count/n. Runtime item IDs include existing corroborating provenance; collapsed old version provenance is retained in `VersionGroup.versions`, not falsely credited as retrieved current evidence.",
        "",
        "Both baseline and round-1 are remeasured with exact server cosine and stable rounded candidate ordering, so changes between their old ANN tables and this table are **not implementation gains**. Sources for pre-fix seeding/fusion are `own_fixes_baseline.json`; round-1 seeding/PPR/fusion are `own_fixes_round1.json`. Baseline and round-1 use their original restart/fusion behavior. Exact search changes the numerical/vector candidate path, so the historical table is retained separately below. The common pipeline uses round-1 identity deduplication, explicitly restored for old seeds.",
        "",
        "| Exact replay, recorded routes | Recall-any | Recall@10 | Full | MRR | Hits@1 | Freshness MRR |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in ["baseline", "round1", "round2"]:
        r = next(
            r
            for r in summary
            if r["routing"] == "current"
            and r["variant"] == variant
            and r["type"] == "all"
        )
        f = next(
            r
            for r in summary
            if r["routing"] == "current"
            and r["variant"] == variant
            and r["type"] == "freshness"
        )
        lines.append(
            f"| {variant} | {r['recall_any']:.3f} | {r['recall_at_10']:.3f} | {r['full_coverage']}/60 | {r['mrr']:.3f} | {r['hits_at_1']:.3f} | {f['mrr']:.3f} |"
        )
    lines += [
        "",
        "Round two improves first-gold rank and freshness, but does not remove retrieval regressions: recorded-route full coverage falls 41 to 39 versus the remeasured round one; Recall@10 falls .786 to .772. Version grouping alone does **not** recover freshness MRR (.475 remains .475); the combined improvement must not be attributed to grouping alone. No constants were changed after measurement.",
        "",
        "Historical published ANN results (not rerun or overwritten): baseline recorded Recall-any .644, Recall@10 .636, full 29/60, MRR .435, Hits@1 .267; round one .803, .778, 42/60, .435, .200. Freshness .858 -> .475. Round-two comparisons against every historical cell are in `historical_deltas.json`; paired exact comparisons are in `paired_deltas.json`.",
        "",
        "## Mechanisms and limits",
        "",
        "1. **Seedability:** the seven named shared ontology types (Person, Organization, Location, Product, Event, FinancialInstrument, Publication) are eligible in name, fuzzy, and fact-endpoint paths. Concept, untyped Entity, and unknown types are ineligible. No orthographic fallback is needed when ingestion supplies the shared types. Case/script tests include eBay, iPhone, arXiv, x86, adidas, bitcoin, mRNA, pH, ffmpeg, Chinese and Arabic. Capitalized generic phrases typed Concept are excluded. A generic phrase wrongly typed Product still passes; the rule is not a named-entity classifier and does not repair extraction.",
        "",
        "2. **Budget/restart:** ten total distinct GlobalEntity identities after combining names, fuzzy matches and eligible fact endpoints; five and fifteen are predeclared sensitivity values. Name candidates are bounded at 50 (or 10 times a custom name budget), fuzzy candidates at 100. Names still contribute at most five identities. Nonpositive fact similarities do not seed. PPR restart mass is normalized nonnegative seed score, with uniform fallback if all scores are zero. This extends the spec: restart remains at the seeds, now weighted by evidence. Fuzzy scores retain their prior [0,1] scale; no calibration claim across semantic and lexical similarity is made.",
        "",
        "3. **Scale/schema:** C4 `ensure_schema` adds an idempotent relationship vector index on `RELATES_TO.fact_embedding`, using the configured `fact_index_name`, configured embedding dimension (384 by default) and cosine. Settings and writer plumbing plus the GraphStore bounded-name contract are the minimal changes outside the listed implementation files. Reader checks the configured index name, relationship/node schema and cosine function before applying `2*score-1`. Default fact ANN fetches 5k, then 15k and 25k if filtering leaves too few; selected groups, grounding and validity are filtered in Cypher. This finite refill can underfill in a heavily skewed database; no exact-ANN recall guarantee is claimed. No population counts or full embedding payloads are fetched. Endpoint hydration uses only the top fact IDs/endpoints. Bounded lexical prefiltering and vector candidates replace repeated `entities_in` scans in production seeding.",
        "",
        "4. **Exact/replay/fallback:** `Neo4jGraphStore(..., exact_search=True)` scores cosine server-side and returns only top-k records. It is explicitly linear compute for evaluation/replay. If a configured index is absent/offline, the same server-side exact fallback is used (an improvement over transferring all vectors for Python scoring). A wrong existing schema/metric raises an error. Paths and elapsed times are logged and available in `search_paths`. Exact queries round scores to six decimals and break ties by UUID. Graph construction sorts edges, paths are deterministic, and fusion rounds each signal to six decimals before competition ranking. `min_cv` remains accepted for old diagnostic callers, but no longer drops low-variance material signals. A 99-at-.92/one-at-.99 confidence test retains corroboration.",
        "",
        "5. **Versions before fusion:** same directed subject/object GlobalEntity identities and normalized relation define a version family; within an endpoint pair, fact-text cosine >= .95 also recognizes near-identical relation paraphrases. This threshold was stated before measurement and was not tuned. Choose the newest valid assertion by valid_at (publication fallback), then publication and UUID. Keep the complete family, original text and provenance in `OwnRetriever.last_version_groups` / `VersionGroup.versions`; only representatives enter global fusion. Point-in-time queries select the latest valid assertion at that point. A routed time interval retains every overlapping version, because an interval may ask about changes. No attempt is made to infer event-relative scopes the router omitted, merge unrelated endpoints, or repair wrong GlobalEntity identities. Such defects limit this mechanism.",
        "",
        "The redundant pipeline seed deduplication is removed; the docstring now describes the implemented mechanism. The neutral regression-test vocabulary replaces the old diagnostic-flavoured examples. BM25 was considered but not added to the already changed seed mechanism: installed Graphiti 0.31.2 `graph_queries.py` provisions relationship fulltext `edge_name_and_fact` over name/fact/group_id, and that index exists in this graph. It does not provision the relationship vector index. A lexical hybrid would require a separate score/candidate ablation; none is claimed.",
        "",
        "## Ingestion-signal audit (283 entities)",
        "",
        "Manual generic list is used only to describe signal limitations, never to select a threshold. Predicted positive below means seedable. All 283 entities have SAME_AS, including all 94 manually generic nodes. Consequently requiring a GlobalEntity link adds no information here. Maximum observed degree is 20; no graph-size-specific hub cutoff was introduced.",
        "",
        "| Manual class | Typed eligible | Typed excluded | SAME_AS yes | SAME_AS no |",
        "|---|---:|---:|---:|---:|",
    ]
    named = {
        "Person",
        "Organization",
        "Location",
        "Product",
        "Event",
        "FinancialInstrument",
        "Publication",
    }
    for label, truth in [("generic", True), ("non-generic", False)]:
        selected = [r for r in signals if (r["id"] in generic) == truth]
        yes = sum(bool(set(r["labels"]) & named) for r in selected)
        lines.append(
            f"| {label} | {yes} | {len(selected) - yes} | {sum(r['linked'] for r in selected)} | {sum(not r['linked'] for r in selected)} |"
        )
    lines += [
        "",
        "Typed eligibility excludes 52/94 generic nodes and also excludes 12/189 manually non-generic nodes. It admits 42 generic nodes through imperfect ingestion types. This is a documented tradeoff of the ontology contract, not evidence that a lower-case multiword heuristic was optimized away.",
        "",
        "## Full offline tables",
        "",
        "All standalone ablations start from round one. `name` changes ontology eligibility for all seed sources; `cap_weight` changes total cap and restart mass; `versions` changes version representatives; `rounding` changes signal precision/constant handling. Combined also uses bounded store candidate queries and the fuzzy candidate prefilter. Thus combined is not asserted to be a simple additive combination. `cap5`/`cap15` each change only the combined total seed cap.",
        "",
    ]
    for routing in ["current", "oracle"]:
        lines += [
            f"### {routing} routing",
            "",
            "| Variant | Type | n | Recall-any | Recall@10 | Full | MRR | Hits@1 |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for r in summary:
            if r["routing"] == routing:
                lines.append(
                    f"| {r['variant']} | {r['type']} | {r['n']} | {r['recall_any']:.3f} | {r['recall_at_10']:.3f} | {r['full_coverage']}/{r['n']} | {r['mrr']:.3f} | {r['hits_at_1']:.3f} |"
                )
    lines += [
        "",
        "## Every combined regression against paired exact references",
        "",
        "A regression means any requested metric decreases; improvements on other metrics do not cancel it. Raw per-question IDs and all signed deltas are preserved, including regressions for standalone and sensitivity configurations.",
        "",
        "| Reference | Routing | Question | Delta recall | Delta R@10 | Delta full | Delta MRR | Delta Hits@1 |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for d in deltas:
        if d["variant"] == "round2" and any(d[m] < 0 for m in METRICS):
            lines.append(
                f"| {d['reference']} | {d['routing']} | {d['question_id']} | {d['recall_any']:+.3f} | {d['recall_at_10']:+.3f} | {d['full_coverage']:+d} | {d['mrr']:+.3f} | {d['hits_at_1']:+.3f} |"
            )
    lines += [
        "",
        "## Determinism and timing",
        "",
        f"Independent uncached reruns of the same **{len(replays)} regression cells**: **{sum(r['changed'] for r in replays)} changed** seed IDs, fact IDs or ranked item IDs. This is exact-path determinism on this graph/clock, not an ANN determinism promise. The original round-one audit had 6/44 differences. Fresh exact queries were executed against Neo4j in the second pass; only local query embeddings were reused.",
        "",
        "Fact-search timing: 60 uncached recorded-route queries per path, excluding query embedding inference, including index metadata check, finite refill and bounded endpoint hydration; warm shared database under concurrent activity. Small synthetic graph only; no real-data throughput claim.",
        "",
        "| Path | n | Mean ms | Median ms | p95 ms |",
        "|---|---:|---:|---:|---:|",
    ]
    times = json.loads((OUT / "fact_timings.json").read_text())
    for path in ["fact_ann", "fact_exact"]:
        ts = [t["seconds"] * 1000 for t in times if t["path"] == path]
        lines.append(
            f"| {path} | {len(ts)} | {mean(ts):.2f} | {median(ts):.2f} | {sorted(ts)[int(0.95 * (len(ts) - 1))]:.2f} |"
        )
    lines += [
        "",
        "## Validation and outstanding work",
        "",
        f"Snapshot hash check: {len(checked)} non-ephemeral E0-recorded snapshot files, changed {len(changed)}, missing {len(missing)}. SQLite -wal/-shm files are ignored as live runtime sidecars. The historical comparison flags `chroma/chroma.sqlite3` as changed since E0; this is not a task-start comparison and cannot attribute the change. This task neither opened Chroma nor wrote snapshot files. No application graph DDL or writes were executed. Password was read privately into the Neo4j process environment; `.env` was never accessed. No Python processes were stopped. No real snapshot or real test split was touched.",
        "",
    ]
    for filename in [
        "retrieval-tests.txt",
        "integration-tests-refill.txt",
        "offline-tests-latest.txt",
    ]:
        p = OUT / filename
        text = (
            (
                p.read_bytes().decode("utf-16")
                if p.read_bytes().startswith((b"\xff\xfe", b"\xfe\xff"))
                else p.read_text(encoding="utf-8")
            )
            if p.exists()
            else "pending"
        )
        lines += [
            f"`{filename}`:",
            "```text",
            "\n".join(text.splitlines()[-10:]),
            "```",
            "",
        ]
    lines += [
        "The suite was executed during unrelated evaluation/LLM edits in this shared checkout. Earlier failures in Judge/token-cap test contracts are recorded in `offline-tests-final.txt`; they were not repaired by changing another task's implementation. The retrieval structural protocol fixture was updated for `name_candidates`.",
        "",
        "Outstanding: real-data dev validation (build is owned by another process), answer-level evaluation (forbidden here), large-corpus ANN recall/latency validation, ingestion typing/identity quality and missing event-relative routing scopes. This synthetic diagnostic is a secondary check, not generalization evidence. BM25 remains considered but unimplemented. No defaults were selected using these tables.",
        "",
        "Reproduce: `.venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.own_fixes_round2`, then `-m omnistream.eval.diagnostics.own_fixes_round2_report`. The runner requires cached local embedding weights, blocks SDK paid completion methods, disables `.env` loading, uses exact graph reads, and rewrites only its own `data/diagnostics/own-fixes-round2/` measurements. Full raw tables, historical comparisons, replay outputs, type/identity signal inventory and timings are retained there.",
    ]
    Path("docs/diagnostics/own-fixes-round2.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
