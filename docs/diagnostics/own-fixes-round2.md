# Own retrieval fixes, round 2

Measured 2026-11-13 on `feat/c5-integration`, with round-1 sources frozen from `f9caa47`. No commits, paid calls, answer generation, web search, snapshot writes, or mutations of the application Neo4j graph. Schema writes in tests target a separate testcontainers database only.

## Result and measurement controls

All 60 questions, recorded and all-bubble routes, nine configurations: **1,080 paired exact-path cells**. Recorded routes retain the first-round qualification: 35 E0 own decisions, 25 E2 repeat-0 decisions; all-bubble routing retains each recorded time scope/exclusion. The clock is frozen to E0 metadata. Gold evidence and metric functions are unchanged. Recall-any is mean gold-item coverage at any returned rank, not a binary hit. Full coverage is count/n. Runtime item IDs include existing corroborating provenance; collapsed old version provenance is retained in `VersionGroup.versions`, not falsely credited as retrieved current evidence.

Both baseline and round-1 are remeasured with exact server cosine and stable rounded candidate ordering, so changes between their old ANN tables and this table are **not implementation gains**. Sources for pre-fix seeding/fusion are `own_fixes_baseline.json`; round-1 seeding/PPR/fusion are `own_fixes_round1.json`. Baseline and round-1 use their original restart/fusion behavior. Exact search changes the numerical/vector candidate path, so the historical table is retained separately below. The common pipeline uses round-1 identity deduplication, explicitly restored for old seeds.

| Exact replay, recorded routes | Recall-any | Recall@10 | Full | MRR | Hits@1 | Freshness MRR |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 0.678 | 0.661 | 31/60 | 0.444 | 0.267 | 0.858 |
| round1 | 0.794 | 0.786 | 41/60 | 0.424 | 0.183 | 0.475 |
| round2 | 0.800 | 0.772 | 39/60 | 0.553 | 0.350 | 1.000 |

Round two improves first-gold rank and freshness, but does not remove retrieval regressions: recorded-route full coverage falls 41 to 39 versus the remeasured round one; Recall@10 falls .786 to .772. Version grouping alone does **not** recover freshness MRR (.475 remains .475); the combined improvement must not be attributed to grouping alone. No constants were changed after measurement.

Historical published ANN results (not rerun or overwritten): baseline recorded Recall-any .644, Recall@10 .636, full 29/60, MRR .435, Hits@1 .267; round one .803, .778, 42/60, .435, .200. Freshness .858 -> .475. Round-two comparisons against every historical cell are in `historical_deltas.json`; paired exact comparisons are in `paired_deltas.json`.

## Mechanisms and limits

1. **Seedability:** the seven named shared ontology types (Person, Organization, Location, Product, Event, FinancialInstrument, Publication) are eligible in name, fuzzy, and fact-endpoint paths. Concept, untyped Entity, and unknown types are ineligible. No orthographic fallback is needed when ingestion supplies the shared types. Case/script tests include eBay, iPhone, arXiv, x86, adidas, bitcoin, mRNA, pH, ffmpeg, Chinese and Arabic. Capitalized generic phrases typed Concept are excluded. A generic phrase wrongly typed Product still passes; the rule is not a named-entity classifier and does not repair extraction.

2. **Budget/restart:** ten total distinct GlobalEntity identities after combining names, fuzzy matches and eligible fact endpoints; five and fifteen are predeclared sensitivity values. Name candidates are bounded at 50 (or 10 times a custom name budget), fuzzy candidates at 100. Names still contribute at most five identities. Nonpositive fact similarities do not seed. PPR restart mass is normalized nonnegative seed score, with uniform fallback if all scores are zero. This extends the spec: restart remains at the seeds, now weighted by evidence. Fuzzy scores retain their prior [0,1] scale; no calibration claim across semantic and lexical similarity is made.

