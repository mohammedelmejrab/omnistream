# Own retrieval fixes: eval-v2 progress report

Measured 2026-11-13 on `feat/c5-integration`. **Implementation and offline measurement complete; answer-level measurement blocked by missing credentials.** No answer correctness gain is claimed.

## Changes and rationale

- **F1 / P1:** add question-to-fact-text vector search (ten facts), seed both eligible endpoint entities using each fact cosine, then deduplicate GlobalEntity identities. Name-vector candidates are filtered by the simple proper-name guard and deduplicated **before** taking five distinct identities; fuzzy matches remain available outside that budget. Generic names can still be fact seeds or expansion nodes.
- Guard: names must contain at least one token starting with an uppercase Unicode letter; explicit `Generic`, `GenericEntity`, `generic_type` types are excluded. `Concept` is not automatically generic. This casing heuristic misses lowercase proper names and admits title-cased common phrases; it is intentionally simple and is not a named-entity model. It removes 124/300 original name top-five slots under current routes, and 52/100 on multi-hop (106/300, 52/100 with all bubbles). Diagnosis used a broader manual generic classification (56/100); these counts are not interchangeable.
- Ten fact matches is twice the five-name budget, allowing event descriptions to supply both endpoints. No gold labels or question-specific names enter the implementation. Five and fifteen are reported as sensitivity, without changing the ten-fact default.
- **F2 / P2:** weighted RRF, relevance:recency:confidence **2:1:1**. Relevance receives twice each auxiliary signal's vote. Drop auxiliary rankings with fewer than two distinct values or coefficient of variation below **0.01** (population SD / absolute mean). One percent means negligible relative dispersion; 0.005 and 0.02 are sensitivity checks. Relevance remains as a deterministic fallback even when constant.
- **Spec deviation:** C5 step 1 now includes fact-text seeding and a generic-name guard. Step 5 changes equal RRF to weighted RRF and removes uninformative auxiliary signals; it remains RRF of fact relevance, recency and corroboration. The existing RRF implementation already assigns equal ranks to exact ties. Thus exactly constant confidence did not invent arbitrary tie order; near-constant auxiliary values and recency competing with relevance are the actionable mechanisms.
- Expansion remains two hops / 500 facts; PPR damping 0.85, fusion k=60, returned facts 20, validity filtering and answer/judge definitions are unchanged. **BM25 not implemented** to keep the two-fix scope tight; no marginal lexical effect is claimed.

See [diagnosis P1/P2 and E3/E4](eval-v2-diagnosis.md) and [Finding 4 and fix plan](../IMPROVEMENT_LOG.md).

## Index and measurement controls

Read-only `SHOW INDEXES` found an existing ONLINE `fact_embedding` VECTOR RELATIONSHIP index on `RELATES_TO.fact_embedding`; production uses `db.index.vector.queryRelationships` and converts Neo4j's normalized score to cosine. If absent, it computes exact Python cosine over eligible group fact embeddings. Graphiti 0.31.2's `graph_queries.py` creates `edge_name_and_fact` fulltext and relationship range indexes; its standard index helpers do not provision a fact vector index. No index creation was needed or performed. Both branches have unit coverage.

To prevent other bubbles or invalid facts consuming a seed budget, the index query requests all indexed relationship candidates before filtering groups/time/grounding and taking ten. This and the exact fallback are linear; **this is not a scalable filtered-ANN implementation**. Endpoint lookup also scans selected-group entities. Future scale work needs filtered ANN/oversampling with explicit recall guarantees; this report makes no latency improvement claim.

All 60 authored eval-v2 questions were evaluated under current recorded routes and all three bubbles, ten predeclared configurations each: **1,200 cells**, no LLM calls. All-bubble routing is an intervention, not a minimal relevant subset. Query scope and exclusions are reused; clock frozen to E0 metadata `2026-11-12T23:49:17.370617+00:00`. Runtime item IDs include corroborating provenance, deduplicated in retrieval order; Recall@10, MRR and Hits@1 use the harness functions. Recall-any is per-question gold-item coverage at any returned rank; full coverage counts questions retrieving every gold item. Means are macro averages.

