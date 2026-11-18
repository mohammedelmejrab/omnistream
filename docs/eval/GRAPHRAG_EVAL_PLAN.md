# OmniStream GraphRAG Evaluation Plan

Status: PLAN. Date: 2026-11-16. Revised 2026-11-17: HippoRAG 2 references replaced with HippoRAG 1.
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
| ref | Published numbers (HippoRAG, GraphRAG-Bench) | n/a | Context only, not a like-for-like comparison (see section 6). |

DECIDED: the external baselines are naive RAG (`external`) and BM25 only. `classic` (alone, without subagents) is added as a sixth, internal diagnostic system; `classic+subagents` is not run. Published systems (HippoRAG and others) appear only as reference numbers in section 6, never as systems we run.

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
| HippoRAG 1 | 2405.14831 | Gold-passage recall and gold-answer QA on 1,000-question dev sets; candidate corpus = supporting + distractor passages | Passage Recall@2/@5 (Table 2), EM and F1 (Table 4) on MuSiQue, 2Wiki, HotpotQA |
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
12. Indexing cost: unblock the probe (`docs/realdata/real-v2-ingestion-cost.md`), instrument `eval/snapshot.py:155` (`SnapshotBuilder`) for tokens, time, and dollars per 1k documents; also incremental-update cost (LightRAG reports this; HippoRAG 1 reports offline indexing cost only, App. G Table 18, and no incremental-update cost).
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

Only figures verified in the paper are listed. HippoRAG 1 table values were read from the rendered PDF pages (Section 6.3), not from extracted text; any cell that could not be read is marked TODO.

| Source | Setting | Verified figure |
|---|---|---|
| HippoRAG 1 (2405.14831) | Table 2 (p.6), MuSiQue passage recall R@2 / R@5, single-step | BM25 32.3 / 41.2; Contriever 34.8 / 46.6; GTR 37.4 / 49.1; ColBERTv2 37.9 / 49.2; **HippoRAG (ColBERTv2) 40.9 / 51.9**; HippoRAG (Contriever) 41.0 / 52.1 |
| HippoRAG 1 | Table 4 (p.7), MuSiQue QA EM / F1, top-5 passages as context | None 12.5 / 24.1; ColBERTv2 15.5 / 26.4; **HippoRAG (ColBERTv2) 19.2 / 29.8**; IRCoT (ColBERTv2) 19.1 / 30.5; IRCoT + HippoRAG (ColBERTv2) 21.9 / 33.3 |
| HippoRAG 1 | Table 3 (p.6), MuSiQue multi-step recall R@2 / R@5 | IRCoT + ColBERTv2 41.7 / 53.7; IRCoT + HippoRAG (ColBERTv2) 45.3 / 57.6 |
| HippoRAG 1 | Averages over MuSiQue, 2Wiki, HotpotQA | Table 2 R@5: ColBERTv2 65.6, HippoRAG (ColBERTv2) 72.9. Table 4 F1: ColBERTv2 42.5, HippoRAG (ColBERTv2) 48.1 |
| HippoRAG 1 | Setup (Sec. 3.1, 3.4, App. H, Table 1) | Default LLM GPT-3.5-turbo-1106 (temperature 0) for OpenIE and query NER; retriever Contriever or ColBERTv2; synonymy threshold 0.8 and PPR damping 0.5, tuned on 100 MuSiQue training examples. Dev sets of 1,000 questions per dataset, extracted "as done in previous work" (no further sampling detail). Corpus = all candidate passages (supporting + distractor), following IRCoT: MuSiQue 11,656 passages. QA reader: top-5 passages, 1-shot CoT; the QA LLM is not named separately. |
| HippoRAG 1 | Cost (App. G, Tables 17-18, p.28) | Online per 1,000 queries: API $ ColBERTv2 0, IRCoT 1-3, HippoRAG 0.1; time 1 / 20-40 / 3 min. Offline per 10,000 passages (GPT-3.5-turbo-1106): API $ 0 / 0 / 15; time 7 / 7 / 60 min |
| HippoRAG (2405.14831) | Single-step vs IRCoT | Intro (p.2): "10 to 30 times cheaper and 6 to 13 times faster" than IRCoT (abstract says 10-20x); Table 17 gives $0.1 vs $1-3 per 1,000 queries |
| GraphRAG-Bench (2506.05690) | Table 5, GPT-4o-mini | Vanilla RAG with rerank 58.8 vs 49.3 ACC for a graph method on one fact-retrieval dataset |
| GraphRAG (2404.16130) | Podcast corpus | Indexing took 281 min |

