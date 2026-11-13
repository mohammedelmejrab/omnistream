"""Reduce raw diagnostics to question-level tables without new model calls."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from statistics import mean

from omnistream.eval.diagnostics.audit import normalized
from omnistream.eval.diagnostics.run import (
    DATA,
    IDS,
    OUT,
    REVERSE,
    SNAP,
    gold_entities,
    primary_answers,
    read,
)

FIXED_TEN = (
    "v2-q03",
    "v2-q04",
    "v2-q10",
    "v2-q17",
    "v2-q24",
    "v2-q31",
    "v2-q37",
    "v2-q43",
    "v2-q48",
    "v2-q58",
)
QUESTIONS = {q["id"]: q for q in DATA["questions"]}


def provenance(fact):
    return {fact["item_id"], *fact.get("item_ids", [])}


def retrieval_cells(answers=None):
    rows = {
        (r["experiment"], r["configuration"], r["question_id"]): r
        for r in read("offline_retrieval")
        if "recall_any" in r and not r.get("error")
    }
    for row in primary_answers() if answers is None else answers:
        if "recall_any" in row and "retrieved_item_ids" in row:
            rows[row["experiment"], row["configuration"], row["question_id"]] = row
    return rows


def summary(answers):
    retrieved = retrieval_cells(answers)
    groups = defaultdict(list)
    for row in answers:
        groups[row["experiment"], row["configuration"], row["type"]].append(row)
    rows = []
    for (experiment, config, kind), values in groups.items():
        good = [r for r in values if r.get("correctness") in (0, 1, 2)]
        measured_retrieval = [
            retrieved[experiment, config, r["question_id"]]
            for r in values
            if (experiment, config, r["question_id"]) in retrieved
        ]
        rows.append(
            {
                "experiment": experiment,
                "configuration": config,
                "type": kind,
                "n": len(values),
                "scored": len(good),
                "retrieval_measured": len(measured_retrieval),
                "correct": sum(r["correctness"] == 2 for r in good),
                "correctness": mean(r["correctness"] for r in good) if good else None,
                "recall_any": mean(r["recall_any"] for r in measured_retrieval)
                if measured_retrieval
                else None,
                "recall_at_10": mean(r["recall_at_10"] for r in measured_retrieval)
                if measured_retrieval
                else None,
                "errors": sorted(
                    {
                        "OpenRouter key lifetime capacity exceeded (403)"
                        if "key limit exceeded" in r.get("error", "").casefold()
                        else r["error"]
                        for r in values
                        if r.get("error")
                    }
                ),
            }
        )
    return rows


def routing(answers):
    con = sqlite3.connect(f"file:{(SNAP / 'state.db').as_posix()}?mode=ro", uri=True)
    assigned = {
        row[0]: json.loads(row[1])
        for row in con.execute("SELECT id,bubble_ids FROM items")
    }
    con.close()
    rows = []
    for q in DATA["questions"]:
        actual = {item: assigned[IDS[item]] for item in q["gold"]}
        expected = {"eval-v2-" + b.lower() for b in q["expected_bubbles"]}
        trials = [r for r in read("routes") if r["question_id"] == q["id"]]
        trials += [
            {"repeat": r["configuration"], "decision": r["routing"]}
            for r in answers
            if r["experiment"] == "E0"
            and r["question_id"] == q["id"]
            and "routing" in r
        ]
        rows.append(
            {
                "question_id": q["id"],
                "type": q["type"],
                "expected_bubbles": sorted(expected),
                "actual_bubbles_by_gold": actual,
                "trials": [
                    {
                        "repeat": r["repeat"],
                        "selected": r["decision"]["bubbles"],
                        "covers_expected": expected <= set(r["decision"]["bubbles"]),
                        "covers_each_gold_actual": all(
                            set(bs) & set(r["decision"]["bubbles"])
                            for bs in actual.values()
                        ),
                        "decision": r["decision"],
                    }
                    for r in trials
                ],
            }
        )
    return rows


def stage_tables(graph):
    traces = defaultdict(dict)
    for row in read("stages"):
        if (
            row.get("experiment")
            in ("E3", "E1", "E4", "E4trace", "E3history", "E4tracehistory")
            and row.get("configuration") == "own"
        ):
            traces[row["experiment"], row["question_id"]][row["event"]] = row
    rows = []
    for (experiment, qid), events in traces.items():
        q = QUESTIONS[qid]
        if q["type"] != "multi_hop":
            continue
        seed_list = events.get("seeds", {}).get("seeds", [])
        gold_set = gold_entities(q, graph)
        expanded = events.get("expansion", {}).get("graph", {})
        ranking = events.get("fusion", {}).get("full_ranking", [])
        expanded_facts = expanded.get("facts", [])
        by_id = {f["id"]: f for f in expanded_facts}
        gold = []
        for item in q["gold"]:
            facts = [f for f in expanded_facts if IDS[item] in provenance(f)]
            ranks = [
                {
                    "rank": rank,
                    "fact_id": entry["fact"]["id"],
                    "signals": entry["ranks"],
                    "score": entry["score"],
                }
                for rank, entry in enumerate(ranking, 1)
                if entry["fact"]["id"] in by_id
                and IDS[item] in provenance(by_id[entry["fact"]["id"]])
            ]
            gold.append(
                {
                    "item": item,
                    "in_expansion": bool(facts),
                    "in_top20": any(r["rank"] <= 20 for r in ranks),
                    "in_fact_score_top20": any(
                        r["signals"]["fact_score"] <= 20 for r in ranks
                    ),
                    "ranks": ranks,
                    "fact_texts": [f["text"] for f in facts],
                }
            )
        rows.append(
            {
                "experiment": experiment,
                "question_id": qid,
                "seeds": seed_list,
                "seed_mentions_gold": any(
                    s["entity"]["id"] in gold_set for s in seed_list
                ),
                "gold_seed_count": sum(
                    s["entity"]["id"] in gold_set for s in seed_list
                ),
                "entities": len(expanded.get("entities", {})),
                "facts": len(expanded_facts),
                "hit_cap": len(expanded_facts) == 500,
                "gold": gold,
                "all_in_expansion": all(g["in_expansion"] for g in gold),
                "all_in_top20": all(g["in_top20"] for g in gold),
                "all_in_fact_score_top20": all(g["in_fact_score_top20"] for g in gold),
            }
        )
    return rows


def tool_tables(answers):
    rows = []
    for row in read("tools"):
        if row.get("question_id") not in FIXED_TEN:
            continue
        result = row["result"]
        entries = (
            result.get("facts", []) + result.get("chunks", []) + result.get("parts", [])
        )
        returned = {item for entry in entries for item in provenance(entry)}
        q = QUESTIONS[row["question_id"]]
        rows.append(
            {
                **{
                    k: row[k]
                    for k in (
                        "experiment",
                        "configuration",
                        "question_id",
                        "bubble",
                        "call",
                    )
                },
                "result_count": len(entries),
                "item_ids": sorted(returned),
                "corpus_item_ids": sorted(REVERSE.get(i, i) for i in returned),
                "gold_items": [g for g in q["gold"] if IDS[g] in returned],
                "error": result.get("error"),
            }
        )
    merges = [
        {
            "experiment": r["experiment"],
            "configuration": r["configuration"],
            "question_id": r["question_id"],
            "correctness": r.get("correctness"),
            "multi_hop": r.get("multi_hop"),
            "answer": r.get("answer"),
        }
        for r in answers
        if r["question_id"] in FIXED_TEN and "+" in r["configuration"]
    ]
    return {"fixed_ten": FIXED_TEN, "calls": rows, "merges": merges}


def time_failures(answers, graph):
    historical = [
        json.loads(l)
        for l in (SNAP / "runs/11/answers.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    failures = []
    for experiment, rows in (("run11", historical), ("E0", answers)):
        for row in rows:
            if (
                row["configuration"] == "external"
                or row.get("correctness") not in (0, 1, 2)
                or row["type"] != "time_sensitive"
                or row.get("correctness") == 2
                or (experiment == "E0" and row["experiment"] != "E0")
            ):
                continue
            q = QUESTIONS[row["question_id"]]
            retrieved = set(row.get("retrieved_item_ids", []))
            gold = {IDS[i] for i in q["gold"]}
            scope = row.get("routing", {}).get("time_scope")
            if experiment == "run11":
                # Original harness did not persist router time scopes.
                scope = "not recorded"
            if (
                "immediately before" in q["question"]
                and experiment == "E0"
                and scope is None
            ):
                label = "wrong/absent time scope"
                why = "Event-relative before cue parses to null; graph retrieval defaults to now and answer system prompt says answer for now. Evidence availability is recorded separately."
            elif gold <= retrieved:
                label = "both old and new retrieved but answer chose wrong"
                why = "Both gold episodes present in item-level evidence; requires source/answer reading to distinguish relevant fact omission from synthesis."
            else:
                label = "evidence not retrieved"
                why = "One or more gold episodes absent; see fact-validity inspection before interpreting as extraction/retrieval failure."
            relevant_facts = [f for f in graph["facts"] if provenance(f["fact"]) & gold]
            if (
                experiment == "run11"
                and row["configuration"] == "own+subagents"
                and q["id"] in ("v2-q06", "v2-q27")
            ):
                label = "historical fact not marked or filtered wrongly"
                why = "Manual source/answer review: cancellation is October 6 in source, but termination valid_at uses October 7 publication date and answer/agent notes report October 7. Temporal metadata error, not evidence of a router-scope error. Missing old agreement is secondary and does not explain the wrong cancellation date."
            failures.append(
                {
                    "run": experiment,
                    "configuration": row["configuration"],
                    "question_id": q["id"],
                    "correctness": row.get("correctness"),
                    "category": label,
                    "reason": why,
                    "time_scope": scope,
                    "missing_gold": [REVERSE[g] for g in gold - retrieved],
                    "answer": row.get("answer"),
                    "facts": [
                        {k: v for k, v in f["fact"].items() if "embedding" not in k}
                        for f in relevant_facts
                    ],
                }
            )
    return failures


def main(verbose=True):
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    answers = primary_answers()
    registry = retrieval_cells(answers)
    checkpoint = []
    for row in answers:
        key = row["experiment"], row["configuration"], row["question_id"]
        scored = row.get("correctness") in (0, 1, 2)
        checkpoint.append(
            {
                "experiment": key[0],
                "configuration": key[1],
                "question_id": key[2],
                "type": row["type"],
                "answer_status": "MEASURED" if scored else "NOT YET MEASURED",
                "correctness": row.get("correctness"),
                "retrieval_status": "MEASURED"
                if key in registry
                else "NOT YET MEASURED",
                "retrieval_only": key in registry
                and registry[key].get("retrieval_only", False),
                "provider_blocked": not scored
                and "limit exceeded" in row.get("error", "").casefold(),
                "answer_journal": "answers.jsonl",
                "retrieval_journal": "offline_retrieval.jsonl"
                if key in registry and registry[key].get("retrieval_only")
                else "answers.jsonl",
            }
        )
    (OUT / "cell_checkpoint.jsonl").write_text(
        "\n".join(json.dumps(r) for r in checkpoint) + "\n", encoding="utf-8"
    )
    granularity = []
    for row in answers:
        retrieval = row.get("retrieval") or {}
        primary = {f["fact"]["item_id"] for f in retrieval.get("facts", [])} | {
            c["item_id"] for c in retrieval.get("chunks", [])
        }
        gold = set(row["gold_item_ids"])
        secondary_only = (gold & set(row.get("retrieved_item_ids", []))) - primary
        granularity.append(
            {
                "experiment": row["experiment"],
                "configuration": row["configuration"],
                "question_id": row["question_id"],
                "type": row["type"],
                "gold_in_primary_context": sorted(primary & gold),
                "gold_credited_only_via_secondary_provenance": sorted(secondary_only),
                "primary_recall_any": len(primary & gold) / len(gold),
            }
        )
    artifacts = {
        "summary": summary(answers),
        "routing_comparison": routing(answers),
        "stage_summary": stage_tables(graph),
        "tool_summary": tool_tables(answers),
        "time_failures": time_failures(answers, graph),
        "evidence_granularity": granularity,
        "coverage": {
            "planned_answer_cells": len(checkpoint),
            "scored_answer_cells": sum(
                r["answer_status"] == "MEASURED" for r in checkpoint
            ),
            "retrieval_cells": len(registry),
            "missing_answer_cells": [
                r for r in checkpoint if r["answer_status"] != "MEASURED"
            ],
        },
    }
    for name, payload in artifacts.items():
        (OUT / (name + ".json")).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if not verbose:
        return
    print(
        json.dumps(
            [
                {k: v for k, v in r.items() if k != "errors"}
                for r in artifacts["summary"]
            ],
            indent=2,
        )
    )
    routes = read("routes")
    print(
        "E2",
        len(routes),
        "unstable",
        sum(
            len(
                {
                    tuple(sorted(r["decision"]["bubbles"]))
                    for r in routes
                    if r["question_id"] == q["id"]
                }
            )
            > 1
            for q in DATA["questions"]
        ),
    )
    print("E6 labels", Counter(r["label"] for r in read("fact_quality")))
    print(
        "Named merge groups",
        [
            (gid, [e["name"] for e in members])
            for gid, members in _groups(graph).items()
            if len({normalized(e["name"]) for e in members}) > 1
        ],
    )


def _groups(graph):
    groups = defaultdict(list)
    for entity in graph["entities"]:
        groups[entity["global_id"]].append(entity)
    return groups


if __name__ == "__main__":
    main()