**Routing qualification:** E0 own answer/routes exist for the 20 multi-hop + 15 time-sensitive questions only. These 35 reuse exactly E0 own decisions and scopes. The other 25 reuse recorded E2 repeat-0 current-model decisions from `routes.jsonl`, explicitly tagged per cell. They cannot honestly be labelled E0 own decisions. The reproduced baseline matches all four E0 retrieval metrics on **35/35** comparable questions. No live rerouting was done.

The first exact-fallback pilot was stopped after discovery of the available index and is kept separately as `exact-fallback-pilot.jsonl`; the final table uses only the completed indexed run. Original implementation sources are frozen in `src/omnistream/eval/diagnostics/own_fixes_baseline.json`. The baseline differs only in seeding/fusion; the original pipeline's identity dedup behavior is preserved.

## Offline ablations

Current routes carry the E0/E2 qualification above. All values below are measured; full is count/n.

### Recorded current routing

| Variant | Type | n | Recall-any | Recall@10 | Full | MRR | Hits@1 |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | all | 60 | 0.644 | 0.636 | 29/60 | 0.435 | 0.267 |
| baseline | single | 15 | 0.800 | 0.800 | 12/15 | 0.327 | 0.067 |
| baseline | multi_hop | 20 | 0.308 | 0.308 | 1/20 | 0.233 | 0.100 |
| baseline | time_sensitive | 15 | 0.700 | 0.667 | 6/15 | 0.529 | 0.333 |
| baseline | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.858 | 0.800 |
| F1 | all | 60 | 0.653 | 0.622 | 29/60 | 0.399 | 0.233 |
| F1 | single | 15 | 0.867 | 0.800 | 13/15 | 0.453 | 0.333 |
| F1 | multi_hop | 20 | 0.358 | 0.317 | 3/20 | 0.255 | 0.150 |
| F1 | time_sensitive | 15 | 0.600 | 0.600 | 3/15 | 0.488 | 0.200 |
| F1 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| F2 | all | 60 | 0.744 | 0.744 | 38/60 | 0.503 | 0.317 |
| F2 | single | 15 | 1.000 | 1.000 | 15/15 | 0.388 | 0.133 |
| F2 | multi_hop | 20 | 0.308 | 0.308 | 1/20 | 0.318 | 0.150 |
| F2 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.628 | 0.400 |
| F2 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.858 | 0.800 |
| F1+F2 | all | 60 | 0.803 | 0.778 | 42/60 | 0.435 | 0.200 |
| F1+F2 | single | 15 | 0.933 | 0.933 | 14/15 | 0.387 | 0.067 |
| F1+F2 | multi_hop | 20 | 0.533 | 0.458 | 6/20 | 0.322 | 0.150 |
| F1+F2 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.606 | 0.333 |
| F1+F2 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |

### All-bubble routing

