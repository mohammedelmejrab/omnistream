# Own retrieval fixes, round 3

Measured 2026-11-13 on `feat/c5-integration`, round-two reference `336cdbd`. No commits, web search, paid LLM calls, `.env` access, application graph writes or snapshot writes. Local embeddings only; OpenAI completion SDK calls are blocked during measurement. Integration schema writes target disposable testcontainers databases.

## Controls and headline

All 60 eval-v2 questions, recorded routes and all-bubble routes, exact search, frozen E0 clock. Recorded routes remain the 35 E0 own decisions plus 25 E2 repeat-0 decisions. All-bubble routing retains the recorded time scope and exclusions. The concurrently implemented event-relative router is not rerun: this keeps routing fixed for the retrieval comparison. Unbounded history is tested independently. No answer correctness claim is made.

Baseline, round 1 and round 2 are freshly remeasured using frozen source fixtures and the round-two store (including its former lexical prefilter). Baseline/round-one seeds, restart and fusion retain their historical behavior; identity deduplication uses the round-two harness contract. Round-three paths use the changed store/seeds/versions. Baseline/round-one/round-two aggregates reproduce the round-two exact table. All metrics credit existing item_ids provenance, without treating suppressed versions as retrieved evidence. Recall-any is mean fraction of gold items found anywhere; full is count with all gold items.

960 cells: four headline variants, two predeclared generic-weight sensitivities (0.25, 1.0), and two mechanism counterfactuals; each has 60 questions × two routing policies. Default 0.5 was declared before measurement and remains unchanged.

| Routing | Variant | Recall-any | R@10 | Full | MRR | Hits@1 | Freshness MRR |
|---|---|---:|---:|---:|---:|---:|---:|
| current | baseline | 0.678 | 0.661 | 31/60 | 0.444 | 0.267 | 0.858 |
| current | round1 | 0.794 | 0.786 | 41/60 | 0.424 | 0.183 | 0.475 |
| current | round2 | 0.800 | 0.772 | 39/60 | 0.553 | 0.350 | 1.000 |
| current | round3 | 0.839 | 0.831 | 42/60 | 0.571 | 0.350 | 1.000 |
| oracle | baseline | 0.689 | 0.689 | 32/60 | 0.464 | 0.317 | 0.858 |
| oracle | round1 | 0.778 | 0.769 | 38/60 | 0.418 | 0.217 | 0.475 |
| oracle | round2 | 0.800 | 0.772 | 38/60 | 0.542 | 0.350 | 1.000 |
| oracle | round3 | 0.800 | 0.800 | 37/60 | 0.564 | 0.350 | 1.000 |

Recorded-route full coverage improves 39 -> 42 and R@10 .772 -> .831; all-bubble full coverage declines 38 -> 37 despite higher R@10 (.772 -> .800). Freshness MRR stays at 1.000 for both routing policies. No constants were tuned in response to these outcomes.

## General mechanisms

1. Name candidates use an online Entity name FULLTEXT index, discovered read-only. Installed Graphiti 0.31.2 graph_queries.py defines `node_name_and_summary`; SHOW INDEXES confirms it exists over name/summary/group_id. Content words exclude a fixed English stopword/legal-suffix list; terms are tokenized, Lucene-escaped and name-field quoted, and the complete query is passed as a parameter. Candidates are ranked by index score and bounded after bubble filtering. With no index, all bubble candidates are ranked by whole content-word overlap, then fuzzy WRatio, then textual ties; no UUID-first truncation. The fallback is intentionally linear; the online index avoids the CONTAINS population scan. Aliases remain available in fallback and final fuzzy matching, while Graphiti indexes canonical names.

2. Version collapse requires the same bubble, directed local endpoints and normalized relation, plus identical normalized text or fact-text cosine >= .95. Different digit/amount/quarter/date tokens or spelled month names prevent collapse unless explicit invalid_at/expired_at <= newer.valid_at proves replacement. Global identities never cross bubble boundaries. Local endpoint keys deliberately prefer retention over collapsing ingestion duplicates. Families use deterministic newest-first ordering and require compatibility with every member, preventing first-member and transitive-bridge effects. Point/current scopes keep representatives; all interval scopes, including TimeScope(None, None), retain every overlapping assertion. Other assertions remain untouched; no extra recency demotion was needed. Temporal filtering already removes invalidated older CEOs under now and retains both under unbounded history.

