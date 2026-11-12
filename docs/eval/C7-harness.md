# Evaluation harness operation

Run from the repository with `.venv\Scripts\omni.exe eval --rows all --snapshot eval-v1`.
Resume the same selection using `--resume latest` or `--resume <numeric run id>`.
`--limit N` selects the first N questions per configuration; repeat the same limit on resume.
A limited run is a smoke result, not evidence for the full 60-question acceptance targets.

Each run has data/snapshots/<snapshot>/runs/<id>/metadata.json, answers.jsonl,
and summary.json. Each scored pair is appended, flushed and fsynced before the
SQLite eval_runs row is updated. Resume treats JSONL as authoritative, tolerates
an interrupted final line, and skips completed pairs. On explicit resume, recorded answer or judgement errors are retried once; a resume_retry flag prevents repeated retries.
The question stage has two concurrent questions; only in-flight pairs can be lost.
The application progress and Python logging output go to docs/eval/<snapshot>-<id>.log
in UTF-8; shell redirection is unnecessary. Reports and both CSV exports are
linked from eval_runs. Provider-unreported cost remains N/A rather than zero.

## Frozen snapshots and freshness

Snapshots store `dataset` and `item_content_sha256` in the manifest. New snapshots
accept `--dataset eval-v1|eval-v2` (default v1); names do not select a corpus.
Existing bindings reject conflicting `--dataset`. Legacy frozen snapshots infer
the corpus from the recorded original dataset SHA, using a fixed v1/v2 mapping.
Run `omni eval verify-snapshot --snapshot eval-v1` (and eval-v2) for migration.
Migration pins the original item digest, checks the exact item set and runtime IDs,
SQLite dates/URLs/titles/source IDs/credibility, assigned bubbles against the
manifest, freshness membership and both stored raw/text content. Text comparison
normalizes CRLF/LF. Source display names and manual labels were not separately
persisted by intake; the pinned original item digest protects those fields.
Any mismatch refuses the migration before saving. The original full-dataset SHA
is retained for provenance; the new digest covers every item field, including
IDs, texts, dates, sources, bubbles and freshness flags, excluding questions and
reference answers. Correcting a reference answer therefore preserves integrity.
A complete snapshot freezes only after all expected items are written and their
queue jobs done. Frozen snapshots bypass ingestion and reject `--rebuild`.

There are exactly 15 single, 20 multi-hop, 15 changed-fact and 10 freshness
questions. Every freshness question references injected gold evidence. Freshness
measurements are recorded during the original snapshot build: injected_at is the
wall-clock injection time, write_lag_seconds ends after the worker writes, and
answerable_lag_seconds ends at the first answer probe with correctness 2 and the
injected item in retrieved evidence. Probe lag is an upper bound, not a historical
measurement reconstructed from a later query. Frozen evaluation reuses these
recorded probes and timings, and exports their per-question mapping; it never
re-injects freshness items. Missing measurements cause a visible failure.

## Recovered extraction errors

The UTF-16LE live log identifies the TypeError as Graphiti ExtractedEntities(**list),
caused by a malformed model response, not an item-processing argument error.
The adapter now validates extraction instances against the supplied Pydantic
model before returning them and raises the existing retryable EmptyResponseError
for lists and missing required fields (including EdgeDuplicate). No fields or
facts are fabricated. Offline tests cover invalid-list and missing-field recovery.
The graph reader uses fact_embedding exclusively, matching Graphiti's schema.

## Existing eval-v1 verification

Verified current corpus digest matches the original manifest. SQLite has 85
written items and 85 done jobs. The current manifest is already frozen and has
10 freshness entries (the handoff reported an earlier state). Nine contain a
successful answerability lag; 2-fresh / q21 contains three failed historical
probes and a null lag. Its gold item contains ORV-9303-K, so the dataset is
answerable but the system did not establish answerability during those probes.
The full report must retain this failed freshness target; do not re-ingest or
invent a historical timestamp. The corpus remains fictional-only, and recall
uses supporting item IDs rather than separately labelled atomic facts; these
are disclosed limitations relative to the binding benchmark design.


## Evaluation v2 and reviewed scoring rules

