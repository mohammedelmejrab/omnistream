# OmniStream improvement log

A running record of every change, issue, setback and fix made while improving the
system after the first full evaluation (eval-v2, 12 Nov 2026). Newest entries are at
the bottom. Numbers are copied from real runs; nothing here is estimated unless it says so.

## Ground rules (set by the project owner, 13 Nov 2026)

1. Use real data, not fake data, and check its quality.
2. Do not overfit: never tune for one specific dataset.
3. Find the causes of poor performance, verify that they are the real causes, then fix them.
   Comparing our method with the methods that did better is one way to do this.
4. Log every change, issue, setback and fix in this file.
5. The project LLM is `deepseek/deepseek-v4.1-flash-1017` on OpenRouter.

How rule 2 is applied: fixes are developed on a development split. A held-out test split is
run only to measure, never to tune. eval-v1 and eval-v2 (both synthetic) are kept only as
diagnostic tools and secondary checks.

---

## Starting point: eval-v2 results (12 Nov 2026, model `deepseek/deepseek-chat`)

Report: `docs/eval/eval-v2-20261112T050602182241Z.md`. 60 questions, 6 configurations.

| Configuration | Recall@10 | Hits@1 | Correctness (0-2) | Multi-hop correctness |
|---|---|---|---|---|
| external (LlamaIndex) | 0.74 | 0.82 | 1.23 | 0.30 |
| classic | 0.83 | 0.77 | 1.37 | 0.50 |
| graphiti | 0.84 | 0.52 | 1.28 | 0.70 |
| own | 0.67 | 0.38 | 1.10 | 0.20 |
| own+subagents (the full system) | 0.52 | 0.22 | 0.93 | 0.00 |
| classic+subagents | 0.86 | 0.63 | 1.47 | 0.90 |

The full system loses to plain chunk retrieval on multi-hop questions. That is the problem
this log is about.

---

## 13 Nov 2026

### Change 1: model switched to `deepseek/deepseek-v4.1-flash-1017`

- `LLM_MODEL` in `.env` changed from `deepseek/deepseek-chat`. `JUDGE_MODEL` was left as
  `deepseek/deepseek-chat`, so the judge is now a different model from the one being judged
  (spec section 12, open issue O3).
- Checked on OpenRouter before switching: the model exists, supports JSON mode and tool
  calling, 1M-token context, $0.15 / $0.60 per million tokens (the old model: $0.32 / $0.89).
- Live check after switching: JSON mode and a tool call both worked, about 1.5 s per call.
- Consequence: the eval-v2 graph was built by the old model. Results from the two models
  must not be mixed in one comparison. A new baseline will be measured with the new model.

### Setback 1: a backup of `.env` was briefly outside `.gitignore`

- While switching the model, a backup copy `.env.bak-20261113` was created. The repository's
  `.gitignore` covers `.env` but not that name, and the file contained the API key.
- It was deleted within the same minute. It was never staged or committed.
- Lesson: no backup copies of `.env` inside the repository.

### Finding 1 (verified from the eval-v2 answers): where each failure happens

Every answer in the eval-v2 run was sorted by the first stage that went wrong. Multi-hop
questions only (20 per configuration):

| Configuration | Correct | Router left out a needed bubble | Evidence not retrieved | Evidence ranked below 10 | Had the evidence, wrong answer |
|---|---|---|---|---|---|
| external | 3 | n/a | 17 | 0 | 0 |
| classic | 5 | 11 | 4 | 0 | 0 |
| graphiti | 7 | 10 | 3 | 0 | 0 |
| own | 2 | 16 | 2 | 0 | 0 |
| own+subagents | 0 | 16 | 3 | 1 | 0 |
| classic+subagents | 9 | 9 | 0 | 1 | 1 |

(Each failed answer is counted once, under the earliest stage that failed.)

- The query router is the most common first failure in every routed configuration.
  Counting all multi-hop questions, including ones answered correctly anyway, it left out a
  needed bubble in 14 to 18 of 20. The bubble it leaves out is usually Finance (9 to 13
  times) and sometimes News (5 to 7).
- Example: for "Which research institution received a grant from the manufacturer whose
  chief resigned following the September brake seal recall?" the router often selects only
  Research. It follows the topic words of the question. The evidence is in News (the recall)
  and Finance (the grant).
- The router is not stable: for 21 of 60 questions it chose different bubbles for the same
  question in different configurations.
- Average evidence found on multi-hop questions (share of gold items retrieved at any rank):
  external 0.39, classic 0.47, graphiti 0.60, own 0.31, own+subagents 0.33,
  classic+subagents 0.71.

This is an observation, not yet proof of cause. A routing miss and a retrieval miss can
both be present in the same question. Experiment plan below.

### Finding 2 (verified in the graph): abbreviations are stored as separate entities

- "Halvex Mobility" is linked across all three bubbles, but "HVM" (its abbreviation, stated
  in the source text) is a separate entity. In the Research bubble the funding facts are
  attached to "HVM", so the path from the recall to the grant is broken.
- Extraction also produced wrong facts, for example "Halvex Mobility RESIGNED_FROM
  Tesselmere Controls", and vague entities such as "supplier".
- How often this happens across the whole graph has not been measured yet.

### Finding 3: eval-v2 is too narrow to tune against

- Its 20 multi-hop questions are 3 question templates repeated over 10 fictional scenarios.
- It is also synthetic data, which rule 1 rules out as the main benchmark.
- Decision: eval-v2 is used only to diagnose. Improvements will be measured on a new
  real-data set with a development split and a held-out test split.

### Plan

1. **Verify causes with controlled experiments** on the eval-v2 snapshot (read-only):
   - give every configuration all three bubbles ("oracle routing") and see how much
     multi-hop accuracy returns. This isolates the router's share of the loss;
   - give the own algorithm the correct starting entities ("oracle seeds"). This isolates
     seeding;
   - route each question three times to measure router instability;
   - count abbreviation/alias splits and wrong facts across the whole graph;
   - record what the subagents actually search for, to explain why classic+subagents does
     well and own+subagents does not.
2. **Collect real data** from real feeds (news, finance, research), and write a quality
   report before using it: text lengths, duplicates, date range, and how many real entities
   appear in more than one bubble.
3. Write questions over the real data, with a development split and a held-out test split.
4. Measure a baseline with the new model, fix the verified causes, measure again.

### Change 2: real-data collector and quality verifier (commit `9556854`)

- New commands `omni realdata collect` and `omni realdata verify`, driven by a committed
  source list. The committed manifest holds only URL, date, source and SHA-256 per item.
  Article text stays under `data/real/`, which git ignores.
- Running real feeds through the C1 source code for the first time exposed three bugs,
  now fixed with regression tests: summaries that were empty markup, HTML left inside API
  bodies, and navigation or hidden page content left in the clean text.

### Setback 2: first real corpus (real-v1) not good enough, held back

Quality report: `docs/realdata/real-v1-quality.md`. 228 items from 18 Sep to 13 Nov 2026:
News 110, Finance 60, Research 58. Median 437 words. 63.6% likely full text.

Why it was not approved:

| Problem | Detail | Decision for round 2 |
|---|---|---|
| Research bubble is weak | arXiv was skipped: the collector applied `robots.txt` to arXiv's official API. Research was left with 81-word blog teasers and off-theme biomedical abstracts | Treat documented public APIs by their own terms of use (arXiv: one request per 3 s). Rebuild Research around arXiv abstracts |
| Finance filings are thin | SEC 8-K filings were collected without their press-release exhibits, where the figures are | Fetch the exhibits; widen to about 20-25 technology issuers |
| Off-theme news | 27 NASA items | Drop NASA; add on-theme public-domain and openly licensed sources (FTC, DOJ, NIST, European Commission, EFF, Wikinews and others, each checked for its terms) |
| Too small | 228 against a target of 250-400 | Target 300-400, no bubble under 25% |
| Entity statistics unreliable | Local name extraction was 65% precise by hand check | Use the project LLM for the statistics, hand-check 30 items again |

What was good: 0 exact duplicates kept (61 rejected), dates handled, and one real changed
fact already confirmed by reading the items: an NVIDIA blog post of 23 Oct names the CEO,
and an SEC filing of 12 Nov reports his resignation and a successor.

Round 2 is recorded as `real-v2`; real-v1 files are kept for the record.

### Setback 3: OpenRouter key reached its spending limit

- During the diagnosis experiments the OpenRouter key stopped working. Checked through
  OpenRouter's key endpoint: the key has a 5.00 USD limit and 5.008 USD used
  (0.59 USD of it on 13 Nov). The limit has no automatic reset.
- Effect: every step that calls the LLM is blocked until the limit is raised. That covers
  the remaining diagnosis experiments, the entity statistics for the real corpus, graph
  ingestion and all evaluation runs.
- Mitigation: the diagnosis was told to finish everything that needs no LLM (router code
  analysis, graph connectivity, alias splits, seed and ranking traces with local
  embeddings), to keep the model results already collected, and to make the rest
  resumable so no work is repeated.
- Needs the project owner: raise the key's limit on openrouter.ai.

### Change 3: second real corpus (real-v2), approved with two caveats

Quality report: `docs/realdata/real-v2-quality.md`. 350 real items, 18 Sep to 12 Nov 2026.