| Variant | Type | n | Recall-any | Recall@10 | Full | MRR | Hits@1 |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | all | 60 | 0.689 | 0.689 | 32/60 | 0.483 | 0.333 |
| baseline | single | 15 | 1.000 | 1.000 | 15/15 | 0.654 | 0.467 |
| baseline | multi_hop | 20 | 0.292 | 0.292 | 1/20 | 0.178 | 0.050 |
| baseline | time_sensitive | 15 | 0.700 | 0.700 | 6/15 | 0.470 | 0.267 |
| baseline | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.858 | 0.800 |
| F1 | all | 60 | 0.669 | 0.614 | 32/60 | 0.320 | 0.167 |
| F1 | single | 15 | 0.933 | 0.800 | 14/15 | 0.337 | 0.200 |
| F1 | multi_hop | 20 | 0.358 | 0.292 | 3/20 | 0.200 | 0.100 |
| F1 | time_sensitive | 15 | 0.600 | 0.600 | 5/15 | 0.362 | 0.133 |
| F1 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| F2 | all | 60 | 0.731 | 0.722 | 37/60 | 0.542 | 0.383 |
| F2 | single | 15 | 1.000 | 1.000 | 15/15 | 0.669 | 0.467 |
| F2 | multi_hop | 20 | 0.292 | 0.292 | 1/20 | 0.300 | 0.150 |
| F2 | time_sensitive | 15 | 0.867 | 0.833 | 11/15 | 0.526 | 0.333 |
| F2 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.858 | 0.800 |
| F1+F2 | all | 60 | 0.786 | 0.769 | 39/60 | 0.423 | 0.250 |
| F1+F2 | single | 15 | 0.933 | 0.933 | 14/15 | 0.374 | 0.200 |
| F1+F2 | multi_hop | 20 | 0.533 | 0.483 | 5/20 | 0.308 | 0.150 |
| F1+F2 | time_sensitive | 15 | 0.833 | 0.833 | 10/15 | 0.592 | 0.400 |
| F1+F2 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |

F1 alone helps multi-hop coverage but reduces time-sensitive coverage. F2 alone improves time-sensitive retrieval substantially and does not improve multi-hop full coverage. Their combination improves current multi-hop full coverage from 1 to 6 and time-sensitive from 6 to 12. Across all 60 current-route questions, Recall-any is 0.644 -> 0.803 and full coverage 29 -> 42; Hits@1 falls 0.267 -> 0.200. Recall gains do not imply answer gains.

## Sensitivity (declared defaults retained)

Each sensitivity changes one parameter of F1+F2. The table shows all questions and multi-hop; the linked summary JSON contains every question type and all metrics for every setting. No search or threshold selection followed these results.

| Routing | Setting | Type | Recall-any | Recall@10 | Full | MRR | Hits@1 |
|---|---|---|---:|---:|---:|---:|---:|
| current | F1+F2 | all | 0.803 | 0.778 | 42/60 | 0.435 | 0.200 |
| current | F1+F2 | multi_hop | 0.533 | 0.458 | 6/20 | 0.322 | 0.150 |
| current | fact-k5 | all | 0.800 | 0.783 | 38/60 | 0.481 | 0.267 |
| current | fact-k5 | multi_hop | 0.475 | 0.475 | 1/20 | 0.292 | 0.100 |
| current | fact-k15 | all | 0.794 | 0.786 | 40/60 | 0.446 | 0.250 |
| current | fact-k15 | multi_hop | 0.508 | 0.483 | 4/20 | 0.210 | 0.050 |
| current | weight1 | all | 0.653 | 0.622 | 29/60 | 0.399 | 0.233 |
| current | weight1 | multi_hop | 0.358 | 0.317 | 3/20 | 0.255 | 0.150 |
| current | weight3 | all | 0.803 | 0.794 | 42/60 | 0.509 | 0.283 |
| current | weight3 | multi_hop | 0.533 | 0.508 | 6/20 | 0.394 | 0.200 |
| current | cv005 | all | 0.803 | 0.778 | 42/60 | 0.435 | 0.200 |
| current | cv005 | multi_hop | 0.533 | 0.458 | 6/20 | 0.322 | 0.150 |
| current | cv02 | all | 0.803 | 0.778 | 42/60 | 0.435 | 0.200 |
| current | cv02 | multi_hop | 0.533 | 0.458 | 6/20 | 0.322 | 0.150 |
| oracle | F1+F2 | all | 0.786 | 0.769 | 39/60 | 0.423 | 0.250 |
| oracle | F1+F2 | multi_hop | 0.533 | 0.483 | 5/20 | 0.308 | 0.150 |
| oracle | fact-k5 | all | 0.792 | 0.792 | 38/60 | 0.489 | 0.300 |
| oracle | fact-k5 | multi_hop | 0.475 | 0.475 | 1/20 | 0.297 | 0.100 |
| oracle | fact-k15 | all | 0.778 | 0.761 | 38/60 | 0.343 | 0.150 |
| oracle | fact-k15 | multi_hop | 0.508 | 0.458 | 4/20 | 0.200 | 0.050 |
| oracle | weight1 | all | 0.669 | 0.614 | 32/60 | 0.320 | 0.167 |
| oracle | weight1 | multi_hop | 0.358 | 0.292 | 3/20 | 0.200 | 0.100 |
| oracle | weight3 | all | 0.803 | 0.794 | 41/60 | 0.474 | 0.267 |
| oracle | weight3 | multi_hop | 0.533 | 0.508 | 5/20 | 0.392 | 0.200 |
| oracle | cv005 | all | 0.786 | 0.769 | 39/60 | 0.423 | 0.250 |
| oracle | cv005 | multi_hop | 0.533 | 0.483 | 5/20 | 0.308 | 0.150 |
| oracle | cv02 | all | 0.786 | 0.769 | 39/60 | 0.423 | 0.250 |
| oracle | cv02 | multi_hop | 0.533 | 0.483 | 5/20 | 0.308 | 0.150 |

