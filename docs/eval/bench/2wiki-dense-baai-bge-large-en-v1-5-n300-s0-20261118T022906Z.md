# Bench retrieval check: 2wiki / dense

300 questions, 6119 corpus passages, 0 unmatched gold docs.
Retriever: dense (BAAI/bge-large-en-v1.5); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.6483 | [0.6208, 0.6767] |
| recall_at_5 | 0.7125 | [0.6850, 0.7400] |
| recall_at_10 | 0.7542 | [0.7267, 0.7817] |
| recall_at_20 | 0.7867 | [0.7592, 0.8133] |
| ndcg_at_10 | 0.7822 | [0.7618, 0.8023] |
| mrr | 0.9844 | [0.9733, 0.9933] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| comparison | 65 | 0.9538 | 0.9923 | 0.9923 | 1.0000 | 0.9879 | 1.0000 |
| compositional | 137 | 0.6168 | 0.6898 | 0.7445 | 0.7847 | 0.7538 | 0.9732 |
| bridge_comparison | 76 | 0.4539 | 0.5230 | 0.5691 | 0.5921 | 0.6644 | 0.9934 |
| inference | 22 | 0.6136 | 0.6818 | 0.7500 | 0.8409 | 0.7587 | 0.9773 |

Timing: passage encoding 88.1s, queries 11.4s, wall 121.8s.

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
