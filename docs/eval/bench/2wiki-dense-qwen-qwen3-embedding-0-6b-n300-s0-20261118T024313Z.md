# Bench retrieval check: 2wiki / dense

300 questions, 6119 corpus passages, 0 unmatched gold docs.
Retriever: dense (Qwen/Qwen3-Embedding-0.6B); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.6350 | [0.6083, 0.6617] |
| recall_at_5 | 0.6875 | [0.6600, 0.7142] |
| recall_at_10 | 0.7142 | [0.6858, 0.7425] |
| recall_at_20 | 0.7508 | [0.7233, 0.7783] |
| ndcg_at_10 | 0.7592 | [0.7392, 0.7790] |
| mrr | 0.9889 | [0.9789, 0.9967] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| comparison | 65 | 0.9462 | 1.0000 | 1.0000 | 1.0000 | 0.9868 | 0.9897 |
| compositional | 137 | 0.5876 | 0.6387 | 0.6825 | 0.7336 | 0.7210 | 0.9891 |
| bridge_comparison | 76 | 0.4737 | 0.5099 | 0.5230 | 0.5493 | 0.6429 | 1.0000 |
| inference | 22 | 0.5682 | 0.6818 | 0.7273 | 0.8182 | 0.7267 | 0.9470 |

Timing: passage encoding 221.7s, queries 14.5s, wall 251.0s.

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