`weight1` = 1:1:1, `weight3` = 3:1:1; confidence/recency dropping stays enabled. Default fact-k10 has 6/20 current multi-hop full coverage versus 1/20 at k5 and 4/20 at k15: sensitivity to candidate distribution remains substantial. This is a limitation, not evidence of a generally optimal k10. CV sensitivity leaves the headline multi-hop metrics unchanged.

## Regressions and paired evidence

Reproducibility caveat: a fresh follow-up replay of the 44 regression cells changed seed sets/ranked items in 6 cells (q14 current/all-bubble, q17 all-bubble, q29 all-bubble, q47 current/all-bubble). Root cause has not been isolated; approximate-index results and numerical sensitivity are possible contributors, not established causes. The main table remains the original single paired pass, without cherry-picking a replay. `fresh_replay_audit.json` preserves these checks. To explain that pass accurately, the downstream audit reuses its recorded seed IDs and asserts exact reproduction of ranked item IDs. This isolates ranking/expansion; it does not establish deterministic end-to-end seeding.

Every per-question metric delta against baseline is retained in `data/diagnostics/own-fixes/paired_deltas.json` (1,080 paired rows); all ranked item IDs and seed IDs are in `offline.jsonl`. The following lists **every** F1+F2 question worsening on at least one requested metric. delta R and delta R10 are recall changes; the first-gold rank uses item rank, not fact rank. Losing one gold item while gaining another can leave delta R=0.