Comparability warning: those papers use Wikipedia multi-hop QA (MuSiQue, 2Wiki, HotpotQA) with different readers, retrievers, and judges. OmniStream's corpus is streaming news-style with changing facts. Do not place paper numbers in the same table as OmniStream numbers without labelling them "reference, different setting". For a like-for-like check, run `external`, `bm25`, `graphiti`, `own` and `own+subagents` on a MuSiQue slice of n=100 (cost limit; HippoRAG 1 uses 1,000 MuSiQue dev questions with all candidate passages, 11,656 passages in total (Table 1), and says only that questions were extracted "as done in previous work" (Sec. 3.1), so our slice is a different, smaller set unless we sample from theirs; published numbers are listed as-is for context) and compare against HippoRAG 1's reported F1 (Table 4) under a matched reader. At n=100 the 95% CI on F1 is roughly +/-10 points, so use bootstrap CIs and paired tests, and do not claim small gaps. Fix the random seed and commit the question ids so the slice is reproducible. MuSiQue only; 2Wiki and HotpotQA are dropped for cost.

### 6.3 HippoRAG 1 published numbers, as reported (arXiv 2405.14831, local copy in `eval papers/`)

Values copied from the rendered PDF pages (text extraction did not return the tables). Each dataset-average column reconciles with its per-dataset columns. Rows not copied are named as omitted.

Table 1 (p.5) - corpora and extracted KG statistics, 1,000-question dev sets.

| Count | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|
| Passages (P) | 11,656 | 6,119 | 9,221 |
| Unique nodes (N) | 91,729 | 42,694 | 82,157 |
| Unique edges (E) | 21,714 | 7,867 | 17,523 |
| Unique triples | 107,448 | 50,671 | 98,709 |

Table 2 (p.6) - single-step passage recall, R@2 / R@5. Omitted for length: RAPTOR (ColBERTv2), Proposition, Proposition (ColBERTv2).

| Retrieval | MuSiQue R@2 | MuSiQue R@5 | 2Wiki R@2 | 2Wiki R@5 | HotpotQA R@2 | HotpotQA R@5 | Avg R@2 | Avg R@5 |
|---|---|---|---|---|---|---|---|---|
| BM25 | 32.3 | 41.2 | 51.8 | 61.9 | 55.4 | 72.2 | 46.5 | 58.4 |
| Contriever | 34.8 | 46.6 | 46.6 | 57.5 | 57.2 | 75.5 | 46.2 | 59.9 |
| GTR (T5-base) | 37.4 | 49.1 | 60.2 | 67.9 | 59.4 | 73.3 | 52.3 | 63.4 |
| ColBERTv2 | 37.9 | 49.2 | 59.2 | 68.2 | 64.7 | 79.3 | 53.9 | 65.6 |
| RAPTOR | 35.7 | 45.3 | 46.3 | 53.8 | 58.1 | 71.2 | 46.7 | 56.8 |
| **HippoRAG (Contriever)** | 41.0 | 52.1 | 71.5 | 89.5 | 59.0 | 76.2 | 57.2 | 72.6 |
| **HippoRAG (ColBERTv2)** | 40.9 | 51.9 | 70.7 | 89.1 | 60.5 | 77.7 | 57.4 | 72.9 |

Table 3 (p.6) - multi-step (IRCoT) passage recall, R@2 / R@5.

