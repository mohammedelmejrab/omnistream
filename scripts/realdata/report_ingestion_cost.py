"""Reproduce the real-v2 cost report from saved measurements, without API calls."""

import csv
import json
import random
from pathlib import Path
from statistics import correlation

from omnistream.eval.dataset import load_dataset
from omnistream.eval.real.dataset import SEED, selection_digest

BASE = Path("docs/realdata")


def evaluation_estimates():
    path = Path("docs/eval/eval-v2-20261112T050602182241Z.configurations.csv")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = []
    # Scenario: unchanged prompt/completion mix (90/10), and unchanged caching.
    ratio = (0.9 * 0.15 + 0.1 * 0.60) / (0.9 * 0.32 + 0.1 * 0.89)
    for row in rows:
        n = int(row["questions"])
        answer, judge = float(row["cost_usd"]), float(row["judge_cost_usd"])
        result.append(
            {
                "configuration": row["configuration"],
                "questions": n,
                "answer_tokens": int(row["tokens"]),
                "judge_tokens": int(row["judge_tokens"]),
                "old_answer_usd": answer,
                "judge_usd": judge,
                "per_question_usd": (answer * ratio + judge) / n,
                "per_question_low_usd": (answer * (0.15 / 0.32) + judge) / n,
                "per_question_high_usd": (answer * (0.60 / 0.89) + judge) / n,
                "run_usd": answer * ratio + judge,
            }
        )
    return result


def selections(rows):
    by_id = {row["id"]: row for row in rows}
    result = []
    for split, background, fallback in (("dev", 40, 120), ("test", 60, 200)):
        try:
            data = load_dataset("real-v2", split=split, background=background)
            ids = data["selected_item_ids"]
            label = f"{split}: actual required items + background {background}"
        except (FileNotFoundError, ValueError) as exc:
            ids = random.Random(SEED).sample(sorted(by_id), fallback)
            label = f"{split}: hypothetical {fallback}-item fixed-seed sample ({exc})"
        selected = [by_id[item_id] for item_id in ids]
        result.append(
            {
                "label": label,
                "item_ids": sorted(ids),
                "digest": selection_digest(ids),
                "count": len(ids),
                "words": sum(row["word_count"] for row in selected),
                "words_by_bubble": {
                    bubble: sum(
                        row["word_count"]
                        for row in selected
                        if row["bubble_hint"] == bubble
                    )
                    for bubble in ("news", "finance", "research")
                },
            }
        )
    result.append(
        {
            "label": "full 350-item corpus",
            "item_ids": sorted(by_id),
            "digest": selection_digest(by_id),
            "count": len(rows),
            "words": sum(row["word_count"] for row in rows),
            "words_by_bubble": {
                bubble: sum(
                    row["word_count"] for row in rows if row["bubble_hint"] == bubble
                )
                for bubble in ("news", "finance", "research")
            },
        }
    )
    return result


