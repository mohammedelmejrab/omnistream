# eval-v2 graph-retrieval diagnosis

## Status and scope

**Offline diagnosis complete; model-based comparisons have explicit gaps.** 111/370 answer/judge cells are measured; 259 remain unmeasured. Retrieval is measured in 236/370 cells. The shared OpenRouter key reached its $5 lifetime cap; the owner confirmed $5.008 used and instructed completion without waiting. This diagnostic run's provider-reported spend is **USD 0.735018**, not $5.008. Provider failures are never scored as incorrect answers.

Answer/router/subagent model: `deepseek/deepseek-v4.1-flash-1017`. Harness judge: `deepseek/deepseek-chat`. **The frozen graph was built by the older `deepseek/deepseek-chat`.** Run 11 is historical evidence, never a substitute for a same-model ablation baseline. No production retrieval behaviour, thresholds, graph data or ingestion was changed.

Correct means judge score 2; mean correctness remains on the 0–2 scale. Recall-any and Recall@10 use the harness's deduplicated runtime item IDs, including corroborating provenance and per-bubble interleaving for agents. Finding a gold item does not establish that its needed atomic assertion was selected. Item rank 10 is an evaluation cutoff; the answerer can see evidence beyond it. Own's fused top-20 fact cutoff, in contrast, really limits each search's returned facts.

## Ranked causes and verdicts

| Rank / suspected cause | Verdict | Measured size among 20 multi-hop questions | Answer-level limit |
|---|---|---|---|
| 1. Seed placement / bounded reachability | CONFIRMED | Forcing gold MENTIONS seeds recovers complete returned gold-item coverage in 13/20: 1/20 → 14/20; expanded coverage 2/20 → 19/20 | E1→E4 correctness gain NOT YET MEASURED (0 paired judged cells) |
| 2. Fusion after candidate recovery | CONFIRMED | 5/20 have every gold item in oracle expansion and fact-score top20 but lose an item after fusion | Five is conditional on oracle seeds; no ranking-only answer intervention |
| 3. Missing/incorrect graph structure | CONFIRMED | 13/20 exposed to at least one measured structural defect; alias-root connectivity fails in 2/20; missing/isolated defect anchors affect 8/20 | Exposure is not thirteen independently attributable answer failures |
| 4. Current-validity filter hides historical bridge | CONFIRMED | Named January appointment claim excluded in 3/20 questions despite oracle seeds; history restores all three to candidates | Independent correctness gain NOT YET MEASURED |
| Routing exclusion as the dominant CURRENT-model native failure | REJECTED | Only q11 is inaccessible in classic/Graphiti E0 selections; none in own. All-bubble local recall does not improve the multi-hop mean | E1 answer-level routing cost NOT YET MEASURED |
| Graph identity/extraction defects individually cause the score gap | PARTLY | 20 explicit alias splits, 2 clear wrong named-identity groups, 19/100 sampled facts judged faulty | No repaired-graph answer counterfactual was run |
| Subagent behaviour explains CURRENT classic-agent superiority | NOT YET MEASURED | Own fixed-ten transcripts: 3/10; classic fixed-ten transcripts: 0/10; paired transcript cells: 0/10 | Do not extrapolate the partial own-agent results |
| 500-edge expansion cap | REJECTED | 0/20 ordinary and 0/20 oracle probes reach 500 facts | Not a bottleneck in these traces |

The ranking above orders measured retrieval losses and structural exposure. It does not invent a ranking of unmeasured correctness counterfactuals. Seed forcing alone, with unchanged fusion, improves full-item coverage by 13 questions. With ordinary seeds, full coverage is 1/20 under both the fact-score top20 and fused top20; fusion's five-question loss appears **after** oracle placement. Oracle candidates/fact-score top20 cover 19/20, an 18-question coverage upper bound over the ordinary returned 1/20 when seed placement and downstream selection losses are jointly bypassed. This is not an answer-accuracy estimate or a proposed fix.

Seed-intervention full-coverage gains: q10, q11, q18, q25, q37, q38, q42, q43, q48, q52, q53, q57, q58. Conditional fusion losses: q03, q04, q17, q24, q47. The 13 structural exposures overlap these sets and are not additive.

## E0: current-model baseline

| Configuration | Type | Judged / target | Retrieval n | Fully correct / judged | Mean correctness | Recall-any | Recall@10 |
|---|---|---|---|---|---|---|---|
| classic | multi_hop | 20/20 | 20 | 4/20 | 0.400 | 0.600 | 0.600 |
| classic | time_sensitive | 15/15 | 15 | 11/15 | 1.467 | 1.000 | 1.000 |
| graphiti | multi_hop | 20/20 | 20 | 4/20 | 0.450 | 0.833 | 0.792 |
| graphiti | time_sensitive | 15/15 | 15 | 10/15 | 1.333 | 0.900 | 0.900 |
| own | multi_hop | 20/20 | 20 | 1/20 | 0.100 | 0.308 | 0.308 |
| own | time_sensitive | 15/15 | 15 | 10/15 | 1.333 | 0.700 | 0.667 |
| own+subagents | multi_hop | 4/20 | 4 | 2/4 | 1.000 | 0.833 | 0.083 |
| own+subagents | time_sensitive | 2/15 | 2 | 2/2 | 2.000 | 0.750 | 0.500 |
| classic+subagents | multi_hop | 0/20 | 0 | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED |
| classic+subagents | time_sensitive | 0/15 | 0 | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED |

All 35 classic, Graphiti and own baseline questions are judged. Own+subagents is judged only on q03, q04, q05, q06, q10 and q11; classic+subagents has no current-model judged result. Native multi-hop own is 1/20 fully correct versus classic 4/20; Graphiti is also 4/20, with mean 0.45 versus classic 0.40. A claim about the full 20-question current-model agent comparison would be unsupported.

## E1: all three bubbles forced

| Configuration | Type | Judged / target | Retrieval n | Fully correct / judged | Mean correctness | Recall-any | Recall@10 |
|---|---|---|---|---|---|---|---|
| classic | multi_hop | 0/20 | 20 | NOT YET MEASURED | NOT YET MEASURED | 0.600 | 0.600 |
| classic | time_sensitive | 0/15 | 15 | NOT YET MEASURED | NOT YET MEASURED | 1.000 | 1.000 |
| graphiti | multi_hop | 0/20 | 20 | NOT YET MEASURED | NOT YET MEASURED | 0.758 | 0.725 |
| graphiti | time_sensitive | 0/15 | 15 | NOT YET MEASURED | NOT YET MEASURED | 0.900 | 0.900 |
| own | multi_hop | 0/20 | 20 | NOT YET MEASURED | NOT YET MEASURED | 0.292 | 0.292 |
| own | time_sensitive | 0/15 | 15 | NOT YET MEASURED | NOT YET MEASURED | 0.700 | 0.700 |
| own+subagents | multi_hop | 0/20 | 0 | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED |
| own+subagents | time_sensitive | 0/15 | 0 | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED |
| classic+subagents | multi_hop | 0/20 | 0 | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED |
| classic+subagents | time_sensitive | 0/15 | 0 | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED | NOT YET MEASURED |

