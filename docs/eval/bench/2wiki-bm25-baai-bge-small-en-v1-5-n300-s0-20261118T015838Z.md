# Bench retrieval check: 2wiki / bm25

300 questions, 6119 corpus passages, 0 unmatched gold docs.
Retriever: bm25; corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.5550 | [0.5275, 0.5842] |
| recall_at_5 | 0.6375 | [0.6117, 0.6642] |
| recall_at_10 | 0.6875 | [0.6608, 0.7150] |
| recall_at_20 | 0.7133 | [0.6858, 0.7408] |
| ndcg_at_10 | 0.7053 | [0.6832, 0.7276] |
| mrr | 0.9376 | [0.9157, 0.9581] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| comparison | 65 | 0.8077 | 0.9000 | 0.9692 | 1.0000 | 0.9095 | 0.9434 |
| compositional | 137 | 0.5219 | 0.5912 | 0.6277 | 0.6569 | 0.6510 | 0.9115 |
| bridge_comparison | 76 | 0.4079 | 0.5164 | 0.5428 | 0.5526 | 0.6316 | 0.9770 |
| inference | 22 | 0.5227 | 0.5682 | 0.7273 | 0.7727 | 0.6952 | 0.9470 |

Timing: passage encoding 0.0s, queries 10.7s, wall 16.0s.

## Reference (published, different setting)

HippoRAG 1 Table 2 single-step passage Recall@2 / Recall@5 for this dataset,
with their retrievers and corpus settings; not directly comparable to our numbers above:

| Retriever | R@2 | R@5 |
|---|---|---|
| BM25 | 51.8 | 61.9 |
| Contriever | 46.6 | 57.5 |
| GTR | 60.2 | 67.9 |
| ColBERTv2 | 59.2 | 68.2 |
| HippoRAG (ColBERTv2) | 70.7 | 89.1 |