3. **Scale/schema:** C4 `ensure_schema` adds an idempotent relationship vector index on `RELATES_TO.fact_embedding`, using the configured `fact_index_name`, configured embedding dimension (384 by default) and cosine. Settings and writer plumbing plus the GraphStore bounded-name contract are the minimal changes outside the listed implementation files. Reader checks the configured index name, relationship/node schema and cosine function before applying `2*score-1`. Default fact ANN fetches 5k, then 15k and 25k if filtering leaves too few; selected groups, grounding and validity are filtered in Cypher. This finite refill can underfill in a heavily skewed database; no exact-ANN recall guarantee is claimed. No population counts or full embedding payloads are fetched. Endpoint hydration uses only the top fact IDs/endpoints. Bounded lexical prefiltering and vector candidates replace repeated `entities_in` scans in production seeding.

4. **Exact/replay/fallback:** `Neo4jGraphStore(..., exact_search=True)` scores cosine server-side and returns only top-k records. It is explicitly linear compute for evaluation/replay. If a configured index is absent/offline, the same server-side exact fallback is used (an improvement over transferring all vectors for Python scoring). A wrong existing schema/metric raises an error. Paths and elapsed times are logged and available in `search_paths`. Exact queries round scores to six decimals and break ties by UUID. Graph construction sorts edges, paths are deterministic, and fusion rounds each signal to six decimals before competition ranking. `min_cv` remains accepted for old diagnostic callers, but no longer drops low-variance material signals. A 99-at-.92/one-at-.99 confidence test retains corroboration.

5. **Versions before fusion:** same directed subject/object GlobalEntity identities and normalized relation define a version family; within an endpoint pair, fact-text cosine >= .95 also recognizes near-identical relation paraphrases. This threshold was stated before measurement and was not tuned. Choose the newest valid assertion by valid_at (publication fallback), then publication and UUID. Keep the complete family, original text and provenance in `OwnRetriever.last_version_groups` / `VersionGroup.versions`; only representatives enter global fusion. Point-in-time queries select the latest valid assertion at that point. A routed time interval retains every overlapping version, because an interval may ask about changes. No attempt is made to infer event-relative scopes the router omitted, merge unrelated endpoints, or repair wrong GlobalEntity identities. Such defects limit this mechanism.

The redundant pipeline seed deduplication is removed; the docstring now describes the implemented mechanism. The neutral regression-test vocabulary replaces the old diagnostic-flavoured examples. BM25 was considered but not added to the already changed seed mechanism: installed Graphiti 0.31.2 `graph_queries.py` provisions relationship fulltext `edge_name_and_fact` over name/fact/group_id, and that index exists in this graph. It does not provision the relationship vector index. A lexical hybrid would require a separate score/candidate ablation; none is claimed.

## Ingestion-signal audit (283 entities)

Manual generic list is used only to describe signal limitations, never to select a threshold. Predicted positive below means seedable. All 283 entities have SAME_AS, including all 94 manually generic nodes. Consequently requiring a GlobalEntity link adds no information here. Maximum observed degree is 20; no graph-size-specific hub cutoff was introduced.

| Manual class | Typed eligible | Typed excluded | SAME_AS yes | SAME_AS no |
|---|---:|---:|---:|---:|
| generic | 42 | 52 | 94 | 0 |
| non-generic | 177 | 12 | 189 | 0 |

Typed eligibility excludes 52/94 generic nodes and also excludes 12/189 manually non-generic nodes. It admits 42 generic nodes through imperfect ingestion types. This is a documented tradeoff of the ontology contract, not evidence that a lower-case multiword heuristic was optimized away.

## Full offline tables

All standalone ablations start from round one. `name` changes ontology eligibility for all seed sources; `cap_weight` changes total cap and restart mass; `versions` changes version representatives; `rounding` changes signal precision/constant handling. Combined also uses bounded store candidate queries and the fuzzy candidate prefilter. Thus combined is not asserted to be a simple additive combination. `cap5`/`cap15` each change only the combined total seed cap.

### current routing