The 105 native retrieval cells were completed without LLM calls. They reuse each E0 router's parsed time scope and force the union of all three bubbles. The SDK completion methods were guarded to reject any accidental model call. Answer correctness is unmeasured in all 175 E1 cells, as are agent-planned retrieval results. On resume, E1 holds E0 scope/flags fixed and changes only the bubble set; E4 reuses E1 metadata, avoiding an original-text-expansion flag confound.

| Config | Type | Paired n | E0 recall-any | E1 recall-any | Difference | Recall gains | Recall losses |
|---|---|---|---|---|---|---|---|
| classic | multi_hop | 20 | 0.600 | 0.600 | 0.000 | none | none |
| classic | time_sensitive | 15 | 1.000 | 1.000 | 0.000 | none | none |
| graphiti | multi_hop | 20 | 0.833 | 0.758 | -0.075 | none | q25, q43, q48 |
| graphiti | time_sensitive | 15 | 0.900 | 0.900 | 0.000 | q20 | q34 |
| own | multi_hop | 20 | 0.308 | 0.292 | -0.017 | none | q04 |
| own | time_sensitive | 15 | 0.700 | 0.700 | 0.000 | q19 | q05 |

For multi-hop questions, all-bubble recall-any is unchanged for classic (0.600), falls from 0.833 to 0.758 for Graphiti, and falls from 0.308 to 0.292 for own. Adding bubbles can add competing candidates; ‘all bubbles’ is the requested intervention, not an oracle minimal relevant subset. The decreases must not be reported as a positive cost of routing. An unchanged bubble set can also produce answer variation, so no missing answer deltas are inferred from recall.

### Router selection versus authored labels and actual ingestion

N=News, F=Finance, R=Research. Actual assignments come from SQLite `items.bubble_ids`. One selected copy suffices for a replicated item; requiring the union of all its assigned bubbles overstates exclusion. In own mode the selected groups constrain seeds, while expansion can cross into unselected bubbles unless explicitly excluded; a selection miss is not a hard expansion gate. ‘unmeasured’ is not an empty route.

| Question | Expected | Actual per gold item | E0 C/G/O/O+A/C+A | E2 five selections |
|---|---|---|---|---|
| v2-q01 | F | 0-funding:F+R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q03 | F+N | 0-recall:N; 0-funding:F+R | N+F+R; N+F+R; N+F+R; N+R+F; unmeasured | N+R+F; N+F+R; N+F+R; N+F+R; N+F+R |
| v2-q04 | F+N+R | 0-recall:N; 0-funding:F+R; 0-study:R | N+F+R; N+F+R; N+R; N+F+R; unmeasured | N+R; N+R; N+R; N+R; N+F+R |
| v2-q05 | N | 0-leader:N+F; 0-recall:N | N; N; N; N; unmeasured | N; N; N; N; N |
| v2-q07 | R | 0-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q02 | R | 0-study:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q06 | F | 0-deal:F; 0-cancel:F | F; F; F; F; unmeasured | F; F; F; F; F |
| v2-q08 | F | 1-funding:F | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q09 | R | 1-study:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q10 | F+N | 1-recall:N; 1-funding:F | N+F+R; N+F+R; N+F+R; N+F+R; unmeasured | N+F+R; N+R+F; N+F+R; N+F+R; N+F+R |
| v2-q11 | F+N+R | 1-recall:N; 1-funding:F; 1-study:R | N+R; N+R; N+F+R; N+R; unmeasured | N+R; N+R; N+R; N+R; N+F+R |
| v2-q12 | N | 1-leader:N+F; 1-recall:N | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q13 | F | 1-deal:F; 1-cancel:F | F; F; F; unmeasured; unmeasured | F; F; F; F; F |
| v2-q14 | R | 1-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q15 | F | 2-funding:F+R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q16 | R | 2-study:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q17 | F+N | 2-recall:N; 2-funding:F+R | N+R+F; N+F+R; N+R; unmeasured; unmeasured | N+F+R; N+F+R; N+F+R; N+F+R; N+R |
| v2-q18 | N+R | 2-leader:N+F; 2-study:R | N+R; N+R; N+R; unmeasured; unmeasured | N+R; N+R; N+R; N+R; N+R |
| v2-q19 | N | 2-leader:N+F; 2-recall:N | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q20 | F | 2-deal:F+N; 2-cancel:F | F; F; F; unmeasured; unmeasured | F; F; F; F; F |
| v2-q21 | R | 2-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q22 | F | 3-funding:R+F | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F+N; F; F; F |
| v2-q23 | R | 3-study:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q24 | F+N | 3-recall:N; 3-funding:R+F | N+F+R; N+F+R; N+F+R; unmeasured; unmeasured | N+F+R; N+F+R; N+F+R; N+F+R; N+F+R |
| v2-q25 | N+R | 3-leader:N+F; 3-study:R | N+R; N+R; N+R; unmeasured; unmeasured | N+R; N+R; N+R; N+R; N+R |
| v2-q26 | N | 3-leader:N+F; 3-recall:N | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q27 | F | 3-deal:F; 3-cancel:F | F; F; F; unmeasured; unmeasured | F; F; F; F; F |
| v2-q28 | R | 3-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q29 | F | 4-funding:F+R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q30 | R | 4-study:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q31 | F+N | 4-recall:N; 4-funding:F+R | N+F+R; N+F+R; N+F+R; unmeasured; unmeasured | N+F+R; N+R+F; N+R+F; N+F+R; N+F+R |
| v2-q32 | N+R | 4-leader:N; 4-study:R | N+R; N+R; N+R; unmeasured; unmeasured | N+R; N+R; N+R; N+R; N+R |
| v2-q33 | N | 4-leader:N; 4-recall:N | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q34 | F | 4-deal:F; 4-cancel:F | F; F; F; unmeasured; unmeasured | F; F; F; F; F |
| v2-q35 | R | 4-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q36 | F | 5-funding:F+R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q37 | F+N | 5-recall:N; 5-funding:F+R | N+R+F; N+F+R; N+F+R; unmeasured; unmeasured | N+F+R; N+R+F; N+F+R; N+F+R; N+F+R |
| v2-q38 | N+R | 5-leader:N+F; 5-study:R | N+R; N+R; N+R; unmeasured; unmeasured | N+R; N+R; N+R; N+R; N+R |
| v2-q39 | N | 5-leader:N+F; 5-appointment:N | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q40 | R | 5-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q41 | F | 6-funding:F+R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q42 | F+N | 6-recall:N; 6-funding:F+R | N+F+R; N+F+R; N+F+R; unmeasured; unmeasured | N+F+R; N+F+R; N+F+R; N+R+F; N+F+R |
| v2-q43 | N+R | 6-leader:N+F; 6-study:R | N+R; R+N; N+R; unmeasured; unmeasured | N+R; N+R; N+R; N+R; N+R |
| v2-q44 | N | 6-leader:N+F; 6-appointment:N+F | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q45 | R | 6-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q46 | F | 7-funding:F+R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q47 | F+N | 7-recall:N; 7-funding:F+R | N+R+F; N+F+R; N+F+R; unmeasured; unmeasured | N+R; N+R+F; N+F+R; N+F+R; N+F+R |
| v2-q48 | F+R | 7-deal:F+N; 7-study:R | F+R; F+R; F+R; unmeasured; unmeasured | F+R; F+N+R; F+R; F+R; F+R |
| v2-q49 | N | 7-leader:N; 7-appointment:N+F | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q50 | R | 7-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q51 | F | 8-funding:F+R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q52 | F+N | 8-recall:N; 8-funding:F+R | N+F+R; N+R+F; N+F+R; unmeasured; unmeasured | N+F+R; N+F+R; N+F+R; N+F+R; N+F+R |
| v2-q53 | F+R | 8-deal:F; 8-study:R | F+R; F+R; F+R; unmeasured; unmeasured | F+R; F+R; F+R; F+R; F+R |
| v2-q54 | N | 8-leader:N; 8-appointment:N+F | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q55 | R | 8-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |
| v2-q56 | F | 9-funding:F+R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | F; F; F; F; F |
| v2-q57 | F+N | 9-recall:N; 9-funding:F+R | N+F+R; N+F+R; N+F+R; unmeasured; unmeasured | N+F+R; N+F+R; N+F+R; N+R; N+F+R |
| v2-q58 | F+R | 9-deal:F; 9-study:R | F+R; F+R; F+R; unmeasured; unmeasured | F+R; F+R; F+R; F+R; F+R |
| v2-q59 | N | 9-leader:N+F; 9-appointment:N+F | N; N; N; unmeasured; unmeasured | N; N; N; N; N |
| v2-q60 | R | 9-fresh:R | unmeasured; unmeasured; unmeasured; unmeasured; unmeasured | R; R; R; R; R |

