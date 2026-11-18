# BGE-large cosine thresholds on eval-v2

The cutover preserves all thresholds. The table uses the post-alias-merge graph in the three eval-v2 bubbles, the 60 frozen questions, and 90 corpus items. Both local models encoded the same text. Retrieval questions use the BGE instruction. Names, facts, and passages use document encoding. Counts after the gate are pair counts, before top-k truncation.

| Gate | Location | Cosine rule |
| --- | --- | --- |
| Global linking | `config.py` and `graph/linker.py` | At least 0.88. Source-evidenced aliases and fuzzy matching are separate signals. |
| Duplicate entity audit | `eval/audit.py` | At least 0.88 when normalized names differ. |
| Name seeding | `retrieval/own_algorithm/seeding.py`, `retrieval/protocols.py`, `graph/{neo4j,memory}_store.py` | At least 0.50. |
| Fact seeding and scoring | `retrieval/own_algorithm/{seeding,scoring}.py` | Seed only above zero. Fact scoring clips below zero. |
| Hybrid dense search | `retrieval/hybrid.py` | Above zero by default. |
| Graphiti semantic search | Graphiti 0.31.2 `search/search_utils.py` and `graph_queries.py` | Above 0.60 on Neo4j's normalized scale, equivalent to raw cosine above 0.20. |
| Fact version collapse | `retrieval/own_algorithm/versions.py` | At least 0.95 after checking bubble, directed endpoints, relation, and protected tokens. Identical normalized text bypasses the cosine comparison. |
| Near-duplicate source audit | `eval/real/verify.py` | At least 0.92 on L2-normalized, pooled 1,200-character segment vectors. |

Routing confidence, fuzzy matching, publication boosts, and RRF parameters operate on other signals. Classic and the local Graphiti embedding reranker rank cosine without an application cutoff.

| Eval-v2 sample | Pairs | Small p05/p50/p95 | Large p05/p50/p95 | Small pass | Large pass |
| --- | ---: | --- | --- | ---: | ---: |
| SAME_AS Entity to GlobalEntity | 283 | 0.539/1.000/1.000 | 0.537/1.000/1.000 | 227 (80.2%) | 228 (80.6%) |
| SAME_AS with different normalized names | 58 | 0.485/0.587/0.873 | 0.507/0.569/0.877 | 2 (3.4%) | 3 (5.2%) |
| Random same-type GlobalEntity, different identity and name | 1415 | 0.431/0.515/0.625 | 0.369/0.474/0.593 | 0 (0.0%) | 0 (0.0%) |
| Duplicate audit pairs with different normalized names | 28030 | 0.416/0.501/0.600 | 0.369/0.462/0.566 | 10 (0.0%) | 7 (0.0%) |
| Question to named entity mentioned verbatim | 68 | 0.602/0.699/0.755 | 0.577/0.694/0.757 | 68 (100.0%) | 68 (100.0%) |
| Question to other named entities in expected bubbles | 5993 | 0.363/0.431/0.517 | 0.334/0.411/0.508 | 561 (9.4%) | 379 (6.3%) |
| Question to fact with gold-item provenance | 273 | 0.406/0.607/0.819 | 0.365/0.570/0.813 | 273 (100.0%) | 273 (100.0%) |
| Question to other facts in expected bubbles | 10338 | 0.345/0.434/0.605 | 0.309/0.402/0.586 | 10338 (100.0%) | 10338 (100.0%) |
| Graphiti cosine gate, facts with gold-item provenance | 273 | 0.406/0.607/0.819 | 0.365/0.570/0.813 | 273 (100.0%) | 273 (100.0%) |
| Graphiti cosine gate, other facts | 10338 | 0.345/0.434/0.605 | 0.309/0.402/0.586 | 10338 (100.0%) | 10338 (100.0%) |
| Hybrid dense gate, all question-chunk pairs | 5400 | 0.411/0.508/0.658 | 0.421/0.503/0.659 | 5400 (100.0%) | 5400 (100.0%) |
| Version candidates eligible for cosine comparison | 1 | 0.970/0.970/0.970 | 0.965/0.965/0.965 | 1 (100.0%) | 1 (100.0%) |
| Same family, protected tokens differ | 0 | - | - | - | - |
| Same endpoints, different normalized relation | 102 | 0.620/0.724/0.870 | 0.574/0.659/0.837 | 0 (0.0%) | 0 (0.0%) |
| Item pairs for near-duplicate audit | 4005 | 0.593/0.681/0.859 | 0.528/0.619/0.822 | 20 (0.5%) | 27 (0.7%) |

Linker positives are actual Entity-to-GlobalEntity `SAME_AS` links. The negative sample includes up to five randomly drawn same-type GlobalEntities per entity, with different linked identity and normalized name (seed 731). The duplicate-entity audit is a 100-entity sample with the existing cross-bubble exclusion. Mentioned names require a full token sequence in the question. Question-to-fact samples use recorded expected bubbles and gold item provenance, before time-scope filtering. Version scores cover candidate pairs before query-time filtering. The document audit compares all item pairs. These proxies measure score movement and have limited coverage of hard negatives.

At 0.88, only 2/58 small-model and 3/58 large-model distinct-name links pass. No sampled same-type negative crosses the gate under either model. All 68 verbatim-name pairs stay above 0.50, while the pass count for other named entities falls from 561 to 379. The sole fact-version pair eligible for cosine remains above 0.95, so eval-v2 provides little evidence about the cutoff near that boundary.
