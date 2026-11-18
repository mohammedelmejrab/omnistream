# Own retrieval fixes, round 4

On eval-v2 recorded routes, passage seeds recovered one additional complete multi-hop answer set (v2-q43), taking full coverage from 5/20 to 6/20. Overall R@10 rose from 0.831 to 0.839. Both passage variants lost all five single-question first-place hits. Keep round 3 as the runtime default. All-bubble routing shows a larger benefit from passage seeds with specificity, reaching 10/20 multi-hop full coverage against 1/20 for round 3.

## Methods and controls

The 360 cells cover 60 dev questions, three seed modes and two routing policies. Current uses 35 E0 own decisions and 25 E2 repeat-0 decisions. Oracle selects all three bubbles and preserves each recorded time scope and exclusions. The clock is fixed at 2026-11-12 23:49:17.370617 UTC. Neo4j entity and fact searches use exact mode. Half-lives, two-hop expansion, identity deduplication, fact validity, version selection, PageRank, fusion and the 20-fact output cap follow round 3. All three variants ran in the same process on the same graph. No answer generation or judging was performed.

The passage arm shares the production ClassicRetriever. It retrieves stored local BGE chunk embeddings from a temporary copy of the eval-v2 Chroma snapshot, requests all chunks in each selected collection, and applies the existing classic publication-time rules to the similarity top five. The graph join uses both bubble and item ID. Each matched episode votes once for each named entity it mentions, using its best chunk rank. The passage score is the sum of reciprocal ranks divided by the number of distinct episodes mentioning the local entity. Multiple MENTIONS edges cannot duplicate a vote. The round-3 ontology filter excludes generic passage entities. Item IDs that lack a matching episode contribute no vote.

Predeclared choices were five chunks, reciprocal one-based rank, inverse mention frequency, and up to three reserved passage identities after the existing five fact reservations. Remaining slots use the highest score across sources, up to ten distinct identities. A stronger score can replace a reserved candidate for the same identity. The specificity arm keeps that selection and multiplies every selected restart score by inverse mention frequency, including passage scores that already used specificity during selection. An entity with no counted episode keeps its restart weight. No parameters were tuned after measurement.

Recall-any is the mean fraction of gold items anywhere in the ranked output. R@10 credits its first ten distinct item IDs. Full counts questions retrieving every gold item. MRR and Hits@1 use the first gold item. Freshness MRR uses only the ten freshness questions.

## Headline results

| Routes | Variant | Type | Recall-any | R@10 | Full | MRR | Hits@1 | Freshness MRR |
|---|---|---|---:|---:|---:|---:|---:|---:|
| current | round3 | overall | 0.839 | 0.831 | 42/60 | 0.588 | 0.383 | 1.000 |
| current | passage | overall | 0.839 | 0.839 | 43/60 | 0.539 | 0.317 | 1.000 |
| current | passage_specificity | overall | 0.842 | 0.842 | 42/60 | 0.536 | 0.300 | 1.000 |
| oracle | round3 | overall | 0.800 | 0.800 | 37/60 | 0.564 | 0.350 | 1.000 |
| oracle | passage | overall | 0.833 | 0.833 | 41/60 | 0.594 | 0.383 | 1.000 |
| oracle | passage_specificity | overall | 0.881 | 0.875 | 47/60 | 0.602 | 0.400 | 1.000 |

## By type

