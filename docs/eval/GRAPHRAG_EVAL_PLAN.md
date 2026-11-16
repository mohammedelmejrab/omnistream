# OmniStream GraphRAG Evaluation Plan

Status: PLAN. Date: 2026-11-16.
Sources: arXiv literature survey

## 1. Systems under comparison

| # | System | Code mode | Notes |
|---|---|---|---|
| 1 | **Naive RAG** (baseline) | `external` (LlamaIndex) | DECIDED: existing LlamaIndex baseline, no new mode. Dense top-k chunks, no graph. Every surveyed paper has this baseline. |
| 2 | **BM25** | new mode on `retrieval/sparse.py:17` (`BM25Index`) | Currently unused in eval. Template: `eval/external.py:31-67`. |
| 3 | **Graphiti** | `graphiti` | Graphiti core search. |
| 4 | **Own** | `own` | Seeding, 2-hop expansion, PageRank, fact fusion. |
| 5 | **Own + subagents** | `own+subagents` | One agent per bubble. |
| 6 | **Classic** (OmniStream diagnostic) | `classic` | OmniStream's own chunk-vector pipeline (Chroma, top-10, own routing, prompts and citations), without graph and WITHOUT subagents. Only `classic` alone; `classic+subagents` is not run. |
| ref | Published numbers (HippoRAG 2, GraphRAG-Bench) | n/a | Context only, not a like-for-like comparison (see section 6). |

DECIDED: the external baselines are naive RAG (`external`) and BM25 only. `classic` (alone, without subagents) is added as a sixth, internal diagnostic system; `classic+subagents` is not run. Published systems (HippoRAG 2 and others) appear only as reference numbers in section 6, never as systems we run.

| Comparison | Isolates |
|---|---|
| `external` vs `classic` | Pipeline effect (routing, prompts, Chroma, citations), no graph |
| `classic` vs `graphiti` / `own` | Graph effect, same pipeline, no subagents |
| `own` vs `own+subagents` | Subagent effect |
| `own+subagents` vs `external` / `bm25` | Full system vs outside baselines (mixes graph, pipeline and subagents) |

Limit: without `classic+subagents`, the graph effect cannot be isolated under subagents. Earlier eval-v2 numbers hinted subagents may drive most of the gain (own+subagents 1.78 vs classic+subagents 1.73), and this plan will not re-test that; state the limit in the report.

Caveat: `external` uses LlamaIndex's own embedder, chunking and prompt defaults, so differences vs the other four are not purely retrieval. Record `external`'s embedder, chunk size, top-k and generator in the report; align the generator model with the others.

## 2. What the papers do (verified from paper text)

| Paper | arXiv | Eval style | Metrics |
|---|---|---|---|
| GraphRAG | 2404.16130 | Pairwise LLM judge, global questions | Win rate: comprehensiveness, diversity, empowerment; indexing time |
| LightRAG | 2410.05779 | Pairwise LLM judge (GPT-4o-mini), answer order alternated | Win rate (4 criteria), tokens and API calls, ablations |
| HippoRAG | 2405.14831 | Gold-answer multi-hop QA | Recall@2/@5, EM, F1 on MuSiQue, 2Wiki, HotpotQA |
| HippoRAG 2 | 2502.14802 | Gold QA, 3 task families | Passage recall@5, F1; NQ, PopQA, NarrativeQA, MuSiQue, 2Wiki, HotpotQA, LV-Eval |
| GraphRAG-Bench | 2506.05690 | Stage-wise (construction, retrieval, generation) | ACC, ROUGE-L, evidence coverage, faithfulness |
| RAGChecker | 2408.08067 | Claim-level diagnostics, meta-evaluated vs humans | Claim precision/recall, context utilization, noise sensitivity, hallucination |
| RAGAS / ARES | 2309.15217 / 2311.09476 | Reference-free | Faithfulness, answer relevance, context relevance; ARES adds PPI confidence intervals |
| MultiHop-RAG | 2401.15391 | Retrieval + answer on news multi-hop | MAP@K, MRR@K, Hit@K, accuracy |
| G-Retriever | 2402.07630 | KGQA | Hit@1, hallucination rate |

Standard protocol: (1) build index with an LLM and report indexing cost; (2) fixed reader LLM across systems; (3) compare against naive vector RAG; (4) gold QA uses EM/F1 + recall@k, open-ended uses pairwise win rate with swapped order and replicates; (5) report cost.

