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

## End-to-end QA: full corpora, 200 questions per dataset (test run)

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

