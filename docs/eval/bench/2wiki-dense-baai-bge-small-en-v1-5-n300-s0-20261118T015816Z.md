# Bench retrieval check: 2wiki / dense

300 questions, 6119 corpus passages, 0 unmatched gold docs.
Retriever: dense (BAAI/bge-small-en-v1.5); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.6342 | [0.6075, 0.6608] |
| recall_at_5 | 0.6883 | [0.6617, 0.7158] |
| recall_at_10 | 0.7275 | [0.7000, 0.7558] |
| recall_at_20 | 0.7508 | [0.7233, 0.7783] |
| ndcg_at_10 | 0.7664 | [0.7467, 0.7860] |
| mrr | 0.9917 | [0.9833, 0.9983] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| comparison | 65 | 0.9615 | 1.0000 | 1.0000 | 1.0000 | 0.9851 | 0.9846 |
| compositional | 137 | 0.5839 | 0.6350 | 0.6861 | 0.7190 | 0.7249 | 0.9964 |
| bridge_comparison | 76 | 0.4572 | 0.5197 | 0.5559 | 0.5691 | 0.6567 | 0.9934 |
| inference | 22 | 0.5909 | 0.6818 | 0.7727 | 0.8409 | 0.7580 | 0.9773 |

Timing: passage encoding 1468.0s, queries 105.6s, wall 1590.0s.

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
