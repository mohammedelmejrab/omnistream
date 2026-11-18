# Own and Classic retrieval, round 5

## Hits@1 diagnosis

All five recorded-route losses are funding-agreement questions. The gold item remains retrievable in every case. Adding passage seeds changes both the entities receiving restart mass and the set of facts entering reciprocal rank fusion (RRF). This matters because even a fact whose text, embedding, publication date and confidence stay fixed can change rank on all three signals when its competitors change. Confidence drops out entirely when all candidate confidences tie.

The interventions below run the production pipeline on eval-v2 at the round 4 clock. **Clamp PR** replaces only the PageRank vector consumed by fact scoring with the round 3 vector (zero for absent endpoints). **Shared pool** keeps passage-specificity scores and restricts representatives entering fusion to those also present under round 3. It removes added representatives without restoring missing ones. **No confidence** makes confidence constant in round 3 so only relevance and recency contribute. Fact ranks count assertions before item deduplication. A first-place hit still requires that the first assertion carry a gold item.

| Question | Round 3 | Passage | Passage specificity | Clamp PR | Shared pool | No confidence |
|---|---:|---:|---:|---:|---:|---:|
| q15 | 1 | 5 | 4 | 2 | 2 | 1 |
| q22 | 1 | 6 | 5 | 2 | 2 | 1 |
| q36 | 1 | 7 | 6 | 2 | 3 | 1 |
| q51 | 1 | 2 | 3 | 2 | 1 | 1 |
| q56 | 1 | 3 | 2 | 3 | 2 | 1 |

Restoring baseline PageRank moves the first gold assertion up on q15, q22, q36 and q51. Filtering the passage pool to shared representatives removes both higher-ranked assertions on q51. On q36, two versions of the funding assertion carry gold provenance. The specificity arm promotes a version ranked first on relevance but 45th on recency. On q56 the gold assertion actually gains endpoint mass (0.0251 to 0.0333) while the leading distractor loses mass (0.0791 to 0.0702). Its recency rank improves from 17 to 11 as the pool changes. A one-factor RRF replay verifies this pairwise reversal. With the measured specificity ranks, the distractor scores 2/67 + 1/71 = 0.04394, above the gold score of 2/72 + 1/63 = 0.04365. Restoring only its recency rank gives 2/67 + 1/77 = 0.04284, below gold. Both assertions tied on confidence in round 3.

The table lists every specificity-arm assertion before the first gold item, followed by the first gold assertion. Ranks are one-based within the fusion pool. An absent confidence signal is shown with a dash.

| Question | Assertion | In round 3 pool | Relevance / recency / confidence rank | Mean endpoint PR, round 3 to specificity |
|---|---|---|---|---|
| q15 | The SMC team deposited the replication archive for Kiteglass under accession VT-73. | no | 1 / 1 / 2 | 0.0027 to 0.0845 |
| q15 | Investigators at SMC developed Kiteglass, an experimental energy membrane. | no | 2 / 2 / 2 | 0.0027 to 0.0845 |
| q15 | Talia Muren supervised the instrument calibration at SMC. | yes | 4 / 2 / 2 | 0.0120 to 0.0843 |
| q15 | **Gold** Brindle Arc signed a research funding agreement with Sable Meridian Centre on February 7, committing 6.25 million crowns. | yes | 11 / 7 / 2 | 0.0284 to 0.0213 |
| q22 | Visiting fellow Neri Solvek supervised the instrument calibration at IDL. | no | 1 / 2 / - | 0.0000 to 0.0826 |
| q22 | Investigators at IDL developed Thistledrive, an experimental energy membrane. | no | 2 / 2 / - | 0.0000 to 0.0659 |
| q22 | The IDL team deposited the replication archive for Thistledrive under accession BK-26 | no | 3 / 1 / - | 0.0000 to 0.0659 |
| q22 | Oxbrier Logistics is legally separate from Oxbriar Robotics | yes | 5 / 19 / - | 0.0596 to 0.0376 |
| q22 | **Gold** Oxbriar Robotics signed a research funding agreement with Ivory Delta Laboratory on February 7, 2026, committing 42.9 million crowns payable in three tranches subject to audited spending. | yes | 14 / 4 / - | 0.0311 to 0.0202 |
| q36 | IVC developed Emberfoil, an experimental energy membrane. | no | 5 / 3 / - | 0.0033 to 0.0751 |
| q36 | IVC team deposited the replication archive for Emberfoil under accession ER-35 | no | 7 / 1 / - | 0.0033 to 0.0751 |
| q36 | Visiting fellow Mina Tolvik supervised the instrument calibration at IVC. | yes | 8 / 3 / - | 0.0151 to 0.0783 |
| q36 | Quenaro Digital is legally separate from Quenara Devices | yes | 4 / 15 / - | 0.0938 to 0.0637 |
| q36 | Quenaro Digital rejected suggestions that it financed Indigo Vale Centre | yes | 9 / 15 / - | 0.0799 to 0.0543 |
| q36 | **Gold** Quenara Devices signed a research funding agreement with Indigo Vale Centre on February 7, committing 27.3 million crowns payable in three tranches subject to audited spending. | yes | 1 / 45 / - | 0.1149 to 0.0721 |
| q51 | The VSC team deposited the replication archive for Frostweave under accession JF-87 | no | 1 / 1 / - | 0.0000 to 0.0595 |
| q51 | Investigators at Violet Strand Centre (VSC) developed Frostweave, an experimental energy membrane. | no | 2 / 2 / - | 0.0000 to 0.0595 |
| q51 | **Gold** PCF signed a research funding agreement with Violet Strand Centre on February 7, committing 37.2 million crowns payable in three tranches subject to audited spending. | yes | 4 / 4 / - | 0.0188 to 0.0435 |
| q56 | An editor confirmed that Ravenspear Insurance is legally separate from Ravenspire Instruments. | yes | 7 / 11 / - | 0.0791 to 0.0702 |
| q56 | **Gold** Ravenspire Instruments signed a research funding agreement with SML on February 7, 2026, committing 14.15 million crowns, payable in three tranches subject to audited spending. | yes | 12 / 3 / - | 0.0251 to 0.0333 |