## E2: router stability, inputs and prompt/code

| Measure | Result |
|---|---|
| Completed routes | 300/300 |
| Questions changing selection | 7/60: q04, q11, q17, q22, q47, q48, q57 |
| Omitted authored expected bubble | 11/300 |
| Omitted every ingested copy of ≥1 gold item | 4/300, all q11 |
| Multi-hop trials with actual omission | 4/100; 6/20 multi-hop questions change selection |

| Type | Trials | Bubble | Underselected versus label | Overselected versus label |
|---|---|---|---|---|
| single | 75 | News | 0 | 1 |
| single | 75 | Finance | 0 | 0 |
| single | 75 | Research | 0 | 0 |
| multi_hop | 100 | News | 0 | 1 |
| multi_hop | 100 | Finance | 11 | 0 |
| multi_hop | 100 | Research | 0 | 50 |
| time_sensitive | 75 | News | 0 | 0 |
| time_sensitive | 75 | Finance | 0 | 0 |
| time_sensitive | 75 | Research | 0 | 0 |
| freshness | 50 | News | 0 | 0 |
| freshness | 50 | Finance | 0 | 0 |
| freshness | 50 | Research | 0 | 0 |

`QueryRouter.route` calls `LLMClient.chat_json` at its default **temperature=0.0**, without seed, top_p, max_tokens or JSON response_format. Omitted sampling settings use provider defaults. Temperature zero did not make selection deterministic. Malformed JSON can fall back to cosine top1; provider/transport errors propagate. The user payload is `{question,catalog,similarity_hints,pins,exclude}`. Catalog entries contain id/name/description/auto_summary. The system prompt makes user descriptions primary and authoritative, with summaries and cosine hints supplementary, and supplies the current UTC date and validity-date interpretation rules.

| ID | Name | Actual catalog text | Auto-summary |
|---|---|---|---|
| eval-v2-finance | Finance | Financial markets, company investments, funding agreements, acquisitions and business performance. | None |
| eval-v2-news | News | Public affairs, company announcements, leadership changes, product recalls and community events. | None |
| eval-v2-research | Research | Scientific studies, research institutions, experimental methods and results, and scholarly publications. | None |

| Example | Actual cosine hints | First selection |
|---|---|---|
| v2-q03 | eval-v2-research:0.5259; eval-v2-news:0.5215; eval-v2-finance:0.5023 | N+R+F |
| v2-q04 | eval-v2-research:0.4935; eval-v2-news:0.4772; eval-v2-finance:0.4426 | N+R |
| v2-q18 | eval-v2-research:0.4796; eval-v2-finance:0.4497; eval-v2-news:0.3772 | N+R |

The router sees topic descriptions, not episode contents, a company-to-bubble index, alias mappings or a retrieved evidence path. There is no explicit instruction to include every intermediate domain of an unnamed chain. Thus goal/topic words (‘research institution’, ‘membrane’) favour Research similarity and can make Finance seem unnecessary. Current-model rationales usually identify News plus intermediate funding/research hops, so the old log's large topic-only exclusion pattern is **not** assumed to persist. A supplementary historical-model router probe was blocked before its first response (n=0); it supports no new old-versus-new model claim. Saved rationales and all hints are in `routes.jsonl`.

## E3: own-mode seeds, expansion and ranking

All 20 multi-hop queries were traced with all three bubbles and local embeddings. The ordinary 100 raw seeds shrink to **68 after GlobalEntity deduplication** (3.4/query); the top5 vector budget is applied before that deduplication and is not refilled. **56/100 raw seeds are generic nodes**, versus 94/283 in the graph. Fifteen questions have some gold-mentioned seed, yet only two expanded graphs contain facts from every gold item. A gold-mentioned generic/isolated seed is not necessarily the useful anchor.