## 3. Current OmniStream status (from audit)

Strengths: Recall@10, MRR, Hits@1; claim-level citation entailment; changed-fact and freshness tests; contamination check (0/60 closed-book correct); query cost/latency/tokens; invalid-run safeguard.

eval-v2 mean correctness (0-2, LLM judge, single run, n=60): external 1.13, classic 1.28, graphiti 1.10, own 1.12, own+subagents 1.78, classic+subagents 1.73. Citation faithfulness: classic 0.95, graphiti 0.70, own 0.76, own+subagents 0.86 (threshold 0.90).
real-v2 dev (n=24): external 1.58, classic 1.54, own 0.88.

Caveats: judge is same DeepSeek family as the answerer and has 0/30 human labels; 111/370 answer cells measured (OpenRouter $5 cap); indexing cost not measured; ingestion routing accuracy 0.63-0.72 (fails 0.85); duplicate-entity rate 0.12 (fails 0.05).

## 4. Gaps and plan

Phases in priority order. Each phase has an acceptance check.

### Phase 0 - Make existing numbers trustworthy
1. **Judge calibration.** Label the 30 rows from `eval/calibration.py:10` (`export_sample`), compute agreement with `:107`. Add a second judge from a different model family and report agreement. *Accept:* agreement reported (e.g. Cohen's kappa) and a decision on whether correctness is usable.
2. **Fix budget.** Raise or replace the OpenRouter cap so the full answer matrix runs. *Accept:* 100% of answer cells measured, run not flagged INVALID.

### Phase 1 - Baselines (the 5 systems)
3. Add a `bm25` configuration only (`external` already serves as naive): `eval/dataset.py:8-15` (CONFIGURATIONS), `retrieval/models.py:10` (`RetrievalMode`), dispatch `retrieval/modes.py:11-35`, runtime `retrieval/runtime.py:98`, run loop `eval/__init__.py:186`.
4. Keep the generator, prompt, top-k, and context budget identical across all five. *Accept:* one config table in the report proves this.

### Phase 2 - Metrics comparable to the papers
5. In `eval/metrics.py:62-73`: add Recall@k curve (k=2,5,10,20), nDCG@10, MAP.
6. In `eval/__init__.py:112-185` (`score_question`): add EM and token-level F1 on questions with short gold answers; add context precision/recall and RAGChecker-style claim recall.
7. Keep the 0-2 judge score, but report it as secondary to EM/F1 where gold exists.
*Accept:* each system has Recall@5 and F1 on the multi-hop subset, matching HippoRAG's reporting format.

### Phase 3 - Statistics
8. Bootstrap 95% CIs on every mean; paired bootstrap or Wilcoxon between systems; report n per question type; run each system 3 times to estimate variance.
9. Merge small types (real-v2 dev has 1-6 per type) or report only aggregate. *Accept:* every comparison in the report carries a CI or an explicit "not significant" note.

### Phase 4 - Pairwise win rate (GraphRAG/LightRAG protocol)
10. Add `eval/pairwise.py`: judge compares two answers on comprehensiveness, diversity, empowerment, overall; run both orders and average; judge model differs from answerer. Pairs: each system vs naive.
11. DECIDED: global/sensemaking (community detection + community summaries + map-reduce, as in Microsoft GraphRAG) is OUT OF SCOPE. OmniStream has no such mode and none is planned. State this as a limitation in the report. Pairwise win rate is applied to the normal question set only.

### Phase 5 - Cost and ablations
12. Indexing cost: unblock the probe (`docs/realdata/real-v2-ingestion-cost.md`), instrument `eval/snapshot.py:155` (`SnapshotBuilder`) for tokens, time, and dollars per 1k documents; also incremental-update cost (LightRAG, HippoRAG 2 report this).
13. Answer-level ablations for own: seeding, fusion, PageRank, 2-hop on/off; complete the E1 all-bubble runs. Mirrors LightRAG `-High/-Low` and G-Retriever component ablations.

### Phase 6 - Final held-out run
14. Run real-v2 test (55 questions) once, after Phases 0-5 are frozen. Do not tune on it.

## 4b. Track B - OmniStream strengths (eval-v2 and real-v2)

**Purpose.** Track A (MuSiQue, section 4) makes us comparable to the papers but is static, entity-centric, and has no dates. Track B measures what the papers' benchmarks cannot: changing facts, freshness, citation faithfulness, routing, and ingestion quality on OmniStream's own data. Same five systems as Track A: `external`, `bm25`, `graphiti`, `own`, `own+subagents`.

**Data.**
| Set | Questions | Use |
|---|---|---|
| eval-v2 | 60: 15 single-hop, 20 multi-hop, 15 time-sensitive/changed-fact, 10 freshness | Main Track B set; iterate here |
| real-v2 dev | 24 scored (split already run once; per-type cells hold 1-6 questions) | Sanity checks only, never for claims |
| real-v2 test | 55, held out, not yet run | Run exactly once, last, after all code and prompts are frozen (Phase 6) |

**Metrics, by what they show.**
| Strength | Metrics | Applies to |
|---|---|---|
| Retrieval quality | Recall@10, MRR, Hits@1, Recall@k curve, nDCG | all five |
| Answer quality | Judge correctness 0-2 (calibrated), EM/F1 where a short gold answer exists | all five |
| Changing facts | Changed-fact accuracy (answer uses the current value, not the superseded one) | all five; baselines have no time scope, so this tests whether they surface stale facts |
| Freshness | Freshness lag on the 10 freshness questions (currently N/A in the existing report; fix the measurement first) | all five |
| Provenance | Claim-level citation faithfulness (threshold 0.90), zero-citation answers, abstention precision | all five |
| Routing | Routing precision and recall | only configurations that route (`graphiti`, `own`, `own+subagents`); report N/A for baselines, do not score them as 0 |
| Ingestion quality | Ingestion routing accuracy (threshold 0.85), duplicate-entity rate (threshold 0.05), entity audit | OmniStream graph only; N/A for baselines |
| Cost | Latency p50/p95, tokens, dollars per query, peak memory | all five |
| Comparison to baselines | Pairwise win rate vs `external` and vs `bm25`, answer order swapped, judge from a different model family | all OmniStream systems |

**Rules.**
1. Re-run the baselines and the OmniStream systems on the same code version, judge and seed. Do not mix the old eval-v2 numbers (which exclude `bm25` and mix runs) with new ones. Keep the invalid-run safeguard (more than 10% unmeasured flags INVALID).
2. Split every number by question type (single, multi-hop, changed-fact, freshness) and report n per cell. With n of 10-20 per type, report bootstrap CIs and treat differences within the CI as ties.
3. Judge calibration (Phase 0) must be done before Track B correctness is quoted.
4. Pre-register the hypotheses before running: (a) graph systems beat the baselines on changed-fact accuracy; (b) `own+subagents` beats the baselines on multi-hop correctness; (c) graph systems match `external` on single-hop. State them in the report whether or not they hold. The existing eval-v2 results do not yet support (a): changed-fact accuracy fails for most configurations.
5. Report the graph-vs-pipeline-vs-subagents confound (section 1): `classic` isolates graph from pipeline, but without `classic+subagents` a win for `own+subagents` cannot be attributed to the graph alone.

**Not covered yet (open gaps).** Multi-source credibility (the corroboration confidence signal in `fact_fusion.py`) has no metric; incremental-update cost and correctness (freshness lag aside) is untested; real-v2's small per-type cells limit what real-data claims can say. A credibility test would need questions where two sources disagree and the higher-credibility one is correct.

**Cost (Track B).** Scaled from the measured eval-v2 token counts (60 questions per system; real-v2 test 55 questions, assumed similar size). One run of both sets at DeepSeek judge rates: about $1.14 (HY4 list), $0.62 (HY4 column 2), $0.74 (DeepSeek answerer). Ingestion for the real-v2 test snapshot (140 items) is unmeasured; rough estimate $0.1-0.5. Real documents and retrieved contexts may be larger than the eval-v2 ones, so treat these as lower bounds. Three variance runs of the answering side roughly triple these figures; ingestion is paid once.

**Order of work.** Phase 0 (calibration) -> Phase 1 (`bm25` config) -> Phase 2 (metrics) -> run Track B on eval-v2 and Track A on MuSiQue -> Phases 3-5 (statistics, pairwise, ablations, indexing cost) -> real-v2 test once.

## 5. Metrics matrix (target report)

| Metric | Naive | BM25 | Graphiti | Own | Own+sub |
|---|---|---|---|---|---|
| Recall@2 / @5 / @10 | | | | | |
| nDCG@10 / MRR | | | | | |
| EM / F1 (gold subset) | | | | | |
| Judge correctness (0-2) + CI | | | | | |
| Citation faithfulness | | | | | |
| Pairwise win rate vs naive | - | | | | |
| Changed-fact accuracy | | | | | |
| Freshness lag | | | | | |
| Latency p50/p95, tokens, $ / query | | | | | |
| Indexing time, tokens, $ | | | | | |

## 6. Published reference numbers

Only figures verified in the paper text are listed. Table cells were not extractable from the text, so they are marked TODO and must be read from the PDF before citing.

| Source | Setting | Verified figure |
|---|---|---|
| HippoRAG 2 (2502.14802) | Llama-3.3-70B reader, top-5 passages, NV-Embed-v2 retriever | HippoRAG 2 has the highest average F1; beats NV-Embed-v2 by 9.5% F1 on 2Wiki and 3.1% on LV-Eval; NV-Embed-v2 beats GTR (T5-base) by 6.6% on average |
| HippoRAG 2 | Table 2, MuSiQue F1, Llama-3.3-70B-Instruct reader | GritLM-7B 44.8; NV-Embed-v2 45.7; RAPTOR 28.9; GraphRAG 38.5; LightRAG 1.6; HippoRAG 35.1; **HippoRAG 2 48.6**. (Full table in 6.3.) |
| HippoRAG 2 | Table 3, MuSiQue passage recall@5 | BM25 43.5; Contriever 46.6; GTR 49.1; GTE-Qwen2-7B 63.6; GritLM-7B 65.9; NV-Embed-v2 69.7; RAPTOR 57.8; HippoRAG 51.9 (original paper) / 53.2 (reproduced); **HippoRAG 2 74.7** |
| HippoRAG 2 | Average F1 over all 7 datasets (Table 2) | NV-Embed-v2 57.0; RAPTOR 48.8; GraphRAG 49.6; HippoRAG 53.1; **HippoRAG 2 59.8** |
| HippoRAG 2 | Setup | Structure-augmented baselines use Llama-3.3-70B-Instruct to build the graph and NV-Embed-v2 as retriever; dataset statistics (Table 1): MuSiQue has 1,000 queries and 11,656 passages (2Wiki 1,000 / 6,119; HotpotQA 1,000 / 9,811). Sampling procedure not captured; see PDF section 5.2. |
| HippoRAG 2 | Table 8 (EM/F1, GPT-4o-mini reader) | Not extracted; read from PDF only if needed |
| HippoRAG (2405.14831) | Single-step vs IRCoT | Claims 10-30x cheaper and 6-13x faster than IRCoT (intro text) |
| GraphRAG-Bench (2506.05690) | Table 5, GPT-4o-mini | Vanilla RAG with rerank 58.8 vs 49.3 ACC for a graph method on one fact-retrieval dataset |
| GraphRAG (2404.16130) | Podcast corpus | Indexing took 281 min |

Comparability warning: those papers use Wikipedia multi-hop QA (MuSiQue, 2Wiki, HotpotQA) with different readers, retrievers, and judges. OmniStream's corpus is streaming news-style with changing facts. Do not place paper numbers in the same table as OmniStream numbers without labelling them "reference, different setting". For a like-for-like check, run `external`, `bm25`, `graphiti`, `own` and `own+subagents` on a MuSiQue slice of n=100 (cost limit; HippoRAG 2 randomly samples 1,000 MuSiQue queries following HippoRAG, HippoRAG 2 reports 1,000 MuSiQue queries over 11,656 passages, so our slice is a different, smaller set unless we sample from theirs; published numbers are listed as-is for context) and compare against HippoRAG 2's reported F1 under the same reader. At n=100 the 95% CI on F1 is roughly +/-10 points, so use bootstrap CIs and paired tests, and do not claim small gaps. Fix the random seed and commit the question ids so the slice is reproducible. MuSiQue only; 2Wiki and HotpotQA are dropped for cost.

### 6.3 HippoRAG 2 published numbers, as reported (arXiv 2502.14802, local copy in `eval papers/`)

Table 2 - QA F1, Llama-3.3-70B-Instruct reader. Structure-augmented baselines and HippoRAG 2 use Llama-3.3-70B-Instruct for graph building and NV-Embed-v2 as retriever. Dagger = HippoRAG 2 significantly beats the best NV-Embed-v2 baseline (bootstrap, p<0.05).

| Retrieval | NQ | PopQA | MuSiQue | 2Wiki | HotpotQA | LV-Eval | NarrativeQA | Avg |
|---|---|---|---|---|---|---|---|---|
| None | 54.9 | 32.5 | 26.1 | 42.8 | 47.3 | 6.0 | 12.9 | 38.4 |
| Contriever | 58.9 | 53.1 | 31.3 | 41.9 | 62.3 | 8.1 | 19.7 | 46.9 |
| BM25 | 59.0 | 49.9 | 28.8 | 51.2 | 63.4 | 5.9 | 18.3 | 47.7 |
| GTR (T5-base) | 59.9 | 56.2 | 34.6 | 52.8 | 62.8 | 7.1 | 19.9 | 50.4 |
| GTE-Qwen2-7B-Instruct | 62.0 | 56.3 | 40.9 | 60.0 | 71.0 | 7.1 | 21.3 | 54.9 |
| GritLM-7B | 61.3 | 55.8 | 44.8 | 60.6 | 73.3 | 9.8 | 23.9 | 56.1 |
| NV-Embed-v2 (7B) | 61.9 | 55.7 | 45.7 | 61.5 | 75.3 | 9.8 | 25.7 | 57.0 |
| RAPTOR | 50.7 | 56.2 | 28.9 | 52.1 | 69.5 | 5.0 | 21.4 | 48.8 |
| GraphRAG | 46.9 | 48.1 | 38.5 | 58.6 | 68.6 | 11.2 | 23.0 | 49.6 |
| LightRAG | 16.6 | 2.4 | 1.6 | 11.6 | 2.4 | 1.0 | 3.7 | 6.6 |
| HippoRAG | 55.3 | 55.9 | 35.1 | 71.8 | 63.5 | 8.4 | 16.3 | 53.1 |
| **HippoRAG 2** | 63.3 (dagger) | 56.2 | 48.6 (dagger) | 71.0 (dagger) | 75.5 | 12.9 (dagger) | 25.9 | **59.8** |

Table 3 - passage recall@5.

| Retrieval | NQ | PopQA | MuSiQue | 2Wiki | HotpotQA | Avg |
|---|---|---|---|---|---|---|
| BM25 | 56.1 | 35.7 | 43.5 | 65.3 | 74.8 | 55.1 |
| Contriever | 54.6 | 43.2 | 46.6 | 57.5 | 75.3 | 55.4 |
| GTR (T5-base) | 63.4 | 49.4 | 49.1 | 67.9 | 73.9 | 60.7 |
| GTE-Qwen2-7B-Instruct | 74.3 | 50.6 | 63.6 | 74.8 | 89.1 | 70.5 |
| GritLM-7B | 76.6 | 50.1 | 65.9 | 76.0 | 92.4 | 72.2 |
| NV-Embed-v2 (7B) | 75.4 | 51.0 | 69.7 | 76.5 | 94.5 | 73.4 |
| RAPTOR | 68.3 | 48.7 | 57.8 | 66.2 | 86.9 | 65.6 |
| HippoRAG (original paper) | - | - | 51.9 | 89.1 | 77.7 | - |
| HippoRAG (reproduced) | 44.4 | 53.8 | 53.2 | 90.4 | 77.3 | 63.8 |
| **HippoRAG 2** | 78.0 | 51.7 | 74.7 | 90.4 | 96.3 | 78.2 |

Note for our n=100 run: the rows most comparable to our systems are BM25 (our `bm25`), NV-Embed-v2 or GTR (dense naive, closest to `external`), GraphRAG, and HippoRAG/HippoRAG 2 (closest to `own`). Our embedder is a small 384-dim BGE model and our reader is a DeepSeek model, so absolute numbers will differ from these; compare orderings, not values. The PDF text says the sampled datasets are summarized in its Table 1; I did not capture how MuSiQue's 1,000 queries were sampled.

### 6.1 HippoRAG vs HippoRAG 2 (2405.14831 vs 2502.14802)

Same core idea: build a KG of phrase nodes from LLM-extracted triples, then rank with Personalized PageRank (PPR). HippoRAG 2 changes (from its abstract and sections 4.2-4.5):
1. **Dense-sparse integration:** passages become nodes in the graph, linked by "contains" edges to their phrases. HippoRAG instead ran graph search and embedding matching separately and simply aggregated their scores.
2. **Deeper contextualization:** query-to-triple matching, instead of matching only extracted query entities.
3. **Recognition memory:** retrieved triples are filtered by an LLM before seeding the graph.
4. **Online retrieval:** seeds are filtered phrase nodes plus all passage nodes, with reset probabilities weighted by a factor tuned on a dev set. Falls back to plain embedding retrieval when no triples survive.
Motivation stated in the abstract: earlier structure-augmented RAG fell below standard RAG on basic factual QA; HippoRAG 2 aims to be better on factual, sense-making and associative tasks. Result: 48.6 vs 35.1 MuSiQue F1 (same reader, section 6 table).
Relevance: OmniStream's `own` mode (seeding, 2-hop expansion, PageRank, fact fusion) is the same family, so HippoRAG 2 is the most relevant published reference.

### 6.2 Graphiti

Graphiti is the open-source engine behind Zep, described in "Zep: A Temporal Knowledge Graph Architecture for Agent Memory" (2501.13956): a temporally-aware dynamic knowledge graph for agent memory. It was not designed or evaluated on MuSiQue-style QA; the paper reports DMR (94.8% vs MemGPT 93.4%) and LongMemEval-s (about 115k-token conversations; up to 18.5% accuracy gain and 90% lower latency vs baseline), both conversation-memory benchmarks. So there are no published Graphiti MuSiQue numbers to list; Graphiti enters our comparison only as a system we run. Whether it is disadvantaged on static multi-hop QA is untested; measure indexing cost for it explicitly, since it extracts the graph with LLM calls (our audit shows Graphiti does entity/relation extraction via the LLM).

## 7. Known pitfalls to design around

- Judge position bias: swap answer order (LightRAG).
- Judge-model drift: do not compare win rates across papers.
- Same-family judge and answerer: use a different family.
- HotpotQA has spurious signals; prefer MuSiQue and 2Wiki for multi-hop.
- Graph methods can lose to reranked vanilla RAG on fact retrieval (GraphRAG-Bench). A negative result for `own` vs `external` or `bm25` is plausible and should be reported honestly.
- Unverified: whether length bias affects LLM-judge win rates (no surveyed paper discussed it). Control for answer length anyway.

## 8. Open decisions

Decided: naive = `external`; public benchmark = MuSiQue, n=100; global/sensemaking out of scope.
Still open:
1. Budget for the full run and a judge from a second model family.
2. (Decided) Slice: 100 MuSiQue queries, indexing only those queries' own paragraphs (supporting + distractors) as one shared corpus. This is cheaper and an easier retrieval problem than HippoRAG 2's 1,000 queries over 11,656 passages, so published numbers are context only, not a like-for-like target. Fixed seed, commit the question ids. Published numbers are listed as-is in section 6.
3. (Decided) MuSiQue is loaded directly into each retriever's index, bypassing bubbles and routing, so routing is not a confound and `external` is treated fairly. Paragraphs of the 100 sampled questions plus distractors form the corpus; use one shared corpus for all five systems.

## 8b. `own` vs HippoRAG 2 (read from `retrieval/own_algorithm/`)

| Step | HippoRAG 2 | OmniStream `own` |
|---|---|---|
| Seeds | Query-to-triple embedding match, LLM triple filter, all passage nodes as extra seeds | Three non-LLM sources: entity-embedding match (cosine >= 0.5, top 5), fuzzy name match against the question (>= 90), and top-10 fact-embedding match. Max 10 seeds, half the budget reserved for fact-derived seeds. Only typed named entities (person, organization, location, product, event, financial instrument, publication) count as name seeds; generic concepts are excluded (`seeding.py:26-41`) |
| LLM at query time | Yes (triple filter) | None in retrieval |
| Graph | Phrase + passage nodes over the whole corpus | Graphiti entities/facts, `store.expand()` of the seeds into a bounded subgraph, with SAME_AS links |
| Ranking | Personalized PageRank on the full graph, restart at phrase and passage nodes | Undirected weighted PPR (damping 0.85) on the expanded subgraph only, restart at seeds only (`pagerank.py`, `pipeline.py`) |
| Output | Top passages | Top-20 facts. Score = fact-similarity x endpoint PageRank, fused by weighted RRF (k=60, weights 2:1:1) with recency (per-bubble half-life, news 3 days, finance 30, research 365) and source-confidence signals; constant signals are dropped (`fact_fusion.py`) |
| Time | None | Recency decay, fact versions collapsed to representatives |

Consequences for the MuSiQue run:
1. **Facts, not passages.** Recall@5 and F1 need a map from retrieved facts back to source paragraphs. `Fact`'s docstring says it carries provenance to the original item; the exact field was not checked. Define the mapping before running (a paragraph is retrieved if any retrieved fact points to it) and report it.
2. **Named-entity seeding.** MuSiQue hops often go through descriptions ("the performer of X") and generic concepts that `is_named_entity` filters out of name seeds; fact-embedding seeds partly compensate. Expect weaker multi-hop recall than HippoRAG 2's concept-level seeding, and report it as a diagnostic rather than a bug.
3. **Recency/confidence must be neutral.** MuSiQue paragraphs have no dates or source credibility. Ingest all with the same timestamp and credibility so those RRF signals drop out (`drop_constant`); otherwise recency noise will distort ranking.
4. **No passage-node bridge.** HippoRAG 2's main gain over HippoRAG is passage nodes plus LLM triple filtering. `own` has neither; an ablation adding either is a candidate experiment, not part of this plan's headline.

## 8c. Cost estimate (MuSiQue n=100, five systems)

**Basis.** Token counts per configuration come from your measured eval-v2 run (60 questions, `docs/eval/eval-v2-20261113T123043918544Z.md`), scaled by 100/60, so they assume MuSiQue answers use similar context sizes. Prices (per 1M tokens): HY4 Flash list $0.07 in / $0.281 out; second HY4 column $0.035 / $0.1405 (assumed to be a discounted tier); DeepSeek $0.036 in / $0.50 out. The judge is priced at DeepSeek rates in all scenarios. `bm25` is assumed to cost the same as `external`. Cache discounts are ignored.

Per system, 100 questions, answer + judge (USD):

| System | HY4 list | HY4 col 2 | DeepSeek |
|---|---|---|---|
| external | 0.013 | 0.012 | 0.013 |
| bm25 | 0.013 | 0.012 | 0.013 |
| graphiti | 0.050 | 0.034 | 0.047 |
| own | 0.045 | 0.031 | 0.042 |
| own + subagents | 0.865 | 0.451 | 0.526 |
| **5 systems, one run** | **0.99** | **0.54** | **0.64** |
| classic (added, alone) | 0.043 | 0.032 | 0.041 |
| **6 systems, one run** | **1.03** | **0.57** | **0.68** |

Own+subagents is about 11.1M prompt tokens per 100 questions (60 questions measured 6.67M), roughly 85% of the answer-side spend; subagents multiply search calls.

Other items (HY4 list / col 2 / DeepSeek):
- Pairwise judge (100 q x 2 orders x 4 pairs, about 1,300 prompt + 200 completion tokens each, assumed): $0.12 at DeepSeek judge rates.
- **Ingestion (NOT MEASURED; the probe was blocked).** About 2,000 paragraphs (100 questions x about 20 each). Assumption: Graphiti makes about 6 LLM calls per episode, 8k-25k prompt and 0.8k-2.5k completion tokens per episode. Range $1.57-$4.91 (HY4 list), $0.78-$2.45 (col 2), $1.38-$4.30 (DeepSeek); mid case $2.94 / $1.47 / $2.58. One shared graph serves `graphiti`, `own` and `own+subagents`; `external` and `bm25` use local embeddings (no LLM cost).

Totals, mid ingestion, 5 systems + pairwise:

| Scenario | One run | Three runs of answering (variance), one ingestion |
|---|---|---|
| HY4 list | about $4.05 | about $6.26 |
| HY4 col 2 | about $2.13 | about $3.44 |
| DeepSeek | about $3.34 | about $4.86 |

Cost caveats: ingestion is the least certain term (it could be several times higher if MuSiQue paragraphs trigger more extraction calls or retries); the eval-v2 token counts include only the answer and judge calls of that run; the earlier $5 OpenRouter cap that cut off eval-v2 would just cover a three-run plan at DeepSeek rates but not with the high ingestion case; use the first 10 questions as a cost probe before the full run, which also measures real ingestion cost per paragraph.

## 9. Provenance and limits

Literature claims were read from the paper text via arXiv tools; garbled table text was re-read from the PDFs in `eval papers/`. Repo facts come from a read-only code audit with line references accurate to about +/-2. Spot-check before citing in the capstone report.
