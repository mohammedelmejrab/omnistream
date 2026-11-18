# Bench retrieval check: musique / dense

300 questions, 11656 corpus passages, 0 unmatched gold docs.
Retriever: dense (BAAI/bge-large-en-v1.5); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.4119 | [0.3794, 0.4456] |
| recall_at_5 | 0.5567 | [0.5219, 0.5919] |
| recall_at_10 | 0.6439 | [0.6100, 0.6781] |
| recall_at_20 | 0.7200 | [0.6861, 0.7528] |
| ndcg_at_10 | 0.6022 | [0.5705, 0.6338] |
| mrr | 0.7764 | [0.7379, 0.8148] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| 3hop1 | 72 | 0.3380 | 0.5093 | 0.6204 | 0.6944 | 0.5773 | 0.7636 |
| 2hop | 154 | 0.5260 | 0.6753 | 0.7565 | 0.8149 | 0.6967 | 0.8267 |
| 4hop2 | 9 | 0.1389 | 0.2778 | 0.3611 | 0.4722 | 0.3648 | 0.6455 |
| 4hop1 | 32 | 0.2109 | 0.2812 | 0.3047 | 0.3594 | 0.3353 | 0.6435 |
| 3hop2 | 21 | 0.4286 | 0.5873 | 0.6667 | 0.8571 | 0.6634 | 0.8770 |
| 4hop3 | 12 | 0.1042 | 0.2083 | 0.4167 | 0.5625 | 0.3229 | 0.4828 |

Timing: passage encoding 114.5s, queries 11.9s, wall 333.5s.

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