| Question | Seeds before dedup: name (bubble, score, source) | Any gold MENTIONS seed | Entities/facts | Gold item: expanded / fused-top20 / best rank |
|---|---|---|---|---|
| v2-q03 | research funding agreement (R, 0.569, vector); research funding agreement (F, 0.569, vector); Ivory Delta Laboratory (R, 0.539, vector); Ivory Delta Laboratory (F, 0.539, vector); Ivory Delta Laboratory (N, 0.539, vector) | False | 24/22 | 0-recall: False / False / —; 0-funding: False / False / — |
| v2-q04 | Ivory Delta Laboratory (R, 0.595, vector); Ivory Delta Laboratory (F, 0.594, vector); Ivory Delta Laboratory (N, 0.594, vector); laboratory equipment (R, 0.568, vector); experimental records (R, 0.563, vector) | False | 33/26 | 0-recall: False / False / —; 0-funding: False / False / —; 0-study: False / False / — |
| v2-q10 | defective coolant valve (N, 0.667, vector); research funding agreement (R, 0.558, vector); research funding agreement (F, 0.558, vector); manufacturing divisions (N, 0.553, vector); manufacturing divisions (F, 0.551, vector) | True | 46/46 | 1-recall: True / True / 9; 1-funding: True / False / 46 |
| v2-q11 | defective coolant valve (N, 0.669, vector); Ivory Delta Laboratory (F, 0.597, vector); Ivory Delta Laboratory (N, 0.597, vector); Ivory Delta Laboratory (R, 0.596, vector); laboratory equipment (R, 0.574, vector) | True | 39/33 | 1-recall: True / True / 11; 1-funding: False / False / —; 1-study: False / False / — |
| v2-q17 | research funding agreement (R, 0.578, vector); research funding agreement (F, 0.578, vector); Silver Marsh Laboratory (F, 0.533, vector); industry newsletter (F, 0.530, vector); Ivory Delta Laboratory (R, 0.522, vector) | False | 39/33 | 2-recall: False / False / —; 2-funding: True / True / 15 |
| v2-q18 | BDA chief (N, 1.000, both); BDA (N, 1.000, both); BDA (F, 1.000, both); BDA (R, 1.000, both); Cobalt Reach Laboratory (F, 0.558, vector) | True | 25/23 | 2-leader: True / True / 12; 2-study: False / False / — |
| v2-q24 | research funding agreement (R, 0.582, vector); research funding agreement (F, 0.582, vector); manufacturing divisions (N, 0.547, vector); manufacturing divisions (F, 0.541, vector); Cobalt Reach Laboratory (F, 0.536, vector) | False | 49/52 | 3-recall: False / False / —; 3-funding: False / False / — |
| v2-q25 | OBR (N, 1.000, both); OBR chief (N, 1.000, both); OBR (F, 1.000, both); OBR (R, 1.000, both); Opal Ridge Laboratory (F, 0.573, vector) | True | 34/26 | 3-leader: True / True / 9; 3-study: False / False / — |
| v2-q31 | defective pressure relay (N, 0.651, vector); research funding agreement (R, 0.567, vector); research funding agreement (F, 0.567, vector); manufacturing divisions (N, 0.559, vector); manufacturing divisions (F, 0.554, vector) | True | 42/39 | 4-recall: True / True / 18; 4-funding: True / True / 1 |
| v2-q32 | VGW (N, 1.000, both); VGW (R, 1.000, both); Tesselmar Construction (N, 0.526, vector); Tesselmar Construction (F, 0.522, vector); Cobalt Reach Laboratory (R, 0.522, vector) | True | 40/45 | 4-leader: False / False / —; 4-study: False / False / — |
| v2-q37 | steering pin (N, 1.000, both); research funding agreement (R, 0.570, vector); research funding agreement (F, 0.570, vector); manufacturing divisions (N, 0.536, vector); manufacturing divisions (F, 0.534, vector) | True | 38/36 | 5-recall: False / False / —; 5-funding: False / False / — |
| v2-q38 | QND chief (N, 1.000, both); QND (N, 1.000, both); QND (F, 1.000, both); QD-18 (R, 0.530, vector); Cobalt Reach Laboratory (R, 0.519, vector) | True | 21/19 | 5-leader: True / True / 8; 5-study: False / False / — |
| v2-q42 | power connector (N, 1.000, both); research funding agreement (R, 0.607, vector); research funding agreement (F, 0.607, vector); manufacturing divisions (F, 0.555, vector); manufacturing divisions (N, 0.553, vector) | True | 38/36 | 6-recall: False / False / —; 6-funding: False / False / — |
| v2-q43 | TMC (N, 1.000, both); TMC (R, 1.000, both); TMC chief (N, 1.000, both); TMC (F, 1.000, both); Cobalt Reach Laboratory (R, 0.554, vector) | True | 24/22 | 6-leader: True / True / 8; 6-study: False / False / — |
| v2-q47 | axle collar (N, 1.000, both); research funding agreement (R, 0.554, vector); research funding agreement (F, 0.554, vector); manufacturing divisions (N, 0.541, vector); manufacturing divisions (F, 0.539, vector) | True | 38/36 | 7-recall: False / False / —; 7-funding: True / True / 2 |
| v2-q48 | Aldervane Transit (N, 1.000, both); Aldervane Transit (F, 1.000, both); Aldervane Transit (R, 1.000, both); research funding agreement (R, 0.580, vector); research funding agreement (F, 0.580, vector) | True | 62/62 | 7-deal: True / False / 36; 7-study: False / False / — |
| v2-q52 | research funding agreement (R, 0.566, vector); research funding agreement (F, 0.566, vector); manufacturing divisions (N, 0.543, vector); manufacturing divisions (F, 0.540, vector); industry newsletter (F, 0.539, vector) | False | 38/36 | 8-recall: False / False / —; 8-funding: False / False / — |
| v2-q53 | Pellucid Forge (R, 1.000, both); Pellucid Forge (F, 1.000, both); Pellucid Forge (N, 1.000, both); June purchase agreement (F, 0.598, vector); research funding agreement (R, 0.595, vector) | True | 33/30 | 8-deal: True / False / 24; 8-study: False / False / — |
| v2-q57 | control fuse (N, 1.000, both); manufacturing divisions (N, 0.557, vector); research funding agreement (R, 0.556, vector); research funding agreement (F, 0.556, vector); manufacturing divisions (F, 0.555, vector) | True | 46/46 | 9-recall: True / True / 9; 9-funding: False / False / — |
| v2-q58 | Ravenspire Instruments (F, 1.000, both); Ravenspire Instruments (N, 1.000, both); Ravenspire Instruments (R, 1.000, both); June purchase agreement (F, 0.590, vector); research funding agreement (R, 0.587, vector) | True | 53/43 | 9-deal: True / True / 9; 9-study: False / False / — |