The new seed names relative to round 3 were as follows. Several are local acronym entities for laboratories. A high rank for a laboratory assertion therefore need not identify the funding relationship in the question.

- q15 added SMC, Dovetail Quay 3, industry newsletter.
- q22 added IDL, Neri Solvek.
- q36 added IVC, CFI, 12.6 million crowns, Dovetail Quay 6.
- q51 added PCF, VSC.
- q56 added RSI, Jori Anvek, Uma Cevran.

**All-bubble routing.** The two 5/15 totals hide turnover. Specificity keeps q22, q36 and q41, gains q01 and q56, and loses q15 and q29. Keeping all-bubble graph search and expansion but restricting only passage lookup to the recorded collections produces 4/15 (q15, q22, q36, q41). Widening the passage collection explains those three switches in this arm. With the passage collections fixed to recorded routes, widening graph retrieval still recovers four first-place hits relative to recorded routing. The experiments establish interacting routing, expansion and scoring effects. They do not establish a general correction to graph scoring, so round 3 scoring is unchanged.

## Rerank benchmark

Graphiti implements its local reranker with independent BGE embeddings and cosine similarity. Round 5 uses the local CPU cross-encoder BAAI/bge-reranker-base (cached revision 2cfc18c9415c912f9d8155881c133215df768a70). The predeclared rule orders up to 30 candidates by model score, breaking ties by the existing order. Inputs are the question paired with verbatim assertion or chunk text. Own reranks after version selection and RRF, then returns up to 20. Classic applies the existing time constraints and publication ordering to its similarity candidate window, then returns up to 10. Classic reranking is independent of the Classic instance supplying passage seeds. Result records retain first-stage scores and provenance. Set `OMNI_OWN_RERANK=on` or `OMNI_CLASSIC_RERANK=on` independently. Both default to `off`. Enabling either requires cached BGE reranker weights. The runtime loads them lazily with local-only resolution.

All 60 eval-v2 dev questions use the frozen round 4 routes, exclusions, clock, exact graph searches, bubble half-lives and a temporary copy of the Chroma snapshot. Recall-any and R@10 are fractions of gold items found anywhere and among the first ten distinct retrieved items. Full counts questions with every gold item. MRR and Hits@1 use the first gold item. Freshness MRR includes only freshness questions. Latency is arithmetic mean wall time per retrieval in milliseconds, paired by question for the added time. The cross-encoder was warmed once. Shared embedding and filesystem caches, fixed arm order, and concurrent local work during the first questions limit timing precision. No generation, judging or parameter search was performed.

To reproduce, cache the tokenizer and safetensors weights first. From the repository root use the following commands. Trace records include both plain passage and specificity top facts, seed names, endpoint mass and RRF component ranks.

