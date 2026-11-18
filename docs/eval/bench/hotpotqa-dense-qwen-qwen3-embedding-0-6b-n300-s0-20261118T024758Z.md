# Bench retrieval check: hotpotqa / dense

300 questions, 9811 corpus passages, 0 unmatched gold docs.
Retriever: dense (Qwen/Qwen3-Embedding-0.6B); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.6483 | [0.6133, 0.6833] |
| recall_at_5 | 0.7833 | [0.7517, 0.8150] |
| recall_at_10 | 0.8550 | [0.8267, 0.8817] |
| recall_at_20 | 0.9017 | [0.8783, 0.9250] |
| ndcg_at_10 | 0.7983 | [0.7716, 0.8235] |
| mrr | 0.9011 | [0.8732, 0.9268] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| bridge | 241 | 0.5871 | 0.7303 | 0.8195 | 0.8776 | 0.7534 | 0.8769 |
| comparison | 59 | 0.8983 | 1.0000 | 1.0000 | 1.0000 | 0.9815 | 1.0000 |

Timing: passage encoding 252.7s, queries 15.1s, wall 281.7s.

## Reference (published, different setting)

HippoRAG 1 Table 2 single-step passage Recall@2 / Recall@5 for this dataset,
with their retrievers and corpus settings; not directly comparable to our numbers above:

| Retriever | R@2 | R@5 |
|---|---|---|
| BM25 | 55.4 | 72.2 |
| Contriever | 57.2 | 75.5 |
| GTR | 59.4 | 73.3 |
| ColBERTv2 | 64.7 | 79.3 |
| HippoRAG (ColBERTv2) | 60.5 | 77.7 |
