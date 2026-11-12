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
