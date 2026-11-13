"""Machine-readable and Markdown exports; missing metrics remain visibly missing."""

import csv
import json
from pathlib import Path

from .metrics import run_validity


def display(value):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def table(metrics):
    keys = [
        "recall_at_10",
        "mrr",
        "hits_at_1",
        "correctness",
        "routing_recall",
        "routing_precision",
        "citation_faithfulness",
        "citation_faithfulness_micro",
        "correctness_errors",
        "faithfulness_errors",
        "zero_citation_answers",
        "abstentions",
        "changed_fact_accuracy",
        "latency_seconds",
        "tokens",
        "cost_usd",
        "judge_tokens",
        "judge_cost_usd",
        "errors",
    ]
    lines = [
        "| Configuration | " + " | ".join(keys) + " |",
        "|---|" + "---|" * len(keys),
    ]
    lines += [
        "| " + name + " | " + " | ".join(display(m.get(k)) for k in keys) + " |"
        for name, m in metrics.items()
    ]
    return "\n".join(lines)


def write_csv(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for record in records for key in record))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    k: json.dumps(v, ensure_ascii=False)
                    if isinstance(v, (dict, list, tuple))
                    else v
                    for k, v in record.items()
                }
            )


def write_report(directory, snapshot, stamp, metrics, results, global_metrics, checks):
    base = Path(directory) / f"{snapshot}-{stamp}"
    base.parent.mkdir(parents=True, exist_ok=True)
    question_path = base.with_suffix(".questions.csv")
    config_path = base.with_suffix(".configurations.csv")
    report_path = base.with_suffix(".md")
    write_csv(question_path, results)
    write_csv(
        config_path,
        [
            {
                "configuration": name,
                **m,
                **{
                    k: v
                    for k, v in global_metrics.items()
                    if k.startswith("ingestion_")
                },
            }
            for name, m in metrics.items()
        ],
    )
    validity = run_validity(metrics)
    lines = [
        f"# OmniStream evaluation: {snapshot}",
        "",
        "INVALID RUN"
        if validity["status"] == "invalid"
        else validity["status"].upper(),
        f"Unmeasured pairs: {validity['unmeasured_pairs']}; invalid if any configuration exceeds {validity['unmeasured_limit']:.0%}. Error types: {json.dumps(validity['error_types'], sort_keys=True)}",
        f"Provider-error pairs (answer/retrieval or judge): {validity['provider_error_pairs']}. Judge error types (separate): {json.dumps(validity['judge_error_types'], sort_keys=True)}",
        "Invalid configurations: " + ", ".join(validity["invalid_configurations"]),
        "",
        table(metrics),
        "",
        "Native retrieval limits: classic 10 chunks; graphiti/own 20 facts; external LlamaIndex default 2 nodes. Subagents can perform several searches. Recall@10 cuts the deduplicated item ranking after round-robin interleaving per-bubble evidence. Footnote: with the three-bubble catalog, round-robin guarantees each routed bubble with returned evidence representation in the top-10; empty evidence cannot be represented.",
        "Faithfulness: macro per-answer mean is used for the section 8.3 target; micro weights citation attributions. Answers with zero citations score 0. External answers without inline markers use the union of all returned sources as one attribution unit.",
        "Answer tokens/cost exclude judging; judge usage is reported separately in global measurements.",
        "Judge calibration: "
        + (
            f"pending human labels (n={global_metrics['judge_calibration']['n']} exported)"
            if global_metrics.get("judge_calibration", {}).get("status")
            == "pending human labels"
            else str(global_metrics.get("judge_calibration", "pending real v2 sample"))
        ),
        "## Per-question-type metrics",
        "| Configuration | Type | Correctness (0-2) | Recall@10 | Errors |",
        "|---|---|---|---|---|",
    ]
    for name, m in metrics.items():
        for kind, values in m["by_type"].items():
            lines.append(
                f"| {name} | {kind} | {display(values['correctness'])} | {display(values['recall_at_10'])} | {values['errors']} |"
            )
    lines += [
        "",
        "## Success criteria (section 8.3)",
        "Table notes: ingestion_routing_accuracy is exact-set agreement against original labels. Primary-label recall counts items whose labelled bubble is assigned; over-assignment rate counts extra bubble assignments / items; wrong-routing rate counts items missing their label. Category counts appear in global measurements and configuration CSV. Failed judgements make dependent checks UNMEASURED; measured values remain partial. MRR/Hits@1 use the first gold-or-acceptable evidence item; Recall@10 still uses gold only.",
        "| Criterion | Status | Measured | Target |",
        "|---|---|---|---|",
    ]
    for key, check in checks.items():
        lines.append(
            f"| {key} | {check['status'] + (' (' + str(check['failed_judgements']) + ' failed judgements)' if check.get('failed_judgements') else '')} | {display(check['value'])} | {check['target']} |"
        )
    lines += [
        "",
        "## Global measurements",
        "```json",
        json.dumps(global_metrics, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Method and limitations",
        "- Corpus: versioned fictional scripted records only, no recorded real-world feed. Ten updates are held back until runtime. Snapshot manifest binds the corpus name and ingested item-content SHA-256 (excluding question/reference edits); reruns reuse the data.",
        "- Recall@10 uses distinct supporting item IDs, in retrieval order for direct configurations and round-robin per-bubble rank for subagents; retrieved/read IDs contribute after deduplication. MRR uses the full observed ranking. This is item-level provenance, not a separately annotated atomic-fact benchmark.",
        "- Routing is scored without gold bubble pins; other application bubbles are excluded. Ingestion uses automatic routing for every item; exact set agreement with manual labels is required.",
        "- Correctness rubric: 0 incorrect/unsupported/abstention, 1 partial answer with a required fact missing, 2 all required facts correct at the requested date. Answer/retrieval failures are UNMEASURED and excluded from every metric denominator; failed judgements retain partial values and separate error counts, and dependent section 8.3 checks are UNMEASURED. Changed-fact accuracy is the fraction scoring 2.",
        "- Citation faithfulness is judged for each cited claim against the union of the cited stored originals, with valid spans supplied as additional context. Missing source text, invalid citations, or unsupported claims count as unfaithful. Zero citations yields 0 per-answer faithfulness. Multi-marker sentence claims are judged against the union of their cited sources.",
        "- Calibration uses thirty real v2 answer/reference triples from one specified run, stratified by judge score and spread across configurations/question types. Human labeling files omit configuration and judge score, retained in a separate key; exact agreement and Cohen kappa are computed when labels are supplied. Same-family answer and judge models may share biases (O3).",
        "- Duplicate audit samples 100 bubble-local entities deterministically; normalized equal names or cosine >=0.88 generate candidates, and the LLM confirms semantic identity. Same identity across bubbles is a duplicate only when global IDs differ; same-bubble duplicate nodes always count. Denominator is sampled nodes; each duplicate node counted once. Ungrounded rate uses all snapshot entities.",
        "- Memory samples application RSS plus Neo4j container usage; host/container sampling is approximate. Tokens/cost come from provider usage fields only; unavailable cost is N/A, never estimated from guessed prices.",
        "- Freshness measures injection->written and injection->first correct, nonempty-evidence own answer through the real queue. Frozen reruns retain the original freshness measurements. No pre-injection polling delay is simulated; the target still includes the configured poll interval.",
        "- External uses LlamaIndex default sentence splitting, default top-k and synthesis, same OpenAI-compatible model and shared local BGE embeddings. External routing is N/A; external citations refer to retrieved source nodes and are explicitly marked as source-node attribution.",
        "- Resource and usage totals include ingestion, audit, calibration, contamination, answers and judges, split by stage. Runtime errors and unsorted/failed ingestion are retained rather than silently removed.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return (
        str(report_path.resolve()),
        str(question_path.resolve()),
        str(config_path.resolve()),
    )


def reaggregate(answers_path, directory, snapshot="eval-v2", stamp="reaggregated"):
    """Offline report repair: read recorded rows only; never initialize clients or DBs."""
    from .metrics import aggregate, success_criteria

    rows = [
        json.loads(line)
        for line in Path(answers_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    metrics = aggregate(rows)
    global_metrics = {
        "run_validity": run_validity(metrics),
        "offline_reaggregation": True,
        "source": str(answers_path),
    }
    return write_report(
        directory,
        snapshot,
        stamp,
        metrics,
        rows,
        global_metrics,
        success_criteria(metrics, global_metrics),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Re-aggregate recorded answers offline (no provider calls)"
    )
    parser.add_argument("--answers", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--stamp", default="reaggregated")
    args = parser.parse_args()
    path, _, _ = reaggregate(args.answers, args.output_dir, stamp=args.stamp)
    print("\n".join(Path(path).read_text(encoding="utf-8").splitlines()[:7]))
    print(path)