| Variant | Type | n | Recall-any | Recall@10 | Full | MRR | Hits@1 |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | all | 60 | 0.678 | 0.661 | 31/60 | 0.444 | 0.267 |
| baseline | single | 15 | 0.867 | 0.867 | 13/15 | 0.334 | 0.067 |
| baseline | multi_hop | 20 | 0.333 | 0.333 | 1/20 | 0.255 | 0.100 |
| baseline | time_sensitive | 15 | 0.733 | 0.667 | 7/15 | 0.529 | 0.333 |
| baseline | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.858 | 0.800 |
| round1 | all | 60 | 0.794 | 0.786 | 41/60 | 0.424 | 0.183 |
| round1 | single | 15 | 0.933 | 0.933 | 14/15 | 0.376 | 0.067 |
| round1 | multi_hop | 20 | 0.508 | 0.483 | 5/20 | 0.298 | 0.100 |
| round1 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.606 | 0.333 |
| round1 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| name | all | 60 | 0.794 | 0.786 | 41/60 | 0.504 | 0.283 |
| name | single | 15 | 0.933 | 0.933 | 14/15 | 0.365 | 0.067 |
| name | multi_hop | 20 | 0.508 | 0.483 | 5/20 | 0.301 | 0.100 |
| name | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.683 | 0.467 |
| name | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.850 | 0.700 |
| cap_weight | all | 60 | 0.825 | 0.789 | 40/60 | 0.556 | 0.333 |
| cap_weight | single | 15 | 1.000 | 0.933 | 15/15 | 0.444 | 0.133 |
| cap_weight | multi_hop | 20 | 0.550 | 0.492 | 3/20 | 0.413 | 0.200 |
| cap_weight | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.680 | 0.467 |
| cap_weight | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.825 | 0.700 |
| versions | all | 60 | 0.794 | 0.778 | 41/60 | 0.401 | 0.167 |
| versions | single | 15 | 0.933 | 0.867 | 14/15 | 0.326 | 0.000 |
| versions | multi_hop | 20 | 0.508 | 0.508 | 5/20 | 0.277 | 0.100 |
| versions | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.594 | 0.333 |
| versions | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| rounding | all | 60 | 0.794 | 0.786 | 41/60 | 0.424 | 0.183 |
| rounding | single | 15 | 0.933 | 0.933 | 14/15 | 0.376 | 0.067 |
| rounding | multi_hop | 20 | 0.508 | 0.483 | 5/20 | 0.298 | 0.100 |
| rounding | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.606 | 0.333 |
| rounding | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| round2 | all | 60 | 0.800 | 0.772 | 39/60 | 0.553 | 0.350 |
| round2 | single | 15 | 1.000 | 0.933 | 15/15 | 0.312 | 0.000 |
| round2 | multi_hop | 20 | 0.475 | 0.442 | 2/20 | 0.445 | 0.250 |
| round2 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.641 | 0.400 |
| round2 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |
| cap5 | all | 60 | 0.831 | 0.822 | 41/60 | 0.546 | 0.317 |
| cap5 | single | 15 | 1.000 | 1.000 | 15/15 | 0.358 | 0.067 |
| cap5 | multi_hop | 20 | 0.567 | 0.542 | 4/20 | 0.393 | 0.100 |
| cap5 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.636 | 0.400 |
| cap5 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |
| cap15 | all | 60 | 0.819 | 0.786 | 42/60 | 0.524 | 0.333 |
| cap15 | single | 15 | 0.933 | 0.867 | 14/15 | 0.370 | 0.133 |
| cap15 | multi_hop | 20 | 0.583 | 0.533 | 6/20 | 0.317 | 0.100 |
| cap15 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.639 | 0.400 |
| cap15 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |
### oracle routing