| Measure | real-v1 | real-v2 |
|---|---|---|
| Items | 228 | 350 |
| News / Finance / Research | 110 / 60 / 58 | 115 / 115 / 120 |
| Full articles or complete abstracts | 63.6% | 95.7% (66.6% articles, 29.1% abstracts) |
| Median words | 437 | 564.5 |
| Exact duplicates kept | 0 | 0 |
| Verified changed facts | 1 | 25 |

- Sources: company blogs (NVIDIA, Microsoft, Samsung), EFF, Mozilla, UK CMA, DOJ, FTC, NIST;
  SEC filings with press-release exhibits for 24 technology companies, SEC releases, Federal
  Reserve; arXiv abstracts (51 from a general query, 51 from a query for named companies),
  Microsoft Research, BAIR.
- Sources that failed and were left out, not replaced with invented items: Commerce/BIS and
  The Conversation (terms could not be verified), Wikinews (blocked by robots.txt), European
  Commission (no on-theme matches), two Mozilla pages (HTTP 403).

Decision: approved for building the question set, with these caveats.

1. arXiv is 85% of the Research bubble, above the 25% per-source cap. The cap is waived for
   arXiv because it is a repository of papers by independent authors, not one publisher.
2. 21 of the 25 verified changed facts come from one company (TSMC monthly figures). The
   time-sensitive questions must not lean on them: more varied changed facts have to be
   found while writing questions.
3. Not yet measured, blocked by the API key limit (setback 3): LLM-based entity statistics
   (cross-bubble entities, how many appear under several names).
4. 101 of the 350 items are dated in the last 4 days of the window (mostly arXiv).

### Finding 4: controlled diagnosis on eval-v2 (commit `b0089a7`)

Full report: `docs/diagnostics/eval-v2-diagnosis.md`. Each suspected cause was tested by
changing one thing at a time on the frozen eval-v2 snapshot, with the new model, without
modifying the system. Spent 0.74 USD before the key limit was hit. 111 of 370 planned
answer cells were judged; the rest are marked NOT YET MEASURED and can be resumed with
`python -m omnistream.eval.diagnostics.resume`. Results that needed no LLM are complete.

Same-model baseline on the 20 multi-hop questions: classic 4/20 fully correct,
graphiti 4/20, own 1/20.

| Suspected cause | Verdict | Evidence |
|---|---|---|
| 1. Own mode starts from the wrong entities (seeding) | CONFIRMED, largest | 56 of 100 seeds are generic nodes ("research funding agreement", "manufacturing divisions"). Giving own the correct starting entities raised full evidence coverage from 1/20 to 14/20 questions |
| 2. Fusion pushes relevant facts out of the top 20 | CONFIRMED | With correct seeds, 5/20 questions still lose a gold item. The best fact by relevance (rank 1) drops to fused rank 21-24 because recency and confidence get equal weight. Confidence is 0.92 for 378 of 381 facts, so it adds noise, not signal |
| 3. Graph defects (missing entities, wrong merges, alias splits) | CONFIRMED, overlapping | 13/20 questions are exposed to at least one. All 20 abbreviations stated in the texts ("HVM, the abbreviation used by Halvex Mobility") are separate unlinked entities. 2 wrong merges. 19 of 100 sampled facts are wrong (mostly wrong direction or subject). 33% of entities are generic phrases, not names |
| 4. "Current facts only" filter hides needed historical facts | CONFIRMED | In 3/20 questions the January appointment that identifies a person is filtered out because a later change made it historical |
| 5. Event-relative time ("immediately before the September recall") | CONFIRMED | All 14 measured time-sensitive failures are this phrasing. The router returns no time scope, so the answer prompt says "prefer the most recent statement" - the opposite of what is asked |
| Query router leaves out needed bubbles | REJECTED for the new model | With the new model the router omitted a needed bubble in only 4 of 300 trials. Forcing all bubbles did not improve recall. Yesterday's routing finding (Finding 1) was a property of the old model |
| 500-edge expansion cap | REJECTED | No query reached it |
| Why classic+subagents does better | NOT YET MEASURED | Code-level reason: classic `search` matches query text against passages, so a search without a company name still finds the right passage. Own `search` needs an entity name to seed from; queries naming no entity land on generic neighbourhoods |

Why graphiti beats own: graphiti searches fact text directly (hybrid search), so it does not
depend on finding the right starting entity. That is the same weakness as cause 1.

Correction to Finding 1: the router was the most common first failure with the old model
(`deepseek-chat`), but not with the new one. Router fixes are therefore not a priority.

### Plan for fixes (general mechanisms, not tuned to eval-v2)

1. Seeding: seed from fact text and passages as well as entity names, and stop generic
   phrases from taking seed slots.
2. Fusion: weight relevance above recency and confidence.
3. Graph: merge abbreviations and aliases that the source text states explicitly, during
   ingestion. Reduce generic entities.
4. Time: support event-relative questions ("before X") and do not hide historical facts
   when the question is about the past.

Each fix will be developed on the real-data dev split and checked on eval-v2 as a
secondary check. The real-data test split is used only for the final measurement.

### Budget

OpenRouter key limit raised to 14 USD by the owner on 13 Nov; 8.99 USD available at this
point. Plan: measure the ingestion cost on a few real items first, build a small dev
snapshot for developing fixes, and build the test snapshot once.

### Change 4: real-v2 evaluation plumbing and bounded ingestion probe

- Added a local-text real-v2 loader with explicit dev/test selection, manifest text
  hash checks, disjoint gold validation, freshness hold-back, and deterministic
  background selection (default dev 40 / test 60). Snapshots bind the selected IDs,
  digest, split and background size; CLI forwards `--split` and `--background`.
- Manual routing annotations score C3 without pinning source bubbles. No changes
  to retrieval, answering or ingestion behavior. Shared usage metering now records
  prompt and completion tokens separately in addition to existing totals/costs.
- Added a ten-item fixed-seed probe (3 News / 3 Finance / 4 Research, including two
  SEC exhibits and two long blog posts), conservative $0.55 request budget guard,
  durable per-item measurements, and scoped cleanup. It never builds a full snapshot.
- Measurement is pending credentials: LLM_API_KEY is absent from the process
  environment and the task forbids opening `.env`; a private credential request was
  made and timed out without delivery. No LLM requests were sent, actual spend $0.00.
  Read-only Neo4j verification:
  zero nodes for `real-v2-costprobe`, and no throwaway snapshot directory.
- Finding: the existing snapshot API-item path writes one Graphiti episode per
  routed bubble, not 1,500-token document-upload parts. The probe records actual
  episode counts plus the hypothetical C1 document split count separately. This
  behavior was left unchanged; it limits transfer to document-upload ingestion.
- The current question file has 60 test questions and no dev questions. The loader
  rejects an empty split. Projection inputs: hypothetical dev 120-item fixed-seed
  sample 132,534 words; actual test selection + background 60 has 140 items and
  170,065 words; full corpus 350 items / 456,032 words. Ingestion USD projections
  remain unmeasured. Recorded eval-v2 costs, repriced under an explicit token-mix
  scenario with unchanged deepseek-chat judge, imply $0.601318 for a 60-question,
  six-configuration run, excluding shared overhead. Report:
  `docs/realdata/real-v2-ingestion-cost.md`.
- Final offline validation: `1021 passed, 1 skipped, 21 deselected in 43.57s`;
  ruff clean. Full captured output: `docs/realdata/real-v2-ingestion-tests.txt`.
  No commits and no protected snapshot/diagnostic/question artifacts modified.

### Setback 4: the new model "thinks" before answering, which broke ingestion

- First cost probe (one 2,139-word NVIDIA blog post through the real pipeline): 17 LLM calls,
  213,928 completion tokens (about 12,600 per call), 0.14 USD, 23 minutes, and the item
  FAILED. The probe stopped there and cleaned up after itself (0 nodes left).
- Verified cause with a single small extraction call:

  | Request | Time | Completion tokens | Of which hidden reasoning | Valid JSON |
  |---|---|---|---|---|
  | default | 12.2 s | 1,654 | 1,379 | yes |
  | reasoning switched off | 1.6 s | 330 | 0 | yes |
  | reasoning effort "low" | 6.5 s | 1,352 | 1,048 | yes |

- `deepseek/deepseek-v4.1-flash-1017` reasons by default; the old `deepseek-chat` did not.
  With reasoning on, a long document's extraction calls most likely ran out of their output
  budget before finishing the JSON.
- Fix in progress: a project setting for reasoning (default off) applied to every LLM call
  path, plus treating truncated completions as retryable failures. The cost probe will be
  re-run after the fix.
- Also logged by the probe: the snapshot builder writes one Graphiti episode per routed
  bubble rather than splitting long documents into ~1,500-token parts. Left unchanged for
  now; it affects long items.

### Change 5: explicit reasoning policy and truncated-response recovery

- Added `OMNI_LLM_REASONING` and independent `OMNI_JUDGE_REASONING`, both
  defaulting to `off`; effort levels and `provider_default` are supported.
  `OMNI_LLM_SEND_REASONING_PARAM=auto|always|never` defaults to an exact
  `openrouter.ai` hostname check. See `docs/llm-reasoning.md` for wire mappings.