Every fact rank, signal rank, score, raw seed score/source/bubble, actual post-dedup seed ID and expanded fact/entity is retained in `stages.jsonl`; `stage_summary.json` gives every gold item's facts and all ranks. Ordinary expansion covers all gold items in 2/20; fact-score top20 and fused top20 each cover 1/20. No expansion reaches the 500-edge cap. q03 starts from generic funding agreements and the wrong Ivory Delta Laboratory. q10 reaches the right funding item but its best fact ranks 46.

## E4: oracle seeds (retrieval complete; correctness blocked)

| Configuration | Type | Judged / target | Retrieval n | Fully correct / judged | Mean correctness | Recall-any | Recall@10 |
|---|---|---|---|---|---|---|---|
| own | multi_hop | 0/20 | 20 | NOT YET MEASURED | NOT YET MEASURED | 0.858 | 0.817 |

Stage source: LLM-free oracle-seed retrieval probe. The seed wrapper forces all entities linked by MENTIONS from gold episodes; the production identity dedup, two-hop expansion, temporal filter, PageRank, fact score and fusion remain unchanged. These privileged seeds include answer-side entities and can bypass identity/path gaps: recovery identifies a placement/reachability gate, not the practical gain of changing just a question's initial name matcher. No E4 answer was generated or judged.

| Question | E1→E4 recall-any | E4 Recall@10 | All gold expanded | All gold fused top20 | Best fused ranks per gold |
|---|---|---|---|---|---|
| v2-q03 | 0.000 → 0.500 | 0.500 | True | False | 0-recall:23; 0-funding:1 |
| v2-q04 | 0.000 → 0.667 | 0.667 | True | False | 0-recall:23; 0-funding:5; 0-study:3 |
| v2-q10 | 0.500 → 1.000 | 0.500 | True | True | 1-recall:18; 1-funding:4 |
| v2-q11 | 0.333 → 1.000 | 0.667 | True | True | 1-recall:18; 1-funding:3; 1-study:1 |
| v2-q17 | 0.500 → 0.500 | 0.500 | True | False | 2-recall:24; 2-funding:1 |
| v2-q18 | 0.500 → 1.000 | 1.000 | True | True | 2-leader:6; 2-study:2 |
| v2-q24 | 0.000 → 0.500 | 0.500 | True | False | 3-recall:21; 3-funding:2 |
| v2-q25 | 0.500 → 1.000 | 1.000 | True | True | 3-leader:16; 3-study:12 |
| v2-q31 | 1.000 → 1.000 | 1.000 | True | True | 4-recall:13; 4-funding:1 |
| v2-q32 | 0.000 → 0.500 | 0.500 | False | False | 4-leader:—; 4-study:2 |
| v2-q37 | 0.000 → 1.000 | 1.000 | True | True | 5-recall:13; 5-funding:1 |
| v2-q38 | 0.500 → 1.000 | 1.000 | True | True | 5-leader:17; 5-study:4 |
| v2-q42 | 0.000 → 1.000 | 1.000 | True | True | 6-recall:7; 6-funding:2 |
| v2-q43 | 0.500 → 1.000 | 1.000 | True | True | 6-leader:19; 6-study:2 |
| v2-q47 | 0.500 → 0.500 | 0.500 | True | False | 7-recall:23; 7-funding:2 |
| v2-q48 | 0.000 → 1.000 | 1.000 | True | True | 7-deal:12; 7-study:2 |
| v2-q52 | 0.000 → 1.000 | 1.000 | True | True | 8-recall:15; 8-funding:6 |
| v2-q53 | 0.000 → 1.000 | 1.000 | True | True | 8-deal:19; 8-study:2 |
| v2-q57 | 0.500 → 1.000 | 1.000 | True | True | 9-recall:7; 9-funding:1 |
| v2-q58 | 0.500 → 1.000 | 1.000 | True | True | 9-deal:16; 9-study:12 |

Oracle seeds expand every gold item in 19/20 and retain every gold item in 14/20 fused results. The fact-score top20 alone covers all 19 available questions. Fusion drops five despite relevant fact-score ranks: q17 recall is rank 1 by fact score → fused rank 24 (recency rank 68); q24 rank 1 → 21; q47 rank 1 → 23. Confidence is 0.92 for 378/381 facts and 0.9936 for 3/381; ties correctly share ranks, so no arbitrary UUID penalty is inferred. Recency rankings compete with relevance even for historical bridge facts. No threshold or ranking fix was applied.

![Own-mode full gold-item coverage](../../data/diagnostics/eval-v2/stage-coverage.png)

### Additional temporal/atomic-bridge check (no LLM)

| Question | Required bridge | Extracted claims | Oracle current: expanded / fused ranks | Oracle history: expanded / fused ranks |
|---|---|---|---|---|
| v2-q18 | January appointment identifying the chief | 2 | {'in_expansion': True, 'fused_ranks': [6]} | {'in_expansion': True, 'fused_ranks': [6, 26]} |
| v2-q18 | visiting fellowship at laboratory | 1 | {'in_expansion': True, 'fused_ranks': [4]} | {'in_expansion': True, 'fused_ranks': [3]} |
| v2-q25 | January appointment identifying the chief | 2 | {'in_expansion': False, 'fused_ranks': []} | {'in_expansion': True, 'fused_ranks': [18, 24]} |
| v2-q25 | visiting fellowship at laboratory | 1 | {'in_expansion': True, 'fused_ranks': [12]} | {'in_expansion': True, 'fused_ranks': [11]} |
| v2-q32 | January appointment identifying the chief | 1 | {'in_expansion': False, 'fused_ranks': []} | {'in_expansion': True, 'fused_ranks': [27]} |
| v2-q32 | visiting fellowship at laboratory | 1 | {'in_expansion': True, 'fused_ranks': [4]} | {'in_expansion': True, 'fused_ranks': [4]} |
| v2-q38 | January appointment identifying the chief | 2 | {'in_expansion': True, 'fused_ranks': [17]} | {'in_expansion': True, 'fused_ranks': [20, 23]} |
| v2-q38 | visiting fellowship at laboratory | 1 | {'in_expansion': True, 'fused_ranks': [7]} | {'in_expansion': True, 'fused_ranks': [5]} |
| v2-q43 | January appointment identifying the chief | 2 | {'in_expansion': False, 'fused_ranks': []} | {'in_expansion': True, 'fused_ranks': [9, 29]} |
| v2-q43 | visiting fellowship at laboratory | 1 | {'in_expansion': True, 'fused_ranks': [4]} | {'in_expansion': True, 'fused_ranks': [4]} |

