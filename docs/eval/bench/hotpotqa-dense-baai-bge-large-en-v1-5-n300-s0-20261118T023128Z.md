# Bench retrieval check: hotpotqa / dense

300 questions, 9811 corpus passages, 0 unmatched gold docs.
Retriever: dense (BAAI/bge-large-en-v1.5); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.7517 | [0.7183, 0.7850] |
| recall_at_5 | 0.8767 | [0.8500, 0.9033] |
| recall_at_10 | 0.9250 | [0.9033, 0.9450] |
| recall_at_20 | 0.9500 | [0.9317, 0.9667] |
| ndcg_at_10 | 0.8739 | [0.8517, 0.8954] |
| mrr | 0.9376 | [0.9152, 0.9580] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| bridge | 241 | 0.6971 | 0.8465 | 0.9066 | 0.9378 | 0.8440 | 0.9223 |
| comparison | 59 | 0.9746 | 1.0000 | 1.0000 | 1.0000 | 0.9959 | 1.0000 |

Timing: passage encoding 106.0s, queries 11.5s, wall 138.3s.

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