| Retrieval | MuSiQue R@2 | MuSiQue R@5 | 2Wiki R@2 | 2Wiki R@5 | HotpotQA R@2 | HotpotQA R@5 | Avg R@2 | Avg R@5 |
|---|---|---|---|---|---|---|---|---|
| IRCoT + BM25 (default) | 34.2 | 44.7 | 61.2 | 75.6 | 65.6 | 79.0 | 53.7 | 66.4 |
| IRCoT + Contriever | 39.1 | 52.2 | 51.6 | 63.8 | 65.9 | 81.6 | 52.2 | 65.9 |
| IRCoT + ColBERTv2 | 41.7 | 53.7 | 64.1 | 74.4 | 67.9 | 82.0 | 57.9 | 70.0 |
| IRCoT + HippoRAG (Contriever) | 43.9 | 56.6 | 75.3 | 93.4 | 65.8 | 82.3 | 61.7 | 77.4 |
| **IRCoT + HippoRAG (ColBERTv2)** | 45.3 | 57.6 | 75.8 | 93.9 | 67.0 | 83.0 | 62.7 | 78.2 |

Table 4 (p.7) - QA EM / F1, top-5 retrieved passages as context.

| Retriever | MuSiQue EM | MuSiQue F1 | 2Wiki EM | 2Wiki F1 | HotpotQA EM | HotpotQA F1 | Avg EM | Avg F1 |
|---|---|---|---|---|---|---|---|---|
| None | 12.5 | 24.1 | 31.0 | 39.6 | 30.4 | 42.8 | 24.6 | 35.5 |
| ColBERTv2 | 15.5 | 26.4 | 33.4 | 43.3 | 43.4 | 57.9 | 30.8 | 42.5 |
| **HippoRAG (ColBERTv2)** | 19.2 | 29.8 | 46.6 | 59.5 | 41.8 | 55.0 | 35.9 | 48.1 |
| IRCoT (ColBERTv2) | 19.1 | 30.5 | 35.4 | 45.1 | 45.5 | 58.4 | 33.3 | 44.7 |
| IRCoT + HippoRAG (ColBERTv2) | 21.9 | 33.3 | 47.7 | 62.7 | 45.7 | 59.2 | 38.4 | 51.7 |

Tables 17-18 (App. G, p.28) - cost. Online: 1,000 queries, GPT-3.5 Turbo. Offline: 10,000 passages, GPT-3.5 Turbo-1106.

| Measure | ColBERTv2 | IRCoT | HippoRAG |
|---|---|---|---|
| Online API cost ($), Table 17 | 0 | 1-3 | 0.1 |
| Online time (min), Table 17 | 1 | 20-40 | 3 |
| Offline API cost ($), Table 18 | 0 | 0 | 15 |
| Offline time (min), Table 18 | 7 | 7 | 60 |

Note for our n=100 run: the rows most comparable to our systems are BM25 (our `bm25`), Contriever or ColBERTv2 single-step (dense naive, closest to `external`), and HippoRAG (Contriever or ColBERTv2, closest to `own`, same PPR family). Our embedder is a small 384-dim BGE model and our reader is a DeepSeek model, so absolute numbers will differ from these; compare orderings, not values. The paper says only that it extracts 1,000 questions from each validation set "as done in previous work" (Sec. 3.1). It does not state how MuSiQue's questions were sampled, so that is not captured here.

### 6.1 HippoRAG 1 mechanism (2405.14831, Sec. 2.3, 3.4, App. F.2)

Offline indexing: an instruction-tuned LLM (GPT-3.5-turbo-1106 by default) extracts named entities from each passage, then runs OpenIE with those entities in the prompt to get triples. The triples form one open KG over the corpus: noun-phrase nodes N and relation edges E. A retrieval encoder (Contriever or ColBERTv2) adds synonymy edges E' between noun-phrase nodes whose embedding cosine exceeds a threshold tau (0.8). A matrix P counts how many times each node appears in each passage.