The explicit unbounded TimeScope probe allows historical nonempty intervals while preserving seed selection and hop limits. Ordinary full-item coverage stays 2/20 expanded and 1/20 fused. Oracle coverage changes 19/20→20/20 expanded but 14/20→13/20 fused. All five person-to-laboratory calibration links exist; two fact sentences omit the visiting-fellow qualifier. Named January appointment assertions are removed by default current-time filtering in q25/q32/q43. History restores all three, but q32's best appointment remains fused rank 27. In q25/q43 another fact from the leader item had survived, hiding this loss from item recall. Bubble copies have inconsistent historical validity, allowing one old appointment copy to survive for q18/q38. Answer benefits from the history probe were not measured.

## E5: graph connectivity

| Question | One root entity reaches all other gold items ≤2 logical hops | Failure class | Virtual source-asserted alias joins restore test |
|---|---|---|---|
| v2-q03 | True | — | True |
| v2-q04 | False | abbreviation/alias stored as separate unlinked entity | True |
| v2-q10 | True | — | True |
| v2-q11 | False | abbreviation/alias stored as separate unlinked entity | True |
| v2-q17 | True | — | True |
| v2-q18 | True | — | True |
| v2-q24 | True | — | True |
| v2-q25 | True | — | True |
| v2-q31 | True | — | True |
| v2-q32 | True | — | True |
| v2-q37 | True | — | True |
| v2-q38 | True | — | True |
| v2-q42 | True | — | True |
| v2-q43 | True | — | True |
| v2-q47 | True | — | True |
| v2-q48 | True | — | True |
| v2-q52 | True | — | True |
| v2-q53 | True | — | True |
| v2-q57 | True | — | True |
| v2-q58 | True | — | True |

This undirected grounded-only test ignores validity time: RELATES_TO is one hop; Entity→GlobalEntity←Entity is one hop. It requires one root entity, not different roots from the same episode. It passes 18/20; q04/q11 fail, and virtual addition of source-stated alias joins repairs both. The virtual adjacency list never changes Neo4j. Missing-entity, missing-fact and ungrounded counts are zero **for these two broad-test failures**, not for the whole graph. Passing can use incidental entities or wrong merges and does not prove a semantic answer chain.

| Recall item | Source discriminator | Graph status |
|---|---|---|
| 0-recall | brake seal | entity missing |
| 1-recall | coolant valve | connected |
| 2-recall | battery latch | entity missing |
| 3-recall | sensor housing | entity missing |
| 4-recall | pressure relay | connected |
| 5-recall | steering pin | fact missing |
| 6-recall | power connector | fact missing |
| 7-recall | axle collar | fact missing |
| 8-recall | motor bearing | entity missing |
| 9-recall | control fuse | connected |

Four of ten recall discriminators have no entity; three have an entity with no factual edge. Those seven recall-to-grant questions miss their recall gold item in ordinary all-bubble expansion. The same seven items support eight multi-hop questions, including q04. All 381 facts are marked grounded, so lexical grounding did not establish semantic correctness.

| Structural exposure | n /20 | Questions |
|---|---|---|
| missing_discriminator | 8 | q03, q04, q17, q24, q37, q42, q47, q52 |
| wrong_named_identity | 5 | q17, q18, q48, q53, q58 |
| alias_connectivity_failure | 2 | q04, q11 |
| structural_union | 13 | q03, q04, q11, q17, q18, q24, q37, q42, q47, q48, q52, q53, q58 |

The structural union is 13/20 exposed questions. Independent graph-repair correctness gain is NOT YET MEASURED; the exposure counts overlap.

## E6: whole-snapshot graph quality

| Measure | Measured result |
|---|---|
| Local entities / linked GlobalEntity IDs / facts / episode copies | 283 / 171 / 381 / 123 |
| Explicit source alias pairs / split / missing side | 20 / 20 / 0 |
| Multi-member global groups audited | 74; remaining 97 are single-member in this snapshot |
| Clearly wrong named identity groups | 2/171, involving 17/283 local nodes |
| Generic-role/document conflations | 12 groups, ontology-dependent, separated from clear named errors |
| Fact precision: fixed-seed sample | 81/100 supported; 18 wrong direction/subject; 1 unsupported |
| Manual source read by research agent | 16/20 supported; 15/20 agreement with judge |
| Generic non-name entities | 94/283 = 33.2% |

| Abbreviation | Source full name | Separate unlinked identity | Source |
|---|---|---|---|
| AVT | Aldervane Transit | True | 7-funding |
| BDA | Brindle Arc | True | 2-funding |
| CFI | Copper Fen Institute | True | 4-funding |
| CRL | Cobalt Reach Laboratory | True | 0-funding |
| HVM | Halvex Mobility | True | 0-funding |
| IDL | Ivory Delta Laboratory | True | 3-funding |
| IVC | Indigo Vale Centre | True | 5-funding |
| JBI | Juniper Basin Institute | True | 1-funding |
| NLS | Nacreline Systems | True | 1-funding |
| OBR | Oxbriar Robotics | True | 3-funding |
| OHI | Ochre Hollow Institute | True | 7-funding |
| ORL | Opal Ridge Laboratory | True | 6-funding |
| PCF | Pellucid Forge | True | 8-funding |
| QND | Quenara Devices | True | 5-funding |
| RSI | Ravenspire Instruments | True | 9-funding |
| SMC | Sable Meridian Centre | True | 2-funding |
| SML | Silver Marsh Laboratory | True | 9-funding |
| TMC | Tesselmere Controls | True | 6-funding |
| VGW | Vespergate Works | True | 4-funding |
| VSC | Violet Strand Centre | True | 8-funding |

Company aliases can have a RELATES_TO abbreviation assertion without sharing a GlobalEntity; no shared identity does not mean no path of any length. The clear wrong merges are Brindle Arc with explicitly legally distinct Brindle Arch (five local nodes), and nine differently numbered Dovetail Quay names under one identity (twelve nodes). Quay 10 has already been locally conflated with other numbered nodes. Equal proper names in different roles were not accepted as evidence of different people: the merge judge overcalled such errors, including Talia Muren as chief and visiting fellow. `merge_quality_review.json` conservatively separates two confirmed named groups, twelve ambiguous generic groups and sixty groups with no demonstrated wrong merge.

The extraction sample is uniform over 381 stored relationships, including bubble copies, sorted by UUID and sampled with seed 20261113. The judge checks both assertion text and graph subject/relation/object against source episodes. Endpoint errors can damage traversal even if the accompanying sentence is usable by the answerer. Manual reading covers the first twenty fixed sample indices: the judge missed a fabricated deposit return direction and a positive FINANCED edge for an explicit denial, and wrongly rejected some reasonable triples. Thus 81% is judge-based precision, with an 80% manual subset and 75% agreement exposed; it is not independent human calibration. The generic-name rule includes common-noun descriptions, document/event labels and acronym-qualified chief roles, but excludes specific amounts and accession identifiers. Every classified node and manual judgment is saved.