| Variant | Type | n | Recall-any | Recall@10 | Full | MRR | Hits@1 |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | all | 60 | 0.689 | 0.689 | 32/60 | 0.464 | 0.317 |
| baseline | single | 15 | 1.000 | 1.000 | 15/15 | 0.587 | 0.400 |
| baseline | multi_hop | 20 | 0.292 | 0.292 | 1/20 | 0.166 | 0.050 |
| baseline | time_sensitive | 15 | 0.700 | 0.700 | 6/15 | 0.476 | 0.267 |
| baseline | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.858 | 0.800 |
| round1 | all | 60 | 0.778 | 0.769 | 38/60 | 0.418 | 0.217 |
| round1 | single | 15 | 0.933 | 0.933 | 14/15 | 0.395 | 0.200 |
| round1 | multi_hop | 20 | 0.533 | 0.508 | 5/20 | 0.318 | 0.150 |
| round1 | time_sensitive | 15 | 0.800 | 0.800 | 9/15 | 0.536 | 0.267 |
| round1 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| name | all | 60 | 0.786 | 0.778 | 39/60 | 0.476 | 0.267 |
| name | single | 15 | 0.933 | 0.933 | 14/15 | 0.367 | 0.133 |
| name | multi_hop | 20 | 0.508 | 0.483 | 4/20 | 0.325 | 0.150 |
| name | time_sensitive | 15 | 0.867 | 0.867 | 11/15 | 0.536 | 0.267 |
| name | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.850 | 0.700 |
| cap_weight | all | 60 | 0.817 | 0.789 | 39/60 | 0.522 | 0.300 |
| cap_weight | single | 15 | 1.000 | 0.933 | 15/15 | 0.457 | 0.200 |
| cap_weight | multi_hop | 20 | 0.525 | 0.492 | 2/20 | 0.381 | 0.150 |
| cap_weight | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.571 | 0.333 |
| cap_weight | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.825 | 0.700 |
| versions | all | 60 | 0.786 | 0.778 | 39/60 | 0.399 | 0.200 |
| versions | single | 15 | 0.933 | 0.933 | 14/15 | 0.345 | 0.133 |
| versions | multi_hop | 20 | 0.533 | 0.508 | 5/20 | 0.314 | 0.150 |
| versions | time_sensitive | 15 | 0.833 | 0.833 | 10/15 | 0.516 | 0.267 |
| versions | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| rounding | all | 60 | 0.778 | 0.769 | 38/60 | 0.418 | 0.217 |
| rounding | single | 15 | 0.933 | 0.933 | 14/15 | 0.395 | 0.200 |
| rounding | multi_hop | 20 | 0.533 | 0.508 | 5/20 | 0.318 | 0.150 |
| rounding | time_sensitive | 15 | 0.800 | 0.800 | 9/15 | 0.536 | 0.267 |
| rounding | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| round2 | all | 60 | 0.800 | 0.772 | 38/60 | 0.542 | 0.350 |
| round2 | single | 15 | 1.000 | 0.933 | 15/15 | 0.391 | 0.133 |
| round2 | multi_hop | 20 | 0.475 | 0.442 | 1/20 | 0.413 | 0.200 |
| round2 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.559 | 0.333 |
| round2 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |
| cap5 | all | 60 | 0.797 | 0.781 | 37/60 | 0.576 | 0.367 |
| cap5 | single | 15 | 1.000 | 1.000 | 15/15 | 0.456 | 0.133 |
| cap5 | multi_hop | 20 | 0.542 | 0.517 | 3/20 | 0.379 | 0.100 |
| cap5 | time_sensitive | 15 | 0.800 | 0.767 | 9/15 | 0.677 | 0.533 |
| cap5 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |
| cap15 | all | 60 | 0.803 | 0.786 | 40/60 | 0.490 | 0.300 |
| cap15 | single | 15 | 0.933 | 0.933 | 14/15 | 0.329 | 0.067 |
| cap15 | multi_hop | 20 | 0.533 | 0.483 | 4/20 | 0.307 | 0.100 |
| cap15 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.554 | 0.333 |
| cap15 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |

## Every combined regression against paired exact references

A regression means any requested metric decreases; improvements on other metrics do not cancel it. Raw per-question IDs and all signed deltas are preserved, including regressions for standalone and sensitivity configurations.

