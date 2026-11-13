"""Render measured evidence and explicit provider-blocked cells; no model calls."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean

from omnistream.eval.diagnostics import summarize
from omnistream.eval.diagnostics.run import DATA, OUT, primary_answers, read

CONFIGS = ("classic", "graphiti", "own", "own+subagents", "classic+subagents")


def load(name):
    return json.loads((OUT / (name + ".json")).read_text(encoding="utf-8"))


def table(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "|" + "---|" * len(headers),
            *(
                "| "
                + " | ".join(str(v).replace("|", "/").replace("\n", " ") for v in row)
                + " |"
                for row in rows
            ),
        ]
    )


def fmt(value):
    return "NOT YET MEASURED" if value is None else f"{value:.3f}"


def ids(values):
    return ", ".join(v.replace("v2-q", "q") for v in sorted(values)) or "none"


def bubbles(values):
    labels = {"eval-v2-news": "N", "eval-v2-finance": "F", "eval-v2-research": "R"}
    return "+".join(labels.get(v, v) for v in values) or "unmeasured"


def main():
    summarize.main(False)
    answers = primary_answers()
    lookup = {
        (r["experiment"], r["configuration"], r["question_id"]): r for r in answers
    }
    retrieved = summarize.retrieval_cells(answers)
    stats, coverage = load("summary"), load("coverage")
    stages = load("stage_summary")
    ordinary = {r["question_id"]: r for r in stages if r["experiment"] == "E3"}
    oracle = {r["question_id"]: r for r in stages if r["experiment"] == "E4"}
    oracle_source = "E4 answer run"
    if len(oracle) != 20:
        oracle = {r["question_id"]: r for r in stages if r["experiment"] == "E4trace"}
        oracle_source = "LLM-free oracle-seed retrieval probe"
    multi = [q["id"] for q in DATA["questions"] if q["type"] == "multi_hop"]
    routes, routing = read("routes"), load("routing_comparison")
    exposure = load("cause_exposure")
    usage = [v for run in read("usage_final") for v in run["usage"].values()]
    tokens, cost = (
        sum(v["tokens"] for v in usage),
        sum(v["cost_usd"] or 0 for v in usage),
    )
    scored = coverage["scored_answer_cells"]
    seed_gains = {
        qid
        for qid in multi
        if retrieved.get(("E1", "own", qid), {}).get("recall_any", 0) < 1
        and retrieved.get(("E4", "own", qid), {}).get("recall_any") == 1
    }
    rank_losses = {
        qid
        for qid, r in oracle.items()
        if r["all_in_expansion"] and not r["all_in_top20"]
    }
    lines = [
        "# eval-v2 graph-retrieval diagnosis",
        "",
        "## Status and scope",
        "",
        f"**Offline diagnosis complete; model-based comparisons have explicit gaps.** {scored}/370 answer/judge cells are measured; {370 - scored} remain unmeasured. Retrieval is measured in {coverage['retrieval_cells']}/370 cells. The shared OpenRouter key reached its $5 lifetime cap; the owner confirmed $5.008 used and instructed completion without waiting. This diagnostic run's provider-reported spend is **USD {cost:.6f}**, not $5.008. Provider failures are never scored as incorrect answers.",
        "",
        "Answer/router/subagent model: `deepseek/deepseek-v4.1-flash-1017`. Harness judge: `deepseek/deepseek-chat`. **The frozen graph was built by the older `deepseek/deepseek-chat`.** Run 11 is historical evidence, never a substitute for a same-model ablation baseline. No production retrieval behaviour, thresholds, graph data or ingestion was changed.",
        "",
        "Correct means judge score 2; mean correctness remains on the 0–2 scale. Recall-any and Recall@10 use the harness's deduplicated runtime item IDs, including corroborating provenance and per-bubble interleaving for agents. Finding a gold item does not establish that its needed atomic assertion was selected. Item rank 10 is an evaluation cutoff; the answerer can see evidence beyond it. Own's fused top-20 fact cutoff, in contrast, really limits each search's returned facts.",
        "",
        "## Ranked causes and verdicts",
        "",
        table(
            [
                "Rank / suspected cause",
                "Verdict",
                "Measured size among 20 multi-hop questions",
                "Answer-level limit",
            ],
            [
                [
                    "1. Seed placement / bounded reachability",
                    "CONFIRMED",
                    f"Forcing gold MENTIONS seeds recovers complete returned gold-item coverage in {len(seed_gains)}/20: 1/20 → 14/20; expanded coverage 2/20 → 19/20",
                    "E1→E4 correctness gain NOT YET MEASURED (0 paired judged cells)",
                ],
                [
                    "2. Fusion after candidate recovery",
                    "CONFIRMED",
                    f"{len(rank_losses)}/20 have every gold item in oracle expansion and fact-score top20 but lose an item after fusion",
                    "Five is conditional on oracle seeds; no ranking-only answer intervention",
                ],
                [
                    "3. Missing/incorrect graph structure",
                    "CONFIRMED",
                    "13/20 exposed to at least one measured structural defect; alias-root connectivity fails in 2/20; missing/isolated defect anchors affect 8/20",
                    "Exposure is not thirteen independently attributable answer failures",
                ],
                [
                    "4. Current-validity filter hides historical bridge",
                    "CONFIRMED",
                    "Named January appointment claim excluded in 3/20 questions despite oracle seeds; history restores all three to candidates",
                    "Independent correctness gain NOT YET MEASURED",
                ],
                [
                    "Routing exclusion as the dominant CURRENT-model native failure",
                    "REJECTED",
                    "Only q11 is inaccessible in classic/Graphiti E0 selections; none in own. All-bubble local recall does not improve the multi-hop mean",
                    "E1 answer-level routing cost NOT YET MEASURED",
                ],
                [
                    "Graph identity/extraction defects individually cause the score gap",
                    "PARTLY",
                    "20 explicit alias splits, 2 clear wrong named-identity groups, 19/100 sampled facts judged faulty",
                    "No repaired-graph answer counterfactual was run",
                ],
                [
                    "Subagent behaviour explains CURRENT classic-agent superiority",
                    "NOT YET MEASURED",
                    "Own fixed-ten transcripts: 3/10; classic fixed-ten transcripts: 0/10; paired transcript cells: 0/10",
                    "Do not extrapolate the partial own-agent results",
                ],
                [
                    "500-edge expansion cap",
                    "REJECTED",
                    "0/20 ordinary and 0/20 oracle probes reach 500 facts",
                    "Not a bottleneck in these traces",
                ],
            ],
        ),
        "",
        "The ranking above orders measured retrieval losses and structural exposure. It does not invent a ranking of unmeasured correctness counterfactuals. Seed forcing alone, with unchanged fusion, improves full-item coverage by 13 questions. With ordinary seeds, full coverage is 1/20 under both the fact-score top20 and fused top20; fusion's five-question loss appears **after** oracle placement. Oracle candidates/fact-score top20 cover 19/20, an 18-question coverage upper bound over the ordinary returned 1/20 when seed placement and downstream selection losses are jointly bypassed. This is not an answer-accuracy estimate or a proposed fix.",
        "",
        f"Seed-intervention full-coverage gains: {ids(seed_gains)}. Conditional fusion losses: {ids(rank_losses)}. The 13 structural exposures overlap these sets and are not additive.",
        "",
        "## E0: current-model baseline",
        "",
    ]

    def metric_table(experiment):
        return table(
            [
                "Configuration",
                "Type",
                "Judged / target",
                "Retrieval n",
                "Fully correct / judged",
                "Mean correctness",
                "Recall-any",
                "Recall@10",
            ],
            [
                [
                    r["configuration"],
                    r["type"],
                    f"{r['scored']}/{r['n']}",
                    r["retrieval_measured"],
                    f"{r['correct']}/{r['scored']}"
                    if r["scored"]
                    else "NOT YET MEASURED",
                    fmt(r["correctness"]),
                    fmt(r["recall_any"]),
                    fmt(r["recall_at_10"]),
                ]
                for r in stats
                if r["experiment"] == experiment
            ],
        )

    lines += [
        metric_table("E0"),
        "",
        "All 35 classic, Graphiti and own baseline questions are judged. Own+subagents is judged only on q03, q04, q05, q06, q10 and q11; classic+subagents has no current-model judged result. Native multi-hop own is 1/20 fully correct versus classic 4/20; Graphiti is also 4/20, with mean 0.45 versus classic 0.40. A claim about the full 20-question current-model agent comparison would be unsupported.",
        "",
        "## E1: all three bubbles forced",
        "",
        metric_table("E1"),
        "",
        "The 105 native retrieval cells were completed without LLM calls. They reuse each E0 router's parsed time scope and force the union of all three bubbles. The SDK completion methods were guarded to reject any accidental model call. Answer correctness is unmeasured in all 175 E1 cells, as are agent-planned retrieval results. On resume, E1 holds E0 scope/flags fixed and changes only the bubble set; E4 reuses E1 metadata, avoiding an original-text-expansion flag confound.",
        "",
    ]
    comparisons = []
    for config in ("classic", "graphiti", "own"):
        for kind in ("multi_hop", "time_sensitive"):
            qs = [q["id"] for q in DATA["questions"] if q["type"] == kind]
            pairs = [
                (qid, retrieved["E0", config, qid], retrieved["E1", config, qid])
                for qid in qs
            ]
            gains = {qid for qid, a, b in pairs if b["recall_any"] > a["recall_any"]}
            losses = {qid for qid, a, b in pairs if b["recall_any"] < a["recall_any"]}
            comparisons.append(
                [
                    config,
                    kind,
                    len(pairs),
                    fmt(mean(a["recall_any"] for _, a, _ in pairs)),
                    fmt(mean(b["recall_any"] for _, _, b in pairs)),
                    fmt(mean(b["recall_any"] - a["recall_any"] for _, a, b in pairs)),
                    ids(gains),
                    ids(losses),
                ]
            )
    lines += [
        table(
            [
                "Config",
                "Type",
                "Paired n",
                "E0 recall-any",
                "E1 recall-any",
                "Difference",
                "Recall gains",
                "Recall losses",
            ],
            comparisons,
        ),
        "",
        "For multi-hop questions, all-bubble recall-any is unchanged for classic (0.600), falls from 0.833 to 0.758 for Graphiti, and falls from 0.308 to 0.292 for own. Adding bubbles can add competing candidates; ‘all bubbles’ is the requested intervention, not an oracle minimal relevant subset. The decreases must not be reported as a positive cost of routing. An unchanged bubble set can also produce answer variation, so no missing answer deltas are inferred from recall.",
        "",
        "### Router selection versus authored labels and actual ingestion",
        "",
        "N=News, F=Finance, R=Research. Actual assignments come from SQLite `items.bubble_ids`. One selected copy suffices for a replicated item; requiring the union of all its assigned bubbles overstates exclusion. In own mode the selected groups constrain seeds, while expansion can cross into unselected bubbles unless explicitly excluded; a selection miss is not a hard expansion gate. ‘unmeasured’ is not an empty route.",
        "",
    ]
    lines += [
        table(
            [
                "Question",
                "Expected",
                "Actual per gold item",
                "E0 C/G/O/O+A/C+A",
                "E2 five selections",
            ],
            [
                [
                    r["question_id"],
                    bubbles(r["expected_bubbles"]),
                    "; ".join(
                        k + ":" + bubbles(v)
                        for k, v in r["actual_bubbles_by_gold"].items()
                    ),
                    "; ".join(
                        bubbles(
                            lookup.get(("E0", c, r["question_id"]), {})
                            .get("routing", {})
                            .get("bubbles", [])
                        )
                        for c in CONFIGS
                    ),
                    "; ".join(
                        bubbles(t["decision"]["bubbles"])
                        for t in routes
                        if t["question_id"] == r["question_id"]
                    ),
                ]
                for r in routing
            ],
        ),
        "",
        "## E2: router stability, inputs and prompt/code",
        "",
    ]
    unstable = {
        q["id"]
        for q in DATA["questions"]
        if len(
            {
                tuple(sorted(r["decision"]["bubbles"]))
                for r in routes
                if r["question_id"] == q["id"]
            }
        )
        > 1
    }
    trial_rows = [
        t for r in routing for t in r["trials"] if isinstance(t["repeat"], int)
    ]
    lines += [
        table(
            ["Measure", "Result"],
            [
                ["Completed routes", f"{len(routes)}/300"],
                [
                    "Questions changing selection",
                    f"{len(unstable)}/60: {ids(unstable)}",
                ],
                [
                    "Omitted authored expected bubble",
                    f"{sum(not t['covers_expected'] for t in trial_rows)}/300",
                ],
                [
                    "Omitted every ingested copy of ≥1 gold item",
                    f"{sum(not t['covers_each_gold_actual'] for t in trial_rows)}/300, all q11",
                ],
                [
                    "Multi-hop trials with actual omission",
                    "4/100; 6/20 multi-hop questions change selection",
                ],
            ],
        ),
        "",
    ]
    stability = []
    for kind in ("single", "multi_hop", "time_sensitive", "freshness"):
        trials = [r for r in routes if r["type"] == kind]
        for name in ("News", "Finance", "Research"):
            bid = "eval-v2-" + name.lower()
            stability.append(
                [
                    kind,
                    len(trials),
                    name,
                    sum(
                        name in r["expected_bubbles"]
                        and bid not in r["decision"]["bubbles"]
                        for r in trials
                    ),
                    sum(
                        name not in r["expected_bubbles"]
                        and bid in r["decision"]["bubbles"]
                        for r in trials
                    ),
                ]
            )
    lines += [
        table(
            [
                "Type",
                "Trials",
                "Bubble",
                "Underselected versus label",
                "Overselected versus label",
            ],
            stability,
        ),
        "",
        "`QueryRouter.route` calls `LLMClient.chat_json` at its default **temperature=0.0**, without seed, top_p, max_tokens or JSON response_format. Omitted sampling settings use provider defaults. Temperature zero did not make selection deterministic. Malformed JSON can fall back to cosine top1; provider/transport errors propagate. The user payload is `{question,catalog,similarity_hints,pins,exclude}`. Catalog entries contain id/name/description/auto_summary. The system prompt makes user descriptions primary and authoritative, with summaries and cosine hints supplementary, and supplies the current UTC date and validity-date interpretation rules.",
        "",
        table(
            ["ID", "Name", "Actual catalog text", "Auto-summary"],
            [
                [b["id"], b["name"], b["description"], b["auto_summary"]]
                for b in read("metadata")[0]["catalog"]
            ],
        ),
        "",
        table(
            ["Example", "Actual cosine hints", "First selection"],
            [
                [
                    r["question_id"],
                    "; ".join(b + ":" + f"{s:.4f}" for b, s in r["decision"]["hints"]),
                    bubbles(r["decision"]["bubbles"]),
                ]
                for r in routes
                if r["repeat"] == 0
                and r["question_id"] in ("v2-q03", "v2-q04", "v2-q18")
            ],
        ),
        "",
        "The router sees topic descriptions, not episode contents, a company-to-bubble index, alias mappings or a retrieved evidence path. There is no explicit instruction to include every intermediate domain of an unnamed chain. Thus goal/topic words (‘research institution’, ‘membrane’) favour Research similarity and can make Finance seem unnecessary. Current-model rationales usually identify News plus intermediate funding/research hops, so the old log's large topic-only exclusion pattern is **not** assumed to persist. A supplementary historical-model router probe was blocked before its first response (n=0); it supports no new old-versus-new model claim. Saved rationales and all hints are in `routes.jsonl`.",
        "",
        "## E3: own-mode seeds, expansion and ranking",
        "",
        "All 20 multi-hop queries were traced with all three bubbles and local embeddings. The ordinary 100 raw seeds shrink to **68 after GlobalEntity deduplication** (3.4/query); the top5 vector budget is applied before that deduplication and is not refilled. **56/100 raw seeds are generic nodes**, versus 94/283 in the graph. Fifteen questions have some gold-mentioned seed, yet only two expanded graphs contain facts from every gold item. A gold-mentioned generic/isolated seed is not necessarily the useful anchor.",
        "",
        table(
            [
                "Question",
                "Seeds before dedup: name (bubble, score, source)",
                "Any gold MENTIONS seed",
                "Entities/facts",
                "Gold item: expanded / fused-top20 / best rank",
            ],
            [
                [
                    qid,
                    "; ".join(
                        s["entity"]["name"]
                        + " ("
                        + bubbles([s["entity"]["bubble"]])
                        + ", "
                        + f"{s['score']:.3f}"
                        + ", "
                        + s["source"]
                        + ")"
                        for s in ordinary[qid]["seeds"]
                    ),
                    ordinary[qid]["seed_mentions_gold"],
                    f"{ordinary[qid]['entities']}/{ordinary[qid]['facts']}",
                    "; ".join(
                        g["item"]
                        + ": "
                        + str(g["in_expansion"])
                        + " / "
                        + str(g["in_top20"])
                        + " / "
                        + str(min((r["rank"] for r in g["ranks"]), default="—"))
                        for g in ordinary[qid]["gold"]
                    ),
                ]
                for qid in multi
            ],
        ),
        "",
        "Every fact rank, signal rank, score, raw seed score/source/bubble, actual post-dedup seed ID and expanded fact/entity is retained in `stages.jsonl`; `stage_summary.json` gives every gold item's facts and all ranks. Ordinary expansion covers all gold items in 2/20; fact-score top20 and fused top20 each cover 1/20. No expansion reaches the 500-edge cap. q03 starts from generic funding agreements and the wrong Ivory Delta Laboratory. q10 reaches the right funding item but its best fact ranks 46.",
        "",
        "## E4: oracle seeds (retrieval complete; correctness blocked)",
        "",
        metric_table("E4"),
        "",
        f"Stage source: {oracle_source}. The seed wrapper forces all entities linked by MENTIONS from gold episodes; the production identity dedup, two-hop expansion, temporal filter, PageRank, fact score and fusion remain unchanged. These privileged seeds include answer-side entities and can bypass identity/path gaps: recovery identifies a placement/reachability gate, not the practical gain of changing just a question's initial name matcher. No E4 answer was generated or judged.",
        "",
        table(
            [
                "Question",
                "E1→E4 recall-any",
                "E4 Recall@10",
                "All gold expanded",
                "All gold fused top20",
                "Best fused ranks per gold",
            ],
            [
                [
                    qid,
                    fmt(retrieved["E1", "own", qid]["recall_any"])
                    + " → "
                    + fmt(retrieved["E4", "own", qid]["recall_any"]),
                    fmt(retrieved["E4", "own", qid]["recall_at_10"]),
                    oracle[qid]["all_in_expansion"],
                    oracle[qid]["all_in_top20"],
                    "; ".join(
                        g["item"]
                        + ":"
                        + str(min((r["rank"] for r in g["ranks"]), default="—"))
                        for g in oracle[qid]["gold"]
                    ),
                ]
                for qid in multi
            ],
        ),
        "",
        "Oracle seeds expand every gold item in 19/20 and retain every gold item in 14/20 fused results. The fact-score top20 alone covers all 19 available questions. Fusion drops five despite relevant fact-score ranks: q17 recall is rank 1 by fact score → fused rank 24 (recency rank 68); q24 rank 1 → 21; q47 rank 1 → 23. Confidence is 0.92 for 378/381 facts and 0.9936 for 3/381; ties correctly share ranks, so no arbitrary UUID penalty is inferred. Recency rankings compete with relevance even for historical bridge facts. No threshold or ranking fix was applied.",
        "",
        "![Own-mode full gold-item coverage](../../data/diagnostics/eval-v2/stage-coverage.png)",
        "",
        "### Additional temporal/atomic-bridge check (no LLM)",
        "",
        table(
            [
                "Question",
                "Required bridge",
                "Extracted claims",
                "Oracle current: expanded / fused ranks",
                "Oracle history: expanded / fused ranks",
            ],
            [
                [
                    r["question_id"],
                    r["required_bridge"],
                    len(r["extracted_facts"]),
                    r["conditions"].get("E4trace"),
                    r["conditions"].get("E4tracehistory"),
                ]
                for r in load("critical_bridges")
            ],
        ),
        "",
        "The explicit unbounded TimeScope probe allows historical nonempty intervals while preserving seed selection and hop limits. Ordinary full-item coverage stays 2/20 expanded and 1/20 fused. Oracle coverage changes 19/20→20/20 expanded but 14/20→13/20 fused. All five person-to-laboratory calibration links exist; two fact sentences omit the visiting-fellow qualifier. Named January appointment assertions are removed by default current-time filtering in q25/q32/q43. History restores all three, but q32's best appointment remains fused rank 27. In q25/q43 another fact from the leader item had survived, hiding this loss from item recall. Bubble copies have inconsistent historical validity, allowing one old appointment copy to survive for q18/q38. Answer benefits from the history probe were not measured.",
        "",
        "## E5: graph connectivity",
        "",
        table(
            [
                "Question",
                "One root entity reaches all other gold items ≤2 logical hops",
                "Failure class",
                "Virtual source-asserted alias joins restore test",
            ],
            [
                [
                    r["question_id"],
                    r["single_entity_rooted_within_two"],
                    r["failure_class"] or "—",
                    r["alias_join_rooted_within_two"],
                ]
                for r in load("connectivity")
            ],
        ),
        "",
        "This undirected grounded-only test ignores validity time: RELATES_TO is one hop; Entity→GlobalEntity←Entity is one hop. It requires one root entity, not different roots from the same episode. It passes 18/20; q04/q11 fail, and virtual addition of source-stated alias joins repairs both. The virtual adjacency list never changes Neo4j. Missing-entity, missing-fact and ungrounded counts are zero **for these two broad-test failures**, not for the whole graph. Passing can use incidental entities or wrong merges and does not prove a semantic answer chain.",
        "",
        table(
            ["Recall item", "Source discriminator", "Graph status"],
            [
                [r["item"], r["discriminator"], r["classification"]]
                for r in load("discriminator_connectivity")
            ],
        ),
        "",
        "Four of ten recall discriminators have no entity; three have an entity with no factual edge. Those seven recall-to-grant questions miss their recall gold item in ordinary all-bubble expansion. The same seven items support eight multi-hop questions, including q04. All 381 facts are marked grounded, so lexical grounding did not establish semantic correctness.",
        "",
        table(
            ["Structural exposure", "n /20", "Questions"],
            [[k, len(v), ids(v)] for k, v in exposure.items()],
        ),
        "",
        "The structural union is 13/20 exposed questions. Independent graph-repair correctness gain is NOT YET MEASURED; the exposure counts overlap.",
        "",
        "## E6: whole-snapshot graph quality",
        "",
        table(
            ["Measure", "Measured result"],
            [
                [
                    "Local entities / linked GlobalEntity IDs / facts / episode copies",
                    "283 / 171 / 381 / 123",
                ],
                ["Explicit source alias pairs / split / missing side", "20 / 20 / 0"],
                [
                    "Multi-member global groups audited",
                    "74; remaining 97 are single-member in this snapshot",
                ],
                [
                    "Clearly wrong named identity groups",
                    "2/171, involving 17/283 local nodes",
                ],
                [
                    "Generic-role/document conflations",
                    "12 groups, ontology-dependent, separated from clear named errors",
                ],
                [
                    "Fact precision: fixed-seed sample",
                    "81/100 supported; 18 wrong direction/subject; 1 unsupported",
                ],
                [
                    "Manual source read by research agent",
                    "16/20 supported; 15/20 agreement with judge",
                ],
                ["Generic non-name entities", "94/283 = 33.2%"],
            ],
        ),
        "",
        table(
            [
                "Abbreviation",
                "Source full name",
                "Separate unlinked identity",
                "Source",
            ],
            [
                [r["abbreviation"], r["full_name"], r["split"], r["source"]]
                for r in load("aliases")
            ],
        ),
        "",
        "Company aliases can have a RELATES_TO abbreviation assertion without sharing a GlobalEntity; no shared identity does not mean no path of any length. The clear wrong merges are Brindle Arc with explicitly legally distinct Brindle Arch (five local nodes), and nine differently numbered Dovetail Quay names under one identity (twelve nodes). Quay 10 has already been locally conflated with other numbered nodes. Equal proper names in different roles were not accepted as evidence of different people: the merge judge overcalled such errors, including Talia Muren as chief and visiting fellow. `merge_quality_review.json` conservatively separates two confirmed named groups, twelve ambiguous generic groups and sixty groups with no demonstrated wrong merge.",
        "",
        "The extraction sample is uniform over 381 stored relationships, including bubble copies, sorted by UUID and sampled with seed 20261113. The judge checks both assertion text and graph subject/relation/object against source episodes. Endpoint errors can damage traversal even if the accompanying sentence is usable by the answerer. Manual reading covers the first twenty fixed sample indices: the judge missed a fabricated deposit return direction and a positive FINANCED edge for an explicit denial, and wrongly rejected some reasonable triples. Thus 81% is judge-based precision, with an 80% manual subset and 75% agreement exposed; it is not independent human calibration. The generic-name rule includes common-noun descriptions, document/event labels and acronym-qualified chief roles, but excludes specific amounts and accession identifiers. Every classified node and manual judgment is saved.",
        "",
        "## E7: subagent behaviour and measurement gaps",
        "",
        "Fixed ten: q03, q04, q10, q17, q24, q31, q37, q43, q48, q58. This list mixes run-11 classic-agent successes and failures (four successes among the ten; own agents had zero). Current fixed-ten own transcripts are complete for q03/q04/q10 only (3/10), plus q11 outside the fixed list. Current classic-agent transcripts are 0/10. A current paired explanation of classic-agent superiority is NOT YET MEASURED.",
        "",
    ]
    historical = [
        json.loads(l)
        for l in Path("data/snapshots/eval-v2/runs/11/answers.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    tools = load("tool_summary")
    toolrows = []
    for qid in summarize.FIXED_TEN:
        row = [qid]
        for config in ("own+subagents", "classic+subagents"):
            ans = lookup.get(("E0", config, qid), {})
            calls = [
                r
                for r in tools["calls"]
                if r["experiment"] == "E0"
                and r["configuration"] == config
                and r["question_id"] == qid
            ]
            row += [
                ans.get("correctness", "unmeasured"),
                len(calls),
                len({g for c in calls for g in c["gold_items"]})
                if calls
                else "unmeasured",
            ]
        row += [
            next(
                r["correctness"]
                for r in historical
                if r["configuration"] == "classic+subagents" and r["question_id"] == qid
            )
        ]
        toolrows.append(row)
    lines += [
        table(
            [
                "Question",
                "Own current score",
                "Own calls",
                "Own gold items returned",
                "Classic current score",
                "Classic calls",
                "Classic gold items returned",
                "Historical classic-agent score",
            ],
            toolrows,
        ),
        "",
        "Observed q03: the initial Finance search `September brake seal recall chief resigned manufacturer grant research institution` returns 20 facts from eleven items, none gold. The initial Research search `September brake seal recall chief resigned manufacturer` returns 20 facts from nine items, none gold. News's initial event search returns the correct recall. Later explicit Halvex Mobility grant searches return the correct funding item; the merged answer is correct. Each of its three agents uses all six calls, all search, stopping at the tool limit. q04 collects recall and funding but not 0-study and answers incorrectly. The measured q03/q04/q10/q11 multi-hop agents all reach their six-call budgets; this is observed tool pressure, not proof of a current classic-agent causal advantage.",
        "",
        "Own `search` is entity seeding plus expansion. A query naming no proper entity can return generic/wrong-name neighborhoods (as observed), or no facts if neither cosine nor fuzzy seeding succeeds; it is not guaranteed to return zero. Classic search compares the query against chunk contents and can preserve an abbreviation, negation, date and bridge in the same passage. `read_item` can expose original wording missing from graph assertions. This is a code-level comparison; no current classic-agent transcript was invented. Graphiti hybrid fact-text search bypasses the entity-name seed gate, explaining its higher native item recall (0.833 versus own 0.308); it still inherits incomplete/wrong assertions and has only a small correctness advantage over classic here.",
        "",
        "Agents independently receive the same question; they do not exchange intermediate names during research. QA deduplicates collected facts/chunks, groups findings sharing GlobalEntity IDs, keeps joined bubbles adjacent, and appends per-bubble answers as supplementary notes. Numbered evidence, not notes, supplies citations. The full q03 per-bubble findings/joins/final answer are in `answers.jsonl`; full model/tool histories are in `agent_turns.jsonl` and `tools.jsonl`. `tool_summary.json` lists every captured query, result count, runtime/corpus item ID and gold hit. An identity-based join does not establish a valid semantic chain. Item Recall@10 can be very low even when later searches collect enough evidence for the final answer.",
        "",
        "## E8: time-sensitive failures",
        "",
    ]
    failures = load("time_failures")
    count = Counter((r["run"], r["configuration"], r["category"]) for r in failures)
    ntime = sum(
        r["type"] == "time_sensitive" and r.get("correctness") in (0, 1, 2)
        for r in answers
        if r["experiment"] == "E0"
    )
    lines += [
        f"Current E0 has {ntime}/75 judged time-sensitive cells; 14 are wrong/partial. Only scored cells are classified. All 75 comparable native/agent run-11 cells exist, with 27 wrong/partial. The union has eight distinct question IDs. Provider-blocked cells are excluded from failure categories, not called retrieval failures.",
        "",
        table(
            ["Run", "Configuration", "Category", "n"],
            [[*key, n] for key, n in sorted(count.items())],
        ),
        "",
        table(
            [
                "Run",
                "Configuration",
                "Question",
                "Category",
                "Missing gold items",
                "Recorded scope",
            ],
            [
                [
                    r["run"],
                    r["configuration"],
                    r["question_id"],
                    r["category"],
                    ", ".join(r["missing_gold"]) or "none",
                    r["time_scope"],
                ]
                for r in failures
            ],
        ),
        "",
        "All fourteen measured current failures are ‘immediately before the September recall’ questions with recorded null scopes. `_parse_scope` cannot resolve an event-relative day and returns None; graph retrieval defaults to now and `generate_answer` adds **‘Answer for now: prefer the most recent statement valid now.’** The scope/prompt mismatch is confirmed; its independent answer-level remedy has not been tested. Two current own-agent time cases are correct, so this mechanism does not force failure in every configuration.",
        "",
        "Run 11 did not save router scopes, so they remain unmeasured rather than reconstructed as observations. Its ‘both old and new’ category is an item-level evidence classification with atomic-fact completeness explicitly uncertain. Two old own-agent answers (q06/q27) report cancellation on October 7 instead of the source's October 6. Their graph termination validity uses publication time; across the snapshot, 13/17 termination assertions use October 7 and four use October 6. This is a temporal metadata error, distinguished from the q13 old own-agent case with absent evidence. Source/answer text and all relevant validity metadata are in `time_failures.json` and `termination_dates.json`.",
        "",
        "## Exact coverage, checkpoint and resume",
        "",
        f"The authoritative per-cell journal is `data/diagnostics/eval-v2/answers.jsonl`; `cell_checkpoint.jsonl` gives one status record for every one of the 370 planned cells, with model-result and retrieval-result status separately. `coverage.json` lists all {370 - scored} unmeasured answer cells. A score of zero is retained as a finished measurement; 403 failures are unfinished. `offline_retrieval.jsonl` contains the 105 native E1 and 20 E4 local retrieval cells and is never mistaken for a judged answer.",
        "",
        "Once the owner restores provider capacity, run exactly from the repository root:",
        "",
        "```powershell",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.resume",
        "```",
        "",
        "It skips every already scored cell, retries failed/unscored cells, reuses a cached answer if only its judge failed, and fsyncs cell records. The two in-flight cells settle before a capacity error aborts further calls; it will not spray 403s across the remaining grid. Oracle routing reuses baseline scope/flags and oracle seeds are still supplied only by diagnostics. Three offline billing-safety tests verify finished-cell skipping, failure resumability/fail-fast behaviour, and judge-only retries without answer regeneration. No model-based resume was run after the instruction to finish offline.",
        "",
        "## Cost, integrity, validation and limits",
        "",
        f"Provider-reported total: **{tokens:,} tokens, USD {cost:.9f}**. Usage totals include the completed baseline calls, all router repetitions, 100 fact judges and 74 merge judges, plus all other returned completions. `usage_final.jsonl` holds final per-process/stage totals; do not sum cumulative `usage.jsonl` checkpoints. Missing provider cost is not estimated from prices. The failed historical-router supplement has zero returned measurements and zero reported usage; the shared account-key $5.008 total includes work outside this diagnostic.",
        "",
        f"Integrity: {read('integrity')[-1]}. Frozen file bytes and the normalized graph export match initial hashes. SQLite uses read-only URI mode without Repository schema migration; Chroma reads a diagnostic copy; Graphiti is built read-only. No source data, Neo4j facts, corpus, CLI, pyproject, `.env` or production retrieval file was edited by this work; no commit was made. No optional production trace hook was added. Other work in the shared checkout is outside this diagnostic's changes.",
        "",
        f"Live-clock sensitivity: {load('clock_sensitivity')['rankings_checked']} saved fusion rankings checked, {load('clock_sensitivity')['rankings_changed']} changed; {len(load('clock_sensitivity')['fact_validity_changes'])} fact-validity changes across the measurement interval. The run crossed a UTC day but no question's yearless date crossed an occurrence boundary.",
        "",
        "Validation: `ruff check src/omnistream/eval/diagnostics` passed; diagnostic checkpoint tests **3 passed**. Original offline suite **985 passed, 1 skipped, 21 deselected**; the final validation log records any additional tests from concurrent checkout work.",
        "",
        "Limits: 35 end-to-end questions (20 multi-hop, 15 time-sensitive); three repeated synthetic question families with two three-record variants; no held-out real-data generalisation. The graph-builder model is older than the answer/router model. The fact sample includes bubble copies; manual review is by the research agent, not independent human calibration. Item recall is coarser than needed-assertion recall. Partial agent results are not extrapolated to twenty questions. E1/E4 correctness and the requested current paired classic-agent tool comparison remain NOT YET MEASURED. No thresholds, graph repairs or ranking fixes were proposed or tested.",
        "",
        "## Offline reproduction",
        "",
        "These commands read saved results and/or local embeddings; they do not require model capacity:",
        "",
        "```powershell",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.offline",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.trace",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.trace --oracle",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.trace --history",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.trace --oracle --history",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.manual",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.bridges",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.summarize",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.critical",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.clock_check",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.verify",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.plot",
        ".venv\\Scripts\\python.exe -m omnistream.eval.diagnostics.report",
        ".venv\\Scripts\\ruff.exe check src/omnistream/eval/diagnostics",
        ".venv\\Scripts\\python.exe -m pytest -q src/omnistream/eval/diagnostics/test_checkpoint.py",
        ".venv\\Scripts\\python.exe -m pytest -q",
        "```",
        "",
        "Plotting uses isolated dependencies under `data/diagnostics/eval-v2/plot-deps`, leaving the project's environment and dependency files unchanged. If that helper directory is absent: `.venv\\Scripts\\python.exe -m pip install --target data/diagnostics/eval-v2/plot-deps matplotlib==3.11.2`. `manual_reviews.json` preserves source-read labels; `manual.py` validates fixed sample IDs before exporting them. The completed E2 and E6 model artifacts can be inspected without rerunning their model calls. All trace/model journals are under `data/diagnostics/eval-v2/`.",
        "",
    ]
    Path("docs/diagnostics/eval-v2-diagnosis.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(
        f"Report written: {scored}/370 judged; {coverage['retrieval_cells']}/370 retrieval cells; ${cost:.6f}"
    )


if __name__ == "__main__":
    main()