3. Every positive top-10 fact match may seed endpoints, including Concept/untyped/unknown endpoints. Each source (vector, fuzzy, fact) uses reciprocal dense rank 1/(1 + number of distinct higher scores) within the query before cross-source selection. Generic fact endpoints multiply their normalized fact score by the declared 0.5 default. Thus cosine and fuzzy magnitudes no longer compete directly. Names retain five distinct identities; all sources share ten total identities. Half the total capacity (ceiling for odd budgets) is reserved for the strongest distinct fact-derived identities, with remaining slots filled by the combined normalized ranking. Duplicate identities take maximum score. This rank scale and symmetric reservation are structural choices, not eval-tuned constants.

4. Incompatible/offline/missing vector indexes select exact server-side cosine; incompatible schema/metric emits a warning instead of raising during retrieval. Explicit writer/schema dimension validation remains strict. Both entity and fact ANN paths refill at 5k/15k/25k and warn/fall back to exact when fewer than k survive. Read-only SHOW PROCEDURES on Neo4j 5.26.33 confirms queryNodes/queryRelationships accept only (indexName, numberOfNearestNeighbours, query), with no filter parameter. Signatures and index inventory are retained in schema.json. No unsupported in-index filter was introduced.

## By-type tables

| Routing | Variant | Type | n | Recall-any | R@10 | Full | MRR | Hits@1 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| current | baseline | single | 15 | 0.867 | 0.867 | 13/15 | 0.334 | 0.067 |
| current | baseline | multi_hop | 20 | 0.333 | 0.333 | 1/20 | 0.255 | 0.100 |
| current | baseline | time_sensitive | 15 | 0.733 | 0.667 | 7/15 | 0.529 | 0.333 |
| current | baseline | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.858 | 0.800 |
| current | round1 | single | 15 | 0.933 | 0.933 | 14/15 | 0.376 | 0.067 |
| current | round1 | multi_hop | 20 | 0.508 | 0.483 | 5/20 | 0.298 | 0.100 |
| current | round1 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.606 | 0.333 |
| current | round1 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| current | round2 | single | 15 | 1.000 | 0.933 | 15/15 | 0.312 | 0.000 |
| current | round2 | multi_hop | 20 | 0.475 | 0.442 | 2/20 | 0.445 | 0.250 |
| current | round2 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.641 | 0.400 |
| current | round2 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |
| current | round3 | single | 15 | 1.000 | 1.000 | 15/15 | 0.536 | 0.267 |
| current | round3 | multi_hop | 20 | 0.592 | 0.567 | 5/20 | 0.377 | 0.150 |
| current | round3 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.580 | 0.267 |
| current | round3 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |
| oracle | baseline | single | 15 | 1.000 | 1.000 | 15/15 | 0.587 | 0.400 |
| oracle | baseline | multi_hop | 20 | 0.292 | 0.292 | 1/20 | 0.166 | 0.050 |
| oracle | baseline | time_sensitive | 15 | 0.700 | 0.700 | 6/15 | 0.476 | 0.267 |
| oracle | baseline | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.858 | 0.800 |
| oracle | round1 | single | 15 | 0.933 | 0.933 | 14/15 | 0.395 | 0.200 |
| oracle | round1 | multi_hop | 20 | 0.533 | 0.508 | 5/20 | 0.318 | 0.150 |
| oracle | round1 | time_sensitive | 15 | 0.800 | 0.800 | 9/15 | 0.536 | 0.267 |
| oracle | round1 | freshness | 10 | 1.000 | 1.000 | 10/10 | 0.475 | 0.300 |
| oracle | round2 | single | 15 | 1.000 | 0.933 | 15/15 | 0.391 | 0.133 |
| oracle | round2 | multi_hop | 20 | 0.475 | 0.442 | 1/20 | 0.413 | 0.200 |
| oracle | round2 | time_sensitive | 15 | 0.900 | 0.900 | 12/15 | 0.559 | 0.333 |
| oracle | round2 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |
| oracle | round3 | single | 15 | 1.000 | 1.000 | 15/15 | 0.563 | 0.333 |
| oracle | round3 | multi_hop | 20 | 0.500 | 0.500 | 1/20 | 0.368 | 0.150 |
| oracle | round3 | time_sensitive | 15 | 0.867 | 0.867 | 11/15 | 0.533 | 0.200 |
| oracle | round3 | freshness | 10 | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 |