The existing eval-v2 snapshot binds to `src/omnistream/eval/corpus/eval-v2.json`
through its manifest, including when the snapshot has a custom name. V1 corpus bytes are unchanged. V2 has
90 fictional records, all manually routing-labelled, and 60 questions with the
15/20/15/10 category counts. Ten independent industrial research networks use
unrelated names, company abbreviations and laboratory initialisms. Bridges span
sponsor-to-grantee, executive-to-visiting-fellow affiliation, and acquisition-target
to-instrument-supplier relations. Two queries require a three-record chain.
Near-name businesses explicitly correct misleading sponsorship and recall claims.
Five acquisition agreements are questioned after cancellation; leadership questions
cover dates before recalls and after appointments. Ten archive deposits are held
back for freshness injection. News/Finance/Research descriptions are generic for
v2; v1 descriptions are preserved. Source formats include wire reports, minutes,
analyst notes, abstracts, filings, interviews and archive notices.

Validate using `python -c "from omnistream.eval.dataset import load_dataset; load_dataset('eval-v2')"`.
`python -m omnistream.eval.build_v2` reproduces the corpus. Validation checks
counts, IDs, routing labels, cross-bubble gold sets and proper-name token shortcuts.
These checks are heuristics, not proof that a question requires graph retrieval.

Retrieval and routing metrics are computed before judgement. Correctness and
faithfulness failures independently leave only that judgement missing; aggregate
means show the partial measured value and expose correctness_errors / faithfulness_errors.
Any failed judgement makes dependent section 8.3 checks UNMEASURED with the count: faithfulness,
changed-fact accuracy, and correctness gains (either configuration). Retrieval-only
checks remain independently measurable. Structured
judge responses retry at most three times on malformed JSON or invalid rubric
values; numeric score strings are accepted. Answer failures remain errors.

Citation extraction preserves decimals and common abbreviations. A claim is the
sentence with citation markers removed. Multiple markers select a union of stored
originals, judged for entailment of precisely the asserted content; omission of
unasserted source details is allowed. External LlamaIndex answers without inline
markers use the union of all returned node sources as one attribution unit.
External documents include titles. Macro faithfulness averages each answer's
faithful/total attribution ratio, with zero-citation answers scoring zero. It is
the section 8.3 metric. Micro faithfulness pools attribution counts. Both are
reported. Native search limits are 10 classic chunks, 20 graph facts and 2 external
nodes (LlamaIndex default); agents can execute multiple searches. Subagent evidence
is deduplicated within bubbles, then interleaved by per-bubble rank before the
item-level top-10 cutoff. Facts precede chunks and item reads within each bubble. With three routed bubbles,
interleaving guarantees representation for each bubble with nonempty evidence in
the top-10; it cannot represent a bubble that returned no evidence.
MRR and Hits@1 use the rank of first gold-or-acceptable evidence, while Recall@10
continues to require gold. v2-q02/09/16/23/30 accept the corresponding fresh record
for the product name; it is not gold. v2-q48/53/58 include full institution names
and abbreviations, with explicit key-fact alternatives accepting either.
Per configuration, `zero_citation_answers` counts all answers with zero citation
attributions; `abstentions` is the conservative rubric proxy of correctness 0
with zero citations (not a separate semantic abstention classifier).

`omni eval calibrate --snapshot eval-v2 --run latest` (or a numeric run ID)
reads only that v2 checkpoint and exports exactly 30 rows, aiming for 10 per
judge score 0/1/2 when available, balancing configurations and question types.
It refuses a checkpoint with fewer than 30 eligible real answers. No run is
launched. The labeling JSONL contains question/answer/reference, alternatives,
an opaque sample ID and blank human_score; configuration and judge_score are
only in the separate `.key.jsonl` join file. Keep the key away from labelers.
Fill human_score with 0/1/2 and run `omni eval calibration-report --snapshot eval-v2`
for exact agreement and Cohen's kappa. Re-export refuses to overwrite human labels.
Until labels exist, reports say `judge calibration: pending human labels (n=30 exported)`
only if a real 30-row file exists; absent samples report pending real sample.
The old v1-derived export was invalid and has been deleted. Current v2 run 8 has
only 15 rows, so a real 30-row export remains blocked until a sufficiently large
v2 checkpoint exists. No full evaluation was run to fill that gap.

Known v1 judge error: own+subagents q23 answered "20 million Orvellan crowns"
against reference "20" and received score 1. The judge prompt now explicitly
accepts equivalent numeric answers with units in the question's scale. This
motivates independent calibration; it does not retroactively change stored scores.
O3 remains unresolved until independent labels are supplied. Run summaries identify
judge/answer models and whether equal; usage reports judge calls separately.

New snapshot example: `.venv\Scripts\omni.exe eval --rows classic --snapshot new-v2 --dataset eval-v2 --limit 1`.
Smoke: `.venv\Scripts\omni.exe eval --rows classic,own,own+subagents --snapshot eval-v2 --limit 5`.
Full run (supervisor only): `.venv\Scripts\omni.exe eval --rows all --snapshot eval-v2`.
Never rebuild or mutate the protected v1 snapshot while its evaluation is running.