## E7: subagent behaviour and measurement gaps

Fixed ten: q03, q04, q10, q17, q24, q31, q37, q43, q48, q58. This list mixes run-11 classic-agent successes and failures (four successes among the ten; own agents had zero). Current fixed-ten own transcripts are complete for q03/q04/q10 only (3/10), plus q11 outside the fixed list. Current classic-agent transcripts are 0/10. A current paired explanation of classic-agent superiority is NOT YET MEASURED.

| Question | Own current score | Own calls | Own gold items returned | Classic current score | Classic calls | Classic gold items returned | Historical classic-agent score |
|---|---|---|---|---|---|---|---|
| v2-q03 | 2 | 18 | 2 | unmeasured | 0 | unmeasured | 0 |
| v2-q04 | 0 | 18 | 2 | unmeasured | 0 | unmeasured | 0 |
| v2-q10 | 2 | 18 | 2 | unmeasured | 0 | unmeasured | 0 |
| v2-q17 | unmeasured | 0 | unmeasured | unmeasured | 0 | unmeasured | 0 |
| v2-q24 | unmeasured | 0 | unmeasured | unmeasured | 0 | unmeasured | 0 |
| v2-q31 | unmeasured | 0 | unmeasured | unmeasured | 0 | unmeasured | 2 |
| v2-q37 | unmeasured | 0 | unmeasured | unmeasured | 0 | unmeasured | 0 |
| v2-q43 | unmeasured | 0 | unmeasured | unmeasured | 0 | unmeasured | 2 |
| v2-q48 | unmeasured | 0 | unmeasured | unmeasured | 0 | unmeasured | 2 |
| v2-q58 | unmeasured | 0 | unmeasured | unmeasured | 0 | unmeasured | 2 |

Observed q03: the initial Finance search `September brake seal recall chief resigned manufacturer grant research institution` returns 20 facts from eleven items, none gold. The initial Research search `September brake seal recall chief resigned manufacturer` returns 20 facts from nine items, none gold. News's initial event search returns the correct recall. Later explicit Halvex Mobility grant searches return the correct funding item; the merged answer is correct. Each of its three agents uses all six calls, all search, stopping at the tool limit. q04 collects recall and funding but not 0-study and answers incorrectly. The measured q03/q04/q10/q11 multi-hop agents all reach their six-call budgets; this is observed tool pressure, not proof of a current classic-agent causal advantage.

Own `search` is entity seeding plus expansion. A query naming no proper entity can return generic/wrong-name neighborhoods (as observed), or no facts if neither cosine nor fuzzy seeding succeeds; it is not guaranteed to return zero. Classic search compares the query against chunk contents and can preserve an abbreviation, negation, date and bridge in the same passage. `read_item` can expose original wording missing from graph assertions. This is a code-level comparison; no current classic-agent transcript was invented. Graphiti hybrid fact-text search bypasses the entity-name seed gate, explaining its higher native item recall (0.833 versus own 0.308); it still inherits incomplete/wrong assertions and has only a small correctness advantage over classic here.

Agents independently receive the same question; they do not exchange intermediate names during research. QA deduplicates collected facts/chunks, groups findings sharing GlobalEntity IDs, keeps joined bubbles adjacent, and appends per-bubble answers as supplementary notes. Numbered evidence, not notes, supplies citations. The full q03 per-bubble findings/joins/final answer are in `answers.jsonl`; full model/tool histories are in `agent_turns.jsonl` and `tools.jsonl`. `tool_summary.json` lists every captured query, result count, runtime/corpus item ID and gold hit. An identity-based join does not establish a valid semantic chain. Item Recall@10 can be very low even when later searches collect enough evidence for the final answer.

## E8: time-sensitive failures

Current E0 has 47/75 judged time-sensitive cells; 14 are wrong/partial. Only scored cells are classified. All 75 comparable native/agent run-11 cells exist, with 27 wrong/partial. The union has eight distinct question IDs. Provider-blocked cells are excluded from failure categories, not called retrieval failures.

| Run | Configuration | Category | n |
|---|---|---|---|
| E0 | classic | wrong/absent time scope | 4 |
| E0 | graphiti | wrong/absent time scope | 5 |
| E0 | own | wrong/absent time scope | 5 |
| run11 | classic | both old and new retrieved but answer chose wrong | 4 |
| run11 | classic+subagents | both old and new retrieved but answer chose wrong | 5 |
| run11 | graphiti | both old and new retrieved but answer chose wrong | 4 |
| run11 | graphiti | evidence not retrieved | 1 |
| run11 | own | both old and new retrieved but answer chose wrong | 2 |
| run11 | own | evidence not retrieved | 3 |
| run11 | own+subagents | both old and new retrieved but answer chose wrong | 1 |
| run11 | own+subagents | evidence not retrieved | 5 |
| run11 | own+subagents | historical fact not marked or filtered wrongly | 2 |

| Run | Configuration | Question | Category | Missing gold items | Recorded scope |
|---|---|---|---|---|---|
| run11 | classic | v2-q05 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | classic | v2-q12 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | classic | v2-q19 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | classic | v2-q33 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | graphiti | v2-q05 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | graphiti | v2-q12 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | graphiti | v2-q19 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | graphiti | v2-q26 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | graphiti | v2-q33 | evidence not retrieved | 4-leader | not recorded |
| run11 | own | v2-q05 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | own | v2-q12 | evidence not retrieved | 1-leader | not recorded |
| run11 | own | v2-q19 | evidence not retrieved | 2-leader | not recorded |
| run11 | own | v2-q26 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | own | v2-q33 | evidence not retrieved | 4-leader | not recorded |
| run11 | own+subagents | v2-q05 | evidence not retrieved | 0-recall | not recorded |
| run11 | own+subagents | v2-q06 | historical fact not marked or filtered wrongly | 0-deal | not recorded |
| run11 | own+subagents | v2-q12 | evidence not retrieved | 1-leader, 1-recall | not recorded |
| run11 | own+subagents | v2-q13 | evidence not retrieved | 1-cancel, 1-deal | not recorded |
| run11 | own+subagents | v2-q19 | evidence not retrieved | 2-recall, 2-leader | not recorded |
| run11 | own+subagents | v2-q26 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | own+subagents | v2-q27 | historical fact not marked or filtered wrongly | none | not recorded |
| run11 | own+subagents | v2-q33 | evidence not retrieved | 4-leader, 4-recall | not recorded |
| run11 | classic+subagents | v2-q05 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | classic+subagents | v2-q12 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | classic+subagents | v2-q19 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | classic+subagents | v2-q26 | both old and new retrieved but answer chose wrong | none | not recorded |
| run11 | classic+subagents | v2-q33 | both old and new retrieved but answer chose wrong | none | not recorded |
| E0 | classic | v2-q05 | wrong/absent time scope | none | None |
| E0 | classic | v2-q19 | wrong/absent time scope | none | None |
| E0 | classic | v2-q26 | wrong/absent time scope | none | None |
| E0 | classic | v2-q33 | wrong/absent time scope | none | None |
| E0 | graphiti | v2-q05 | wrong/absent time scope | none | None |
| E0 | graphiti | v2-q12 | wrong/absent time scope | none | None |
| E0 | graphiti | v2-q19 | wrong/absent time scope | none | None |
| E0 | graphiti | v2-q26 | wrong/absent time scope | none | None |
| E0 | graphiti | v2-q33 | wrong/absent time scope | 4-leader | None |
| E0 | own | v2-q05 | wrong/absent time scope | none | None |
| E0 | own | v2-q12 | wrong/absent time scope | 1-leader | None |
| E0 | own | v2-q19 | wrong/absent time scope | 2-leader | None |
| E0 | own | v2-q26 | wrong/absent time scope | none | None |
| E0 | own | v2-q33 | wrong/absent time scope | 4-leader | None |