Online retrieval: the LLM extracts named entities from the query. Each query entity is linked to its most similar KG node (the query nodes). Personalized PageRank runs over the whole KG, restarting only at the query nodes with equal probability, and damping 0.5. Before PPR, each query node's probability is multiplied by its node specificity 1/|P_i|. The resulting node probabilities are multiplied by P to give a passage score, and passages are ranked by it.

Dense retrieval: it enters through entity linking and the synonymy edges, not as score fusion in the main method. The paper's optional "Uncertainty Ensemble" (App. F.2, Tables 13-14) averages HippoRAG and dense passage scores, both normalized to 0-1, only when the query-to-KG entity similarity is below a threshold.

Relevance: OmniStream's `own` mode (seeding, 2-hop expansion, PageRank, fact fusion) is the same family (PPR over a knowledge graph), so HippoRAG 1 is the reference for it.

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
2. (Decided) Slice: 100 MuSiQue queries, indexing only those queries' own paragraphs (supporting + distractors) as one shared corpus. This is cheaper and an easier retrieval problem than HippoRAG 1's setup (1,000 dev questions per dataset with all their candidate passages; 11,656 passages for MuSiQue, Table 1), so published numbers are context only, not a like-for-like target. Fixed seed, commit the question ids. Published numbers are listed as-is in section 6.
3. (Decided) MuSiQue is loaded directly into each retriever's index, bypassing bubbles and routing, so routing is not a confound and `external` is treated fairly. Paragraphs of the 100 sampled questions plus distractors form the corpus; use one shared corpus for all five systems.

## 8b. `own` vs HippoRAG 1 (read from `retrieval/own_algorithm/`)

| Step | HippoRAG 1 (2405.14831) | OmniStream `own` |
|---|---|---|
| Seeds | LLM NER on the query (1-shot); each query entity linked to its most similar KG node by retrieval-encoder cosine. No passage seeds, no LLM triple filter | Three non-LLM sources: entity-embedding match (cosine >= 0.5, top 5), fuzzy name match against the question (>= 90), and top-10 fact-embedding match. Max 10 seeds, half the budget reserved for fact-derived seeds. Only typed named entities (person, organization, location, product, event, financial instrument, publication) count as name seeds; generic concepts are excluded (`seeding.py:26-41`) |
| LLM at query time | Yes, query NER only (App. I, Figure 8); no triple filtering | None in retrieval |
| Graph | Noun-phrase nodes and OpenIE relation edges over the whole corpus, plus synonymy edges (tau 0.8). No passage nodes; passages attach through matrix P | Graphiti entities/facts, `store.expand()` of the seeds into a bounded subgraph, with SAME_AS links |
| Ranking | Personalized PageRank on the full graph, damping 0.5, restart at the query nodes; node specificity 1/\|P_i\| applied before PPR; passage score = P x node probability | Undirected weighted PPR (damping 0.85) on the expanded subgraph only, restart at seeds only (`pagerank.py`, `pipeline.py`) |
| Output | Passages ranked by passage score (top-5 used as QA context) | Top-20 facts. Score = fact-similarity x endpoint PageRank, fused by weighted RRF (k=60, weights 2:1:1) with recency (per-bubble half-life, news 3 days, finance 30, research 365) and source-confidence signals; constant signals are dropped (`fact_fusion.py`) |
| Time | Not addressed in the paper | Recency decay, fact versions collapsed to representatives |