- One shared request policy covers structured extraction, chat/JSON/answer,
  tools, routing, production citation entailment, eval judges, Graphiti, and
  LlamaIndex. Graphiti wraps its SDK completion resource so its own request
  construction and four-attempt retry loop remain intact.
- Length-truncated completions are logged and rejected before parsing JSON or
  tool arguments. Shared usage reports now include hidden reasoning tokens
  without counting them twice in total completion usage.
- Serialized transport tests exercise all paths under OpenRouter auto,
  generic auto/always, never, and provider-default policies; truncation tests
  cover resampling and exhausted retries. Existing replay expectations include
  the new default field. Offline suite: 1053 passed, 1 skipped, 21 deselected;
  ruff clean. Additional focused exhaustion/missing-details tests added afterward.
- Live verification pending a private credential delivery; the process has no
  LLM credential and `.env` was not accessed. Added the bounded
  `scripts/verify_reasoning.py` (128 output tokens/request, ten-call hard cap,
  no ingestion). Actual spend so far: $0.00.

### Change 6: reasoning control for the new model (fix for setback 4)

- New settings `llm_reasoning` and `judge_reasoning` (default `off`), sent as OpenRouter's
  `reasoning` request field; endpoint gating `auto|always|never` (auto = only for
  openrouter.ai, since other OpenAI-compatible providers may reject unknown fields).
  Documentation: `docs/llm-reasoning.md`.
- Applied through shared code to every LLM call path. A truncated completion
  (`finish_reason == "length"`) is now retried instead of parsed as broken JSON.
  Reasoning tokens are recorded in usage metering.
- Verified live on all 8 call paths (structured parse, chat, chat_json, answer, tool
  calls, judge, Graphiti, LlamaIndex baseline): 0 reasoning tokens, every call finished
  with `stop`. Cost of the check: 0.00007 USD. Offline suite: 1,053 passed.

### Change 7: real-v2 questions written, independently verified, repaired

- 87 questions over the real corpus (test 60, dev 27; dev is 3 short because few genuine
  cross-bubble links and changed facts stay inside the dev companies). Written by one model
  from the source texts (`docs/realdata/real-v2-questions-report.md`).
- Checked one by one against the sources by a different model
  (`docs/realdata/real-v2-questions-verification.md`): 54 OK, 3 fixed (wrong bubble label),
  27 flagged, 3 rejected.
