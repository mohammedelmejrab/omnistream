# real-v2 ingestion cost

No full snapshot was built. Only the ten-item throwaway probe is authorized.

**BLOCKED: no live measurement.** LLM_API_KEY is absent from the process environment; the task prohibits opening `.env`. The private key-entry request timed out without delivery. No provider requests have been made; actual spend is $0.00. No throwaway snapshot has been created. A read-only Neo4j check verified zero nodes for the `real-v2-costprobe` prefix and the snapshot directory is absent; no cleanup was necessary.

Ingestion USD/item, USD/1,000 words, strongest cost predictor, and USD projections are **NOT MEASURED**. Word totals below are real manifest inputs, not cost measurements.

| Snapshot selection | Items | Actual manifest words | Stratum projection USD | Pooled projection USD |
|---|---:|---:|---:|---:|
| dev: hypothetical 120-item fixed-seed sample (split has no questions) | 120 | 132,534 | NOT MEASURED | NOT MEASURED |
| test: actual required items + background 60 | 140 | 170,065 | NOT MEASURED | NOT MEASURED |
| full 350-item corpus | 350 | 456,032 | NOT MEASURED | NOT MEASURED |

The companion projection JSON records the exact selected IDs and SHA-256 digest. Missing or invalid split annotations produce explicitly hypothetical samples; they are never silently ingested.

The existing SnapshotBuilder calls C1 Intake for an API source, C3 automatic routing, then C4 GraphWriter and Chroma chunks. It does **not** call C1 `load_document` / `split_episodes` for Graphiti episodes. Observed episodes are counted from Neo4j; `document_split_episodes` records how many 1,500-token document parts the upload path would create, for comparison only. The system under test was not changed. New entity/fact counts are net group-count deltas (deduplication can reduce them); global entities are excluded.

## Evaluation run estimate

Source: `docs/eval/eval-v2-20261112T050602182241Z.md` and its configurations CSV (60 questions/configuration). Old recordings contain only total tokens, not prompt/completion counts. Exact repricing is impossible. Central scenario assumes a stable 90% prompt / 10% completion mix and unchanged caching: answer costs × ((0.9×0.15+0.1×0.60)/(0.9×0.32+0.1×0.89)) = ×0.517241. Sensitivity range uses all-prompt ×0.46875 through all-completion ×0.674157. These are pricing scenarios, not confidence bounds. Judge stays `deepseek/deepseek-chat`; its recorded provider cost is unchanged. Larger real documents/retrieved contexts may increase tokens. No new evaluation requests were sent.

| Configuration | Estimated USD/question incl. judge | Mix sensitivity USD/question | Estimated 60-question run USD |
|---|---:|---:|---:|
| external | 0.000410 | 0.000403–0.000434 | 0.024629 |
| classic | 0.001156 | 0.001117–0.001282 | 0.069367 |
| graphiti | 0.001224 | 0.001163–0.001422 | 0.073464 |
| own | 0.001039 | 0.000986–0.001208 | 0.062326 |
| own+subagents | 0.003711 | 0.003413–0.004677 | 0.222677 |
| classic+subagents | 0.002481 | 0.002333–0.002960 | 0.148854 |

All six configurations, 60 questions each: estimated **$0.601318** for answers + per-answer judges. Shared contamination, audit, calibration and snapshot construction are additional; this is not a measured real-v2 evaluation run.
