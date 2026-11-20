# OmniStreamRAG results

Progress so far on the multi-hop QA benchmarks (MuSiQue, 2WikiMultiHopQA, HotpotQA), compared with
the published HippoRAG numbers.

Full logs: [`docs/IMPROVEMENT_LOG.md`](IMPROVEMENT_LOG.md); raw reports: [`docs/eval/bench/`](eval/bench/).

## Retrieval check (HippoRAG protocol, full corpora, 300 questions, passage Recall@2 / @5)

| Retriever | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|
| BM25 (ours) | 33.8 / 44.7 | 55.5 / 63.7 | 56.3 / 73.3 |
| BM25 (HippoRAG 1 paper) | 32.3 / 41.2 | 51.8 / 61.9 | 55.4 / 72.2 |
| HippoRAG 1, ColBERTv2 (paper) | 40.9 / 51.9 | **70.7 / 89.1** | 60.5 / 77.7 |
| **bge-large-en-v1.5 (ours, local GPU)** | **41.2 / 55.7** | 64.8 / 71.3 | **75.2 / 87.7** |

Our BM25 reproduces the published BM25 within about 3 points, which validates the harness.

## Final results vs HippoRAG 1 (full corpora, 200 test questions per dataset)

OpenIE graph over the full released corpus (MuSiQue 11,656, 2Wiki 6,119, HotpotQA 9,811 passages),
200 questions per dataset (seed 0; MuSiQue development questions excluded). Answering model
`deepseek/deepseek-v4.1-flash-1017`. All settings were chosen on a separate 100-question
development set per dataset (no shared questions); the test set was run once with the chosen
setting. ✅ = ahead of HippoRAG 1 (ColBERTv2, paper), ❌ = behind.

**Table 2: single-step retrieval, R@2 / R@5**

| | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|
| Own retrieval | **49.1 / 64.1** ✅ | **72.0 / 90.4** ✅ | **69.0 / 90.0** ✅ |
| HippoRAG 1 | 40.9 / 51.9 | 70.7 / 89.1 | 60.5 / 77.7 |

**Table 3: multi-step retrieval, R@2 / R@5**

| | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|
| IRCoT + own retrieval | **54.2 / 73.2** ✅ | **80.8 / 97.9** ✅ | **75.0 / 94.8** ✅ |
| IRCoT + HippoRAG 1 | 45.3 / 57.6 | 75.8 / 93.9 | 67.0 / 83.0 |

**Table 4: QA, EM / F1**

| | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|
| Closed book (no retrieval) | 11.0 / 22.8 | 38.5 / 42.2 | 33.0 / 43.0 |
| External (LlamaIndex) | 19.0 / 25.3 | 41.5 / 48.0 | 50.5 / 62.5 |
| **Own retrieval (single-step)** | **36.0 / 44.2** ✅ | **60.5 / 68.1** ✅ | **58.5 / 74.1** ✅ |
| HippoRAG 1 | 19.2 / 29.8 | 46.6 / 59.5 | 41.8 / 55.0 |
| **Own retrieval + subagents (multi-step)** | **38.0 / 49.0** ✅ | **75.0 / 82.7** ✅ | **65.0 / 79.8** ✅ |
| IRCoT + HippoRAG 1 | 21.9 / 33.3 | 47.7 / 62.7 | 45.7 / 59.2 |

**All-recall (all gold passages retrieved), AR@2 / AR@5, single-step**

| | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|
| Own retrieval | **18.0 / 38.0** ✅ | 45.5 ✅ / 72.0 ❌ | **42.5 / 81.0** ✅ |
| HippoRAG 1 | 10.2 / 22.4 | 45.4 / 75.7 | 33.8 / 57.9 |
| IRCoT + own retrieval (multi-step) | 25.5 / 49.5 | 63.5 / 92.0 | 54.5 / 90.0 |

One number is behind: single-step 2Wiki AR@5 (72.0 vs 75.7). 2Wiki AR@2 and single-step 2Wiki
R@2 / R@5 are within noise. Caveats: the paper uses a different reader and 1,000 questions; at n=200
the 95% bootstrap intervals are about +-6-7 points for EM/F1 and +-3-4 for recall.

Against HippoRAG 2 (paper: F1 about 48.6 / 71.0 / 75.5, R@5 74.7 / 90.4 / 96.3): own + subagents F1
is ahead on all three; single-step F1 and R@5 are behind or tied; IRCoT + own R@5 is ahead on 2Wiki
only.

## Earlier test run (before the final setting)


OpenIE graph over the full released corpus (MuSiQue 11,656, 2Wiki 6,119, HotpotQA 9,811 passages),
200 questions per dataset (seed 0; the MuSiQue development questions are excluded). Short answers,
EM / token F1 / passage Recall@5 (%), answering model `deepseek/deepseek-v4.1-flash-1017`.
Own retrieval uses passage seeding, the local reranker and HippoRAG 2-style passage nodes.

| Configuration | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|
| Closed book (no retrieval) | 7.5 / 12.8 / - | 30.5 / 33.6 / - | 29.5 / 38.2 / - |
| External (LlamaIndex) | 14.5 / 16.7 / 40.9 | 35.0 / 37.6 / 64.4 | 44.0 / 54.5 / 74.0 |
| Classic RAG | not run | 49.5 / 53.7 / 69.9 | not run |
| Own retrieval | 23.0 / 27.0 / 56.3 | 50.5 / 55.0 / 86.2 | 48.0 / 60.0 / 80.8 |
| **Own retrieval + subagents** | **37.0 / 47.3** / 45.9 | **71.5 / 77.1** / 71.9 | **62.0 / 75.6** / 71.2 |
| HippoRAG 1 (paper, EM / F1) | 19.2 / 29.8 | 46.6 / 59.5 | 41.8 / 55.0 |
| IRCoT + HippoRAG (paper, EM / F1) | 21.9 / 33.3 | 47.7 / 62.7 | 45.7 / 59.2 |

Own retrieval + subagents beats the published HippoRAG 1 QA by 17-20 F1 points on all three
datasets. Caveats: the papers use different answering models and 1,000 questions; at n=200 the 95%
bootstrap intervals are about +-6-7 points. Reports: [`docs/eval/bench/`](eval/bench/).

## End-to-end QA: MuSiQue, 50 questions (seed 0), 928-passage slice corpus (development set)

Short answers, SQuAD-normalised EM / token F1, answering model `deepseek/deepseek-v4.1-flash-1017`.

| Configuration | EM | F1 | Recall@2 | Recall@10 | Cost ($) |
|---|---|---|---|---|---|
| Closed book (no retrieval) | 10.0 | 13.1 | - | - | 0.001 |
| External (LlamaIndex) | 20.0 | 24.4 | 45.5 | 45.5 | 0.003 |
| Classic RAG | 36.0 | 44.0 | 45.5 | 78.8 | 0.017 |
| Graphiti | 34.0 | 40.0 | 43.7 | 72.3 | 0.025 |
| Own retrieval | 34.0 | 38.6 | **52.5** | 77.5 | 0.024 |
| **Own retrieval + subagents** | **48.0** | **60.2** | 45.3 | **83.2** | 0.300 |

95% bootstrap intervals are about +-13 EM points at n=50. Published HippoRAG 1 MuSiQue QA (EM / F1:
HippoRAG 19.2 / 29.8, IRCoT + HippoRAG 21.9 / 33.3) uses the full 11,656-passage corpus and 1,000
questions, so it is context, not a like-for-like comparison.