| Reference | Routing | Question | Delta recall | Delta R@10 | Delta full | Delta MRR | Delta Hits@1 |
|---|---|---|---:|---:|---:|---:|---:|
| baseline | current | v2-q04 | +0.333 | +0.000 | +0 | -0.500 | -1.000 |
| baseline | current | v2-q06 | +0.000 | +0.000 | +0 | -0.500 | -1.000 |
| baseline | current | v2-q09 | +0.000 | +0.000 | +0 | -0.800 | -1.000 |
| baseline | oracle | v2-q09 | +0.000 | +0.000 | +0 | -0.800 | -1.000 |
| baseline | current | v2-q11 | +0.000 | -0.333 | +0 | -0.109 | +0.000 |
| baseline | oracle | v2-q11 | +0.000 | -0.333 | +0 | -0.109 | +0.000 |
| baseline | current | v2-q16 | +0.000 | +0.000 | +0 | -0.300 | +0.000 |
| baseline | oracle | v2-q16 | +0.000 | +0.000 | +0 | -0.133 | +0.000 |
| baseline | current | v2-q18 | +0.000 | +0.000 | +0 | -0.190 | +0.000 |
| baseline | oracle | v2-q18 | +0.000 | +0.000 | +0 | -0.024 | +0.000 |
| baseline | current | v2-q22 | +0.000 | +0.000 | +0 | -0.167 | +0.000 |
| baseline | oracle | v2-q23 | +0.000 | -1.000 | +0 | -0.909 | -1.000 |
| baseline | current | v2-q25 | -0.500 | -0.500 | +0 | -0.250 | +0.000 |
| baseline | oracle | v2-q25 | +0.000 | +0.000 | +0 | -0.075 | +0.000 |
| baseline | current | v2-q26 | +0.000 | +0.000 | +0 | -0.133 | +0.000 |
| baseline | oracle | v2-q26 | +0.000 | +0.000 | +0 | -0.133 | +0.000 |
| baseline | current | v2-q29 | +0.000 | +0.000 | +0 | -0.167 | +0.000 |
| baseline | oracle | v2-q29 | +0.000 | +0.000 | +0 | -0.667 | -1.000 |
| baseline | current | v2-q30 | +0.000 | +0.000 | +0 | -0.250 | +0.000 |
| baseline | oracle | v2-q30 | +0.000 | +0.000 | +0 | -0.250 | +0.000 |
| baseline | current | v2-q31 | -0.500 | -0.500 | -1 | +0.000 | +0.000 |
| baseline | oracle | v2-q31 | -0.500 | -0.500 | -1 | +0.000 | +0.000 |
| baseline | current | v2-q36 | +0.000 | +0.000 | +0 | -0.167 | +0.000 |
| baseline | current | v2-q38 | -0.500 | -0.500 | +0 | -0.167 | +0.000 |
| baseline | oracle | v2-q38 | -0.500 | -0.500 | +0 | -0.167 | +0.000 |
| baseline | current | v2-q43 | +0.000 | +0.000 | +0 | -0.075 | +0.000 |
| baseline | oracle | v2-q43 | +0.000 | +0.000 | +0 | -0.042 | +0.000 |
| baseline | current | v2-q46 | +0.000 | +0.000 | +0 | -0.150 | +0.000 |
| baseline | oracle | v2-q51 | +0.000 | +0.000 | +0 | -0.750 | -1.000 |
| round1 | oracle | v2-q05 | -0.500 | -0.500 | -1 | +0.000 | +0.000 |
| round1 | current | v2-q08 | +0.000 | +0.000 | +0 | -0.250 | +0.000 |
| round1 | oracle | v2-q08 | +0.000 | +0.000 | +0 | -0.083 | +0.000 |
| round1 | current | v2-q09 | +0.000 | +0.000 | +0 | -0.050 | +0.000 |
| round1 | current | v2-q11 | +0.000 | -0.333 | +0 | -0.109 | +0.000 |
| round1 | oracle | v2-q11 | +0.000 | -0.333 | +0 | -0.109 | +0.000 |
| round1 | oracle | v2-q12 | +0.000 | +0.000 | +0 | -0.250 | +0.000 |
| round1 | oracle | v2-q15 | +0.000 | +0.000 | +0 | -0.667 | -1.000 |
| round1 | oracle | v2-q19 | +0.000 | +0.000 | +0 | -0.167 | +0.000 |
| round1 | current | v2-q22 | +0.000 | +0.000 | +0 | -0.667 | -1.000 |
| round1 | current | v2-q24 | -1.000 | -1.000 | -1 | -0.333 | +0.000 |
| round1 | oracle | v2-q24 | -1.000 | -1.000 | -1 | -0.333 | +0.000 |
| round1 | current | v2-q26 | +0.000 | +0.000 | +0 | -0.050 | +0.000 |
| round1 | oracle | v2-q26 | +0.000 | +0.000 | +0 | -0.050 | +0.000 |
| round1 | current | v2-q29 | +0.000 | +0.000 | +0 | -0.167 | +0.000 |
| round1 | current | v2-q31 | -0.500 | -0.500 | -1 | +0.000 | +0.000 |
| round1 | oracle | v2-q31 | -0.500 | -0.500 | -1 | +0.000 | +0.000 |
| round1 | current | v2-q33 | +0.000 | +0.000 | +0 | -0.083 | +0.000 |
| round1 | current | v2-q36 | +0.000 | +0.000 | +0 | -0.167 | +0.000 |
| round1 | current | v2-q41 | +0.000 | +0.000 | +0 | -0.083 | +0.000 |
| round1 | current | v2-q42 | -0.500 | -0.500 | -1 | -0.167 | +0.000 |
| round1 | oracle | v2-q42 | -0.500 | -0.500 | -1 | -0.167 | +0.000 |
| round1 | current | v2-q44 | +0.000 | +0.000 | +0 | -0.500 | -1.000 |
| round1 | oracle | v2-q44 | +0.000 | +0.000 | +0 | -0.500 | -1.000 |
| round1 | current | v2-q46 | +0.000 | +0.000 | +0 | -0.233 | +0.000 |
| round1 | oracle | v2-q48 | +0.000 | +0.000 | +0 | -0.750 | -1.000 |
| round1 | oracle | v2-q53 | -0.500 | +0.000 | -1 | +0.000 | +0.000 |
| round1 | oracle | v2-q56 | +0.000 | +0.000 | +0 | -0.083 | +0.000 |