## Sensitivity and counterfactuals

| Routing | Variant | Recall-any | R@10 | Full | MRR | Hits@1 | Freshness MRR |
|---|---|---:|---:|---:|---:|---:|---:|
| current | generic025 | 0.839 | 0.831 | 42/60 | 0.563 | 0.333 | 1.000 |
| current | round3 | 0.839 | 0.831 | 42/60 | 0.571 | 0.350 | 1.000 |
| current | generic100 | 0.839 | 0.831 | 42/60 | 0.580 | 0.367 | 1.000 |
| current | seed_only | 0.831 | 0.831 | 42/60 | 0.553 | 0.333 | 1.000 |
| current | versions_only | 0.817 | 0.781 | 39/60 | 0.590 | 0.383 | 1.000 |
| oracle | generic025 | 0.808 | 0.808 | 38/60 | 0.567 | 0.350 | 1.000 |
| oracle | round3 | 0.800 | 0.800 | 37/60 | 0.564 | 0.350 | 1.000 |
| oracle | generic100 | 0.800 | 0.800 | 37/60 | 0.573 | 0.367 | 1.000 |
| oracle | seed_only | 0.800 | 0.800 | 38/60 | 0.593 | 0.417 | 1.000 |
| oracle | versions_only | 0.817 | 0.789 | 39/60 | 0.547 | 0.333 | 1.000 |

`seed_only` uses new name retrieval/seeding and old version grouping; `versions_only` uses old names/seeding with new version grouping. Both retain weighted PPR/current fusion. They separate seeding and grouping effects; interactions can still affect ranks. Sensitivities are reported without changing the default.

## Every regression versus round 2

A regression is any requested metric loss, even when another metric improves. Reasons below distinguish gold-item loss before expansion, suppression, and final top-20 truncation using captured expansion/representative IDs. Rank-only losses report changed seed identity count and the two controlled counterfactual MRRs; they are evidence of ranking competition, not a claim of unique causal attribution. Each MRR pair is seed-only / versions-only (round-two MRR is also shown).

