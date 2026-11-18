# Bench retrieval check: musique / dense

300 questions, 11656 corpus passages, 0 unmatched gold docs.
Retriever: dense (BAAI/bge-small-en-v1.5); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.3658 | [0.3358, 0.3972] |
| recall_at_5 | 0.5072 | [0.4728, 0.5419] |
| recall_at_10 | 0.5811 | [0.5456, 0.6156] |
| recall_at_20 | 0.6611 | [0.6283, 0.6939] |
| ndcg_at_10 | 0.5460 | [0.5140, 0.5778] |
| mrr | 0.7422 | [0.7013, 0.7823] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| 3hop1 | 72 | 0.2778 | 0.4769 | 0.5972 | 0.6667 | 0.5231 | 0.6839 |
| 2hop | 154 | 0.4675 | 0.6071 | 0.6753 | 0.7532 | 0.6284 | 0.7913 |
| 4hop2 | 9 | 0.1667 | 0.2500 | 0.2500 | 0.4167 | 0.3144 | 0.7101 |
| 4hop1 | 32 | 0.2031 | 0.2422 | 0.2578 | 0.3594 | 0.3109 | 0.6610 |
| 3hop2 | 21 | 0.3810 | 0.5397 | 0.6349 | 0.6825 | 0.6193 | 0.8274 |
| 4hop3 | 12 | 0.1458 | 0.2500 | 0.2917 | 0.3958 | 0.2969 | 0.5549 |

Timing: passage encoding 747.5s, queries 6.0s, wall 778.4s.

## Reference (published, different setting)

HippoRAG 1 Table 2 single-step passage Recall@2 / Recall@5 for this dataset,
with their retrievers and corpus settings; not directly comparable to our numbers above:

| Retriever | R@2 | R@5 |
|---|---|---|
| BM25 | 32.3 | 41.2 |
| Contriever | 34.8 | 46.6 |
| GTR | 37.4 | 49.1 |
| ColBERTv2 | 37.9 | 49.2 |
| HippoRAG (ColBERTv2) | 40.9 | 51.9 |