| Routes | Variant | Type | Recall-any | R@10 | Full | MRR | Hits@1 | Freshness MRR |
|---|---|---|---:|---:|---:|---:|---:|---:|
| current | round3 | single | 1.000 | 1.000 | 15/15 | 0.569 | 0.333 | - |
| current | passage | single | 1.000 | 1.000 | 15/15 | 0.284 | 0.000 | - |
| current | passage_specificity | single | 1.000 | 1.000 | 15/15 | 0.356 | 0.000 | - |
| current | round3 | multi_hop | 0.592 | 0.567 | 5/20 | 0.377 | 0.150 | - |
| current | passage | multi_hop | 0.592 | 0.592 | 6/20 | 0.450 | 0.200 | - |
| current | passage_specificity | multi_hop | 0.600 | 0.600 | 5/20 | 0.403 | 0.150 | - |
| current | round3 | time_sensitive | 0.900 | 0.900 | 12/15 | 0.613 | 0.333 | - |
| current | passage | time_sensitive | 0.900 | 0.900 | 12/15 | 0.606 | 0.333 | - |
| current | passage_specificity | time_sensitive | 0.900 | 0.900 | 12/15 | 0.583 | 0.333 | - |
| current | round3 | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 |
| current | passage | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 |
| current | passage_specificity | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 |
| oracle | round3 | single | 1.000 | 1.000 | 15/15 | 0.563 | 0.333 | - |
| oracle | passage | single | 1.000 | 1.000 | 15/15 | 0.528 | 0.333 | - |
| oracle | passage_specificity | single | 1.000 | 1.000 | 15/15 | 0.544 | 0.333 | - |
| oracle | round3 | multi_hop | 0.500 | 0.500 | 1/20 | 0.368 | 0.150 | - |
| oracle | passage | multi_hop | 0.600 | 0.600 | 5/20 | 0.468 | 0.200 | - |
| oracle | passage_specificity | multi_hop | 0.717 | 0.700 | 10/20 | 0.459 | 0.150 | - |
| oracle | round3 | time_sensitive | 0.867 | 0.867 | 11/15 | 0.533 | 0.200 | - |
| oracle | passage | time_sensitive | 0.867 | 0.867 | 11/15 | 0.558 | 0.267 | - |
| oracle | passage_specificity | time_sensitive | 0.900 | 0.900 | 12/15 | 0.586 | 0.400 | - |
| oracle | round3 | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 |
| oracle | passage | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 |
| oracle | passage_specificity | freshness | 1.000 | 1.000 | 10/10 | 1.000 | 1.000 | 1.000 |

## Ranking and coverage trade-offs

On recorded routes, passage seeding gained one fully covered multi-hop question and lost none. Adding restart specificity gained v2-q31 and v2-q37 but lost v2-q04 and v2-q17 versus round 3. This leaves full coverage at 5/20 despite higher multi-hop R@10. Under all-bubble routing, the specificity arm gained nine fully covered multi-hop questions and lost none. Freshness remained perfect across the six comparisons.

The fresh round-3 baseline reproduced every archived seed list, recall-any, R@10 and full-coverage value in all 120 route/question cells. Thirteen ranked item lists differed. Only two differences affected the requested rank metrics. On recorded routes v2-q44 and v2-q56 moved the first gold item from second to first, changing overall MRR from the archived 0.571 to 0.588 and Hits@1 from 0.350 to 0.383. The cause of that rank drift is unverified. All table comparisons use the fresh baseline.

## Default, limits and reproduction

Set `OMNI_OWN_SEED_MODE` to `round3` (default), `passage` or `passage_specificity`. The one extra full-coverage result on recorded routes does not justify the observed loss in first-result quality. The all-bubble improvement warrants keeping both experiments available. This synthetic dev set contains only 20 multi-hop questions, and provenance recall measures retrieval of an item without establishing that its needed assertion reached the answer. No held-out or end-to-end accuracy or latency was measured. The passage path adds a Chroma read and a graph join, and restart specificity adds a second graph read. Counts are local-node corpus frequencies across time, including episodes outside a question's time window.

All round-3 controls and frozen inputs were present. The run used local cached embeddings, blocked sync and async OpenAI chat completions, constructed settings with dotenv disabled, and issued read-only graph queries. From the repo root, reproduce with the following PowerShell commands. Per-cell seed IDs, ranked item IDs and metrics are written to `data/diagnostics/own-fixes-round4/offline.jsonl`.

```powershell
$env:NEO4J_PASSWORD = (Get-Content C:/Users/mehme/.omnistream/neo4j_pw.txt -Raw).Trim()
$env:HF_HUB_OFFLINE = '1'
$env:OMP_NUM_THREADS = '2'
.venv/Scripts/python.exe -m omnistream.eval.diagnostics.own_fixes_round4
```
