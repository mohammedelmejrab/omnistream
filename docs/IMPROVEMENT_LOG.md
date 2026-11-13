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
