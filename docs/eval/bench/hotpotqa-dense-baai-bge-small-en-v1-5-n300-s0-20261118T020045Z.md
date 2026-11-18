# Bench retrieval check: hotpotqa / dense

300 questions, 9811 corpus passages, 0 unmatched gold docs.
Retriever: dense (BAAI/bge-small-en-v1.5); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.7100 | [0.6750, 0.7433] |
| recall_at_5 | 0.8367 | [0.8067, 0.8650] |
| recall_at_10 | 0.9100 | [0.8850, 0.9333] |
| recall_at_20 | 0.9467 | [0.9283, 0.9633] |
| ndcg_at_10 | 0.8467 | [0.8223, 0.8700] |
| mrr | 0.9127 | [0.8861, 0.9374] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| bridge | 241 | 0.6515 | 0.7967 | 0.8880 | 0.9336 | 0.8112 | 0.8913 |
| comparison | 59 | 0.9492 | 1.0000 | 1.0000 | 1.0000 | 0.9918 | 1.0000 |

Timing: passage encoding 1697.2s, queries 9.7s, wall 1726.4s.

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