```powershell
$env:NEO4J_PASSWORD = (Get-Content C:/Users/mehme/.omnistream/neo4j_pw.txt -Raw).Trim()
$env:HF_HUB_OFFLINE = '1'
$env:OMP_NUM_THREADS = '2'
.venv/Scripts/python.exe -m omnistream.eval.diagnostics.own_fixes_round5 --trace
.venv/Scripts/python.exe -m omnistream.eval.diagnostics.own_fixes_round5
.venv/Scripts/python.exe -m omnistream.eval.diagnostics.own_fixes_round5 --summary
```

## Results

| Routes | Variant | Type | Recall-any | R@10 | Full | MRR | Hits@1 | Freshness MRR | Mean ms | Added ms |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | round3 | overall | 0.839 | 0.831 | 42/60 | 0.588 | 0.383 | 1.000 | 457 | - |
| current | round3+rerank | overall | 0.839 | 0.839 | 42/60 | 0.751 | 0.633 | 1.000 | 3519 | +3062 |
| current | passage_specificity | overall | 0.842 | 0.842 | 42/60 | 0.536 | 0.300 | 1.000 | 372 | - |
| current | passage_specificity+rerank | overall | 0.856 | 0.856 | 44/60 | 0.762 | 0.650 | 1.000 | 3418 | +3046 |
| current | classic | overall | 0.867 | 0.867 | 44/60 | 0.887 | 0.817 | 1.000 | 11 | - |
| current | classic+rerank | overall | 0.892 | 0.892 | 47/60 | 0.884 | 0.817 | 1.000 | 9970 | +9959 |
| current | round3 | single | 1.000 | 1.000 | 15/15 | 0.569 | 0.333 | - | 482 | - |
| current | round3+rerank | single | 1.000 | 1.000 | 15/15 | 0.967 | 0.933 | - | 3819 | +3337 |
| current | passage_specificity | single | 1.000 | 1.000 | 15/15 | 0.356 | 0.000 | - | 325 | - |
| current | passage_specificity+rerank | single | 1.000 | 1.000 | 15/15 | 1.000 | 1.000 | - | 3720 | +3395 |
| current | classic | single | 1.000 | 1.000 | 15/15 | 0.942 | 0.933 | - | 8 | - |
| current | classic+rerank | single | 1.000 | 1.000 | 15/15 | 1.000 | 1.000 | - | 10540 | +10531 |
| current | round3 | multi_hop | 0.592 | 0.567 | 5/20 | 0.377 | 0.150 | - | 460 | - |
| current | round3+rerank | multi_hop | 0.617 | 0.617 | 6/20 | 0.443 | 0.200 | - | 3348 | +2888 |
| current | passage_specificity | multi_hop | 0.600 | 0.600 | 5/20 | 0.403 | 0.150 | - | 442 | - |
| current | passage_specificity+rerank | multi_hop | 0.692 | 0.692 | 9/20 | 0.437 | 0.200 | - | 3480 | +3038 |
| current | classic | multi_hop | 0.600 | 0.600 | 4/20 | 0.781 | 0.650 | - | 17 | - |
| current | classic+rerank | multi_hop | 0.675 | 0.675 | 7/20 | 0.714 | 0.550 | - | 9986 | +9969 |
| current | round3 | time_sensitive | 0.900 | 0.900 | 12/15 | 0.613 | 0.333 | - | 551 | - |
| current | round3+rerank | time_sensitive | 0.867 | 0.867 | 11/15 | 0.780 | 0.667 | - | 3756 | +3205 |
| current | passage_specificity | time_sensitive | 0.900 | 0.900 | 12/15 | 0.583 | 0.333 | - | 435 | - |
| current | passage_specificity+rerank | time_sensitive | 0.833 | 0.833 | 10/15 | 0.800 | 0.667 | - | 3433 | +2999 |
| current | classic | time_sensitive | 1.000 | 1.000 | 15/15 | 0.900 | 0.800 | - | 10 | - |
| current | classic+rerank | time_sensitive | 1.000 | 1.000 | 15/15 | 0.917 | 0.867 | - | 9647 | +9636 |
| current | round3 | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 272 | - |
| current | round3+rerank | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 3056 | +2785 |
| current | passage_specificity | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 210 | - |
| current | passage_specificity+rerank | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 2816 | +2606 |
| current | classic | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 6 | - |
| current | classic+rerank | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 9571 | +9564 |
| oracle | round3 | overall | 0.800 | 0.800 | 37/60 | 0.564 | 0.350 | 1.000 | 412 | - |
| oracle | round3+rerank | overall | 0.831 | 0.831 | 41/60 | 0.758 | 0.650 | 1.000 | 3283 | +2871 |
| oracle | passage_specificity | overall | 0.881 | 0.875 | 47/60 | 0.602 | 0.400 | 1.000 | 417 | - |
| oracle | passage_specificity+rerank | overall | 0.872 | 0.872 | 46/60 | 0.797 | 0.683 | 1.000 | 3316 | +2899 |
| oracle | classic | overall | 0.867 | 0.867 | 44/60 | 0.887 | 0.817 | 1.000 | 22 | - |
| oracle | classic+rerank | overall | 0.883 | 0.883 | 46/60 | 0.890 | 0.833 | 1.000 | 9983 | +9961 |
| oracle | round3 | single | 1.000 | 1.000 | 15/15 | 0.563 | 0.333 | - | 379 | - |
| oracle | round3+rerank | single | 1.000 | 1.000 | 15/15 | 1.000 | 1.000 | - | 3352 | +2973 |
| oracle | passage_specificity | single | 1.000 | 1.000 | 15/15 | 0.544 | 0.333 | - | 397 | - |
| oracle | passage_specificity+rerank | single | 1.000 | 1.000 | 15/15 | 1.000 | 1.000 | - | 3167 | +2770 |
| oracle | classic | single | 1.000 | 1.000 | 15/15 | 0.942 | 0.933 | - | 24 | - |
| oracle | classic+rerank | single | 1.000 | 1.000 | 15/15 | 1.000 | 1.000 | - | 10361 | +10337 |
| oracle | round3 | multi_hop | 0.500 | 0.500 | 1/20 | 0.368 | 0.150 | - | 434 | - |
| oracle | round3+rerank | multi_hop | 0.592 | 0.592 | 5/20 | 0.434 | 0.200 | - | 3302 | +2868 |
| oracle | passage_specificity | multi_hop | 0.717 | 0.700 | 10/20 | 0.459 | 0.150 | - | 448 | - |
| oracle | passage_specificity+rerank | multi_hop | 0.742 | 0.742 | 11/20 | 0.542 | 0.300 | - | 3417 | +2969 |
| oracle | classic | multi_hop | 0.600 | 0.600 | 4/20 | 0.781 | 0.650 | - | 21 | - |
| oracle | classic+rerank | multi_hop | 0.650 | 0.650 | 6/20 | 0.733 | 0.600 | - | 9741 | +9719 |
| oracle | round3 | time_sensitive | 0.867 | 0.867 | 11/15 | 0.533 | 0.200 | - | 524 | - |
| oracle | round3+rerank | time_sensitive | 0.867 | 0.867 | 11/15 | 0.786 | 0.667 | - | 3538 | +3014 |
| oracle | passage_specificity | time_sensitive | 0.900 | 0.900 | 12/15 | 0.586 | 0.400 | - | 496 | - |
| oracle | passage_specificity+rerank | time_sensitive | 0.833 | 0.833 | 10/15 | 0.800 | 0.667 | - | 3486 | +2990 |
| oracle | classic | time_sensitive | 1.000 | 1.000 | 15/15 | 0.900 | 0.800 | - | 22 | - |
| oracle | classic+rerank | time_sensitive | 1.000 | 1.000 | 15/15 | 0.917 | 0.867 | - | 10084 | +10062 |
| oracle | round3 | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 248 | - |
| oracle | round3+rerank | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 2756 | +2508 |
| oracle | passage_specificity | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 268 | - |
| oracle | passage_specificity+rerank | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 3080 | +2812 |
| oracle | classic | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 20 | - |
| oracle | classic+rerank | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 | 9749 | +9729 |

## Defaults

Keep round 3 with both rerank flags off for the latency-sensitive default. Where first-result quality justifies approximately three additional CPU seconds per query, enable Own reranking with passage specificity. On recorded routes it reached 15/15 single first-place hits and 9/20 complete multi-hop questions. Time-sensitive full coverage fell from 12/15 to 10/15, and all-bubble overall full coverage fell from 47/60 to 46/60. Classic reranking added about ten seconds and left recorded overall Hits@1 at 49/60 while improving full coverage from 44/60 to 47/60. These comparisons concern synthetic dev retrieval only.

Raw cells are in `data/diagnostics/own-fixes-round5/offline.jsonl` and interventions in `trace.jsonl` beside it. Unit suite: 1282 passed, 1 skipped, 4 deselected in 158.84s (0:02:38). The three fake-encoder reranking tests also passed independently.
