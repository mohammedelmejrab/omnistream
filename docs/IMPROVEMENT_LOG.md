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

### Change 2: real-data collector and quality verifier (commit `70fcbcb`)

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

### Finding 4: controlled diagnosis on eval-v2 (commit `a363621`)

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

### Change 5: reasoning control for the new model (fix for setback 4)

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

### Change 6: real-v2 questions written, independently verified, repaired

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


### Change 5: own fact seeding and relevance-weighted fusion (2026-11-13)

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

### Change 7: own-mode fixes, round 1 (commit `cbba2e7`)

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

### Change 8: the evaluation harness no longer scores provider errors as wrong answers

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


### Change 9: own retrieval fixes, round 2 (commit `646beb6`)

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
