# Evaluation metrics: definitions and how each is computed

Companion to `GRAPHRAG_EVAL_PLAN.md`. Each entry gives what the metric means, how it is computed, its range and direction, which systems it applies to, and its known limits.

**Status labels**
- **Implemented**: already computed by the harness in `src/omnistream/eval/`; file references given.
- **To add**: planned in the evaluation plan; the definition here is the intended one.

**Systems**: `external` (naive RAG), `bm25`, `graphiti`, `own`, `own+subagents`, plus `classic` (OmniStream's own chunk-vector pipeline, no graph, no subagents) as an internal diagnostic.
**Tracks**: A = MuSiQue, n=100, directly loaded into each retriever. B = eval-v2 (60 questions) and real-v2 (dev 24, test 55).

---

## 1. Retrieval metrics

Retrieved items are deduplicated in first-retrieval order before scoring (`metrics.py:62`). Gold is the set of source items that contain the evidence for a question.

### Recall@k
- **Meaning:** the share of gold evidence items that appear in the top k retrieved items.
- **Computation:** `|top-k retrieved ∩ gold| / |gold|`, averaged over questions. Range 0-1, higher is better.
- **Status:** Recall@10 implemented (`metrics.py:69`, gold only, acceptable evidence not counted). Recall@2, @5 and a full recall@k curve are **to add**; @5 is what HippoRAG 2 reports (passage recall@5), so it is the comparison point for Track A.
- **Track A note:** `own` returns facts, not paragraphs. A paragraph counts as retrieved if any retrieved fact points to it as source. The fact-to-paragraph mapping must be defined and reported before running, because it decides the score.
- **Limits:** a question with several gold items needs all of them for recall 1.0; recall ignores ranking order and ignores wrong items retrieved alongside.

### MRR (mean reciprocal rank)
- **Meaning:** how early the first correct item appears.
- **Computation:** per question `1 / rank` of the first retrieved item that is in gold or in the question's `acceptable` evidence set; 0 if none. Mean over questions. Range 0-1, higher is better (`metrics.py:65-70`).
- **Status:** implemented.
- **Limit:** counts acceptable evidence, unlike recall, so the two are not on identical footing.

### Hits@1
- **Meaning:** whether the top-ranked item is correct.
- **Computation:** 1 if the first-ranked correct item is rank 1, else 0; mean over questions (`metrics.py:71`).
- **Status:** implemented.

### nDCG@k
- **Meaning:** ranking quality that rewards putting more gold items higher.
- **Computation:** `DCG@k / IDCG@k` with binary relevance (gold = 1) and `DCG = sum(rel_i / log2(i + 1))`. Range 0-1.
- **Status:** **to add** in `retrieval_metrics`.

---

## 2. Answer quality metrics

### Judge correctness (0-2)
- **Meaning:** whether the final answer matches the reference answer's key facts.
- **Computation:** an LLM judge applies a fixed rubric (`judge.py:10`): **2** = all reference key facts correct including the requested time scope; **1** = partially correct, missing required facts; **0** = incorrect, unsupported guess, or abstention. Numerically equivalent answers with explicit units are accepted; correct facts about a different date are not rewarded; scoring is against the supplied (fictional) reference, not prior knowledge. The judge returns JSON `{score, rationale}`, retried up to 3 times on invalid output. Mean over measured questions. Range 0-2, higher is better.
- **Status:** implemented. **Calibration pending:** 0 of 30 human labels exist (`calibration.py`), and the judge is in the same model family as the answerer, so these scores are provisional until Section 8 is done.
- **Limits:** a three-level scale is coarse; judge bias (position, verbosity, same-family preference) is not controlled.

### Exact match (EM) and token F1
- **Meaning:** string-level agreement with a short gold answer, for questions that have one (MuSiQue).
- **Computation:** normalize both strings (lowercase, strip punctuation and articles, collapse whitespace); EM = 1 if equal else 0. F1 = harmonic mean of token precision and recall between prediction and gold: `2PR / (P + R)`, with `P = overlap / |pred tokens|`, `R = overlap / |gold tokens|`. When a question has several accepted answers, take the maximum. Range 0-1, higher is better. This is the MuSiQue/HippoRAG 2 convention (token-based F1).
- **Status:** **to add** in `score_question` (`eval/__init__.py:112`). Needed for comparison against HippoRAG 2's published F1.
- **Limits:** penalizes correct but verbose answers; use the judge score as the secondary measure.

### Changed-fact accuracy
- **Meaning:** among questions whose answer changed over time, how often the system gives the current value.
- **Computation:** over questions of type `time_sensitive`, the fraction whose judge correctness equals 2 (`metrics.py:118-125`). Range 0-1, target 0.80.
- **Status:** implemented. Applies to all five systems; the baselines have no time scope, so a low score for them is informative rather than an error.
- **Limit:** based on 15 questions in eval-v2, so confidence intervals are wide.

### Pairwise win rate
- **Meaning:** how often a judge prefers system A's answer to system B's.
- **Computation:** for each question and pair, the judge sees both answers twice (original and swapped order), choosing on comprehensiveness, diversity, empowerment and overall (the GraphRAG and LightRAG criteria). A pair counts as a win only if the preference is consistent across both orders; otherwise it is a tie. Win rate = wins / (wins + losses + ties), reported per criterion. The judge must come from a different model family than the answerer.
- **Status:** **to add** (new `eval/pairwise.py`).
- **Limits:** relative, not absolute; win rates from different judges are not comparable (the papers use different judges).

---

## 3. Provenance and faithfulness metrics

### Citation faithfulness (macro and micro)
- **Meaning:** whether the sources an answer cites actually support what the answer says.
- **Computation:** the answer is split into claim groups, one per sentence with its trailing `[n]` citation markers (`claim_groups`, `judge.py:155`; protects decimals, abbreviations and initials from sentence splitting). For each group, the judge checks whether the union of the cited original texts entails the claim; mere topic overlap does not count. A missing stored original or an invalid citation number counts as unsupported. Invalid numbers not covered by a claim group each add one unsupported citation.
  - **Micro:** `sum(supported citations) / sum(all citations)` over all answers.
  - **Macro:** mean over answers of `supported / total citations` (answers with zero citations count 0). This is the value tested against the 0.90 target.
- **Status:** implemented. `external` has no inline markers, so its entire source set is judged as one unit (`judge.py:77-80`), which makes it easier to pass than a per-claim system; note this in any comparison.
- **Limits:** depends on the judge; sentence splitting is heuristic.

### Zero-citation answers and abstentions
- **Zero-citation answers:** count of answers with no citations; they score 0 in macro faithfulness.
- **Abstentions:** answers with correctness 0 and zero citations (`metrics.py:162-167`); a proxy for "I don't know". **To add:** abstention precision (how often abstaining was right because no evidence existed).
- **Status:** counts implemented, precision to add.

### Contamination check
- **Meaning:** whether the model could answer from its own knowledge, which would make retrieval metrics meaningless.
- **Computation:** the question is asked with no context ("answer from your own knowledge, say you do not know otherwise") and judged for correctness with the same rubric (`judge.py:135`). Reported as the number of closed-book-correct questions; target 0. eval-v2 shows 0 of 60.
- **Status:** implemented for eval-v2 (fictional facts). **For Track A it will not be 0**: MuSiQue is built from Wikipedia, which models have seen. Report a closed-book (no retrieval) row as the floor, as HippoRAG 2 does ("None": 26.1 F1 on MuSiQue).

---

## 4. Routing and ingestion metrics

Apply to OmniStream configurations only. Baselines are N/A, not 0.

### Query routing recall and precision
- **Meaning:** whether a question is sent to the right domain bubbles.
- **Computation:** `selected` = bubbles chosen for the question, `expected` = labelled bubbles. Recall = `|selected ∩ expected| / |expected|` (1.0 if nothing expected); precision = `|selected ∩ expected| / |selected|` (0 if none selected) (`metrics.py:75`). Targets: recall 0.90, precision 0.70.
- **Status:** implemented.

### Ingestion routing metrics
- **Meaning:** whether incoming items land in the right bubbles at ingestion.
- **Computation** (`metrics.py:297`), per item, comparing labelled bubbles to assigned bubbles (an Unsorted item has an empty assigned set):
  - **Routing accuracy:** assigned set equals labelled set exactly; fraction of items. Target 0.85.
  - **Primary-label recall:** labelled set is contained in the assigned set.
  - **Over-assignment rate:** mean number of extra bubbles assigned beyond the labels.
  - **Wrong-routing rate:** labelled set not contained in the assigned set.
  - Also reported: Unsorted count, and which questions depend on Unsorted items.
- **Status:** implemented. eval-v2 shows 0.63 (FAIL) and real-v2 dev 0.72 (FAIL).

### Duplicate-entity rate
- **Meaning:** how often the graph holds two nodes for the same real entity.
- **Computation** (`audit.py`): sample entity nodes (target at least 100), find candidate near-duplicates by embedding cosine, and ask an LLM whether each pair names the same identity (aliases count). `duplicates / sample size`. Lower is better, target at most 0.05.
- **Status:** implemented. real-v2 dev shows 0.12 (FAIL).
- **Limits:** only checks pairs the embedding search surfaces, so it can miss duplicates with dissimilar names.

### Ungrounded-entity rate
- **Meaning:** share of graph entities with no grounding link. Reported only, no target.
- **Computation:** nodes whose `grounded` flag is false, over audited nodes; nodes with no flag are counted separately (`audit.py:89`).
- **Status:** implemented.

---

## 5. Freshness metrics

### Freshness lag
- **Meaning:** how long after a new item is injected until the system can answer a question that depends on it.
- **Computation:** wall-clock time from injecting an item to the first answer probe that is both grounded and judged correct, for each of 10 freshness items during snapshot construction (`eval/__init__.py:~575-596`). Reported as the maximum lag. Target: `poll_interval_minutes × 60 + 300` seconds (default config). If fewer than 10 items become answerable, the check fails.
- **Status:** implemented but currently reports N/A in existing results, so the measurement needs fixing before relying on it. The lag is an upper bound because it is sampled by probes.
- **Applies to:** OmniStream systems; baselines would need the same injection test to be compared.

---

## 6. Cost and resource metrics

### Latency
- **Computation:** wall-clock seconds per question for the full answer path, mean over measured questions. **To add:** p50 and p95.
- **Status:** mean implemented.

### Tokens and dollars per query
- **Computation:** every provider call is metered by stage (`resources.py:12`): prompt, completion and total tokens, call count, and cost where the provider reports it. Cost is reported only if every call in the stage reported one, otherwise null. Answer usage and judge usage are separate. Dollars can be recomputed from token counts at any rate (the plan uses HY4 Flash and DeepSeek prices).
- **Status:** implemented.

### Indexing cost
- **Meaning:** one-off cost of building each system's index (tokens, wall-clock, dollars, per 1k documents; plus incremental-update cost).
- **Status:** **not measured** (probe blocked). Graph systems pay LLM extraction cost; `external` and `bm25` use local embeddings only.

### Peak memory
- **Computation:** peak resident memory of the application plus Neo4j, sampled during the run (`resources.py:74`). Target at most 4 GiB.
- **Status:** implemented.

---

## 7. Run validity and statistics

### Run validity
- A question-configuration pair is unmeasured if it errored or could not be judged. If more than 10% of pairs in a configuration are unmeasured, the run is flagged **INVALID** and every dependent check is reported UNMEASURED (`metrics.py:7-60`, `283-293`). Error types are tallied (provider HTTP codes, judge errors).

### Confidence intervals and significance
- **To add:** non-parametric bootstrap (resample questions with replacement, 10,000 draws) for 95% intervals on every mean; paired bootstrap or Wilcoxon signed-rank for system-vs-system differences on the same questions. Report n per question type; treat differences inside the interval as ties. Run each system three times to estimate run-to-run variance (indexing paid once).
- HippoRAG 2 uses a bootstrapped significance test for its comparisons, so this matches the reference.

---

## 8. Judge calibration (needed before quoting correctness)

- **Meaning:** how far the LLM judge agrees with a human.
- **Computation** (`calibration.py:107`): 30 sampled answers are labelled blind by a human (0, 1 or 2). Report **exact agreement** (share of identical scores) and **Cohen's kappa** `(p_o − p_e) / (1 − p_e)`, where `p_o` is exact agreement and `p_e` is the agreement expected by chance from the human and judge score distributions.
- **Plan:** also run a second judge from a different model family and report judge-vs-judge agreement.
- **Status:** the sampling and kappa code exist; labels do not (0 of 30).

---

## 9. Success thresholds already in the harness

From `metrics.py:182`. Ingestion and memory checks apply to the OmniStream graph; the rest per configuration.

| Check | Target |
|---|---|
| Query routing recall | at least 0.90 |
| Query routing precision | at least 0.70 |
| Citation faithfulness (macro) | at least 0.90 |
| Changed-fact accuracy | at least 0.80 |
| Ingestion routing accuracy | at least 0.85 |
| Duplicate-entity rate | at most 0.05 |
| Peak memory | at most 4 GiB |
| Freshness max lag | at most poll interval + 5 minutes |
| Entity audit sample size | at least 100 |
| Multi-hop recall improvement | positive, versus `classic` |
| Full-system multi-hop correctness gain | at least 0.3, versus `classic` and versus `external` |

**Note:** the multi-hop checks compare against `classic`. `classic` is back in the evaluation (alone, without subagents), so these checks can be computed. They treat `own+subagents` as the full system, which is compared against a `classic` that has no subagents, so a pass mixes graph and subagent effects.

---

## 10. Which metric answers which question

| Question | Metrics |
|---|---|
| Does retrieval find the evidence? | Recall@k, MRR, Hits@1, nDCG |
| Is the final answer right? | Judge correctness, EM, F1, pairwise win rate |
| Can we trust the citations? | Citation faithfulness, zero-citation answers, abstentions |
| Does it handle changing facts? | Changed-fact accuracy, freshness lag |
| Does it route and ingest well? | Query routing, ingestion routing, duplicate-entity rate |
| What does it cost? | Latency, tokens, dollars per query, indexing cost, peak memory |
| Can the numbers be trusted? | Run validity, confidence intervals, judge calibration |