## Determinism and timing

Independent uncached reruns of the same **44 regression cells**: **0 changed** seed IDs, fact IDs or ranked item IDs. This is exact-path determinism on this graph/clock, not an ANN determinism promise. The original round-one audit had 6/44 differences. Fresh exact queries were executed against Neo4j in the second pass; only local query embeddings were reused.

Fact-search timing: 60 uncached recorded-route queries per path, excluding query embedding inference, including index metadata check, finite refill and bounded endpoint hydration; warm shared database under concurrent activity. Small synthetic graph only; no real-data throughput claim.

| Path | n | Mean ms | Median ms | p95 ms |
|---|---:|---:|---:|---:|
| fact_ann | 60 | 49.10 | 24.87 | 51.69 |
| fact_exact | 60 | 14.99 | 14.23 | 20.16 |

## Validation and outstanding work

Snapshot hash check: 105 non-ephemeral E0-recorded snapshot files, changed 1, missing 0. SQLite -wal/-shm files are ignored as live runtime sidecars. The historical comparison flags `chroma/chroma.sqlite3` as changed since E0; this is not a task-start comparison and cannot attribute the change. This task neither opened Chroma nor wrote snapshot files. No application graph DDL or writes were executed. Password was read privately into the Neo4j process environment; `.env` was never accessed. No Python processes were stopped. No real snapshot or real test split was touched.

`retrieval-tests.txt`:
```text
........................................................................ [ 48%]

........................................................................ [ 96%]

.....                                                                    [100%]

149 passed in 2.30s

```

`integration-tests-refill.txt`:
```text
.                                                                        [100%]

1 passed in 20.71s

```

`offline-tests-latest.txt`:
```text
........................................................................ [ 84%]

........................................................................ [ 90%]

........................................................................ [ 97%]

.............................                                            [100%]

1108 passed, 1 skipped, 22 deselected in 101.30s (0:01:41)

```

The suite was executed during unrelated evaluation/LLM edits in this shared checkout. Earlier failures in Judge/token-cap test contracts are recorded in `offline-tests-final.txt`; they were not repaired by changing another task's implementation. The retrieval structural protocol fixture was updated for `name_candidates`.

Outstanding: real-data dev validation (build is owned by another process), answer-level evaluation (forbidden here), large-corpus ANN recall/latency validation, ingestion typing/identity quality and missing event-relative routing scopes. This synthetic diagnostic is a secondary check, not generalization evidence. BM25 remains considered but unimplemented. No defaults were selected using these tables.

Reproduce: `.venv\Scripts\python.exe -m omnistream.eval.diagnostics.own_fixes_round2`, then `-m omnistream.eval.diagnostics.own_fixes_round2_report`. The runner requires cached local embedding weights, blocks SDK paid completion methods, disables `.env` loading, uses exact graph reads, and rewrites only its own `data/diagnostics/own-fixes-round2/` measurements. Full raw tables, historical comparisons, replay outputs, type/identity signal inventory and timings are retained there.