| Routing | Question | delta R | delta R10 | First gold rank before -> after | Explanation |
|---|---|---:|---:|---|---|
| current | v2-q04 | +0.000 | +0.000 | 1 -> 6 | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| current | v2-q07 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q07 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q02 | +0.000 | +0.000 | 2 -> 3 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q06 | +0.000 | +0.000 | 1 -> 2 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q09 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q09 | +0.000 | +0.000 | 1 -> 5 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q14 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q14 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q16 | +0.000 | +0.000 | 2 -> 7 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q16 | +0.000 | +0.000 | 2 -> 8 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q17 | -0.500 | -0.500 | 4 -> None | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| oracle | v2-q17 | +0.000 | +0.000 | 4 -> 8 | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| current | v2-q18 | +0.000 | -0.500 | 3 -> 11 | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| oracle | v2-q18 | +0.000 | -0.500 | 6 -> 11 | 1 previously returned gold item(s) remain in expansion but miss fused top20; 1 remain in relevance top20. |
| oracle | v2-q23 | -1.000 | -1.000 | 1 -> None | 1 previously returned gold item(s) remain in expansion but miss fused top20; 1 remain in relevance top20. |
| current | v2-q25 | -0.500 | -0.500 | 4 -> None | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| oracle | v2-q25 | -0.500 | -0.500 | 5 -> None | 1 previously returned gold item(s) remain in expansion but miss fused top20; 1 remain in relevance top20. |
| current | v2-q26 | +0.000 | +0.000 | 3 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q26 | +0.000 | +0.000 | 3 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q29 | +0.000 | +0.000 | 1 -> 6 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q30 | +0.000 | +0.000 | 2 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q30 | +0.000 | +0.000 | 2 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q34 | +0.000 | +0.000 | 1 -> 2 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q34 | -0.500 | -0.500 | 1 -> 2 | 1 previously returned gold item(s) remain in expansion but miss fused top20; 1 remain in relevance top20. |
| current | v2-q35 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q35 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q38 | -0.500 | -0.500 | 6 -> None | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| oracle | v2-q38 | -0.500 | -0.500 | 4 -> None | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| current | v2-q43 | -0.500 | -0.500 | 5 -> None | 1 previously returned gold item(s) remain in expansion but miss fused top20; 1 remain in relevance top20. |
| oracle | v2-q43 | -0.500 | -0.500 | 4 -> None | 1 previously returned gold item(s) remain in expansion but miss fused top20; 1 remain in relevance top20. |
| current | v2-q45 | +0.000 | +0.000 | 3 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q45 | +0.000 | +0.000 | 3 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q46 | +0.000 | +0.000 | 2 -> 3 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q47 | +0.000 | +0.000 | 2 -> 3 | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| oracle | v2-q47 | +0.000 | +0.000 | 2 -> 3 | 1 previously returned gold item(s) remain in expansion but miss fused top20; 0 remain in relevance top20. |
| current | v2-q50 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q50 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q51 | +0.000 | +0.000 | 1 -> 5 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q55 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q55 | +0.000 | +0.000 | 1 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| current | v2-q57 | +0.000 | +0.000 | 4 -> 6 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q57 | +0.000 | +0.000 | 4 -> 6 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |
| oracle | v2-q59 | +0.500 | +0.500 | 3 -> 4 | First relevant item moved lower after added fact seeds changed PPR/candidate competition. |

All lost gold items in the regression audit are still in the expanded candidates. Ranking/PPR dilution and residual fusion competition remain material limitations. Freshness still covers 10/10 questions, but MRR falls 0.858 -> 0.475 and Hits@1 0.8 -> 0.3. Current multi-hop recall losses are q17, q25, q38, q43; q18 loses Recall@10. All-bubble q23 and q34 additionally lose full coverage. No gold-specific repair or reranking override was added.

Other ablation variants with any recall or ranking regression against baseline:

| Routing | Variant | Questions worse on any metric |
|---|---|---|
| current | F1 | v2-q02, v2-q04, v2-q05, v2-q06, v2-q07, v2-q09, v2-q10, v2-q11, v2-q13, v2-q14, v2-q16, v2-q17, v2-q18, v2-q25, v2-q26, v2-q27, v2-q29, v2-q30, v2-q31, v2-q34, v2-q35, v2-q38, v2-q43, v2-q45, v2-q47, v2-q49, v2-q50, v2-q55, v2-q57 |
| current | F2 | v2-q15, v2-q22, v2-q29, v2-q46 |
| oracle | F1 | v2-q02, v2-q07, v2-q09, v2-q10, v2-q11, v2-q14, v2-q16, v2-q17, v2-q18, v2-q19, v2-q23, v2-q25, v2-q26, v2-q27, v2-q29, v2-q30, v2-q31, v2-q33, v2-q34, v2-q35, v2-q38, v2-q43, v2-q44, v2-q45, v2-q46, v2-q47, v2-q49, v2-q50, v2-q51, v2-q54, v2-q55, v2-q57, v2-q59 |
| oracle | F2 | v2-q15, v2-q17, v2-q41 |