Consequences for the MuSiQue run:
1. **Facts, not passages.** Recall@5 and F1 need a map from retrieved facts back to source paragraphs. `Fact`'s docstring says it carries provenance to the original item; the exact field was not checked. Define the mapping before running (a paragraph is retrieved if any retrieved fact points to it) and report it.
2. **Named-entity seeding.** MuSiQue hops often go through descriptions ("the performer of X") and generic concepts that `is_named_entity` filters out of name seeds; fact-embedding seeds partly compensate. HippoRAG 1 also seeds from LLM-extracted query entities, but its nodes are OpenIE noun phrases, so concept phrases can match directly. Its own error analysis puts 48% of MuSiQue errors on NER limits (Table 11). Expect weaker multi-hop recall than HippoRAG 1's phrase-node seeding, and report it as a diagnostic rather than a bug.
3. **Recency/confidence must be neutral.** MuSiQue paragraphs have no dates or source credibility. Ingest all with the same timestamp and credibility so those RRF signals drop out (`drop_constant`); otherwise recency noise will distort ranking.
4. **Closer to HippoRAG 1 on structure.** HippoRAG 1 also has no passage nodes and no query-time triple filtering, as `own` does. The remaining differences (fact nodes vs phrase nodes; restart at seeds on an expanded subgraph vs all query nodes on the full graph; recency and confidence fusion) are candidate ablations, not part of this plan's headline.

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

## 8d. Implemented bench tooling (`omni eval bench-ingest` / `bench-qa`)

**Fact -> item -> passage mapping (definition used by Recall@k).** Every benchmark passage is one item: item text is `title + "\n" + text`, item url is `bench://<dataset>/<passage_id>`, and the snapshot's `bench_manifest.json` records `passage_id -> {runtime_id, status, usage}`. A retrieved fact, chunk or LlamaIndex source node carries the item id (`fact.item_id` / `fact.item_ids` / chunk `item_id` / source-node `item_id` metadata); mapping those ids back through the manifest yields the passage ranking, deduplicated in first-retrieval order (the harness's existing `evidence_ids` order). A paragraph therefore counts as retrieved if ANY retrieved fact or chunk points to the item that stores it. `closed_book` has no retrieval; its recall fields are `null`, never 0.

**Ingestion (`omni eval bench-ingest --dataset musique --n 100 --seed 0 --corpus slice [--limit-passages N] [--snapshot NAME]`).** All slice passages go into ONE dedicated bubble `Bench` with `group_id = snapshot name` (default `bench-musique-n100-s0`), assigned directly through intake's `bubble_ids_override`, so the LLM router is bypassed (`route_confidence` 1.0). Every passage gets the same fixed `published_at` (2026-01-01T00:00:00Z) and credibility (0.8), making the recency/confidence RRF signals constant so `drop_constant` removes them. Resumable per passage (already-written passages are skipped; an interrupted write has no status and is re-run through intake dedup), with per-passage usage/cost in the manifest and a running cost total in the log. `--limit-passages N` ingests the next N pending passages so a 30-passage cost probe precedes the full run in the same snapshot. `--dry-run` reports counts with no LLM calls. The hourly intake cap is lifted (`max_items_per_hour` 1e6) because this is a one-shot bulk load.

**QA (`omni eval bench-qa --dataset musique --n 100 --seed 0 --snapshot NAME --rows closed_book,external,classic,graphiti,own,own+subagents [--limit-questions N]`).** All configurations answer with `answer_style="short"`, pinned to the single Bench bubble (one bubble in the catalog; routing cannot mis-select). `external` (LlamaIndex) gains an `answer_style` parameter mirroring the same short-answer prompt + extraction while keeping source-node provenance; its default behaviour is unchanged. `closed_book` is the floor row: the same model, same short-answer prompt, no context. Scoring per (question, configuration) cell: EM and token F1 against the gold answer aliases (SQuAD standard), passage Recall@2/5/10 via the mapping above, latency, and per-question LLM usage/cost. Provider failures mark the cell UNMEASURED (never 0); more than 10% unmeasured flags the configuration INVALID. Cells are resumable per (question, configuration) like the main harness: `--resume` picks up the latest run directory and retries unmeasured cells. Reports go to `docs/eval/bench/qa-<dataset>-n<N>-s<seed>-<timestamp>.{json,md}` with bootstrap 95% CIs and the HippoRAG 1 Table 4 block as published reference (different setting, context only).

## 9. Provenance and limits

Literature claims were read from the paper text via arXiv tools; garbled table text was re-read from the PDFs in `eval papers/`. Repo facts come from a read-only code audit with line references accurate to about +/-2. Spot-check before citing in the capstone report.
