# Bench retrieval check: musique / dense

300 questions, 11656 corpus passages, 0 unmatched gold docs.
Retriever: dense (Qwen/Qwen3-Embedding-0.6B); corpus: full; seed: 0.

## Our numbers

| Metric | Value | 95% CI |
|---|---|---|
| recall_at_2 | 0.4064 | [0.3789, 0.4350] |
| recall_at_5 | 0.5417 | [0.5103, 0.5725] |
| recall_at_10 | 0.6269 | [0.5953, 0.6586] |
| recall_at_20 | 0.7042 | [0.6731, 0.7347] |
| ndcg_at_10 | 0.6004 | [0.5730, 0.6283] |
| mrr | 0.8246 | [0.7896, 0.8582] |

## By question type

| Type | Questions | recall_at_2 | recall_at_5 | recall_at_10 | recall_at_20 | ndcg_at_10 | mrr |
|---|---|---|---|---|---|---|---|---|
| 3hop1 | 72 | 0.3333 | 0.5139 | 0.6204 | 0.6991 | 0.5720 | 0.7723 |
| 2hop | 154 | 0.4935 | 0.6299 | 0.7078 | 0.7857 | 0.6697 | 0.8571 |
| 4hop2 | 9 | 0.2500 | 0.3333 | 0.3611 | 0.5000 | 0.4360 | 0.8889 |
| 4hop1 | 32 | 0.2500 | 0.2891 | 0.3516 | 0.3906 | 0.3999 | 0.7972 |
| 3hop2 | 21 | 0.4603 | 0.6190 | 0.7460 | 0.8413 | 0.7183 | 0.9127 |
| 4hop3 | 12 | 0.1667 | 0.2708 | 0.3542 | 0.4375 | 0.3340 | 0.5931 |

Timing: passage encoding 263.8s, queries 14.0s, wall 445.5s.

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
