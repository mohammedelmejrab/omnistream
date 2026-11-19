# Eval-v2 Round 5, bge-small to bge-large

The 60 frozen questions use recorded current routes and oracle routes across all three eval-v2 bubbles. Both runs use the post-alias-merge graph. Cells show small → large. R@10, MRR and Hits@1 are overall macro averages. Freshness MRR averages the freshness questions.

| Routing | Variant | Full overall | Full multi-hop | R@10 | MRR | Hits@1 | Freshness MRR |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| current | round3 | 42/60 → 42/60 | 5/20 → 5/20 | 0.831 → 0.856 | 0.577 → 0.649 | 0.350 → 0.483 | 1.000 → 1.000 |
| current | passage_specificity | 45/60 → 44/60 | 9/20 → 7/20 | 0.858 → 0.858 | 0.588 → 0.575 | 0.350 → 0.333 | 1.000 → 1.000 |
| current | round3+rerank | 45/60 → 45/60 | 9/20 → 9/20 | 0.864 → 0.878 | 0.755 → 0.746 | 0.633 → 0.633 | 1.000 → 1.000 |
| current | passage_specificity+rerank | 45/60 → 46/60 | 11/20 → 12/20 | 0.864 → 0.886 | 0.787 → 0.778 | 0.667 → 0.667 | 1.000 → 1.000 |
| current | classic | 44/60 → 44/60 | 4/20 → 4/20 | 0.867 → 0.861 | 0.887 → 0.852 | 0.817 → 0.767 | 1.000 → 1.000 |
| current | classic+rerank | 47/60 → 45/60 | 7/20 → 5/20 | 0.892 → 0.875 | 0.884 → 0.879 | 0.817 → 0.817 | 1.000 → 1.000 |
| oracle | round3 | 42/60 → 45/60 | 4/20 → 7/20 | 0.825 → 0.856 | 0.602 → 0.604 | 0.417 → 0.433 | 1.000 → 1.000 |
| oracle | passage_specificity | 47/60 → 44/60 | 10/20 → 7/20 | 0.872 → 0.864 | 0.614 → 0.551 | 0.417 → 0.333 | 1.000 → 1.000 |
| oracle | round3+rerank | 44/60 → 46/60 | 8/20 → 10/20 | 0.856 → 0.869 | 0.765 → 0.745 | 0.650 → 0.633 | 1.000 → 1.000 |
| oracle | passage_specificity+rerank | 46/60 → 46/60 | 11/20 → 11/20 | 0.872 → 0.889 | 0.788 → 0.775 | 0.667 → 0.667 | 1.000 → 1.000 |
| oracle | classic | 44/60 → 43/60 | 4/20 → 3/20 | 0.867 → 0.853 | 0.887 → 0.852 | 0.817 → 0.767 | 1.000 → 1.000 |
| oracle | classic+rerank | 46/60 → 45/60 | 6/20 → 5/20 | 0.883 → 0.875 | 0.890 → 0.880 | 0.833 → 0.817 | 1.000 → 1.000 |