All fourteen measured current failures are ‘immediately before the September recall’ questions with recorded null scopes. `_parse_scope` cannot resolve an event-relative day and returns None; graph retrieval defaults to now and `generate_answer` adds **‘Answer for now: prefer the most recent statement valid now.’** The scope/prompt mismatch is confirmed; its independent answer-level remedy has not been tested. Two current own-agent time cases are correct, so this mechanism does not force failure in every configuration.

Run 11 did not save router scopes, so they remain unmeasured rather than reconstructed as observations. Its ‘both old and new’ category is an item-level evidence classification with atomic-fact completeness explicitly uncertain. Two old own-agent answers (q06/q27) report cancellation on October 7 instead of the source's October 6. Their graph termination validity uses publication time; across the snapshot, 13/17 termination assertions use October 7 and four use October 6. This is a temporal metadata error, distinguished from the q13 old own-agent case with absent evidence. Source/answer text and all relevant validity metadata are in `time_failures.json` and `termination_dates.json`.

## Exact coverage, checkpoint and resume

The authoritative per-cell journal is `data/diagnostics/eval-v2/answers.jsonl`; `cell_checkpoint.jsonl` gives one status record for every one of the 370 planned cells, with model-result and retrieval-result status separately. `coverage.json` lists all 259 unmeasured answer cells. A score of zero is retained as a finished measurement; 403 failures are unfinished. `offline_retrieval.jsonl` contains the 105 native E1 and 20 E4 local retrieval cells and is never mistaken for a judged answer.

Once the owner restores provider capacity, run exactly from the repository root:

```powershell
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.resume
```

It skips every already scored cell, retries failed/unscored cells, reuses a cached answer if only its judge failed, and fsyncs cell records. The two in-flight cells settle before a capacity error aborts further calls; it will not spray 403s across the remaining grid. Oracle routing reuses baseline scope/flags and oracle seeds are still supplied only by diagnostics. Three offline billing-safety tests verify finished-cell skipping, failure resumability/fail-fast behaviour, and judge-only retries without answer regeneration. No model-based resume was run after the instruction to finish offline.

## Cost, integrity, validation and limits

Provider-reported total: **3,076,663 tokens, USD 0.735018308**. Usage totals include the completed baseline calls, all router repetitions, 100 fact judges and 74 merge judges, plus all other returned completions. `usage_final.jsonl` holds final per-process/stage totals; do not sum cumulative `usage.jsonl` checkpoints. Missing provider cost is not estimated from prices. The failed historical-router supplement has zero returned measurements and zero reported usage; the shared account-key $5.008 total includes work outside this diagnostic.

Integrity: {'action': 'final_verification', 'unchanged': True, 'changed': [], 'graph_unchanged': True, 'graph_before_sha256': '63acb3cc5c3bbb5e76fb0ebc3c6db72c9b05f14292bd24a1b8022ac4ebfe9f85', 'graph_after_sha256': '63acb3cc5c3bbb5e76fb0ebc3c6db72c9b05f14292bd24a1b8022ac4ebfe9f85'}. Frozen file bytes and the normalized graph export match initial hashes. SQLite uses read-only URI mode without Repository schema migration; Chroma reads a diagnostic copy; Graphiti is built read-only. No source data, Neo4j facts, corpus, CLI, pyproject, `.env` or production retrieval file was edited by this work; no commit was made. No optional production trace hook was added. Other work in the shared checkout is outside this diagnostic's changes.

Live-clock sensitivity: 222 saved fusion rankings checked, 0 changed; 0 fact-validity changes across the measurement interval. The run crossed a UTC day but no question's yearless date crossed an occurrence boundary.

Validation: `ruff check src/omnistream/eval/diagnostics` passed; diagnostic checkpoint tests **3 passed**. Original offline suite **985 passed, 1 skipped, 21 deselected**; the final validation log records any additional tests from concurrent checkout work.

Limits: 35 end-to-end questions (20 multi-hop, 15 time-sensitive); three repeated synthetic question families with two three-record variants; no held-out real-data generalisation. The graph-builder model is older than the answer/router model. The fact sample includes bubble copies; manual review is by the research agent, not independent human calibration. Item recall is coarser than needed-assertion recall. Partial agent results are not extrapolated to twenty questions. E1/E4 correctness and the requested current paired classic-agent tool comparison remain NOT YET MEASURED. No thresholds, graph repairs or ranking fixes were proposed or tested.

## Offline reproduction

These commands read saved results and/or local embeddings; they do not require model capacity:

```powershell
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.offline
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.trace
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.trace --oracle
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.trace --history
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.trace --oracle --history
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.manual
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.bridges
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.summarize
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.critical
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.clock_check
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.verify
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.plot
.venv\Scripts\python.exe -m omnistream.eval.diagnostics.report
.venv\Scripts\ruff.exe check src/omnistream/eval/diagnostics
.venv\Scripts\python.exe -m pytest -q src/omnistream/eval/diagnostics/test_checkpoint.py
.venv\Scripts\python.exe -m pytest -q
```

Plotting uses isolated dependencies under `data/diagnostics/eval-v2/plot-deps`, leaving the project's environment and dependency files unchanged. If that helper directory is absent: `.venv\Scripts\python.exe -m pip install --target data/diagnostics/eval-v2/plot-deps matplotlib==3.11.2`. `manual_reviews.json` preserves source-read labels; `manual.py` validates fixed sample IDs before exporting them. The completed E2 and E6 model artifacts can be inspected without rerunning their model calls. All trace/model journals are under `data/diagnostics/eval-v2/`.
