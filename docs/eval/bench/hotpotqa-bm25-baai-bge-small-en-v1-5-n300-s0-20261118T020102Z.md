# Bench retrieval check: hotpotqa / bm25

300 questions, 9811 corpus passages, 0 unmatched gold docs.
Retriever: bm25; corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.5633 | [0.5283, 0.5983] |
| recall_at_5 | 0.7333 | [0.7000, 0.7667] |
| recall_at_10 | 0.8667 | [0.8400, 0.8933] |
| recall_at_20 | 0.9200 | [0.8983, 0.9400] |
| ndcg_at_10 | 0.7524 | [0.7251, 0.7791] |
| mrr | 0.8356 | [0.8023, 0.8675] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| bridge | 241 | 0.5622 | 0.7158 | 0.8485 | 0.9046 | 0.7401 | 0.8292 |
| comparison | 59 | 0.5678 | 0.8051 | 0.9407 | 0.9831 | 0.8024 | 0.8617 |

Timing: passage encoding 0.0s, queries 10.8s, wall 14.1s.

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
