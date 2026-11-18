# Bench retrieval check: musique / bm25

300 questions, 11656 corpus passages, 0 unmatched gold docs.
Retriever: bm25; corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.3378 | [0.3075, 0.3681] |
| recall_at_5 | 0.4472 | [0.4178, 0.4772] |
| recall_at_10 | 0.5189 | [0.4892, 0.5489] |
| recall_at_20 | 0.6028 | [0.5722, 0.6339] |
| ndcg_at_10 | 0.5006 | [0.4710, 0.5298] |
| mrr | 0.7197 | [0.6764, 0.7620] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| 3hop1 | 72 | 0.2731 | 0.4213 | 0.5231 | 0.6250 | 0.4874 | 0.7106 |
| 2hop | 154 | 0.4091 | 0.5097 | 0.5649 | 0.6494 | 0.5424 | 0.7333 |
| 4hop2 | 9 | 0.2500 | 0.2500 | 0.3611 | 0.3889 | 0.4022 | 0.6825 |
| 4hop1 | 32 | 0.1719 | 0.2812 | 0.3516 | 0.4062 | 0.3368 | 0.5891 |
| 3hop2 | 21 | 0.3175 | 0.4444 | 0.5238 | 0.6349 | 0.5149 | 0.7540 |
| 4hop3 | 12 | 0.3542 | 0.3958 | 0.4583 | 0.5000 | 0.5289 | 0.9167 |

Timing: passage encoding 0.0s, queries 10.3s, wall 12.6s.

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