## Answer-level correctness and spend

**NOT MEASURED: 0/35 answers or judges, USD 0.00, zero tokens.** `LLM_API_KEY` is absent from this process environment. A private `request_secret` (`delivery=file`, 60-second timeout) timed out without delivery; `.env` was never opened. No provider failure is scored as an incorrect answer. The USD 0.60 budget was not approached; no request was sent. Own+subagents was intentionally not evaluated offline.

| Configuration | Model | Multi-hop fully correct / n | Mean (0-2) | Time-sensitive fully correct / n | Mean (0-2) | Cost in this task |
|---|---|---|---:|---|---:|---:|
| E0 own | deepseek/deepseek-v4.1-flash-1017 | 1/20 | 0.100 | 10/15 | 1.333 | historical baseline |
| E0 classic | same | 4/20 | 0.400 | 11/15 | 1.467 | historical baseline |
| F1+F2 own | requested same model | UNMEASURED (n=0/20) | unmeasured | UNMEASURED (n=0/15) | unmeasured | $0.00 |

The parallel reasoning-control change is present in the working tree (`Settings.llm_reasoning` default `off`, judge default `off`). **There were no calls, so reasoning was neither observed on nor observed off.** A resumed run must explicitly record its actual settings, provider prompt/completion/reasoning tokens, cumulative provider cost, and stop before $0.60. It must use the harness's existing answer and correctness judge paths (`deepseek/deepseek-chat`) without metric changes; it must not substitute the E0 answers or infer correctness from recall.

## Validation, artifacts and limitations

- `.venv\Scripts\python.exe -m pytest -q`: **1080 passed, 1 skipped, 21 deselected in 99.04s**. The shared checkout includes parallel changes, so the count exceeds the supplied 1021 baseline. New tests cover fact-vector seeds, temporal/grounding/group restrictions, generic guard, post-dedup refill, near-constant dropping, weighted fusion, and index/fallback read-only queries. Existing fusion/protocol/pipeline tests were updated for the explicit new contracts.
- Ruff checks passed for all changed implementation, tests and measurement modules. Initial expected-contract failures were fixed and the complete suite rerun; a new temporal test fixture was corrected to set a valid-at boundary rather than assuming publication implied validity.
- Snapshot integrity: **107/107 recorded E0 snapshot file hashes unchanged** (`integrity.json`). Neo4j use was read-only; no DDL or graph mutation. No commits, no modifications to the protected parallel implementation files, and no `.env` access.
- Reproduce offline: `.venv\Scripts\python.exe -m omnistream.eval.diagnostics.own_fixes`; the cell log is resumable, with saved original baseline sources. For regression detail run `-m omnistream.eval.diagnostics.own_fixes_audit`; render this report with `-m omnistream.eval.diagnostics.own_fixes_report`. Set `HF_HUB_OFFLINE=1` to require cached local model weights.
- Artifacts: `data/diagnostics/own-fixes/{offline.jsonl,summary.json,paired_deltas.json,regression_audit.json,indices.json,integrity.json,answer_status.json}`. Primary metrics are direct JSON calculations, not copied estimates.
- **Synthetic eval-v2 only; graph built by the old deepseek-chat model. Not measured on real data.** The current task explicitly requested these mechanisms and eval-v2 measurements; defaults were declared from the diagnosis, not selected using real-test or eval-v2 score search. The real-data dev validation required by the improvement plan remains outstanding. No real-data test split was used. The planned 35 answer-level questions remain unmeasured and would still be a limited sample once completed.
- Seeding expands candidate reach but uniform-seed PPR can dilute previously useful anchors; score-based restart weighting and historical/event-relative scope changes were outside scope. Casing, alias linkage, graph extraction defects, validity filtering and residual relevance/recency competition remain limitations. This is a measured improvement with regressions, not a claim that P1/P2 or multi-hop answering are solved.