def main():
    rows = [
        json.loads(line)
        for line in Path("src/omnistream/eval/real/real-v2-manifest.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    path = BASE / "real-v2-costprobe.json"
    measurement = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    )
    items = measurement["items"] if measurement else []
    complete = measurement and measurement["status"] == "completed" and len(items) == 10
    costs_known = complete and all(
        i["usage"] and i["usage"]["cost_usd"] is not None for i in items
    )
    lines = [
        "# real-v2 ingestion cost",
        "",
        "No full snapshot was built. Only the ten-item throwaway probe is authorized.",
        "",
    ]
    if not measurement:
        lines += [
            "**BLOCKED: no live measurement.** LLM_API_KEY is absent from the process environment; the task prohibits opening `.env`. The private key-entry request timed out without delivery. No provider requests have been made; actual spend is $0.00. No throwaway snapshot has been created. A read-only Neo4j check verified zero nodes for the `real-v2-costprobe` prefix and the snapshot directory is absent; no cleanup was necessary.",
            "",
        ]
    else:
        lines += [
            f"Probe status: **{measurement['status']}**. Model: `{measurement['model']}`. Seed: {measurement['seed']}.",
            "",
            "| Item (ID prefix) | Stratum | Words | Calls | Prompt tokens | Completion tokens | Provider USD | Seconds | Episodes | New entities (net) | New facts (net) |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for item in items:
            u = item["usage"] or {}
            lines.append(
                f"| {item['title']} (`{item['id'][:12]}`) | {item['bubble_hint']} | {item['words']} | {u.get('calls')} | {u.get('prompt_tokens')} | {u.get('completion_tokens')} | {u.get('cost_usd')} | {item['wall_seconds']:.2f} | {item['episodes']} | {item['entities']} | {item['facts']} |"
            )
        lines += [
            "",
            f"Cleanup: remaining prefix nodes = {measurement.get('remaining_prefix_nodes', 'UNVERIFIED')}; snapshot directory removed = {measurement.get('snapshot_directory_removed', 'UNVERIFIED')}.",
            "",
        ]
    projection = selections(rows)
    if costs_known:
        cost = sum(i["usage"]["cost_usd"] for i in items)
        words = sum(i["words"] for i in items)
        rates = {
            b: sum(i["usage"]["cost_usd"] for i in items if i["bubble_hint"] == b)
            / sum(i["words"] for i in items if i["bubble_hint"] == b)
            for b in ("news", "finance", "research")
        }
        lines += [
            f"Ten items: **${cost:.6f}**, {words:,} words; **${cost / 10:.6f}/item**, **${cost / words * 1000:.6f}/1,000 words**.",
            "",
        ]
        predictors = {}
        for key in ("words", "episodes", "document_split_episodes"):
            try:
                predictors[key] = (
                    correlation(
                        [i[key] for i in items], [i["usage"]["cost_usd"] for i in items]
                    )
                    ** 2
                )
            except ValueError:
                predictors[key] = None
        ranked = {k: v for k, v in predictors.items() if v is not None}
        lines += [
            f"Sample Pearson r²: {json.dumps(predictors)}. Strongest measured association: {max(ranked, key=ranked.get) if ranked else 'unidentifiable'}. Ten deliberately stratified observations do not establish causation or a reliable population confidence interval.",
            "",
            "Projection method: estimate provider USD/word separately for News, Finance and Research from the probe, multiply each rate by that stratum's actual selected manifest word total, and sum. The pooled USD/word alternative is shown as a sensitivity check. These exclude freshness answering/judging, audit and evaluation. Graph growth, entity density, cross-bubble routing and retries can change costs substantially.",
            "",
        ]
        for selected in projection:
            selected["projected_usd"] = sum(
                rates[b] * n for b, n in selected["words_by_bubble"].items()
            )
            selected["pooled_projected_usd"] = cost / words * selected["words"]
    else:
        lines += [
            "Ingestion USD/item, USD/1,000 words, strongest cost predictor, and USD projections are **NOT MEASURED**. Word totals below are real manifest inputs, not cost measurements.",
            "",
        ]
    lines += [
        "| Snapshot selection | Items | Actual manifest words | Stratum projection USD | Pooled projection USD |",
        "|---|---:|---:|---:|---:|",
    ]
    for selected in projection:
        lines.append(
            f"| {selected['label']} | {selected['count']} | {selected['words']:,} | {selected.get('projected_usd', 'NOT MEASURED')} | {selected.get('pooled_projected_usd', 'NOT MEASURED')} |"
        )
    lines += [
        "",
        "The companion projection JSON records the exact selected IDs and SHA-256 digest. Missing or invalid split annotations produce explicitly hypothetical samples; they are never silently ingested.",
        "",
        "The existing SnapshotBuilder calls C1 Intake for an API source, C3 automatic routing, then C4 GraphWriter and Chroma chunks. It does **not** call C1 `load_document` / `split_episodes` for Graphiti episodes. Observed episodes are counted from Neo4j; `document_split_episodes` records how many 1,500-token document parts the upload path would create, for comparison only. The system under test was not changed. New entity/fact counts are net group-count deltas (deduplication can reduce them); global entities are excluded.",
        "",
        "## Evaluation run estimate",
        "",
        "Source: `docs/eval/eval-v2-20261112T050602182241Z.md` and its configurations CSV (60 questions/configuration). Old recordings contain only total tokens, not prompt/completion counts. Exact repricing is impossible. Central scenario assumes a stable 90% prompt / 10% completion mix and unchanged caching: answer costs × ((0.9×0.15+0.1×0.60)/(0.9×0.32+0.1×0.89)) = ×0.517241. Sensitivity range uses all-prompt ×0.46875 through all-completion ×0.674157. These are pricing scenarios, not confidence bounds. Judge stays `deepseek/deepseek-chat`; its recorded provider cost is unchanged. Larger real documents/retrieved contexts may increase tokens. No new evaluation requests were sent.",
        "",
        "| Configuration | Estimated USD/question incl. judge | Mix sensitivity USD/question | Estimated 60-question run USD |",
        "|---|---:|---:|---:|",
    ]
    estimates = evaluation_estimates()
    for row in estimates:
        lines.append(
            f"| {row['configuration']} | {row['per_question_usd']:.6f} | {row['per_question_low_usd']:.6f}–{row['per_question_high_usd']:.6f} | {row['run_usd']:.6f} |"
        )
    lines += [
        "",
        f"All six configurations, 60 questions each: estimated **${sum(r['run_usd'] for r in estimates):.6f}** for answers + per-answer judges. Shared contamination, audit, calibration and snapshot construction are additional; this is not a measured real-v2 evaluation run.",
        "",
    ]
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "real-v2-ingestion-cost.md").write_text("\n".join(lines), encoding="utf-8")
    (BASE / "real-v2-ingestion-projections.json").write_text(
        json.dumps({"selections": projection, "evaluation": estimates}, indent=2),
        encoding="utf-8",
    )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