| Routing | Question | ?Recall | ?R@10 | ?Full | ?MRR | ?H@1 | Reason / diagnostic |
|---|---|---:|---:|---:|---:|---:|---|
| current | v2-q04 | +0.333 | +0.667 | +1 | -0.250 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 0.500, counterfactuals 0.250/0.500 |
| oracle | v2-q04 | +0.000 | +0.333 | +0 | -0.250 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 6; MRR old 0.500, counterfactuals 0.250/0.500 |
| current | v2-q02 | +0.000 | +0.000 | +0 | -0.250 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 4; MRR old 0.500, counterfactuals 0.250/0.500 |
| oracle | v2-q02 | +0.000 | +0.000 | +0 | -0.250 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 4; MRR old 0.500, counterfactuals 0.250/0.500 |
| current | v2-q17 | +0.500 | +0.500 | +1 | -0.167 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 4; MRR old 0.500, counterfactuals 0.333/0.500 |
| oracle | v2-q17 | +0.000 | +0.000 | +0 | -0.167 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 0.500, counterfactuals 0.333/0.500 |
| current | v2-q20 | +0.000 | +0.000 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 1; MRR old 1.000, counterfactuals 1.000/1.000 |
| oracle | v2-q20 | -0.500 | -0.500 | -1 | -0.500 | -1.000 | 0dafc4b234f3430caa1a8bfb95b9620dc8b3e9e68d58cd3018b1bcb53305c81d: outside final top20; seed symmetric difference 3; MRR old 1.000, counterfactuals 1.000/1.000 |
| current | v2-q31 | +0.000 | +0.000 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 6; MRR old 1.000, counterfactuals 0.500/1.000 |
| oracle | v2-q31 | +0.000 | +0.000 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 6; MRR old 1.000, counterfactuals 0.500/1.000 |
| current | v2-q32 | +0.000 | +0.000 | +0 | -0.750 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 6; MRR old 1.000, counterfactuals 0.250/1.000 |
| oracle | v2-q32 | +0.000 | +0.000 | +0 | -0.800 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 4; MRR old 1.000, counterfactuals 0.200/1.000 |
| oracle | v2-q34 | +0.000 | +0.000 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 5; MRR old 1.000, counterfactuals 0.500/1.000 |
| oracle | v2-q39 | +0.000 | +0.000 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 2; MRR old 1.000, counterfactuals 1.000/1.000 |
| current | v2-q42 | +0.000 | +0.000 | +0 | -0.167 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 6; MRR old 0.333, counterfactuals 0.167/0.333 |
| oracle | v2-q42 | +0.000 | +0.000 | +0 | -0.167 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 6; MRR old 0.333, counterfactuals 0.167/0.333 |
| current | v2-q47 | +0.000 | +0.000 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 1.000, counterfactuals 0.500/1.000 |
| oracle | v2-q47 | +0.000 | +0.000 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 1.000, counterfactuals 0.500/1.000 |
| current | v2-q48 | +0.000 | -0.500 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 1.000, counterfactuals 0.333/1.000 |
| current | v2-q49 | +0.000 | +0.000 | +0 | -0.500 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 4; MRR old 1.000, counterfactuals 0.500/1.000 |
| current | v2-q52 | +0.000 | +0.000 | +0 | -0.057 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 0.200, counterfactuals 0.143/0.200 |
| oracle | v2-q52 | +0.000 | +0.000 | +0 | -0.057 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 0.200, counterfactuals 0.143/0.200 |
| current | v2-q53 | +0.500 | +0.500 | +1 | -0.667 | -1.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 1.000, counterfactuals 0.333/0.500 |
| oracle | v2-q53 | +0.000 | +0.000 | +0 | -0.857 | -1.000 | d4370efe5129437613624461467f5fdd4f9748a01679856f7eb69ecafb58869b: outside final top20; seed symmetric difference 8; MRR old 1.000, counterfactuals 0.143/0.500 |
| oracle | v2-q54 | -0.500 | -0.500 | -1 | +0.300 | +0.000 | 804c95c59cd0a237943cf0391d73bbe6d4747b884c12a7bdffb388402c11a427: outside final top20; seed symmetric difference 4; MRR old 0.200, counterfactuals 0.500/0.200 |
| current | v2-q58 | +0.000 | +0.000 | +0 | -0.167 | +0.000 | gold retained; ranking competition (R@10 losses reflect displacement below rank 10); seed symmetric difference 8; MRR old 0.500, counterfactuals 0.333/0.500 |

26 regression cells: 13 current, 13 oracle. Signed deltas for every variant/reference are in paired_deltas.json.

## Determinism, timing and validation

Independent replay with the graph query cache disabled: **0/44 changed** across seed IDs, ranked fact IDs and ranked item IDs. Local query embedding inference remains cached; graph retrieval is independently reread.

| Exact path | n | Mean ms | Median ms |
|---|---:|---:|---:|
| fact_exact | 60 | 12.79 | 12.13 |
| name_fulltext | 60 | 5.95 | 5.59 |

Times are 60 uncached recorded-route queries per search operation, with local embeddings precomputed. Name timing includes schema discovery. This small synthetic graph and concurrently active database do not establish large-corpus latency or ANN quality. Raw paths/times: fact_timings.json.

- `offline-tests-final.txt`: 1189 passed, 1 skipped, 22 deselected in 102.96s (0:01:42)
- `integration-tests.txt`: 10 passed, 1199 deselected in 130.73s (0:02:10)

Added general tests cover common-word name survival beyond 300 distractors, Lucene literal escaping/parameterization, co-existing quarterly/tranche/month facts despite identical embeddings, same-relation near-identical collapse, cross-bubble retention, input permutations, invalidated CEO now versus unbounded scope, generic endpoint reduction, source-scale independence/fact quota, incompatible-index warning, and ANN-shortfall exact fallback. Integration executes actual fulltext/schema/fallback queries in isolated Neo4j. Existing round-two tests were updated where they asserted the rejected over-merge or silent underfill contracts.

All sources/replays/metrics are in `src/omnistream/eval/diagnostics/own_fixes_round3*.py` and `data/diagnostics/own-fixes-round3/`. Source fixture own_fixes_round2_sources.json comes from git show 336cdbd. Diagnostics are retrieval-only and use synthetic eval-v2; real-data dev validation remains outstanding. OpenCode-owned router/QA/runtime/modes/tools files were not edited by this implementation agent; the full suite includes concurrent event-relative changes.