- Most flags were labelling issues, not wrong answers: a second item also supports the
  answer but was listed as a distractor (it would have penalised correct retrieval), or a
  linking item also mentions a company from the other split. Genuine problems: 3
  multi-hop questions answerable from one item (rejected), 2 time-sensitive questions whose
  two versions carry the same date, 1 answerable from general knowledge (Apple's CEO).
- Repair in progress: accept alternative supporting items as valid evidence, sharpen
  ambiguous wording, and exclude genuinely invalid questions from scoring with a reason
  (kept in the file, never deleted).


### Change 8: own fact seeding and relevance-weighted fusion (2026-11-13)

- Implemented P1/P2 mechanisms from Finding 4: ten fact-text vector matches seed
  endpoints, proper-name guard, five distinct name identities after dedup/refill,
  and 2:1:1 weighted RRF dropping near-constant auxiliary signals (CV < 1%).
  Two-hop expansion, 500-edge cap, PPR 0.85 and top20 are unchanged. No BM25.
- Controlled offline eval-v2: 1,200 cells / all 60 questions / recorded and all-bubble
  routes / baseline, F1, F2, F1+F2 and six fixed sensitivity settings. E0 routes
  only exist for 35 questions; remaining 25 reuse labelled E2 repeat-0 routes.
  Reproduced all four E0 retrieval metrics on 35/35 comparable questions.
- Current-route multi-hop Recall-any 0.308 -> 0.533; full coverage 1/20 -> 6/20.
  All-question Recall-any 0.644 -> 0.803; full coverage 29/60 -> 42/60.
  Regressions retained: four multi-hop recall losses, freshness MRR 0.858 -> 0.475.
  All-bubble full coverage 32/60 -> 39/60. Defaults were not tuned after results.
- Answer-level 35-question run BLOCKED: no LLM_API_KEY in process environment;
  private credential request timed out. No .env access, LLM calls or spend ($0.00).
  No correctness gain inferred; E0 own/classic remain historical comparisons.
- Full offline suite: 1080 passed, 1 skipped, 21 deselected in 99.04s. Snapshot
  integrity 107/107 hashes unchanged. Read-only Neo4j; no commits.
- This requested eval-v2 check is synthetic, built by the old extraction model;
  real-data dev validation remains outstanding and no real test data was used.
  Report: docs/diagnostics/own-fixes-eval-v2.md. Durable measurements and paired
  deltas: data/diagnostics/own-fixes/. Baseline source fixture and resumable
  measurement/audit/report modules: src/omnistream/eval/diagnostics/own_fixes*.

### Result: cost probe after the reasoning fix

Same pipeline, same items, reasoning switched off (Change 5):

| Item | Before (reasoning on) | After (reasoning off) |
|---|---|---|
| NVIDIA blog post, 2,139 words | failed, 0 facts, 0.14 USD, 23 min | written, 52 entities, 62 facts, 0.005 USD, 39 s |
| NVIDIA blog post, 1,569 words | not reached | written, 56 entities, 63 facts, 0.005 USD, 38 s |
| NVIDIA blog post, 589 words | not reached | written, 31 entities, 34 facts, 0.001 USD, 18 s |
| ARM 6-K exhibit, 272 words | not reached | failed after 10 calls (see below) |

- Measured cost: about 0.003 USD per 1,000 words, 0 reasoning tokens. Projection from the
  manifest's word counts: full 350-item corpus (456,032 words) about 1.50 USD; a dev
  snapshot of about 120 items well under 0.50 USD.
- Setback 5: the ARM exhibit failed once in the probe. Ingested alone afterwards, the same
  item was written on the first attempt (route confidence 0.97), so the failure is
  intermittent (most likely one malformed LLM response that used up the per-call retries),
  not systematic. The probe stops at the first failure by design, so 6 of 10 items were not
  measured. In a real snapshot build the queue retries a failed item up to 5 times and the
  snapshot refuses to freeze if any item is still failed, so an intermittent failure cannot
  silently drop data. Watch the failure rate in the first real snapshot build.
- Reproducibility limitation found during regression QA: fresh retrieval changed
  seed/rank outputs in 6/44 replayed regression cells. Cause not isolated. Main
  table retains the original paired pass; downstream audit replays captured
  seed IDs and requires matching rankings. Raw replay evidence is retained.

### Change 9: own-mode fixes, round 1 (commit `f9caa47`)

Addresses causes 1 and 2 of Finding 4. Report: `docs/diagnostics/own-fixes-eval-v2.md`.

- Seeding: also seed from facts whose text matches the question (endpoints of the top-10
  matching facts), keep generic entities out of name-seed slots, refill the seed budget
  after merging duplicate identities.
- Fusion: weighted RRF (relevance 2 : recency 1 : confidence 1); near-constant signals
  dropped. The spec says plain RRF; weighted RRF is a documented deviation.

Offline retrieval on eval-v2 (no LLM, local embeddings), own mode:

| | Before | Round 1 |
|---|---|---|
| Multi-hop recall | 0.308 | 0.533 |
| Multi-hop questions with all evidence | 1/20 | 6/20 |
| All 60: recall | 0.644 | 0.803 |
| All 60: all evidence | 29/60 | 42/60 |
| Freshness MRR | 0.858 | 0.475 (regression; gold still found 10/10) |

Also lost: some recall on 4 multi-hop questions. A replay of the 44 regression cells gave
different results in 6.

### Setback 6: independent review of round 1 found an overfitted rule

- The "is this a real name" rule (a word must start with a capital letter) reflects how the
  extractor happened to case words in eval-v2. It rejects real names (eBay, iPhone, arXiv,
  x86, every Chinese or Arabic name) and accepts capitalised generic phrases. This breaks
  the no-overfitting rule, so it is being replaced.
- Other findings: seeds from fact matches have no cap and full weight (generic hubs come
  back); the fact search pulls every fact embedding per query, which will not scale to the
  real corpus; the freshness drop happens because old versions of a fact match as well as
  the current one and get boosted.
- Round 2 in progress: entity-type-based seedability (from ingestion, not casing), capped
  and score-weighted seeds, a fact vector index with bounded queries, grouping of fact
  versions with the newest preferred, deterministic replays. Measured offline again before
  any paid run.

### Setback 7: OpenRouter account out of credit (not the key limit)

- 13 Nov, 14:16-14:21: a full eval-v2 run (run 13) and the real-v2 dev snapshot build both
  failed on almost every request with HTTP 402 "Insufficient credits".
- Cause: the account had 5.00 USD of purchased credit and 5.20 USD used. The key's 14 USD
  limit is only a cap; it does not add money. Calls fail once the purchased balance is gone.
- Effect: dev build stopped at item 3 of 76 (3 written, 64 failed); eval run 13 is invalid
  and must not be reported. Almost no money was spent, since requests were refused.
- Harness flaw found: provider errors were scored as correctness 0 and recall 0, so a run
  that never got answers looked like a real result with all scores at zero. To fix:
  provider errors must be marked unmeasured and excluded, and a run with a high error rate
  must be flagged invalid.
- Needs the project owner: buy credit on OpenRouter (about 10 USD for the remaining work).

### Change 10: the evaluation harness no longer scores provider errors as wrong answers

- Fix for the flaw found in setback 7. A question whose answer or retrieval failed with a
  provider or transport error is now "unmeasured": left out of every metric, counted in an
  errors column.
- A run with more than 10% unmeasured questions in any configuration is labelled INVALID
  RUN, and its spec section 8.3 checks become UNMEASURED instead of FAIL.
- On HTTP 401/402/403 (auth or credit) the run stops launching calls and saves its
  checkpoint; `--resume` retries the unmeasured questions.
- Answer, agent and judge calls now send explicit max_tokens caps (4096 and 1024). Some
  calls had sent no cap, so the provider saw up to 131,072 tokens.
- Check: run 13 re-aggregated with the fixed code says INVALID RUN, 302 unmeasured pairs,
  all HTTP 402. The original report is kept next to it for the record.


### Change 11: own retrieval fixes, round 2 (commit `336cdbd`)

- Replaced casing-based name eligibility with the shared ingestion ontology:
  seven named types seed; Concept/untyped/unknown types do not. Same rule for
  name/fuzzy/fact endpoints. Language/script counterexamples are covered.
  Read-only audit: all 283 eval-v2 nodes have SAME_AS (all 94 generic nodes too),
  so linkage alone is uninformative. Types exclude 52/94 generic and 12/189
  manually non-generic nodes; 42 generic nodes remain eligible through their
  ingestion types. Max degree 20; no eval-specific hub threshold was selected.
- Cap all distinct seed identities at 10; PPR restart mass follows seed scores.
  Five/fifteen sensitivity is recorded, defaults unchanged after measurement.
  Names/fuzzy candidates are bounded; fact endpoints are hydrated by UUID only.
- New C4 snapshots provision configured relationship cosine vector index
  (384 dimensions by default), IF NOT EXISTS. Fact ANN overfetches 5k/15k/25k,
  filters group/validity in Cypher, and records paths/times. Exact replay and
  missing-index fallback score inside Neo4j and transfer only bounded results.
  Existing indexes are checked by configured name/schema/metric before score
  conversion. Settings/writer/protocol plumbing was needed for these contracts.
  Graphiti 0.31.2 supplies edge_name_and_fact fulltext, not this vector index.
  BM25 considered, left for a separate hybrid ablation. No application DDL run.
- Before fusion, group fact versions by global endpoint identities and normalized
  relation (or >=.95 fact cosine within the same endpoint pair), choose latest
  valid assertion. Preserve full version/provenance objects in diagnostics.
  Point queries select the version valid then; intervals retain overlapping
  versions. This does not repair router scopes or wrong ingestion identities.
- Replace CV-based signal dropping with six-decimal rounding; rare corroboration
  remains informative. Stable graph ordering and exact-path score/UUID ordering;
  redundant pipeline dedup removed, pipeline documentation and neutral tests updated.
- 1,080 offline cells: 60 questions x two route policies x nine configurations.
  All use local embeddings, frozen clock, blocked LLM SDK calls. Exact-path paired
  baseline / round1 / round2 recorded-route recall .678/.794/.800, Recall@10
  .661/.786/.772, full 31/41/39 of 60, MRR .444/.424/.553, Hits@1
  .267/.183/.350. Freshness MRR .858/.475/1.000. Grouping alone leaves freshness
  .475; do not attribute the combined gain to that change alone. Historical ANN
  results remain separate; exact-path differences are not implementation gains.
- Regressions: paired exact combined worsens at least one metric in 16 current /
  13 all-bubble cells vs baseline, 14/14 vs round1. Every signed per-cell delta,
  including historical-reference comparisons, is retained. Full coverage and
  Recall@10 regressions versus round1 are explicit; no generalization claim.
- Independent exact replays: 0/44 changed seeds/fact ranks/item ranks (round1
  previously 6/44). Fact path, 60 uncached queries: ANN mean 49.10 ms, median
  24.87 ms; exact mean 14.99 ms, median 14.23 ms. Small synthetic graph, concurrent
  database activity; no large-corpus scaling/latency claim.
- Validation: full offline 1108 passed, 1 skipped, 22 deselected in 101.30s;
  retrieval-focused 149 passed; isolated Neo4j container integration including
  bounded refill 1 passed. Initial old-contract mocks were repaired; concurrent
  unrelated Judge/token-cap failures on an earlier pass are retained in logs.
- No commits, paid LLM calls, web searches, .env access, application graph writes,
  snapshot writes or process termination. E0 historical hash check: 104/105
  non-ephemeral files match; chroma/chroma.sqlite3 differs since E0 (not a
  task-start comparison, origin unestablished). This task never opened Chroma.
  SQLite WAL/SHM sidecars were excluded from that historical check.
- Report: docs/diagnostics/own-fixes-round2.md. Raw measurements, signal inventory,
  replays, historical/exact paired deltas and timings: data/diagnostics/own-fixes-round2/.
  Real-data dev validation and answer-level evaluation remain outstanding;
  the concurrently owned real snapshot and real test split were not used.

### Setback 8: independent review of round 2 found two more problems

- Name matching: any entity sharing the first three letters of any question word
  ("the", "com", "inc") passed a pre-filter, and the list was then cut at 100 by ID order.
  On a large corpus the entity the question names could be cut.
- Version grouping removed facts that are still valid: it kept only the newest fact per
  (subject, object, relation), so co-existing facts (two quarterly results, two stake
  purchases) collapsed. It also merged across bubbles, and it was order-dependent.
- Smaller: facts whose two endpoints are generic no longer contributed seeds (a likely cause
  of full coverage dropping 41 -> 39 between rounds 1 and 2); seed scores from different
  sources were on different scales; an incompatible index crashed instead of falling back.
- Round 3 in progress: full-text-index name ranking with stopwords removed; collapse only
  true supersession (an older fact explicitly replaced), never across bubbles; generic
  endpoints of strong fact matches may seed at reduced weight; normalised seed scores.

### Change 12: event-relative time intent (fix for Finding 4 cause 5 / E8)

- Problem (verified in E8): all 14 measured current time-sensitive failures are
  'immediately before the September recall' questions. QueryRouter._parse_scope
  correctly refused to guess an event-relative date and returned time_scope None;
  graph retrieval then defaulted to 'facts valid now' (the historical predecessor
  fact was filtered out), and generate_answer added 'Answer for now: prefer the
  most recent statement valid now' - the opposite of what the question asks.
- General mechanism (no dataset-specific tuning):
  1. Router returns a structured hint alongside time_scope:
     RoutingDecision.temporal_relation ('before' | 'after' | 'at' | None) and
     anchor_event (event description from the question). The routing LLM's JSON
     schema gained temporal_relation/anchor_event fields (primary source), and a
     deterministic cue check is a safety net for missing/invalid LLM fields.
     Cues: immediately/just/right/shortly before, before, prior to, until, till;
     immediately after, after, since, following, in the wake of, subsequent to;
     at the time of, when <event> happened; role succession without an anchor:
     previously, formerly (not 'formerly known as'), former, predecessor,
     preceded, previous <role>. Rule for anchors: they must name a specific
     event (at least one capitalised character - proper name, month, acronym),
     so 'What happened before markets opened?' produces no hint; pure calendar
     anchors ('before September 18') and 'since when/until when' stay on the
     unchanged explicit-date path. time_scope remains None when no date is given,
     and an explicit date scope suppresses the hint entirely.
  2. Retrieval: qa.answer_question converts an event hint with no date into an
     explicit unbounded TimeScope(None, None) ('any time') and threads it through
     the dispatcher and subagents instead of the None = 'valid now' default. The
     existing store/own APIs already express unbounded scopes (neo4j _VALID with
     now=null, memory_store fact_in_scope, graphiti overlap, own expand/seeding/
     versions), so own expansion, fact seeding and graphiti filtering now keep
     historical facts (valid_at/invalid_at any); classic applies no cutoff for an
     unbounded scope. The agents' facts tool maps an unbounded routed scope to
     sentinel bounds (datetime min/max) because stores' facts_about treats None
     bounds as 'valid now'.
  3. Answer prompt: generate_answer replaces the 'Answer for now' instruction,
     when time_scope is None and temporal_relation is set, with an instruction
     matching the relation: identify the event's date from the evidence, then
     answer with the statement valid immediately before / after / at the time of
     the event; mention both when ambiguous. Existing as-of/now/interval
     instructions are unchanged.
- Offline tests added: tests/unit/test_event_relative.py (68 tests): deterministic
  cue detection over many phrasings, the specificity rule and its false positives,
  LLM JSON field parsing and fallback, explicit-date precedence, retrieval
  threading (simple and subagents), unbounded-scope history inclusion in own
  expansion and graphiti, the facts tool, and answer-prompt selection. Stubs only;
  no paid LLM calls.
- Validation: full offline suite 1172 passed, 4 failed, 1 skipped, 22 deselected.
  The 4 failures are in concurrently edited files outside this task
  (neo4j_store.py ANN shortfall fallback, own_algorithm/versions.py, own_algorithm/
  seeding.py) and their tracebacks never touch this change's files. Ruff clean.
- No commits, no .env access, no data/** changes.
- Supervisor note on the change above (commit `01f7eae`): the deterministic safety net
  decides that an anchor names a specific event when it contains a capital letter
  ("before the September recall" yes, "before markets opened" no). That is a casing
  heuristic of the kind criticised in setback 6. It is acceptable here only because the
  LLM's own `temporal_relation` field is the primary signal and the cue check is a backup;
  it would mis-handle caseless scripts. Revisit if the real-data dev set shows misses.
  Offline suite after the change: 1,189 passed.


### Change 12: own retrieval fixes, round 3 (2026-11-13)

- Name candidate retrieval now uses Graphiti's existing Entity fulltext name
  index with escaped, parameterized content-word terms, score ranking and bounded
  output. Read-only SHOW INDEXES confirms node_name_and_summary. If unavailable,
  rank by whole-word overlap then fuzzy score before capping; removed prefix/UUID
  truncation. Fixed English stopwords/legal suffixes are declared general rules.
- Version grouping now requires same bubble/local endpoints/normalized relation
  and near-identical fact text. Differing numbers/quarters/amounts/months are
  retained unless explicit validity proves replacement. Deterministic complete-link
  families compare every member. Every interval, including two open bounds, keeps
  all overlapping facts. Removed cross-bubble/global-identity and relation-only
  collapse; preserved source provenance. No additional recency tuning.
- Generic endpoints of positive top-10 fact matches can seed at 0.5 times the
  normalized fact rank score. Each source uses reciprocal dense ranks before
  cross-source capping/weighting; reserve half the ten-identity cap for fact seeds,
  then refill by score. Sensitivity 0.25/1.0 measured; default stays 0.5.
- Incompatible vector indexes warn and use exact cosine. ANN shortfall after
  bounded refill warns and falls back to exact for both fact and entity search.
  Neo4j 5.26.33 SHOW PROCEDURES has no vector-call filter argument. No application
  index/schema writes; integration DDL runs only in disposable testcontainers.
- 960 exact offline cells: all 60 questions, fixed recorded and all-bubble routes,
  baseline/round1/round2/round3, two weight sensitivities, two counterfactuals.
  Frozen-source baseline/round1/round2 reproduce round-two exact aggregates.
  Recorded recall .678/.794/.800/.839; R@10 .661/.786/.772/.831;
  full 31/41/39/42 of 60; MRR .444/.424/.553/.571; Hits@1
  .267/.183/.350/.350; freshness MRR .858/.475/1.000/1.000.
- All-bubble round2 -> round3 recall .800 -> .800, R@10 .772 -> .800,
  full 38 -> 37/60 (regression), MRR .542 -> .564, Hits@1 .350 unchanged,
  freshness 1.000 unchanged. Every regression retained: 13 recorded, 13 all-bubble.
  q20/q54 all-bubble gold loss is final top20 displacement, not missing expansion.
  Counterfactuals and per-cell seed changes document ranking interactions.
- Sensitivity recorded .25/.5/1.0: recall .839 throughout, full 42 throughout,
  MRR .563/.571/.580. All-bubble recall .808/.800/.800, full 38/37/37,
  MRR .567/.564/.573. No threshold/default changed after observing outcomes.
- Independent uncached graph replay: 0/44 changed seeds/fact ranks/item ranks.
  Exact fact search: mean 12.79 ms, median 12.13; fulltext name search including
  index discovery: mean 5.95 ms, median 5.59; 60 queries each. Small synthetic
  graph/concurrent activity; no large-corpus scaling claim.
- Full offline: 1189 passed, 1 skipped, 22 deselected in 102.96s; integration
  -m integration: 10 passed, 1199 deselected in 130.73s. Final focused 63 passed;
  owned-file ruff clean. Full suite includes concurrent event-relative changes.
  Early focused pass found four old-contract expectations; updated over-merge
  assertions/ANN mock responses and preserved both-source seed tagging. An initial
  measurement attempt stopped on a Python parameter-name collision in lexical
  query plumbing; corrected to lexical_query and reran the complete paired pass.
- No commits, web search, paid calls, .env access, snapshot or application graph
  writes. OpenCode-owned router/QA/runtime/modes/tools files were not edited here.
  Recorded routes stay fixed; concurrent event-relative routing is not credited
  as a retrieval gain. Answer evaluation and real-data dev validation outstanding.
- Report: docs/diagnostics/own-fixes-round3.md. Raw exact cells, replays, schema
  verification, paired deltas, regression reasons and test outputs:
  data/diagnostics/own-fixes-round3/. Reproducible measurement/report modules:
  src/omnistream/eval/diagnostics/own_fixes_round3*.py; round-two sources frozen
  from 336cdbd in own_fixes_round2_sources.json.

### Change 13: own-mode fixes, round 3 (commit `22cb706`) - reviewed clean

Report: `docs/diagnostics/own-fixes-round3.md`. Independent review: clean.

- Entity names found through the full-text index (stopwords removed, Lucene-escaped,
  passed as a query parameter); the fallback ranks by whole-word matches.
- Fact versions collapse only on true duplicates or explicit replacement, never across
  bubbles; any time interval, including an open one, keeps every version.
- Generic endpoints of the top fact matches may seed at half weight; seed scores are
  normalised per source; index problems fall back to exact search.

Offline retrieval on eval-v2, own mode, all 60 questions (exact search path):

| Routing | Version | Recall | Recall@10 | All evidence | MRR | Hits@1 | Freshness MRR |
|---|---|---|---|---|---|---|---|
| As routed | Baseline | 0.678 | 0.661 | 31/60 | 0.444 | 0.267 | 0.858 |
| As routed | Round 1 | 0.794 | 0.786 | 41/60 | 0.424 | 0.183 | 0.475 |
| As routed | Round 2 | 0.800 | 0.772 | 39/60 | 0.553 | 0.350 | 1.000 |
| As routed | Round 3 | 0.839 | 0.831 | 42/60 | 0.571 | 0.350 | 1.000 |
| All bubbles | Baseline | 0.689 | 0.689 | 32/60 | 0.464 | 0.317 | 0.858 |
| All bubbles | Round 3 | 0.800 | 0.800 | 37/60 | 0.564 | 0.350 | 1.000 |

- 13 questions per routing policy get worse on at least one measure; each is listed with its
  reason in the report. Replays: 0 of 44 differ. Search time: facts 13 ms, names 6 ms.
- Correction from the review: with the stricter rule, version grouping almost never fires,
  so the freshness recovery comes from the other round-2/3 changes (weighted, capped seeds
  and rounding), not from grouping.
- Known limits: exact-word name search no longer matches misspelled names; the entity
  vector index path usually falls through to the exact scan (latency only).
- These are retrieval numbers on synthetic eval-v2 with a graph built by the old model.
  Answer-level and real-data measurement still to come.

### Setback 9 and fixes: first real-data snapshot build exposed two harness gaps

- A held-back freshness item whose question had been excluded from scoring (rq-d-026) made
  the freshness phase crash (`StopIteration`). Fixed (commit `6835ab6`): such items are
  still ingested, the answerability probe is skipped.
- The ingestion router put 2 of 76 real items in the Unsorted queue (confidence 0.10 and
  0.45, below the 0.5 threshold), which the freeze check did not expect. Fixed (commit
  `cd06b91`): "unsorted" is a valid end state and is reported, never rescued. One of them
  (a Mozilla blog post) is the gold item of dev question rq-d-008, so the system genuinely
  cannot answer it. That is a real router weakness: a product announcement fits none of the
  three bubble descriptions well.
- Both failures were flagged INVALID RUN by the new safeguard (change 10) instead of
  producing fake zeros.

## Results: first answer-level measurements after the fixes (13 Nov 2026)

Both runs completed with 0 unmeasured questions and 0 provider errors. Model
`deepseek/deepseek-v4.1-flash-1017` with reasoning off; judge `deepseek/deepseek-chat`.
Correctness is the judge's 0-2 score, averaged.

### Real data, dev split (24 questions; report `docs/eval/real-v2-dev-20261113T132820897538Z.md`)

| Configuration | Correctness, all | Multi-hop (n=6) | Time-sensitive (n=6) | Changed-fact accuracy | Citation faithfulness |
|---|---|---|---|---|---|
| own+subagents (full system) | 1.75 | 1.67 | 1.67 | 0.83 | 0.84 |
| classic+subagents | 1.75 | 1.67 | 1.67 | 0.83 | 0.90 |
| external (LlamaIndex) | 1.58 | 0.67 | 1.67 | 0.83 | 1.00 |
| classic | 1.54 | 1.17 | 1.33 | 0.67 | 0.92 |
| graphiti | 1.04 | 1.00 | 0.67 | 0.33 | 0.61 |
| own | 0.88 | 0.17 | 0.67 | 0.33 | 0.64 |

- Spec section 8.3, "full system exceeds classic and external by >= 0.3 on multi-hop":
  +0.50 over classic and +1.00 over external on dev. Met, but on 6 questions only.
- Freshness: 4 of 4 scored freshness items answerable 25-34 s after injection.
- Ingestion: 74 written, 2 unsorted (see setback 9).
- There is no "before the fixes" run on real data; the comparison here is between
  configurations measured under identical conditions.

### eval-v2, synthetic (60 questions; report `docs/eval/eval-v2-20261113T123043918544Z.md`)

Compared with the 12 Nov run (old model `deepseek-chat`, before any fix). Two things
changed at once (model and fixes), so the difference is not attributable to the fixes alone;
the comparison between configurations within each run is the fair one.

| Configuration | Correctness 12 Nov | Correctness 13 Nov | Multi-hop 12 Nov | Multi-hop 13 Nov |
|---|---|---|---|---|
| own+subagents (full system) | 0.93 | 1.78 | 0.00 | 1.45 |
| classic+subagents | 1.47 | 1.73 | 0.90 | 1.40 |
| classic | 1.37 | 1.28 | 0.50 | 0.40 |
| external | 1.23 | 1.13 | 0.30 | 0.00 |
| graphiti | 1.28 | 1.10 | 0.70 | 0.25 |
| own | 1.10 | 1.12 | 0.20 | 0.25 |

- The full system went from last to first overall. On multi-hop it leads classic by +1.05
  and external by +1.45 (spec target +0.3 met). Changed-fact accuracy 0.47 -> 0.93.
- Single-shot own is still weak on multi-hop (0.25); the gain comes from own retrieval
  inside the subagent loop. Its ranking (Hits@1 0.47) is still well below classic (0.82).

### Cost

OpenRouter usage on 13 Nov for the dev build and both runs: about 3.7 USD (more than the
1.3 USD estimate; subagent configurations and judging cost more than projected). Balance
6.07 USD; the key limit leaves about 5.07 USD usable.

### Still open

1. Held-out real test split (55 questions): measure once, at the end.
2. Merge abbreviations/aliases at ingestion (Finding 2), not yet done.
3. Single-shot own mode and its ranking.
4. Router: product announcements fall into Unsorted.
5. Judge calibration by a human (30 blinded answers exported) is still pending.

## 18 Nov 2026: closing the gap to HippoRAG (items 1-7 of the plan)

Goal: measure ourselves on MuSiQue, 2WikiMultiHopQA and HotpotQA, and fix the causes that keep
our own retrieval behind HippoRAG. Decision by the project owner: HippoRAG is NOT re-run by us;
published numbers are used as a labelled reference. All development measurements below are on
dev data (eval-v2, benchmark dev subsets); the real-v2 test split is still untouched.

### Item 7: benchmark loaders and metrics

- Data: HippoRAG 2's own released subsets (Hugging Face `osunlp/HippoRAG_2`), 1,000 questions per
  dataset with corpora of 11,656 (MuSiQue), 6,119 (2Wiki) and 9,811 (HotpotQA) passages, stored
  under `data/bench/hipporag/` with SHA-256 sums. Gold passages follow HippoRAG 2's
  `get_gold_docs` rule; 0 unmatched gold passages on all three corpora; no duplicate passages.
- New package `src/omnistream/eval/bench/` (loaders, SQuAD-standard EM/F1, Recall@k, nDCG,
  bootstrap CIs) and `omni eval bench-retrieval`. `retrieval_metrics` gained recall@2/5/20 and
  nDCG@10 (existing keys unchanged); `score_question` adds EM/F1 when a question has short answers.
- Harness check: our BM25 lands within 1-3 points of the published BM25 rows (HippoRAG 1 Table 2).

Retrieval-only check, 300 questions per dataset (seed 0), full corpora, R@2 / R@5:

| Dataset | bge-small (ours) | BM25 (ours) | BM25 (published) | ColBERTv2 (published) | HippoRAG 1 (published) |
|---|---|---|---|---|---|
| MuSiQue | 36.6 / 50.7 | 33.8 / 44.7 | 32.3 / 41.2 | 37.9 / 49.2 | 40.9 / 51.9 |
| 2Wiki | 63.4 / 68.8 | 55.5 / 63.7 | 51.8 / 61.9 | 59.2 / 68.2 | 70.7 / 89.1 |
| HotpotQA | see bench reports | 56.3 / 73.3 | 55.4 / 72.2 | 64.7 / 79.3 | 60.5 / 77.7 |

Finding: plain bge-small already matches ColBERTv2; the large HippoRAG 1 gap is 2Wiki R@5
(about 20 points), which plain retrieval cannot close (graph/alias work is needed there).

### Item 6: short-answer mode

`runtime.answer(..., answer_style="short")` asks for the bare answer span and strips wrappers and
citation markers (`extract_short_answer`); sources stay available as structured data. Full mode
is byte-for-byte unchanged.

### Item 4: passage-anchored seeds (round 4, `docs/diagnostics/own-fixes-round4.md`)

New seed source: top-5 dense chunks -> their episodes -> mentioned named entities, weighted by
reciprocal rank and node specificity (1 / number of episodes mentioning the entity, as in
HippoRAG). Constants declared before measuring. Flag `OMNI_OWN_SEED_MODE`.
Result: with all bubbles, multi-hop full coverage 1/20 -> 10/20; with recorded routes 5/20 -> 6/20
but single-question Hits@1 fell 5/15 -> 0/15 (setback, see item 5).

### Item 5: Hits@1 diagnosis and local reranking (round 5, `docs/diagnostics/own-fixes-round5.md`)

- Cause of the Hits@1 collapse, verified by single-factor counterfactuals: the passage seeds
  change both the PageRank mass and the set of candidate facts entering RRF; in one case a
  distractor won through a better recency rank. No general graph-scoring change was justified.
- Fix: optional cross-encoder rerank of the top 30 candidates (flags `OMNI_OWN_RERANK`,
  `OMNI_CLASSIC_RERANK`, default off). About 3 s extra per own query on CPU.

### Item 2: source-evidenced alias and abbreviation merging

- Cause (from the 13 Nov diagnosis): all 20 source-stated abbreviations in eval-v2 were separate
  entities, because the embedding candidate search never surfaces "AVT" for "Aldervane Transit".
- Fix: `graph/aliases.py` extracts pairs stated in the same source ("Full Name (ABBR)", "known
  as", "a.k.a.", "formerly", ...); the linker resolves the other side by exact name/alias lookup.
  No merge on initials alone, none across a number token, tickers not treated as aliases.
- Backfill tool `eval/diagnostics/alias_merge.py` (dry run / apply / revert, manifests in
  `docs/diagnostics/`). Dry run: eval-v2 20/20 pairs, 0 refusals; real-v2-dev 3 merges.
- Setback: the first `--apply` failed on invalid Cypher (`x NOT IN list`) after partly
  re-pointing links without a manifest. The Neo4j volume was restored from the backup taken just
  before (`~/.omnistream/backups/neo4j-data-2026-11-18-before-alias-fix.tgz`), the query was fixed
  (`NOT x IN list`), and apply / revert / re-apply were verified on the real database.

### Combined effect on eval-v2 (offline, 60 questions, recorded routes, LLM calls blocked)

| Own variant | Multi-hop full | Overall full | R@10 | Hits@1 |
|---|---|---|---|---|
| round 3 (start of day) | 5/20 | 42/60 | 0.831 | 23/60 |
| passage seeds + specificity + rerank | 9/20 | 44/60 | 0.856 | 39/60 |
| same, after alias merges | 11/20 | 45/60 | 0.864 | 40/60 |
| classic + rerank (control) | 7/20 | 47/60 | 0.892 | 49/60 |

Classic is unchanged by the alias merges, as expected (it does not use the graph). Own retrieval
now leads classic on multi-hop full coverage (11 vs 7) but still trails it on Hits@1.
Defaults are unchanged (`round3`, rerank off) until answer-level checks are done.

### Item 1: stronger embedder (retrieval-only, 300 questions per dataset, full corpora, GPU)

A separate GPU venv (`~/.omnistream/venv-gpu`, torch 2.7.1+cu118, RTX 3060 6 GB) is used only for
benchmark embedding, so the main venv stays untouched. R@2 / R@5:

| Dataset | bge-small | bge-large-en-v1.5 | Qwen3-Embedding-0.6B | HippoRAG 1 (published) | ColBERTv2 (published) |
|---|---|---|---|---|---|
| MuSiQue | 36.6 / 50.7 | 41.2 / 55.7 | 40.6 / 54.2 | 40.9 / 51.9 | 37.9 / 49.2 |
| 2Wiki | 63.4 / 68.8 | 64.8 / 71.3 | 63.5 / 68.8 | 70.7 / 89.1 | 59.2 / 68.2 |
| HotpotQA | 71.0 / 83.7 | 75.2 / 87.7 | 64.8 / 78.3 | 60.5 / 77.7 | 64.7 / 79.3 |

bge-large is best on all three. Plain bge-large retrieval already exceeds published HippoRAG 1 on
MuSiQue and HotpotQA; 2Wiki stays the gap (graph and alias work). Decision (project owner): switch
the system to bge-large before the paid benchmark run. Backups taken first
(`neo4j-data-2026-11-18-after-alias-before-bge-large.tgz`, snapshot Chroma copies).

### Benchmark QA pipeline and cost probe

- `omni eval bench-ingest` loads a benchmark slice into one `Bench` bubble (router bypassed, fixed
  date and credibility so recency/confidence signals drop out); `omni eval bench-qa` scores
  closed_book, external, classic, graphiti, own and own+subagents with short answers (EM, F1,
  passage R@2/R@5, cost, latency), resumable, INVALID above 10% unmeasured.
- Setback: `python -m omnistream.cli` does nothing (the module has no `__main__` guard); use `omni`.
- Cost probe, 30 MuSiQue passages through Graphiti: 748k tokens, $0.087, about $0.0029 per passage.
  OpenRouter key: $5.05 left. Decision (project owner): run 50 questions (about 880 passages,
  about $2.6 to build plus about $0.4 to answer) rather than 100.

### Item 1 applied: system migrated to bge-large (1024-dim)

- `graph/reembed.py` re-embedded 1,704 Entity names, 1,291 GlobalEntity names, 2,070 facts, 10
  routing descriptions and 788 Chroma chunks (all snapshots), and rebuilt the three Neo4j vector
  indexes at 1024 dims. Verified: no 384-dim vectors left; smoke query works without LLM calls.
- Thresholds were not retuned (`docs/diagnostics/bge-large-thresholds.md`): at the 0.88 linker
  threshold, 0 of 1,415 sampled same-type negatives pass under either model.
- eval-v2 offline (recorded routes), bge-small -> bge-large: passage_specificity+rerank multi-hop
  full 11 -> 12/20, R@10 .864 -> .886; round3 Hits@1 .350 -> .483; classic slightly lower
  (R@10 .867 -> .861). eval-v2 is small and synthetic; the benchmark gains are the stronger evidence.
- Benchmark run settings, declared before the paid run: own uses
  `OMNI_OWN_SEED_MODE=passage_specificity` and `OMNI_OWN_RERANK=on` (best on eval-v2 under both
  routings); classic stays at its default (no rerank). MuSiQue 50 questions, seed 0, slice corpus of
  928 passages, snapshot `bench-musique-n50-s0`. The 30-passage probe group `bench-musique-n100-s0`
  is left in Neo4j unused.

### MuSiQue end-to-end QA (50 questions, slice corpus)

Ingest: 928/928 passages written, 26.6M tokens, $3.69 (about $0.004 per passage, above the
probe's estimate). QA run: $0.37 in total. Report:
`docs/eval/bench/qa-musique-n50-s0-20261118T160657Z.{md,json}`. Settings exactly as declared above.

| Configuration | EM | F1 | R@2 | R@5 | R@10 | latency (s) | cost ($) |
|---|---|---|---|---|---|---|---|
| closed_book | 10.0 | 13.1 | - | - | - | 0.9 | 0.001 |
| external | 20.0 | 24.4 | 45.5 | 45.5 | 45.5 | 1.1 | 0.003 |
| classic | 36.0 | 44.0 | 45.5 | 68.0 | 78.8 | 9.7 | 0.017 |
| graphiti | 34.0 | 40.0 | 43.7 | 62.0 | 72.3 | 16.8 | 0.025 |
| own | 34.0 | 38.6 | **52.5** | 68.2 | 77.5 | 19.0 | 0.024 |
| own+subagents | **48.0** | **60.2** | 45.3 | 62.7 | **83.2** | 52.7 | 0.300 |

- 95% bootstrap CIs are wide at n=50 (EM roughly +-13 points). own vs classic EM is a tie; own has
  the best R@2 (+7 points over classic); own+subagents is the best answerer (+12 EM over classic,
  CIs barely overlap) at 18x the cost of own.
- Reference, HippoRAG 1 Table 4 (full 1,000-question benchmark, full corpus, GPT-3.5 reader):
  None 12.5/24.1, ColBERTv2 15.5/26.4, HippoRAG 19.2/29.8, IRCoT+HippoRAG 21.9/33.3.
  Not a like-for-like comparison: our slice corpus has 928 passages (not 11,656) and a newer
  reader. The closed-book row (10.0 vs 12.5) suggests the reader alone is not the source of the gap.
- Setbacks fixed: `bench-qa` crashed on exit awaiting a synchronous `close()`; `--resume` refused to
  extend a `--limit-questions 10` run to 50. Both fixed in `eval/bench/qa.py` with a unit test.

### Fast bulk ingest (OpenIE) and its validation gate

Cause of the cost: Graphiti's `add_episode` makes many LLM calls per passage (extraction, dedup,
edge resolution, invalidation, summaries): 26.6M tokens for 928 passages. The full HippoRAG corpora
(27,586 passages) would cost about $110 that way.

- `graph/openie.py`: one structured LLM call per passage returns typed entities and
  subject-predicate-object triples with a fact sentence (HippoRAG-style OpenIE). The result is
  written as ordinary Graphiti nodes and edges (`Episodic`, `Entity`, `MENTIONS`, `RELATES_TO`,
  name and fact embeddings) in one transaction, through a new `GraphWriter.episode_builder` hook,
  so grounding, global linking, alias pairs, corroboration and chunks run unchanged. Entities are
  merged within a group by exact normalised name (as HippoRAG does).
- `omni eval bench-ingest --extractor openie [--extract-concurrency 16]`: extraction runs in
  parallel into a resumable `openie.jsonl` cache, then the writes run in order. The manifest
  records the extractor, and resuming with a different one is refused.
- Speed: the CPU venv embeds too slowly (about 2 s per passage); the GPU venv
  (`~/.omnistream/venv-gpu`) writes about 0.5 s per passage after start-up.
- Same 928-passage MuSiQue slice: $0.46 and about 25 minutes, against $3.69 and about 5.5 hours
  through Graphiti (8x cheaper).

Validation gate, same 50 questions and pre-declared settings, paired by question (OpenIE graph
minus Graphiti graph, 95% bootstrap CI):

| Configuration | EM | F1 | R@5 |
|---|---|---|---|
| own | -4.0 [-16, +8] | -4.3 [-16, +7] | +4.7 [-4, +13] |
| own+subagents | -2.0 [-14, +10] | -6.4 [-16, +2] | +3.0 [-5, +11] |
| graphiti | **-16.0 [-28, -4]** | **-12.4 [-24, -1]** | -3.8 [-11, +3] |
| classic (does not use the graph) | 0.0 | 0.0 | 0.0 |

- Our method: no significant change; retrieval slightly up, answer F1 slightly down. Gate passed.
- The Graphiti baseline depends on Graphiti's own extraction (entity summaries, resolved edges), so
  on an OpenIE graph it is no longer the Graphiti system. It is left out of the full-corpus run
  rather than reported under a misleading name.
- Classic is identical, as it should be (it reads Chroma chunks, not the graph).

### Item 3: passage nodes (HippoRAG 2 style)

Cause found first: on the MuSiQue slice, own answered from short fact sentences while classic gave
the reader whole passages; own's F1 (38.6) trailed classic's (44.0) despite better passage recall.

- `retrieval/own_algorithm/passage_nodes.py`: passages (`Episodic` nodes, already linked to their
  entities by `MENTIONS`) join the entity subgraph in the Personalized PageRank. The walk restarts at
  the seed entities (sum 1) and at the top 20 dense passages (sum 0.05, HippoRAG 2's weight); passages
  are ranked by PPR and the top 5 go to the reader as text. Per-entity cap of 100 linked passages.
  Constants are HippoRAG 2's published values, not tuned here.
- `RetrievalResult.chunks_first` makes evidence order (recall and citations) follow that passage
  ranking. Flag `OMNI_OWN_PASSAGE_NODES=on` (default off; needs a passage seed mode).
- Dev/test split: 49 of the 50 slice questions were also in `load_benchmark(n=200, seed=0)`. The slice
  is now the development set, and the full-corpus test samples exclude it
  (`omni eval bench-qa --exclude-sample 50:0`; a full-corpus snapshot accepts any question sample).

Development set (MuSiQue slice, 50 questions, OpenIE graph), paired, passage nodes on minus off:

| Configuration | EM | F1 | R@2 | R@5 |
|---|---|---|---|---|
| own | +6.0 [-2, +16] (4 better / 1 worse) | +6.0 [-2, +16] | -3.0 [-11, +6] | -2.0 [-9, +5] |
| own+subagents | +4.0 [-6, +14] | +4.6 [-7, +15] (10 / 4) | +0.7 | +1.5 |

Answers improve in both rows (not significant at n=50); passage recall is about unchanged. Decision,
declared before the test run: passage nodes on for own and own+subagents.

Test-run settings (declared before any test question is run): OpenIE graph over the full released
corpus; 200 questions per dataset, `--seed 0`; MuSiQue excludes the development sample
(`--exclude-sample 50:0`); rows closed_book, external, classic, own, own+subagents (Graphiti left out,
see the gate above); own uses `OMNI_OWN_SEED_MODE=passage_specificity`, `OMNI_OWN_RERANK=on`,
`OMNI_OWN_PASSAGE_NODES=on`; classic at its default.

## Test run: full corpora, 200 questions per dataset (2026-11-19)

Run notes (no setting changed between datasets; all fixes are result-neutral):
- OpenIE output budget raised from 4096 to 16384 tokens (`graph/openie.py`): two 2Wiki passages with
  long filmographies (Frank Sinatra, Kenneth Branagh) truncated on every retry. All three graphs are
  complete: MuSiQue 11,656, 2Wiki 6,119, HotpotQA 9,811 passages.
- Running two QA processes plus an ingest exhausted RAM (62 of 66 GB committed, heavy paging); the
  HotpotQA ingest crashed once (resumed). QA now runs one process at a time (`scripts/bench_queue.ps1`).
- Neo4j `MemoryPoolOutOfMemoryError` on 51 of the first 68 MuSiQue own+subagents cells. Cause, found
  with `SHOW TRANSACTIONS`: `entities_in` loaded every entity of the group (~650 MB per call on a
  full corpus) only to look up fact endpoints. It now takes `ids` and reads just those
  (`graph/neo4j_store.py`, `agents/tools.py`, `qa.py`); entity/fact projections also drop the unused
  embedding vectors. The failed cells were re-run on resume; no errors after the fix.
- `bench-qa --resume` now accepts reordered or narrowed rows (answers are keyed by configuration and
  question). At the user's request classic was skipped on MuSiQue and HotpotQA (it had finished on
  2Wiki) and own+subagents ran before own.

Results (EM / F1 / passage R@5, %; n=200 each; reader `deepseek/deepseek-v4.1-flash-1017`):

| Configuration | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|
| closed_book | 7.5 / 12.8 / – | 30.5 / 33.6 / – | 29.5 / 38.2 / – |
| external | 14.5 / 16.7 / 40.9 | 35.0 / 37.6 / 64.4 | 44.0 / 54.5 / 74.0 |
| classic | not run | 49.5 / 53.7 / 69.9 | not run |
| own | 23.0 / 27.0 / 56.3 | 50.5 / 55.0 / 86.2 | 48.0 / 60.0 / 80.8 |
| own+subagents | **37.0 / 47.3** / 45.9 | **71.5 / 77.1** / 71.9 | **62.0 / 75.6** / 71.2 |
| HippoRAG 1 (paper, QA Table 4) | 19.2 / 29.8 | 46.6 / 59.5 | 41.8 / 55.0 |
| IRCoT + HippoRAG (paper) | 21.9 / 33.3 | 47.7 / 62.7 | 45.7 / 59.2 |

HippoRAG 2 paper (arXiv 2502.14802, local copy in `eval papers/`, checked against the PDF), Llama-3.3-70B
reader and NV-Embed-v2 retriever: HippoRAG 2 F1 48.6 / 71.0 / 75.5 (Table 2), R@5 74.7 / 90.4 / 96.3
(Table 4). The same table re-runs HippoRAG 1 with that strong reader: F1 35.1 / 71.8 / 63.5. Against
that stronger HippoRAG 1, own+subagents is still ahead on all three, but own alone is behind on all
three. Caveats: the reader models differ from both papers, and
the papers use 1,000 questions; these are 200-question samples, so treat differences of a few points
as noise.

## Closing the retrieval gap to HippoRAG 1 (2026-11-20)

Honest re-check against every HippoRAG 1 table (2, 3, 4 and the all-recall table): the test run
beat HippoRAG 1 on QA with subagents, but own retrieval was behind on R@2 (all three datasets), on
2Wiki R@5, and own+subagents was behind on multi-step recall (Table 3). Work below uses a
development set only: 100 questions per dataset sampled (seed 1) from the released questions minus
every question of the test run (`scripts/dev_retrieval.py`, retrieval-only, no LLM calls).

Causes found first:
- Own answered "Unknown" on 22 of 50 MuSiQue dev questions (F1 0). HippoRAG's reader always answers.
  The benchmark short-answer prompt (all rows, including baselines) now asks for a best guess.
- own+subagents recall ranked fact items before the passages the subagents retrieved, and appended
  later searches' passages after earlier ones. Findings now list passages first, round-robin by rank
  across the subagent's searches (`agents/subagent.py`, `eval/__init__.py`).
- On 2Wiki the passage walk spread evenly over a film's 14 links, so the director's passage got
  little mass (checked in the graph for "Two for Texas").

Development results, R@2 / R@5 (HippoRAG 1: MuSiQue 40.9 / 51.9, 2Wiki 70.7 / 89.1, HotpotQA
60.5 / 77.7):

| Variant | MuSiQue | 2Wiki | HotpotQA | Kept |
|---|---|---|---|---|
| passage nodes (test-run setting) | 36.9 / 56.2 | 63.5 / 86.0 | 62.5 / 81.0 | base |
| + cross-encoder rerank of the passage pool (ce) | 44.0 / 56.6 | 62.5 / 69.2 | 83.5 / 92.5 | no |
| + fused PPR and cross-encoder ranks (rrf) | 45.6 / 62.5 | 67.0 / 85.0 | 77.5 / 93.0 | yes |
| rrf + 50 dense passages (was 20) | 44.8 / 62.7 | 67.0 / 80.0 | 77.0 / 91.5 | no |
| rrf + LLM question decomposition | 44.8 / 62.5 | 67.5 / 84.0 | 74.5 / 92.5 | no (3x slower) |
| rrf + re-seeding (second walk) | 46.2 / 63.5 | 68.0 / 86.0 | 77.5 / 92.5 | yes |
| ... + PPR damping 0.5 | | 65.5 / 81.0 | | no |
| ... + question-aware edge weights (cos^2/4/8) | | 66.8 / 85.2 at best | | no |
| ... + PPR weight 3 in the fusion | 42.8 / 60.9 | 68.2 / 88.5 | 72.0 / 86.5 | no |
| ... + fact seeds (top 3 reranked facts) | 47.1 / 66.1 | 68.5 / 87.8 | 77.5 / 94.0 | yes |
| ... + fact seeds + PPR weight 2 (chosen) | **46.4 / 66.9** | **71.5 / 90.5** | **76.0 / 90.5** | **final** |

Chosen setting (one setting for all datasets): `OMNI_OWN_PASSAGE_RERANK=rrf OMNI_OWN_RESEED=on
OMNI_OWN_FACT_SEEDS=3 OMNI_OWN_RRF_PPR_WEIGHT=2` on top of the test-run flags. All new flags default
to off. The 2Wiki margin on dev is about 1 point (within noise at n=100). The reranker now runs on the
GPU when available (same model).

### Final test run with the chosen setting (2026-11-20)

The chosen setting was run once on the 200 test questions per dataset (seed 0, same questions as
the earlier test run). No setting was changed after seeing a test number. QA reports:
`docs/eval/bench/qa-*-n200-s0-20261120T*.md`; retrieval-only and IRCoT reports:
`docs/eval/bench/test-retrieval/`.

IRCoT row (Table 3): `OMNI_OWN_IRCOT=on` wraps the own retriever in IRCoT-style retrieval (up to 3
chain-of-thought steps, each sentence becomes the next query, rankings merged round-robin). It was
checked on 2Wiki dev only (79.8 / 97.0) before the single test run. LLM step failures: 0 on all
three datasets (steps 458 / 486 / 351).

Against HippoRAG 1 (ColBERTv2), all numbers in %:

| Table | Metric | MuSiQue | 2Wiki | HotpotQA |
|---|---|---|---|---|
| 2 single-step | R@2 / R@5 ours | 49.1 / 64.1 | 72.0 / 90.4 | 69.0 / 90.0 |
| | HippoRAG 1 | 40.9 / 51.9 | 70.7 / 89.1 | 60.5 / 77.7 |
| 3 multi-step | R@2 / R@5 ours (IRCoT + own) | 54.2 / 73.2 | 80.8 / 97.9 | 75.0 / 94.8 |
| | IRCoT + HippoRAG 1 | 45.3 / 57.6 | 75.8 / 93.9 | 67.0 / 83.0 |
| 4 single-step | EM / F1 ours (own) | 36.0 / 44.2 | 60.5 / 68.1 | 58.5 / 74.1 |
| | HippoRAG 1 | 19.2 / 29.8 | 46.6 / 59.5 | 41.8 / 55.0 |
| 4 multi-step | EM / F1 ours (own + subagents) | 38.0 / 49.0 | 75.0 / 82.7 | 65.0 / 79.8 |
| | IRCoT + HippoRAG 1 | 21.9 / 33.3 | 47.7 / 62.7 | 45.7 / 59.2 |
| AR single-step | AR@2 / AR@5 ours | 18.0 / 38.0 | 45.5 / **72.0** | 42.5 / 81.0 |
| | HippoRAG 1 | 10.2 / 22.4 | 45.4 / 75.7 | 33.8 / 57.9 |
| AR multi-step | AR@2 / AR@5 ours (IRCoT + own) | 25.5 / 49.5 | 63.5 / 92.0 | 54.5 / 90.0 |

Every number is ahead of HippoRAG 1 except single-step 2Wiki AR@5 (72.0 vs 75.7); 2Wiki AR@2 and
2Wiki R@2 / R@5 are within noise (n=200, 95% intervals about +-3-4 points for recall). Not tuned
further, since only the test set shows it.

Against HippoRAG 2 (NV-Embed-v2, Llama-3.3-70B reader; R@5 74.7 / 90.4 / 96.3; F1 about 48.6 /
71.0 / 75.5): own + subagents F1 is ahead on all three (49.0 / 82.7 / 79.8); own single-step F1
(44.2 / 68.1 / 74.1) and R@5 (64.1 / 90.4 / 90.0) are behind or tied; IRCoT + own R@5 (73.2 / 97.9
/ 94.8) is ahead on 2Wiki only. Different readers, embedders and question samples, so this is
context.