## Verified v2 construction (2026-11-12)

Offline: `927 passed, 1 skipped, 21 deselected in 42.83s`.
Integration: `9 passed, 937 deselected in 94.28s` (run before the additional eval-only regression tests).
Ruff: `All checks passed!`.

Real build command: `.venv\Scripts\omni.exe eval --rows classic --snapshot eval-v2 --limit 1`.
Run 7 completed. Snapshot validation passed: matching canonical dataset digest,
90 written items, 90 done queue jobs, 10 recorded freshness probes, frozen=true.
The protected v1 corpus still matches its original snapshot's canonical digest.

Ingestion: 90 written, 0 failed, 0 unsorted; 2,730,481 provider tokens;
USD 0.9272862586 provider-reported cost. Summed pipeline write duration:
10,794.407 seconds. Snapshot construction including freshness probes:
11,357.699 seconds (3h 9m 17.7s). Ingestion routing exact-set accuracy:
57/90 = 0.6333333333, below the 0.85 target. Seven of ten injected updates became
both fully judge-correct and grounded in retrieved evidence within three probes;
three did not, so maximum answerable lag is unmeasured and the freshness target
fails. These are measured system outcomes, retained in the report.

Judge and answering model: `deepseek/deepseek-chat`; equal=true (O3).
Historical calibration export used v1 run 6 and was invalid for v2; removed after review.
No independent agreement result is claimed.

Build check output:
```text
classic v2-q01/1: correctness=0 recall@10=0.000
```


Smoke run 8 completed with 15 pairs and zero harness/judge errors. Snapshot remained frozen with matching dataset digest.

```text
classic v2-q01/5: correctness=0 recall@10=0.000
classic v2-q03/5: correctness=0 recall@10=0.500
classic v2-q04/5: correctness=0 recall@10=0.667
classic v2-q05/5: correctness=0 recall@10=1.000
classic v2-q07/5: correctness=2 recall@10=1.000
own v2-q01/5: correctness=0 recall@10=0.000
own v2-q03/5: correctness=0 recall@10=0.000
own v2-q05/5: correctness=0 recall@10=0.000
own v2-q04/5: correctness=0 recall@10=0.333
own v2-q07/5: correctness=1 recall@10=1.000
own+subagents v2-q01/5: correctness=0 recall@10=0.000
own+subagents v2-q03/5: correctness=0 recall@10=0.000
own+subagents v2-q05/5: correctness=0 recall@10=0.000
own+subagents v2-q04/5: correctness=0 recall@10=0.000
own+subagents v2-q07/5: correctness=2 recall@10=1.000
```

Report: `docs/eval/eval-v2-20261112T042405204307Z.md`.
The full v2 evaluation was not run.


## section 8.3 ingestion routing table notes

`ingestion_routing_accuracy` retains the spec's exact-set agreement and original
manual labels; labels are never revised after observing routing. Supplemental
`ingestion_primary_label_recall` is the fraction whose labelled bubble is assigned;
`ingestion_wrong_routing_rate` is the fraction missing the label;
`ingestion_over_assignment_rate` is extra assigned bubble count divided by item
count (it can exceed one). `ingestion_over_assignments_by_category` shows item and
extra-assignment counts by item category. These measurements are included in
Markdown global measurements and configuration CSV, alongside the exact-set target.


## Review polish verification (2026-11-12)

Both frozen manifests were migrated after DB/raw verification; no ingestion was
performed. V2 retains exact-set routing accuracy 57/90 = 0.6333333333; primary-label
recall is 1.0, extra assignments/items is 33/90 = 0.3666666667, and wrong-routing
rate is 0.0. Category extras: appointment 7, cancel 1, deal 2, decoy 7, fresh 0,
funding 9, leader 7, recall 0, study 0 (10 items per category).

The requested two-question classic smoke was attempted as run 9. It verified the
frozen item/queue state, then stopped before answers because Neo4j returned
`Neo.ClientError.Security.Unauthorized` (authentication failure). No credentials
were inspected or changed. This is not a successful smoke result. Report:
`docs/eval/eval-v2-20261112T044200320071Z.md`.
Calibration run 8 export refused with `Need 30 real v2 rows from one run; found 15`.
No synthetic or repeated rows were used to fill the real labeling artifact.

Final verification output:
```text
954 passed, 1 skipped, 21 deselected in 68.85s (0:01:08)
9 passed, 967 deselected in 103.73s (0:01:43)
All checks passed!
```
