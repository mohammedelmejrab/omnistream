# Independent verification of real-v2 questions

Reviewed 13 November 2026 by the second model (Codex), independently of the question author. **Not fit for unfiltered benchmark scoring.** Keep 57 questions provisionally (54 OK, 3 FIXED); quarantine 27 FLAG questions and exclude 3 REJECT questions. The original 87 records remain in JSON; exclusions below are recommendations, not deletions or an implemented scoring filter.

## Scope and method

Reviewed all 87 questions, all 101 distinct gold items, all supplied evidence, and 25 routing annotations. Read actual local source prose, abstracts, table headings and surrounding relevant sections in long filings; did not rely solely on the evidence quotes. Loaded and searched all 350 clean texts. The manifest is metadata, not evidence text. Began with rq-t-030, rq-d-013, rq-t-044, rq-t-033, rq-t-036/037, rq-t-032 and rq-t-039, then completed the remaining questions.

For each question, searched its entities, distinctive description and answer quantities across the corpus; also performed an independent BM25-style lexical search with document-length normalisation. The per-question search ledger records six low-document-frequency query terms and three non-gold candidates. Candidate similarity is not evidence of a conflict. Inspected relevant matching passages to distinguish different periods, companies, units, methods and evaluation conditions. Tested freshness by contextual fact identity, not the mere occurrence of an answer number. No additional contradictory answer was established beyond the qualifications documented below. Search is lexical/manual and cannot prove semantic uniqueness exhaustively.

All 350 text SHA-256 values match the manifest’s `sha256` field. Question file SHA-256 after edits: `35bd09cbc521054e72cf64604b25b50b26d6db1b7869e3fa48c5d30c2e2248c7`. Source identities below use unique eight-character prefixes; the source index resolves them to full IDs and local files.

Applied the real-data/no-overfitting rules in docs/IMPROVEMENT_LOG.md and the multi-hop, routing, changed-fact and freshness measurement objectives in specification sections 8.2–8.3. No LLM API, network request, git commit, .env access, ingestion, snapshot, diagnostics or Neo4j action was used. Existing unrelated work was left untouched. The only repository writes are the three question annotations and this report.

Verdicts: OK = supported and usable with stated scoring qualifications; FIXED = clear error corrected and otherwise usable; FLAG = ambiguity/design or label risk requiring adjudication before scoring; REJECT = clear failure of intended question type. A FLAG is not a claim that its answer is false. Corpus support does not independently authenticate a publisher’s real-world claim. Public CEO facts and older statutory dates require particular caution about prior knowledge.

## Counts

| Split | Type | OK | FIXED | FLAG | REJECT |
|---|---|---:|---:|---:|---:|
| test | single | 12 | 0 | 3 | 0 |
| test | multi_hop | 6 | 0 | 12 | 2 |
| test | time_sensitive | 11 | 0 | 4 | 0 |
| test | freshness | 10 | 0 | 0 | 0 |
| dev | single | 7 | 0 | 1 | 0 |
| dev | multi_hop | 3 | 0 | 4 | 1 |
| dev | time_sensitive | 2 | 3 | 1 | 0 |
| dev | freshness | 3 | 0 | 2 | 0 |
| **All** | **All types** | **54** | **3** | **27** | **3** |

Test totals: 39 OK, 0 FIXED, 19 FLAG, 2 REJECT. Dev totals: 15 OK, 3 FIXED, 8 FLAG, 1 REJECT. Kept test subset: 39; kept dev subset: 18. These do not meet the original category quotas, especially multi-hop (6 test and 3 dev kept). Do not present the reduced subset as the planned 60-test-question benchmark.

## Every edit

Only `expected_bubbles` changed. No answer, fact, type, gold ID, evidence, question wording, split, routing label or freshness list was changed. Each save used a parsed, fully serialized JSON document and atomic replacement. No new question was added.

| Question | Field | Before | After | Evidence |
|---|---|---|---|---|
| rq-d-017 | expected_bubbles | `["News"]` | `["Finance"]` | 5bef2525: “KRW 195.3 trillion in consolidated revenue”; earnings amount, not general product news. |
| rq-d-018 | expected_bubbles | `["News"]` | `["Finance"]` | 90445a7a: “Operating profit 89.49 12.17”; table headers identify Q2 2026/Q3 2025, units trillion won. |
| rq-d-019 | expected_bubbles | `["News"]` | `["Finance"]` | 90445a7a: “Operating Profit: 107.3 trillion to 107.5 trillion Korean won”; earnings guidance. |

Both Samsung items contain financial guidance/results regardless of their news-source hint. Finance is the required content route; optional additional News routing would not invalidate Finance coverage. The manifest’s content_bubbles also includes finance for both items, but the actual text is the basis for these edits.

## Principal findings

### R1–R3: reject from the intended multi-hop score

- **R1, rq-t-030:** AMD Helios is already named in the question. b64c2e06 directly answers with “powered by AMD Instinct MI450 Series GPUs”. Neither robotics-benchmark lookup nor model-to-developer linkage is necessary. No type downgrade was made because preserving the question while retaining three supposedly necessary gold items would leave misleading labels.
- **R2, rq-d-013:** Microsoft and the October agent-harness event are already supplied. 092ccea5 says “the GitHub engineering team built a best-in-class, truly multi-model harness”. The RetroChimera platform hop contributes no needed answer discrimination; its Microsoft Research affiliation also supplies a vendor shortcut.
- **R3, rq-t-026:** 95530714 itself describes the handwritten-exam grading study and gives “r = 0.97; MAE = 0.85 marks”. Amazon’s list is not needed to locate the uniquely described study. Worse, the extra key_fact calls MAE an acceptable alternative to Pearson correlation. These statistics measure different properties; MAE is not a valid answer to how strongly marks correlated.

### S1: split rule is narrower in the data than in its written claim

The union of gold, evidence and distractor IDs has **zero dev/test overlap**. Gold-only totals are test 69, dev 32, shared zero. Evidence belongs to gold. Organisation/topic ownership of the primary publishers/entities is consistent with the assignment (including the explicit EFF, SEC and CMA exceptions). No gold item primarily about a dev organisation was found assigned to test, or vice versa.

However, the additional rule excluding items that mention organisations from both splits is not literally satisfied by the question chains. Examples: OCP item 99e3e5da explicitly names Google and Microsoft, and is used to bridge to test companies; Amazon item 6d389204 names Samsung, Qualcomm and Salesforce and is used in test chains. Microsoft earnings 509b5324 names OpenAI. The following table records all detected mixed-side gold cases. Some are terminal answer items rather than the intermediate bridge. These are conservatively FLAGged pending adjudication of the written rule; incidental mentions alone do not establish actual train/test leakage. Narrowing that rule to primary-entity ownership may resolve those FLAGS, but is a policy decision, so the JSON rule was not edited.

| Questions | Mixed-side item | Opposite-side names in its text |
|---|---|---|
| rq-d-009 | f8764769 | Apple, Amazon |
| rq-d-014, rq-d-015 | 509b5324 | OpenAI |
| rq-t-017, rq-t-034 | 4f4e68d2 | HPE, Dell |
| rq-t-019 | 378b27e8 | Google |
| rq-t-020, rq-t-021 | 99e3e5da | Google, Microsoft |
| rq-t-022, rq-t-024 | f9343678 | Dell |
| rq-t-025, rq-t-026, rq-t-029, rq-t-030 | 6d389204 | Samsung, Qualcomm, Salesforce |
| rq-t-030 | b64c2e06 | Google, Microsoft, HPE |
| rq-t-032 | 692eaf47 | Google, Samsung |

### U1: alternate support is not a wrong-answer distractor

Several items agree with the gold answer. They are not competing *answers*, but exact-ID recall can still be corrupted if their retrieval is counted as wrong. rq-t-002 labels c4bbb8b3 as a distractor even though it gives “4.500 shares of Marvell common stock for each share of Lumentum common stock”. 75ee4f31 also gives the ratio. rq-t-016 labels 6efa7d34 as a distractor while its notes admit it supports the same appointment. rq-t-047 labels c88e556c as a distractor while its notes admit it lists both proposed acquisitions. These are FLAGged even where notes disclose the issue.

rq-d-001 also has unlisted support in ASML slide 321561f3; rq-t-004 has the revenue and prior-year comparator in Arm filing b9715cb4. They need an explicit equivalent-support policy. Adding every alternative to a conjunctive gold list would create a new problem by making redundant evidence appear required. Therefore no speculative gold edits were made. Corroborating items already acknowledged without being stored as distractors, such as rq-t-036/048, are noted in their OK rows; the scoring harness should accept their evidence equivalence. OK verdicts are about the question and its annotated support, not approval of an exact-ID-only scoring implementation.

### T1: event ordering and publication time are different

rq-t-044 and rq-t-050 have correct amounts, but 017deb85 and d210bc08 both carry a 28 September release date and a 2 October manifest publication date. The pricing release’s word “upsized” and retrospective amount establish logical sequence. There is no intervening dated as-of cutoff. Hold them out of strict date-based changed-fact scoring until event ordering is explicitly supported. rq-d-022 is separately ambiguous because both 10.4–10.8% original guidance and 12.0–12.5% preliminary margins preceded final results.

All other time-sensitive rows were checked against the old/new texts and dates, including current, as-of and event-relative phrasing. In rq-t-036 the appointment event is 11 November and publication is 12 November: the answer is supported after the latest corpus item arrives, but a replay must not treat event time as earlier ingestion availability. Current/latest means the frozen corpus cutoff, not a future live date.

### Aliases, leakage and scoring variants

All nine alias-bridge annotations have their stated surface forms in the respective gold texts. The three-item chains have text-backed intermediate links. rq-t-033 is a mild alias, not a wrong answer: IBM appears in the paper and both IBM and its legal name appear in the filing. The same limitation applies to AMD in rq-t-021 and Berkeley in rq-t-035. Product-to-developer bridges (rq-d-010, rq-t-025/030) are ownership relations, not literal name synonyms.

rq-t-032 supplies iOS, an ordinary-knowledge identifier of Apple; its CEO answer can also be known without these sources. rq-t-037 can be answered from widely known Huang identity and several older posts, so correct answering alone does not demonstrate time reasoning. rq-d-011 supplies Google and assumes the classroom chatbot and a specific Flash model are interchangeable. These remain FLAGs. rq-d-026 asks a May 2026 statutory commencement fact published in a November update: corpus uniqueness passes, but prior knowledge can precede freshness injection.

Missing acceptable variants: rq-d-003 Christopher A. Garcia; rq-d-006 50% more variance; rq-t-019 $114.477bn or $114,477m (under the split FLAG); rq-t-060 a 9.45 percentage-point decrease, about 29.8% relative. Existing facts support these. Conversely, rq-t-023’s 91% growth cannot substitute for its requested dollar range, and rq-t-026’s MAE cannot substitute for correlation. Unrequested facts should not become compulsory: rq-d-005 prior-year revenue, rq-d-010 closing date, rq-d-015 growth, rq-d-027 LUT count, rq-t-016 appointment date and rq-t-025 developer name. rq-d-027 is specifically FLAGged because the standalone LUT fact is neither requested nor present in its reference answer.

rq-t-039 needs **no typo edit**: 5a093fbb prints T$ in the sentence, while the same source’s NT$-million table supplies 3,898,727 million and the more precise table supplies 3,898,726,974 thousand. Both round to NT$3,898.73bn. The existing verbatim quote and normalized answer are consistent.

## Per-question decisions

Every row covers source support, question-type suitability and the relevant uniqueness/time/routing qualification. No hidden answer correction is implied by FLAG.

| ID | Split | Type | Verdict | Reason |
|---|---|---|---|---|
| rq-d-001 | dev | single | FLAG | EUR 14.2–15.2bn Q4 guidance is correct (cbca4caf), but 321561f3 independently gives the same guide; unlisted alternative support. Exact-gold recall can penalize correct retrieval. |
| rq-d-002 | dev | single | OK | fe02a290 supports both $5.66bn enterprise value and $47.50 cash per Class A share; 1901c032 is a webinar disclaimer, not competing deal terms. |
| rq-d-003 | dev | single | OK | d0d4e232 explicitly appoints Christopher Garcia effective 1 February 2027. Accept Christopher A. Garcia, used in the signature. Governance content fits the set’s Finance convention. |
| rq-d-004 | dev | single | OK | e1eb2e37 distinguishes Data Center Networking’s low-to-high 50s CAGR through FY2029 from Routing’s 20s target; no competing same-business target found. |
| rq-d-005 | dev | single | OK | ef70a066 states FY2026 revenue $133.19bn and the 3 September year end; $54.23bn is Q4 only. Prior-year $37.38bn is supported but should not be required to answer this question. |
| rq-d-006 | dev | single | OK | 759f3904 supports 1.5 times as much variance, versus the buoyancy diagnostic. Accept 50% more; do not interpret this as 150% more. |
| rq-d-007 | dev | single | OK | 69cf9e2d orders PyriteReasoner before PyriteFeaturizer and reports up to 67% and 74%; retain the up-to qualifier. |
| rq-d-008 | dev | single | OK | 6e8793cc gives 15 active tasks; five pages per task and 60/90-day pause/stop limits are different quantities. 941f0ba7 repeats the feature, not its limit. |
| rq-d-009 | dev | multi_hop | FLAG | Both Qualcomm and FY2026 GAAP revenue $43.1bn are supported; Samsung trademark footnote supplies the bridge. Mixed-side gold f8764769 names Apple/Amazon: written split-rule conflict S1. |
| rq-d-010 | dev | multi_hop | OK | PhyRubric → Gemini 4 Argon → Alphabet → €6bn notes closed 5 November is supported across 1ff30f2f/f436d43a/839e05d9. Surface forms occur; product ownership is a relation, not a literal synonym. |
| rq-d-011 | dev | multi_hop | FLAG | 98.5% is exact in AuDiR, but Google is supplied in the wording and neither gold text establishes that classroom Gemini is specifically the evaluated Gemini-3.8-flash. Family/version equivalence is assumed; no edit. |
| rq-d-012 | dev | multi_hop | OK | 2c5be933 identifies Google Research’s TabFM; f436d43a links Google/Alphabet and reports Google Cloud growth 103% to $30.7bn. No bridge named directly. |
| rq-d-013 | dev | multi_hop | REJECT | The question names Microsoft and the October agent-harness event; 092ccea5 identifies the GitHub engineering team directly. RetroChimera/Foundry lookup is dispensable. Accurate answer, invalid strict multi-hop test (R2). |
| rq-d-014 | dev | multi_hop | FLAG | d3ebd001 identifies Microsoft; 509b5324 gives Devices and Consumer $15,484m and −3%. Mixed-side gold names OpenAI (S1). $15.5bn and a 3% decline are acceptable rounded variants. |
| rq-d-015 | dev | multi_hop | FLAG | c95ca17e identifies Microsoft; 509b5324 supports Microsoft Cloud $63.9bn, +30% reported (+31% constant currency). Mixed-side gold names OpenAI (S1). Growth is supported but not requested. |
| rq-d-016 | dev | multi_hop | OK | 8faa6a57 uses SEC EDGAR; 510738e2 expands the regulator name and schedules 9 November. This is an announcement of a future event, correctly asked in past scheduling language; Research/Finance is defensible. |
| rq-d-017 | dev | time_sensitive | FIXED | Revenue KRW 195.3tn is supported by 5bef2525, replacing 90445a7a’s approximate KRW 195tn. Corrected News → Finance; both source dates fit the latest scope. |
| rq-d-018 | dev | time_sensitive | FIXED | 90445a7a’s table labels KRW 89.49tn as Q2 operating profit; Q3 KRW 107.40tn was still an estimate on 20 October. Date lies between releases. Corrected News → Finance. |
| rq-d-019 | dev | time_sensitive | FIXED | Guided KRW 107.3–107.5tn range and 107.40 midpoint are in 90445a7a; 5bef2525 later supplies actual results. Corrected News → Finance; event-relative before scope is consistent. |
| rq-d-020 | dev | time_sensitive | OK | 43f3b1ec gives preliminary $18.5–19.5bn; e6a19626 gives final net sales $19.9bn on 3 November. Fiscal 2027 Q1 is the quarter ended September 2026. |
| rq-d-021 | dev | time_sensitive | OK | 25 October falls between 20 October and 3 November. The applicable preliminary estimate is $18.5–19.5bn, superseding $14.5–15.5bn original guidance. |
| rq-d-022 | dev | time_sensitive | FLAG | 12.0–12.5% is supported, but the same preliminary item also states earlier 10.4–10.8% guidance. Both are before final results; wording lacks most-recent/preliminary-update qualification. Do not silently choose one. |
| rq-d-023 | dev | freshness | OK | 6f669344 uniquely gives the 26–27 October 2027 strategy meeting and policy-announcement exception. Tentative status retained. Freshness identity/date checks pass. |
| rq-d-024 | dev | freshness | OK | 6c5f9d64 supports estimated average price increase 1.4% for mature payment services, distinct from 101.5% cost recovery. Unique contextual fact; latest-window freshness passes. |
| rq-d-025 | dev | freshness | OK | a80f73b9 spells Katilyn M. Robinson exactly and states customer-fund misappropriation; no competing name or enforcement action for that person found. Freshness passes. |
| rq-d-026 | dev | freshness | FLAG | The 1 May 2026 commencement date is correct and corpus-unique; companion CMA pages omit it. However it is a historical public-law fact preceding the corpus window, hence a prior-knowledge risk for a freshness test. Keep only with that limitation accepted. |
| rq-d-027 | dev | freshness | FLAG | 9b2692ab supports six engines at 140 MHz and 21.1k LUTs; fact is unique in context. key_facts additionally requires LUT count although neither the question nor reference_answer asks for it: scoring overconstraint. |
| rq-t-001 | test | single | OK | 904be74c supports approximately $43bn undiscounted maximum; 72.5% is the liability formula input, not the cap. |
| rq-t-002 | test | single | FLAG | 4.500 Marvell shares per Lumentum share is correct. c4bbb8b3, currently a distractor, explicitly gives that exact exchange ratio; 75ee4f31 does too. Alternatives must not be treated as negative evidence (U1). |
| rq-t-003 | test | single | OK | acb0bb57 states FY2030 total revenue $225bn+, distinct from the FY2027 outlook; preserve at-least/plus qualifier. |
| rq-t-004 | test | single | FLAG | ed092e93 supports $773m and 50% growth. b9715cb4 supplies the same $773m and $515m comparator (about 50% growth); missing alternative gold/notes, affecting exact-item recall. |
| rq-t-005 | test | single | OK | a86bd392 explicitly distinguishes 250m agreed depositary shares, each 1/20 interest, from the optional 37.5m extra shares. Reference and facts supported. |
| rq-t-006 | test | single | OK | 939a45ab states at least three years for carrying non-FOX content; no competing FOX/Roku commitment in the corpus. |
| rq-t-007 | test | single | OK | 60ce7dcd distinguishes approximately $1.25m agreed over five years from about $55,000 actually received. Both requested quantities are supported. |
| rq-t-008 | test | single | OK | 7a85fbb1 supports 2030 key-establishment and 2031 signature deadlines for federal high-value assets, distinct from the older general 2035 target. |
| rq-t-009 | test | single | OK | 185889d3 identifies Florida and Georgia and the appeals-court context; other state-law articles concern different actions/jurisdictions. |
| rq-t-010 | test | single | OK | 0cc91334 supports exact entity names and more than $130m raised. Other SEC fraud releases involve different defendants and amounts. |
| rq-t-011 | test | single | OK | cefc0930 supports 77.6% fully correct lines; 26.8%, 55.0%, 63.6% are comparator methods, not alternate answers. |
| rq-t-012 | test | single | OK | 37222495 supports 8.05% across five characters on 12,800 A10 games; 8.2% is a separate 2,000-game panel and 80.2% is A0. |
| rq-t-013 | test | single | OK | be81cefa supports median correct prediction 90ms before word end on LibriSpeech test-clean; competitor models’ 90–400ms are after word end. |
| rq-t-014 | test | single | FLAG | 9509c40e supports 9th and single-policy Q=0.392, but also reports public submission Q=0.446 including some Astra results. Final-leaderboard wording risks conflating policy-only and submitted-system scores. Source is insufficient to resolve leaderboard association; no edit. |
| rq-t-015 | test | single | OK | 0b4d895e supports verification share 74.8–93.6% for the three specified RSI methods; 65.6–71.0% is baseline token savings. |
| rq-t-016 | test | multi_hop | FLAG | c7708a09 → da5cc113 correctly yields Harvey C. Jones, appointed 11 November; aliases occur. 6efa7d34 is explicitly acceptable corroboration but stored as a distractor. Exact retrieval labels need alternative-support semantics (U1). |
| rq-t-017 | test | multi_hop | FLAG | c2cadf01 identifies Blackwell; 4f4e68d2 says Blackwell Ultra → Vera Rubin HBM capacity rose about 3%, distinct from 30x throughput/$; mixed-side gold HPE/Dell conflicts with S1. |
| rq-t-018 | test | multi_hop | OK | 6bbb2a8b identifies Cisco through the ATS decision; 8dcb1e89 appoints Girish D. Rishi of Cognite effective 9 October. No one gold item supplies both identifiers and answer. |
| rq-t-019 | test | multi_hop | FLAG | 378b27e8 identifies Apple’s 20 October NFC consultation; 30589f0e supports $114.5bn (table $114.477bn). Mixed-company CMA bridge also names Google: S1. |
| rq-t-020 | test | multi_hop | FLAG | 99e3e5da identifies Meta’s Spectrum-X collaboration; 99de9e9e gives Q3 charge $9.89bn, distinct from $18.59bn total settlement. OCP bridge names Google/Microsoft: S1. |
| rq-t-021 | test | multi_hop | FLAG | OCP item identifies AMD; 76535d0b supports about $8.2bn in common stock for World Labs. OCP bridge names Google/Microsoft (S1); AMD also appears as a ticker in the filing, so alias difficulty is mild. |
| rq-t-022 | test | multi_hop | FLAG | f9343678 identifies Palantir Foundry/Ontology/AIP; 6c9efc49 supports $984m US commercial revenue, not government or all-US totals. Bridge also names Dell: S1. |
| rq-t-023 | test | multi_hop | FLAG | 4d5cc1c4 → Palantir → 6c9efc49 supports $8.530–8.534bn guide. The extra key_fact treats 91% growth as an acceptable substitute for an absolute dollar range; these are different requested quantities and should not be interchangeable. |
| rq-t-024 | test | multi_hop | FLAG | f9343678 identifies Snowflake; d210bc08 supports $3.70bn net ($4.24bn with full options), distinct from $3.75bn principal. Bridge names Dell (S1); 7a4b80e2 corroborates offering details rather than contradicting them. |
| rq-t-025 | test | multi_hop | FLAG | a1da460c → Claude Opus 5.5 → 6d389204 → Anthropic → af60f5ac supports ≤US$500m at IPO price. Opus leads numerically, not significantly; OpenAI has same cap with different share terms. Amazon bridge names dev companies: S1. |
| rq-t-026 | test | multi_hop | REJECT | 95530714 alone identifies the handwritten-exam study and supplies r=0.97, so Amazon’s agent list adds no necessary lookup. key_facts also wrongly accepts MAE=0.85 as correlation (different statistic). Mixed-side Amazon bridge: S1. R3. |
| rq-t-027 | test | multi_hop | OK | dd3202e0 identifies TSMC commercial 65nm PDK; 80b4295f supports 2nm wafer share 8%. b12b6e7e has a technology-chart heading but no extracted 2nm percentage, so it is not alternative evidence in this text corpus. |
| rq-t-028 | test | multi_hop | OK | 27a499f3 identifies IBM Heron ibm_kobe; b622243b supports expected free-cash-flow increase of more than $1bn Y/Y, distinct from YTD $7.8bn. |
| rq-t-029 | test | multi_hop | FLAG | 0e8e1a03 identifies Amazon; 6d389204 gives Q4 advertising growth in the high teens, not Q3 12% ex-FX. Mixed-side Amazon bridge: S1. |
| rq-t-030 | test | multi_hop | REJECT | Question explicitly supplies AMD Helios, so b64c2e06 alone yields Instinct MI450 Series. Robotics and model-owner hops are redundant; cross-split Microsoft is even in the target workload list. R1 and S1. |
| rq-t-031 | test | multi_hop | OK | 4d5cc1c4 identifies Palantir; 0b99019f supports California resident/private fund/pre-IPO shares. The company itself is not the charged fund manager. No single item supplies Zyter link plus enforcement answer. |
| rq-t-032 | test | multi_hop | FLAG | 692eaf47 → Apple → 30589f0e supports John Ternus, with Kevan Parekh separately CFO. iOS already identifies Apple from ordinary product knowledge and Apple CEO can be recalled without retrieval. Mixed-side EFF item names Google/Samsung: S1. Accurate but weak multi-hop isolation. |
| rq-t-033 | test | multi_hop | OK | 23512c6f identifies IBM devices and 4ed129d7 gives fourteen directors effective 1 October. Both alias forms occur, although IBM also occurs in the filing, so alias resolution is not strictly necessary. 68bc4819 announces Baker but does not give board size. |
| rq-t-034 | test | multi_hop | FLAG | 4f4e68d2 identifies Meta among NVFP4 model builders; 99de9e9e supports $34.91bn including finance-lease principal. Mixed-side memory item names HPE/Dell: S1. |
| rq-t-035 | test | multi_hop | OK | 162280b6 identifies UC Berkeley; fd7933fb links Berkeley authors/BAIR to 33 main-conference papers. Four LBR posters and ten orals/spotlights are different counts. Alias forms occur, but Berkeley is also explicit in the lab page. |
| rq-t-036 | test | time_sensitive | OK | da5cc113 supports interim CEO Colette M. Kress while remaining CFO, effective 11 November; c7708a09 supplies old Huang state. 6efa7d34 corroboration and older CEO posts are already acknowledged in notes. Keep current answer distinct from old assertions. |
| rq-t-037 | test | time_sensitive | FLAG | As-of 1 November lies between gold publication dates and Huang is correct. But 66b41ebe/4f3416cd/a91dcd5b also call him CEO and are unlisted; this is also a widely recallable CEO fact. Time-sensitive answer accuracy alone cannot show temporal retrieval. |
| rq-t-038 | test | time_sensitive | OK | October NT$586.89bn in 259893e2 supersedes September NT$511.86bn in 5a093fbb; latest scope and units consistent. |
| rq-t-039 | test | time_sensitive | OK | As-of 20 October selects January–September NT$3,898.73bn. Source typo T$ is verbatim; the NT$-million table independently confirms currency and rounding. November cumulative figure is later. No correction to quote warranted. |
| rq-t-040 | test | time_sensitive | OK | Immediately before October revenue publication, September’s change is −0.6% versus August, not October’s +14.7%. Event-relative scope agrees with 8 October/10 November items. |
| rq-t-041 | test | time_sensitive | OK | 80b4295f says Q3 figures not board-approved; af60f5ac approves the Q3 report/statements on 10 November. Genuine changed status; no inference from publication alone. |
| rq-t-042 | test | time_sensitive | OK | 29 October item schedules 4 November arrival; 5 November item confirms launched/streaming. Current status and launch date are supported, and the game identity is specific. |
| rq-t-043 | test | time_sensitive | OK | e3d671e8 says coming this month; a91dcd5b later specifies Friday 23 October. Valid plan refinement rather than a contradictory launch date. |
| rq-t-044 | test | time_sensitive | FLAG | $2.2bn proposed → $1.75bn priced 2031 tranche is supported. Both releases date 28 September and both manifest entries date 2 October: no date boundary between them. Event-text ordering works; date-only changed-fact evaluation does not (T1). |
| rq-t-045 | test | time_sensitive | OK | 5fa2f857 supports latest completed USD offering as of 8 November: $2.75bn 7.500% due 2056. ea94630d’s 6.400% due 2065 offering is completed only on 12 November. |
| rq-t-046 | test | time_sensitive | OK | acb0bb57 sets $20bn additional-raise plan; 16e9a090 explicitly heads equity issuance $10bn and debt $10bn, each closed 4 November. Preserve gross proceeds and refinancing exclusion. |
| rq-t-047 | test | time_sensitive | FLAG | World Labs and Taalas pending agreements are supported by 76535d0b/b64c2e06. c88e556c explicitly corroborates both but is a distractor; this is alternative support, not a competing wrong answer (U1). No closing is reported in the corpus. |
| rq-t-048 | test | time_sensitive | OK | f22f6cac states seven current directors; 5ee625bf expands to ten effective 12 November. 830d165f corroboration is already noted. Distinguish later independent appointments from future Lumentum merger seats. |
| rq-t-049 | test | time_sensitive | OK | Seven as of 5 November is supported; 830d165f increases to ten only effective 12 November. The three merger-related Lumentum directors were future appointments, not already seated. |
| rq-t-050 | test | time_sensitive | FLAG | $3.5bn before $3.75bn upsize is supported, and d210bc08 itself retrospectively contains both values. Same publication/event dates prevent an intervening as-of boundary; unsuitable for strict dated changed-fact scoring without explicit event ordering (T1). |
| rq-t-051 | test | freshness | OK | b2727e77 uniquely supports Cisco FY27 hyperscaler AI-infrastructure revenue expectation $9bn; not overall company revenue. Freshness latest-window/list/one-owner checks pass. |
| rq-t-052 | test | freshness | OK | 957e8680 enumerates all tranches and the $2bn 5.350% due-2036 tranche is largest. Exact issue date and contextual uniqueness pass freshness checks. |
| rq-t-053 | test | freshness | OK | b8b52c86 supports 97 Q3 2026 IPR petitions versus 327 Q3 2025, not September’s 37 versus December 2024’s 129. Contextual uniqueness and freshness pass. |
| rq-t-054 | test | freshness | OK | c161a652 supports 1.71 percentage points/month overall; 1.91 is 2024 only. Preserve percentage points, not relative percent. Contextual uniqueness and freshness pass. |
| rq-t-055 | test | freshness | OK | bc277f19 supports 66.2% full checklist pass; 7c9eebcf only matches numeric substring inside an ASML balance-sheet entry. No competing ARE-bench result; freshness passes. |
| rq-t-056 | test | freshness | OK | 0c025868 supports enhanced A* all 480 versus best-first B&B 445 under equal limits. Additional pruning is material; do not generalize to every A* implementation. Freshness passes. |
| rq-t-057 | test | freshness | OK | 27b21c79 supports kernel MAPE 8.3% versus 14.1% best baseline, distinct from vLLM end-to-end 2.0%. Contextual uniqueness and freshness pass. |
| rq-t-058 | test | freshness | OK | cd9a0000 supports amortised 2.36 minutes/input on one GPU; f9f2e072’s 42.36% token reduction is unrelated, not duplicate support. Freshness passes. |
| rq-t-059 | test | freshness | OK | 358b6cdc supports weighted-average 61.6%/72.2% Safe-Pass@1/@3 across seven benchmarks; no matching contextual result elsewhere. Freshness passes. |
| rq-t-060 | test | freshness | OK | db84505a supports average MAPE 31.69% → 22.24%; accept a 9.45 percentage-point reduction (about 29.8% relative). 34.04% → 23.98% is the LLM-operator subset. Freshness passes. |

## Routing-label spot check (25 of 80)

Deterministic selection: zero-based routing-label indices 0, 3, 5, 8, 9, 10, 16, 22, 26, 28, 29, 30, 31, 34, 35, 40, 42, 49, 53, 54, 61, 67, 70, 72, 77. This covers nine News-hint, ten Finance-hint and six Research-hint items, including all five annotations differing from their source hint. All 25 are defensible under the stated annotation conventions; no clear routing-label error was established. Boundary alternatives are documented rather than silently edited. This is not a statistical estimate of accuracy for all 80.

| Item | Annotated labels | Result and text-based reason |
|---|---|---|
| 9fcaeedc | News | Supported: Competition-policy case page; News despite economic subject. |
| d02369ad | News | Supported: CMA notice publishing competition-law guidance; News. |
| dcfca97c | News | Supported: Copilot Home/Code/Autopilot launch and availability; News. |
| e8ca2bd5 | News | Supported: Healthcare startup feature and deployment descriptions; News, not a clinical study. |
| d36750f8 | News | Supported: Commissioned IDC survey framed as vendor adoption advice; News defensible. Research is a boundary alternative, not settled by sponsorship alone. |
| 60ce7dcd | News | Supported: DOJ bribery plea and contracting facts; News. |
| 6bbb2a8b | News | Supported: Legal advocacy about Cisco/ATS ruling; News. |
| 4f4e68d2 | News | Supported: Vendor explanation of deployed memory products; News defensible, not a new research-method evaluation. |
| 7a85fbb1 | News | Supported: Agency announcement of migration guidance and deadlines; News. |
| 04993caf | Finance | Supported: Director non-reelection and governance disclosure; Finance under the set’s corporate-governance convention. Not classified from the SEC wrapper alone. |
| b64c2e06 | Finance, News | Supported: Financial results plus substantial product/customer/acquisition announcements; Finance + News. |
| f22f6cac | Finance, News | Supported: Merger consideration and financial effects plus corporate combination announcement; Finance + News. |
| 1f9eb868 | News | Supported: Employee-data disclosure, with no financial result; News despite 6-K wrapper. |
| 510738e2 | Finance | Supported: Regulator policy discussion of machine-readable market data; Finance defensible. News also plausible; annotation taxonomy should allow this boundary. |
| 7c9eebcf | Finance | Supported: US GAAP financial statements and quarterly tables; Finance. |
| 30589f0e | Finance, News | Supported: Earnings and capital-return tables plus named new product lineup; Finance + News. |
| 509b5324 | Finance | Supported: Revenue/profit/segment tables and financial outlook; Finance. |
| a80f73b9 | Finance | Supported: Bank-employee prohibition for customer-fund misappropriation; Finance. |
| f436d43a | Finance, News | Supported: Alphabet earnings plus model/product milestones; Finance + News. |
| cd9a0000 | Research | Supported: MOAI method, HE optimizations and measured inference results; Research. |
| a1da460c | Research | Supported: ExpertCrowd-SWE benchmark construction and model comparison; Research. |
| 4daf6932 | Research | Supported: Flint interactive language/compiler design and examples; Research defensible despite developer-facing product presentation. |
| 4e3f7c1c | Research | Supported: Synthetic enterprise evaluation methodology, safeguards and query generation; Research. |
| 93a879f7 | Research | Supported: Retrosynthesis architecture and Nature validation results; Research. |
| 2c5be933 | Research | Supported: Tabular model comparison on financial forecasting; Research, not automatically Finance because of application domain. |

## Freshness audit

All 15 freshness items are in the correct split’s freshness_item_ids, appear as gold in exactly one question, and are not gold in another question. Test dates span 9–12 November; dev dates 10–12 November. These are in the latest four days of the corpus, not necessarily the fifteen most recent timestamps. Each requested contextual fact was searched outside its item; no duplicate contextual fact was established. Shared bare numbers in financial tables are not duplicates. rq-d-026 and rq-d-027 are held for the prior-knowledge/scoring concerns above, not because their source dates or list memberships failed.

| Question | Fresh item | Publication date | Contextual uniqueness check |
|---|---|---|---|
| rq-d-023 | 6f669344 | 2026-11-12 | FOMC strategy-meeting exception, not arbitrary 26/27 date matches. |
| rq-d-024 | 6c5f9d64 | 2026-11-12 | Mature payment-service average price increase, not other 1.4 values. |
| rq-d-025 | a80f73b9 | 2026-11-12 | Exact Robinson name and customer-fund prohibition. |
| rq-d-026 | 6f93879f | 2026-11-10 | TTBEO commencement; both companion CMA items omit the date. Prior-knowledge FLAG remains. |
| rq-d-027 | 9b2692ab | 2026-11-10 | SkipLane six-engine frequency; unrelated 140 values excluded. Extra-key-fact FLAG remains. |
| rq-t-051 | b2727e77 | 2026-11-12 | Cisco hyperscaler AI-revenue expectation for FY27, not arbitrary 9 values. |
| rq-t-052 | 957e8680 | 2026-11-09 | Apple amount/coupon/maturity conjunction. |
| rq-t-053 | b8b52c86 | 2026-11-09 | PTAB IPR Q3-year comparison, not arbitrary 97/327 table cells. |
| rq-t-054 | c161a652 | 2026-11-10 | Fixed-model voting drift; 2024-only 1.91 is a different scope. |
| rq-t-055 | bc277f19 | 2026-11-10 | ARE-bench full-checklist rate; ASML substring 666.2 is unrelated. |
| rq-t-056 | 0c025868 | 2026-11-10 | A*/B&B paired optimality counts under equal limits. |
| rq-t-057 | 27b21c79 | 2026-11-10 | ForeSight kernel-error/baseline pair; other GPU studies use different methods. |
| rq-t-058 | cd9a0000 | 2026-11-10 | MOAI minutes/input; C2-Routing 42.36% is a different quantity. |
| rq-t-059 | 358b6cdc | 2026-11-10 | TopoVerus named paired pass metrics. |
| rq-t-060 | db84505a | 2026-11-10 | GemAtlas full four-GPU average versus LLM-only subset. |

## Recommendation and scoring exclusions

**Exclude these REJECT questions from scoring:** `rq-d-013`, `rq-t-026`, `rq-t-030`.

**Quarantine these FLAG questions from scoring until adjudicated:** `rq-d-001`, `rq-d-009`, `rq-d-011`, `rq-d-014`, `rq-d-015`, `rq-d-022`, `rq-d-026`, `rq-d-027`, `rq-t-002`, `rq-t-004`, `rq-t-014`, `rq-t-016`, `rq-t-017`, `rq-t-019`, `rq-t-020`, `rq-t-021`, `rq-t-022`, `rq-t-023`, `rq-t-024`, `rq-t-025`, `rq-t-029`, `rq-t-032`, `rq-t-034`, `rq-t-037`, `rq-t-044`, `rq-t-047`, `rq-t-050`.

**Keep these OK/FIXED questions provisionally:** `rq-d-002`, `rq-d-003`, `rq-d-004`, `rq-d-005`, `rq-d-006`, `rq-d-007`, `rq-d-008`, `rq-d-010`, `rq-d-012`, `rq-d-016`, `rq-d-017`, `rq-d-018`, `rq-d-019`, `rq-d-020`, `rq-d-021`, `rq-d-023`, `rq-d-024`, `rq-d-025`, `rq-t-001`, `rq-t-003`, `rq-t-005`, `rq-t-006`, `rq-t-007`, `rq-t-008`, `rq-t-009`, `rq-t-010`, `rq-t-011`, `rq-t-012`, `rq-t-013`, `rq-t-015`, `rq-t-018`, `rq-t-027`, `rq-t-028`, `rq-t-031`, `rq-t-033`, `rq-t-035`, `rq-t-036`, `rq-t-038`, `rq-t-039`, `rq-t-040`, `rq-t-041`, `rq-t-042`, `rq-t-043`, `rq-t-045`, `rq-t-046`, `rq-t-048`, `rq-t-049`, `rq-t-051`, `rq-t-052`, `rq-t-053`, `rq-t-054`, `rq-t-055`, `rq-t-056`, `rq-t-057`, `rq-t-058`, `rq-t-059`, `rq-t-060`.

Fit-for-use decision: **No for the full set as currently labelled.** The kept subset is usable for exploratory answer checking with the noted acceptable variants, a fixed corpus cutoff and an evidence-equivalence policy. Do not use the full JSON unfiltered for headline RAG, cross-bubble or changed-fact metrics. Resolve split-rule wording, redundant-hop questions, alternate-support handling, temporal ties and reference/key-fact mismatches before freezing a scoring set. Resolve dev shortfalls separately without adding weak or test-tuned questions. No holdout-driven system tuning was performed.

## Whole-corpus search ledger

Terms are independently extracted from the question; candidate IDs are the three highest-scoring non-gold lexical matches. The manual entity/number/context checks are described above and in the decision rows. False positives are expected. Gold IDs are included for source traceability.

| Question | Gold item prefixes | Six search terms | Non-gold candidates |
|---|---|---|---|
| rq-d-001 | cbca4caf | asml, fourth, guide, sales, range, net | 7c9eebcf, 321561f3, 30022352 |
| rq-d-002 | fe02a290 | agree, braze, salesforce, enterprise, price, cash | 1901c032, b5bb5bd8, c88e556c |
| rq-d-003 | d0d4e232 | retiring, succeed, dell, counsel, legal, technologies | 830d165f, 0ba904b8, 509b5324 |
| rq-d-004 | e1eb2e37 | hpe, networking, center, revenue, rate, investor | c4bbb8b3, b64c2e06, abdb6870 |
| rq-d-005 | ef70a066 | micron, revenue, ended | bd102c5f, e90047dd, 4d32cfb4 |
| rq-d-006 | 759f3904 | buoyancy, asian, monsoon, distillation, precipitation, equation | 2bd73c14, 4daf6932, f54782d9 |
| rq-d-007 | 69cf9e2d | accuracies, pyrite, ligand, pose, protein, ranking | d7d93a71, 4f3416cd, 350ce416 |
| rq-d-008 | 6e8793cc | firefox, window, smart, watch, active, user | 941f0ba7, bf2ae3ba, 47b27032 |
| rq-d-009 | 7174e2bb, f8764769 | eyewear, revenues, chip, intelligent, inside, december | f436d43a, b622243b, f2ab8644 |
| rq-d-010 | 1ff30f2f, f436d43a, 839e05d9 | euro, denominated, judge, diagnostic, proprietary, match | 0d1c4470, abeb6228, 0f13c522 |
| rq-d-011 | 23e20026, 8e63b58e | objected, switched, acoustic, supplied, chatbot, diagnostic | 77af2cde, 95530714, c64e11d2 |
| rq-d-012 | 2c5be933, f436d43a | tabular, firms, predicting, parent, lab, fast | d36750f8, fc43365a, 0f13c522 |
| rq-d-013 | 93a879f7, 092ccea5 | retrochimera, retrosynthesis, distributes, chosen, host, harness | 796f85ac, dcfca97c, a91dcd5b |
| rq-d-014 | d3ebd001, 509b5324 | respects, forces, says, vendor, mozilla, browser | 0f13c522, f436d43a, 23e20026 |
| rq-d-015 | c95ca17e, 509b5324 | reprogram, backdoor, dormant, neurons, malicious, researchers | 2bd73c14, d36750f8, a10e6051 |
| rq-d-016 | 8faa6a57, 510738e2 | regulator, roundtable, understandable, ifrs, electronic, embeddings | 3b0b30c2, 532cf528, 9d7eb9c6 |
| rq-d-017 | 90445a7a, 5bef2525 | electronics, samsung, consolidated, revenue, third | 80b4295f, b9715cb4, 6d389204 |
| rq-d-018 | 90445a7a, 5bef2525 | estimated, actually, profit, electronics, samsung, quarterly | c88e556c, 692eaf47, e6a19626 |
| rq-d-019 | 90445a7a, 5bef2525 | guided, profit, samsung, published, range, third | b622243b, 80b4295f, b64c2e06 |
| rq-d-020 | 43f3b1ec, e6a19626 | supermicro, revenue, first | c3bff6e2, 7c85619d, c4bbb8b3 |
| rq-d-021 | 43f3b1ec, e6a19626 | supermicro, revenue, expect, ended | 99de9e9e, b622243b, 6c9efc49 |
| rq-d-022 | 43f3b1ec, e6a19626 | supermicro, estimated, gross, final, margin, results | ef70a066, b2727e77, c88e556c |
| rq-d-023 | 6f669344 | tentatively, usual, meetings, scheduled, announcement, committee | 18e81a56, 4cce6250, 5bef2525 |
| rq-d-024 | 6c5f9d64 | banks, reserve, payment, established, federal, price | 4cce6250, 99de9e9e, b9715cb4 |
| rq-d-025 | a80f73b9 | announce, prohibition, reserve, whom, conduct, consent | 0ba82383, 6f669344, 6c5f9d64 |
| rq-d-026 | 6f93879f | exemption, force, block, transfer, come, order | f7860b03, a10e6051, a253c6c5 |
| rq-d-027 | 9b2692ab | cnn, pynq, skiplane, skipping, clock, frequency | a2830602, a91dcd5b, d4b07883 |
| rq-t-001 | 904be74c | backstop, owe, undiscounted, racks, broadcom, late | fd7933fb, 4cce6250, 62dae3fa |
| rq-t-002 | f22f6cac | lumentum, marvell, merger, agreed, holders, receive | 75ee4f31, 1a412b7a, c4bbb8b3 |
| rq-t-003 | acb0bb57 | oracle, outlook, revenue, term, investor, day | e1eb2e37, fc43365a, b64c2e06 |
| rq-t-004 | ed092e93 | licence, arm, fast, grow, line, record | 4cce6250, b9715cb4, 6d389204 |
| rq-t-005 | a86bd392 | agree, fraction, depositary, mandatory, meta, convertible | 7c85619d, 5fa2f857, 839e05d9 |
| rq-t-006 | 939a45ab | roku, fox, carrying, commit, justice, department | 60ce7dcd, 0f13c522, bbb7958f |
| rq-t-007 | 60ce7dcd | defence, army, bribe, civilian, hawaii, pleaded | 0ba82383, b8b52c86, 0d1c4470 |
| rq-t-008 | 7a85fbb1 | migrate, cryptography, nist, quantum, moving, federal | 37ba6be8, 4cce6250, 8c4e7a8f |
| rq-t-009 | 185889d3 | courts, enforcing, appeals, gate, age, young | 45bffe61, 54ba7876, c46a4c1e |
| rq-t-010 | 0cc91334 | wealth, relied, false, raise, roughly, entities | 0b99019f, e7241da1, 233392c7 |
| rq-t-011 | cefc0930 | aruz, markov, ottoman, scansion, lattice, hidden | 0d1c4470, eaf3b2d2, 796f85ac |
| rq-t-012 | 37222495 | ascension, slay, spire, averaged, characters, win | f54782d9, 23512c6f, 42a606a9 |
| rq-t-013 | be81cefa | recogniser, earlybird, audiobook, spoken, clean, word | 8f651811, dcfca97c, 2fb2b392 |
| rq-t-014 | 9509c40e | leaderboard, finish, entry, score, behavior, challenge | 162280b6, fc9686b0, 796f85ac |
| rq-t-015 | 0b4d895e | rsi, examined, recursive, verification, costly, improvement | 0c1f5103, 42a606a9, d7cd170f |
| rq-t-016 | c7708a09, da5cc113 | astana, kazakhstan, fireside, minister, stepped, chair | a253c6c5, 6efa7d34, 4cce6250 |
| rq-t-017 | c2cadf01, 4f4e68d2 | sided, codesign, hbm, mixture, vendor, parallel | 99e3e5da, 820a5281, a91dcd5b |
| rq-t-018 | 6bbb2a8b, 8dcb1e89 | alien, statute, supreme, tort, says, liability | 4cce6250, 59120c10, 0d1c4470 |
| rq-t-019 | 378b27e8, 30589f0e | contactless, handset, nfc, maker, consultation, authority | f8764769, 6f93879f, 939a45ab |
| rq-t-020 | 99e3e5da, 99de9e9e | hyperscaler, supernics, credited, ocp, attorneys, spectrum | 820a5281, e36b2ca0, 60ce7dcd |
| rq-t-021 | 99e3e5da, 76535d0b | designer, rival, agree, specification, processor, publishing | 162280b6, e8ca2bd5, f2a83ce1 |
| rq-t-022 | f9343678, 6c9efc49 | deploys, organisation, specialised, ontology, says, foundry | 9bd2920f, fc43365a, 0f13c522 |
| rq-t-023 | 4d5cc1c4, 6c9efc49 | authorisation, zyter, medicare, pilot, vendor, firm | 097fdf4a, b622243b, e8ca2bd5 |
| rq-t-024 | f9343678, d210bc08 | kumo, notebook, relational, priced, letting, vendor | 7c9eebcf, 162280b6, 017deb85 |
| rq-t-025 | a1da460c, 6d389204, af60f5ac | ceiling, bought, expertcrowd, buying, swe, scored | 2c2fd24d, 017deb85, 0ba904b8 |
| rq-t-026 | 6d389204, 95530714 | examiner, correlate, handwritten, marker, continuum, exam | 0d1c4470, 162280b6, 9bd2920f |
| rq-t-027 | dd3202e0, 80b4295f | nanometer, optimisation, analog, wafer, kit, circuit | c4bbb8b3, fc43365a, d6a7f8e2 |
| rq-t-028 | 27a499f3, b622243b | eigensolver, heron, qubits, processor, quantum, generative | 37ba6be8, 23512c6f, 99de9e9e |
| rq-t-029 | 0e8e1a03, 6d389204 | accuse, ftc, inflating, secretly, auctions, retailer | 0f13c522, 99de9e9e, af0b17e2 |
| rq-t-030 | 7b9fc55d, 6d389204, b64c2e06 | organisations, exam, helios, embodied, rack, amd | a91dcd5b, 820a5281, 0d3692e2 |
| rq-t-031 | 4d5cc1c4, 0b99019f | zyter, medicare, wiser, underpins, programme, appears | 097fdf4a, 0d1c4470, 7f207a76 |
| rq-t-032 | 692eaf47, 30589f0e | quoted, maker, ios, assistant, exclude, fourth | 6b8d9dee, 7174e2bb, f8764769 |
| rq-t-033 | 23512c6f, 4ed129d7 | enlarge, bandit, mitigation, contextual, quantum, controller | 73eb9276, 4f3416cd, 99e3e5da |
| rq-t-034 | 4f4e68d2, 99de9e9e | nvfp4, builders, checkpoints, lists, shipping, expenditures | 6d389204, 7fd29352, a91dcd5b |
| rq-t-035 | 162280b6, fd7933fb | californian, presenting, names, robot, papers, university | a91dcd5b, e1698167, f2a83ce1 |
| rq-t-036 | c7708a09, da5cc113 | serves, currently, nvidia, basis, chief, executive | 5ee625bf, 830d165f, 68bc4819 |
| rq-t-037 | c7708a09, da5cc113 | nvidia, chief, executive | 6efa7d34, 937dcced, 0ba904b8 |
| rq-t-038 | 5a093fbb, 259893e2 | tsmc, monthly, figure, month, latest, revenue | af60f5ac, 0ba904b8, 1f9eb868 |
| rq-t-039 | 5a093fbb, 259893e2 | cumulative, tsmc, far, revenue | b12b6e7e, 80b4295f, 5bef2525 |
| rq-t-040 | 5a093fbb, 259893e2 | tsmc, monthly, published, month, revenue, show | b12b6e7e, af60f5ac, 6d389204 |
| rq-t-041 | 80b4295f, af60f5ac | figures, tsmc, status, sign, approval, meeting | 532cf528, b12b6e7e, 9fcaeedc |
| rq-t-042 | d4b07883, 4729dbdd | warcraft, forever, geforce, status, world, current | 4ef022b2, a2830602, 36723e8d |
| rq-t-043 | e3d671e8, a91dcd5b | arrive, dgx, spark, firm, later, availability | 66b41ebe, 3758b4a0, a2830602 |
| rq-t-044 | 017deb85, d210bc08 | snowflake, convertible, proposed, notes, offering, compared | 7a4b80e2, 16e9a090, 839e05d9 |
| rq-t-045 | 5fa2f857, ea94630d | longest, tranche, completed, meta, notes, dated | 7a4b80e2, 16e9a090, 839e05d9 |
| rq-t-046 | acb0bb57, 16e9a090 | raising, cap, told, oracle, raised, investors | 7f207a76, 0b99019f, 9294de0c |
| rq-t-047 | 76535d0b, b64c2e06 | pending, amd, acquisitions, still, announced | c88e556c, fc43365a, 335b9598 |
| rq-t-048 | f22f6cac, 5ee625bf | appointments, sit, marvell, directors, latest, board | 830d165f, 75ee4f31, c4bbb8b3 |
| rq-t-049 | f22f6cac, 830d165f | marvell, directors, board | 5ee625bf, 75ee4f31, c4bbb8b3 |
| rq-t-050 | d210bc08, 017deb85 | upsized, snowflake, placement, deal, convertible, size | 7a4b80e2, 5de0ff1b, 839e05d9 |
| rq-t-051 | b2727e77 | hyperscalers, cisco, raise, expectation, revenue, infrastructure | 99e3e5da, e1eb2e37, 5bef2525 |
| rq-t-052 | 957e8680 | tranche, apple, largest, notes, issued, single | 3e750a4f, 4cce6250, d210bc08 |
| rq-t-053 | b8b52c86 | partes, petitions, patent, inter, trial, appeal | f8764769, 0b99019f, 8f651811 |
| rq-t-054 | c161a652 | climb, evaluator, votes, arena, chatbot, rising | 3b0b30c2, ff7dd746, a91dcd5b |
| rq-t-055 | bc277f19 | checklist, proportion, bench, strongest, frontier, pass | a1da460c, 092ccea5, a91dcd5b |
| rq-t-056 | 0c025868 | branch, scheduling, bound, optimal, instances, constrained | e1eb2e37, ebc9a045, 0c1f5103 |
| rq-t-057 | 27b21c79 | foresight, kernel, analytical, accurately, compare, predict | 4f3416cd, f5aca3fd, 820a5281 |
| rq-t-058 | cd9a0000 | amortised, moai, encrypted, transformer, input, gpu | d1ccfe31, 0d3692e2, 03018bb6 |
| rq-t-059 | 358b6cdc | topoverus, verus, repair, proof, seven, benchmarks | 0d1c4470, db9ea866, 37ba6be8 |
| rq-t-060 | db84505a | gematlas, cut, simulation, tested, gpus, error | 03018bb6, 162280b6, 27b21c79 |

## Validator: real output

Command: `.venv\Scripts\python.exe scripts/realdata/check_questions.py` (exit 0). This validator verifies structural constraints, quotes and token matches; its PASS does not invalidate the semantic FLAGS/REJECTS above. No --table option was used, so no authoring output was overwritten.

```text
[info] test freshness items published 2026-11-09 .. 2026-11-12
[info] dev freshness items published 2026-11-10 .. 2026-11-12
questions: 87  test/single=15  test/multi_hop=20  test/time_sensitive=15  test/freshness=10  dev/single=8  dev/multi_hop=8  dev/time_sensitive=6  dev/freshness=5
alias bridges: test=6 dev=3
gold items: test=69 dev=32 shared=0
routing labels: 80 {'news': 27, 'finance': 27, 'research': 26}; differ from hint: 5
uniqueness search: 87 questions searched; 51 have answer tokens in non-gold items (see table / notes)
WARN count dev/multi_hop: 8 (target 10) -> shortfall 2
WARN count dev/time_sensitive: 6 (target 7) -> shortfall 1
RESULT: PASS (0 failures, 2 warnings)
```

## Source index

Links target the local clean text used for verification, not a live web page. Full item IDs make the short prefixes auditable.

| Prefix | Full item ID | Published | Local source |
|---|---|---|---|
| 017deb85 | `017deb85fa5bc04f88f836deb23b217ce61a179cad7b67c5d5c875af91e26e65` | 2026-10-02 | [Snowflake Inc.: 8-K filed 2026-10-02: exhibit exhibit991-launchpressrele.htm](../../data/real/real-v2/raw/edgar-snowflake/13bf02067763f1566329b08506c62a4ef85dade4103609734512f5baa1f45556.txt) |
| 03018bb6 | `03018bb6e10503e95c6a82ad17c86d0c77c363a8cf10a6f5e303a9c9081b4724` | 2026-11-10 | [SFU-Sim: Bit-Exact Reverse Engineering of NVIDIA MUFU and Validation of …](../../data/real/real-v2/raw/arxiv-entities/72cdbd42249f6f7fb9511ce31a3ebffc2946a67e02e197a6e3318d4673728160.txt) |
| 04993caf | `04993caf723bf947093ffd7cb1701bc7fa06ef093d3f5d995a9f78b6b2ff4171` | 2026-11-05 | [MICROSOFT CORP: 8-K filed 2026-11-05](../../data/real/real-v2/raw/edgar-microsoft/3e8d6c8276f0ed570b8995135ef1d859ce9ce8de98fe61f8af84d8a89f333bb2.txt) |
| 092ccea5 | `092ccea5ebc08633f9116b0db24218e74c5b387a9d09331fb1f33593fd6b5a1f` | 2026-10-28 | [Introducing the Microsoft Copilot harness: Unlocking the potential of truly …](../../data/real/real-v2/raw/microsoft-blog/d202a7107ab36fcc1fb0a0be606656ea950bc3f6a47e783b86da08d382a0a631.txt) |
| 097fdf4a | `097fdf4af9c2d7a65c2cea8a7c1ea2741f0ede3ad371085862ddb2d361047026` | 2026-11-11 | [🤕 Medicare's AI Experiment \| EFFector 38.20](../../data/real/real-v2/raw/eff-deeplinks/c4664748421453a93405637c7b8cb2b69976a5195ba5dac612904fcf87f03a70.txt) |
| 0b4d895e | `0b4d895e86c1100206ed79e079058b1066734f54e5f38d81a8bb4f466af130f6` | 2026-11-10 | [The RSI Tax: When Recursive Self-Improvement Is Not Worth the …](../../data/real/real-v2/raw/arxiv-entities/c1f3f6f4795fa301428d842ef4ec97ef4f6ddbe1ca319d0de13386e1379a53ac.txt) |
| 0b99019f | `0b99019fac565aed8ff3d6351ea1122ef3cf884b3ff8ed494a13f017b9d87673` | 2026-11-10 | [SEC Announces Enforcement Annual Results for Fiscal Year 2026](../../data/real/real-v2/raw/sec-releases/d43bc66bc5c4b6556300b47b759bd7a62f21a351f4583bce364e98e5946b3419.txt) |
| 0ba82383 | `0ba8238342bfea495e808d5e3d438ec318b82fa6fb38f42dbafbf9ce736fd991` | 2026-10-06 | [SEC Seeks Final Judgment Against Former Western Asset Co-CIO Ken …](../../data/real/real-v2/raw/sec-releases/abea9d1593b323c2690154188101a4e897b89478ff5110b6c1851d28db558733.txt) |
| 0ba904b8 | `0ba904b8ad2a8e788c6d0f7c7e840a9cdcbf82b6aec0cd1105eb7bb63a315cd8` | 2026-10-22 | [TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD: 6-K filed 2026-10-22](../../data/real/real-v2/raw/edgar-tsmc/6b7097cc4b814f8b991668303e928a5e91e52d44c53b06003154f156a3760556.txt) |
| 0c025868 | `0c025868d83499a41c3c99b35857b558e495d62ea4a552c269a7e9288d2202d9` | 2026-11-10 | [Two Communities, One Problem: Branch-and-Bound vs. A* for Resource-Constrained Project …](../../data/real/real-v2/raw/arxiv-general/f69315aaeb4b0a79d0fd357514653b7d63b6ffbc406986d05e86f30922d53d36.txt) |
| 0c1f5103 | `0c1f5103614a251ebb81983815a560c5942a95d6fbc23e20f2b12540f47f5b99` | 2026-10-21 | [Solving a 31-year-old grand challenge in mathematics – the KLS …](../../data/real/real-v2/raw/microsoft-research/f503376208abeaa3537cbcb193020551d64248d3a03ab5c4c386698d72d0e894.txt) |
| 0cc91334 | `0cc91334623978a158d8953956f855f3acd88e198b1cb4cf73c2ede460a36fef` | 2026-10-29 | [Two Entities Charged in $130 Million Fraud Scheme That Used …](../../data/real/real-v2/raw/sec-releases/bfcc15c3bf10d0192b2532e6cb522c96a0dfdfa9075597053199a1d98e269557.txt) |
| 0d1c4470 | `0d1c4470ce9cca719de1a68021d2ba56150a5d2fb61a4245bebc4dee8e68448a` | 2026-11-05 | [Formally verifying agent-written full-stack web apps with PDD Kit](../../data/real/real-v2/raw/microsoft-research/5119dd3dfe99893e0374bc28e46a23c09730f13914198a4ecd785830b9e495b3.txt) |
| 0d3692e2 | `0d3692e26888fb6f0252767f52fdce0c065ff9773ad8b4d870f4d97c9de410ab` | 2026-09-23 | [Offloaded inference for real-world physical AI robotics](../../data/real/real-v2/raw/microsoft-research/35ee676fa5796c8b71aa37310bfe6381684c7009255dbbfd2fd76433ce5159ad.txt) |
| 0e8e1a03 | `0e8e1a038107f533fff2af164e6c69aa9b35227f98e74293f9ba6862a0dd5c85` | 2026-11-05 | [New Details Emerge in Amazon Ads Auction-Rigging Case](../../data/real/real-v2/raw/ftc-news/037f449784c2a7e5b9e64de18fdbfaadc632ffa38e27b0442e297100ca0acee4.txt) |
| 0f13c522 | `0f13c52215001e1cfe94665e190b551624627fbffca2ea6e929c070bd77d0e20` | 2026-10-28 | [MICROSOFT CORP: 8-K filed 2026-10-28: exhibit msft-ex99_1.htm](../../data/real/real-v2/raw/edgar-microsoft/b6c479b139ae07f17b49d9d38970e651b1c5964df72e717ffc713955e78d39b2.txt) |
| 162280b6 | `162280b6537a6ba3dcd5c57cb41a427719616d69198202c0d78ca43c340159ec` | 2026-11-09 | [Practice Makes Precise: At CoRL, NVIDIA and Partners Reveal How …](../../data/real/real-v2/raw/nvidia-blog/6f596c4d8f8909c0333930de178ec960c88a9fe4196338c981cb9b5c3736a44a.txt) |
| 16e9a090 | `16e9a090828cb3a7ecbc2f8c661b5bb913678d8e8a41c186247a12594bcc1950` | 2026-11-04 | [ORACLE CORP: 8-K filed 2026-11-04](../../data/real/real-v2/raw/edgar-oracle/9198b26b809724f14d7b53a5e2bde18655110ac02acbf84e201f647a7c5e4f5b.txt) |
| 185889d3 | `185889d3ce3dda885dc4d9a85c4895df996c24057fc0fd5322afc55fdd4c72ad` | 2026-10-23 | [Two States Can Now Restrict Social Media Access—Here’s What To …](../../data/real/real-v2/raw/eff-deeplinks/cb3f1fdecd216d3e35a74275c6669485ae662b0950e30c7197fa08df87210e6a.txt) |
| 18e81a56 | `18e81a569cd52be5c5173f3f2373d762793de386c97875fe483ff0e271fab461` | 2026-10-14 | [SEC Small Business Advisory Committee to Discuss IPO Modernization and …](../../data/real/real-v2/raw/sec-releases/706acfda883cd660e0fc9aaaa610af76fbd62f7c7d77567f56a51566b15efd06.txt) |
| 1901c032 | `1901c0324147bcb41b41df067f68389c37ac4ba652661084e0bea0655bf880ce` | 2026-10-20 | [Salesforce, Inc.: 8-K filed 2026-10-20: exhibit d516983dex992.htm](../../data/real/real-v2/raw/edgar-salesforce/75d8b2b462669c4233cee361179854306603e9b15d46a6641ffab27e5cccad77.txt) |
| 1a412b7a | `1a412b7a56462a6c4593c110f384e00b1917ae22c7fd39379a9b67cd240f2f46` | 2026-11-02 | [Marvell Technology, Inc.: 8-K filed 2026-11-02](../../data/real/real-v2/raw/edgar-marvell/857770058a6b3daf37ab1f3c6ea4a65c18d811454f2c54fed6a91f66bb44b87a.txt) |
| 1f9eb868 | `1f9eb8688ffab83a42b7c51bb63ce3f0a7cc967bacb608f02cb32d26077f882a` | 2026-11-12 | [TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD: 6-K filed 2026-11-12](../../data/real/real-v2/raw/edgar-tsmc/e7eeb31c3d673375675d135b66ccf68c52cd8df4cba2e33450980afbf18f959c.txt) |
| 1ff30f2f | `1ff30f2fbafc9172867581931c6bd586a774ec345dc01331f06c3110dabbb6e7` | 2026-11-10 | [PhyRubric: Rubric-Grounded Diagnostic Evaluation of Physical Commonsense in Text-to-Video Generation](../../data/real/real-v2/raw/arxiv-entities/ee86b1ded7ffa83f384208df0f665471ca0ede728ff8a1aaf3189e00c0911e6e.txt) |
| 233392c7 | `233392c77e81be53babb8c459fe74beb5bf30376bfb8e6821a3f27916a9a23b4` | 2026-09-28 | [SEC Charges Registered Investment Adviser Zoe Financial for Failure to …](../../data/real/real-v2/raw/sec-releases/e02fee236b66a66b3b08e943d754f98ba62dfd4a9f5f0077fe814f1c442bd36c.txt) |
| 23512c6f | `23512c6fd2eda728c8c50795e4232c803997860c0c960af587c3211c6f0460ab` | 2026-11-10 | [Adaptive Policy-Guided Error Mitigation (APGEM): A Unified Learning-Based Framework for …](../../data/real/real-v2/raw/arxiv-entities/0612687f7176a22ec44428fdf8157a2c24ee81a46c0bed4c4711313dd975af14.txt) |
| 23e20026 | `23e20026a4c06e9e316bfbc84039bebae86f1ada98c1fc4549db9382a2c55415` | 2026-11-06 | [Google Forcing AI on Students Is BS](../../data/real/real-v2/raw/eff-deeplinks/10c27cceb7328a273e83460d2ea12218e81b6ea9402665fadb5d58e84ad834d1.txt) |
| 259893e2 | `259893e236f204c37b31de27898dc299bd46c8c542790aba6475add502c9cd2a` | 2026-11-10 | [TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD: 6-K filed 2026-11-10](../../data/real/real-v2/raw/edgar-tsmc/49e10841ae8122e81464d75929005be9810c9ee04a80fcea53abd68b6b129365.txt) |
| 27a499f3 | `27a499f3fef4a638274e99b3f34461ccb1574b578efb10ea4a9cec40116aded2` | 2026-11-10 | [A Hardware-Trained Generative Quantum Eigensolver for Sample-Based Quantum Diagonalization of …](../../data/real/real-v2/raw/arxiv-entities/e358e8514884eb388082886975892473bbbdd844b701cf55f0c075a9c358c008.txt) |
| 27b21c79 | `27b21c79dcb04ce27d3114357ff72294f374a0d9a1c23addd2952948f684c04e` | 2026-11-10 | [Exploiting What NVIDIA Profilers Hide: Fast and Accurate Analytical GPU …](../../data/real/real-v2/raw/arxiv-entities/3f418a583d44cf7b0767de3cf46dc8176b9a958f3fb4c124f283e7843d0d6931.txt) |
| 2bd73c14 | `2bd73c14019c05a6e0248016eab6d751f1a0820e6b94310d8ba8f05e8deabdce` | 2026-10-29 | [Microsoft Research Focus – Edition #97](../../data/real/real-v2/raw/microsoft-research/8103eaf802dedfb0a0790ce7c016c045811d52529f48f32a3667d8f35c092ff3.txt) |
| 2c2fd24d | `2c2fd24d6f29afb3170e51ae3ca7c0015c9c126200303941acefd460f5f9c0ea` | 2026-11-09 | [Toward Sustainable Agentic AI: Carbon Tradeoffs Across Iterative Self-Refinement and …](../../data/real/real-v2/raw/arxiv-entities/e6494e301e693a204e6d20032c7252ce6ff90ba60f33f0bf3af6ed704288a9d1.txt) |
| 2c5be933 | `2c5be9330e2cbc2a90dbec07a4b9795a1140df3d63478c1e87a7ab50c735cafb` | 2026-11-10 | [Tabular Foundation Models in Financial Predictions](../../data/real/real-v2/raw/arxiv-entities/b5990c07cae448f2f3c65f01f49af3f529727552dd4fa38fa0645309cfa36734.txt) |
| 2fb2b392 | `2fb2b3925075da931728d8b6dc2bcac0284b7c9afebe1f8bfec93e72bd7238fa` | 2026-11-09 | [A Multi-Word Tokenizer for 204 Languages That Needs Fewer Tokens …](../../data/real/real-v2/raw/arxiv-entities/8cd0cea1df70551df80dfbaee32e89b72cd68b59d369bdacd0887f9539964dcc.txt) |
| 30022352 | `30022352e51492b6206f594f36612c26de3f0d0b4dfce63498caf1867fee722b` | 2026-10-14 | [ASML HOLDING NV: 6-K filed 2026-10-14](../../data/real/real-v2/raw/edgar-asml/f783cfbdba87288c6581f79c73ad50a7acda003db505f56f41c9b217fefb1ac3.txt) |
| 30589f0e | `30589f0ec53590d9caa0274a226c6d03fab0b8c477971cbe6d8ea7a0b1392aea` | 2026-11-02 | [Apple Inc.: 8-K filed 2026-11-02: exhibit a8-kex991q4202609262026.htm](../../data/real/real-v2/raw/edgar-apple/6d02167447ca83f0eef7aa59371190fccf4ac2a8111f1830da65a0e74a0d500c.txt) |
| 321561f3 | `321561f3ed881e6ce4981b3ece28e394a904037bb5a085db9a4bcd738b0b6e85` | 2026-10-14 | [ASML HOLDING NV: 6-K filed 2026-10-14: exhibit a2026_10x14xpresentation.htm](../../data/real/real-v2/raw/edgar-asml/3a5e41a5aef68e554af74c9bf54a39374eabec754c526c4e123a12fb39cf4f93.txt) |
| 335b9598 | `335b9598350ee40d9d7f06dcb2aa9f453b621b07de1a050a3a27554cc2db270f` | 2026-11-03 | [ADVANCED MICRO DEVICES INC: 8-K filed 2026-11-03](../../data/real/real-v2/raw/edgar-amd/13270e7a0158d30361754695f5ea27d0a671dd5cd5ce66ff4a55beefc5694c46.txt) |
| 350ce416 | `350ce416c6b5bbc5004df6afdbe935f44e4e742f4e34f5227cd4ed6c84a56afc` | 2026-11-10 | [ReTrace: Distilling Tool-Using Agents into Planner-Free Workflows](../../data/real/real-v2/raw/arxiv-general/7c5f531b4a4377acabf1dd57bdcf7c9456cbc2c6307a636687dd2ec7fd3b35d9.txt) |
| 358b6cdc | `358b6cdcd776ed9d655838070e8f19d6ad5a2fe1d2fcfc586ceb4f12030fd235` | 2026-11-10 | [Curriculum proof repair with learned counterexamples](../../data/real/real-v2/raw/arxiv-entities/367a47ade1dc5e25e9f437f7f887ad2628dfab2beb817fa1b123d3943ed8972a.txt) |
| 36723e8d | `36723e8d587ef6c44027fc869996e1ee9a76b55c6eb983b3d5bf1bc52ab5c236` | 2026-10-22 | [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives …](../../data/real/real-v2/raw/nvidia-blog/17111836506ee3070408f9ff67548ed9a3278d077a9f030dbd3c30ca4af2223a.txt) |
| 37222495 | `37222495b652481a3b0de18d8d13ec0a3ced27d56b96f539a90c00e760754034` | 2026-11-09 | [Zero-Search Reinforcement Learning for Slay the Spire 2 with Failure-Driven …](../../data/real/real-v2/raw/arxiv-entities/a28933dfc95ea0714d21329785fc1d69db9a1277aa23b77fd2638d116836c96c.txt) |
| 3758b4a0 | `3758b4a0fa594418d5b7dc919f438e9895ee6829449c71af49feb718292769f8` | 2026-10-15 | [Dial Up the Cloud: NVIDIA DLSS 4.5 Controls Arrive on …](../../data/real/real-v2/raw/nvidia-blog/766a0b946ca069a0c3994ac99e6191830c90e738d7447bba3991cf7697858260.txt) |
| 378b27e8 | `378b27e8577fe9de8595f8d763dfcf5f452b9d6d15d51c6ba90bfe8a7aecc98d` | 2026-11-05 | [Apple’s mobile platform](../../data/real/real-v2/raw/uk-cma/5ef47ba784ff8b7498839ef1b1dbb361b76d502fd470a7f7f1aa9175bb6fc746.txt) |
| 37ba6be8 | `37ba6be81a06cae1a488ce79a00e8d60bca8c534edf2f356e9f9b9b029585cae` | 2026-10-15 | [Proof-based general-purpose computing with Magnetar](../../data/real/real-v2/raw/microsoft-research/4c229237fce0ce8a88911b8b6b3889efe207c75bd440a528a6f1de8abc98c872.txt) |
| 3b0b30c2 | `3b0b30c2117bae0d1c44cf1f30379179bf8adca0a0df0c7b45777ff0329f6665` | 2026-11-09 | [Detecting AI-Authored Text in Authentic Student Writing: Evidence from PISA …](../../data/real/real-v2/raw/arxiv-entities/bd0afaff7f03d867d207b4b6fd0328073cf4fd4b571ee7676729b8585002a217.txt) |
| 3e750a4f | `3e750a4fad39458fc870bed9116385d38c4023bab456a525f9c55d258a939d47` | 2026-11-02 | [Apple Inc.: 8-K filed 2026-11-02](../../data/real/real-v2/raw/edgar-apple/9365d8f6f07a86f435d49365cc64691257e3a0ef6cbadec5fa84b221deeef9b2.txt) |
| 42a606a9 | `42a606a922d9dbf2761e44590564f2834435262358694cffa4fdf44b4a6e5e6a` | 2026-10-12 | [Simulating student learning for better AI tutoring](../../data/real/real-v2/raw/microsoft-research/bc34612b894ef31073c4715ee751bc541724eb03678f5505866bdb45898ad3bf.txt) |
| 43f3b1ec | `43f3b1ecf57c562d03480b0eb5d4f0b2679e5d972ae8e1c432e41dbe09cb989b` | 2026-10-20 | [Super Micro Computer, Inc.: 8-K filed 2026-10-20: exhibit smcifirstquarterfy2027busi.htm](../../data/real/real-v2/raw/edgar-supermicro/9fb73edcebd1122d21c12f32007362973529104bf715a48aa64152ee7a36c26d.txt) |
| 45bffe61 | `45bffe61fe0947716d29b927770312085e643a771d0e36e6aac5d60b93566c80` | 2026-11-05 | [Reflecting on Digital Rights Wins and Losses in Sacramento](../../data/real/real-v2/raw/eff-deeplinks/0d7369a6b15c9b0d7e7ec45a612652852e24faf0749c446bd60934039c269d73.txt) |
| 4729dbdd | `4729dbddfbc0e8991109a7aba0386da7e12b30a53670d23d88a92803660c5b43` | 2026-11-05 | [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on …](../../data/real/real-v2/raw/nvidia-blog/6a2031aebbc3642885a22f7fd66d1b1bbb45aca9bc44e8083c68b5a6662bc15e.txt) |
| 47b27032 | `47b270322a4f45f0d3b5ce4790fb72722d4133a56a66685a25534045e405ac05` | 2026-09-24 | [Classic, Private, or Smart? Choose the right Firefox window for …](../../data/real/real-v2/raw/mozilla-blog/876702fd8d3c44375519b998162a7146c4ccad22da9f6ef1abb8fbd29ddf240b.txt) |
| 4cce6250 | `4cce6250ce56bf228c38b9a95724545c611bd3de347fb4d8d3fe6b888320f13f` | 2026-09-18 | [ARM HOLDINGS PLC /UK: 6-K filed 2026-09-18: exhibit armukconsolidatedannualr.htm](../../data/real/real-v2/raw/edgar-arm/b49752b2774a8cea172e3a04c29eb9ca0cb2114a613d52a00150007b7af07e8b.txt) |
| 4d32cfb4 | `4d32cfb43a1f33f58e3880c506a4e6d1e2be1256fdb6b646313e5ca780b7cdb8` | 2026-11-05 | [MICRON TECHNOLOGY INC: 8-K filed 2026-11-05](../../data/real/real-v2/raw/edgar-micron/5bf5fec80d03fc248ea5a0b385e14d20229dc620198d6c8f6ee78677b584bc13.txt) |
| 4d5cc1c4 | `4d5cc1c48e9c5d6dbc7f4e8e15ab18c2b733ae7d15058d5b1ffa93c115ccf83b` | 2026-10-27 | [New Records Obtained by EFF Expose More Problems with Medicare’s …](../../data/real/real-v2/raw/eff-deeplinks/7c1c3fe3b8af2f5e99162534931db4530dba1904dc06713aaa2c734acf2cffe2.txt) |
| 4daf6932 | `4daf6932e66f7ac6757117303f7a9af5a17ef09e02ecd18ebe31d3fced4aea18` | 2026-10-22 | [Flint-interactive: A language for creating interactive data visualizations](../../data/real/real-v2/raw/microsoft-research/9a02c4308c9cf4d6b6ac2f2a2ed0f087c57efcfd060e806a971e34593fa36902.txt) |
| 4e3f7c1c | `4e3f7c1cedcc50e5fda275e13be3505f56fa75499c4e92b3733fb5fb76404fab` | 2026-10-30 | [From synthetic enterprise data evaluations to real Microsoft Copilot AI …](../../data/real/real-v2/raw/microsoft-research/7f85fd4ac83792d7b7456770471f247a00eda8e8acdf2ae7f1b5aa5e1f345dd1.txt) |
| 4ed129d7 | `4ed129d785f92d4e62dfa5698a841446ea2061819924bd64e31e58acde25d6ed` | 2026-10-01 | [INTERNATIONAL BUSINESS MACHINES CORP: 8-K filed 2026-10-01](../../data/real/real-v2/raw/edgar-ibm/d0378ae954cdbc8c19785730bc80ad2d2f0074fa321b62f674a6154878101a5f.txt) |
| 4ef022b2 | `4ef022b2baa98c318ade4b1b7d04e964c9d2519c3b38cfa78116f4458009400b` | 2026-10-08 | [Rally Up: ‘Gears of War: E-Day’ Launches on GeForce NOW](../../data/real/real-v2/raw/nvidia-blog/ce1f055cc25f7e4df6cb05207caf9b2cd443cdef78f1cf3a4ae15ec18b9fa941.txt) |
| 4f3416cd | `4f3416cdcd60ce1ebc7567a6e950f4ba90470d91fb5f4cb2ce34dcd39a10fb87` | 2026-10-14 | [NVIDIA Announces New Investments in the UK Startup Ecosystem](../../data/real/real-v2/raw/nvidia-blog/3bd47788eaae6b62b4396b60d505cfcb7269fe9a1f6a850d41fca65f1e26d193.txt) |
| 4f4e68d2 | `4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876` | 2026-11-05 | [More Performance From Every Byte: How Full-Stack Codesign Solves AI’s …](../../data/real/real-v2/raw/nvidia-blog/05e26a270e34eede0d7a0f7a6d27a7920b68c119a7e37351ab89d3101941101b.txt) |
| 509b5324 | `509b5324b6063966ebd64480734d2a81565b76ec383f526801c5c118508e8e1e` | 2026-10-28 | [MICROSOFT CORP: 8-K filed 2026-10-28: exhibit msft-ex99_1.htm](../../data/real/real-v2/raw/edgar-microsoft/894cdfda2b053df929f89948f8d64feda5449a8507669e456b9b87b958f6f7de.txt) |
| 510738e2 | `510738e21931d429ea1f6c2c9752255928b85e3a4ce486dfb6e3ef3893bf9a17` | 2026-10-19 | [SEC Announces Roundtable on Machine-Understandable Data in the Age of …](../../data/real/real-v2/raw/sec-releases/89658f3ed474c61b5b575020b7661d01bfca183242bd416cdd6e6aa0d384fde8.txt) |
| 532cf528 | `532cf528c4a38417cb72dbffd16869bdbbd330f3ea4b195eac7b51eb7961d162` | 2026-11-05 | [Google's general search and search advertising services](../../data/real/real-v2/raw/uk-cma/030a24942452ed2bf5098d935abaebc29b7260273c594123b3baf552c14393db.txt) |
| 54ba7876 | `54ba7876027c9cf2646b15115699e52aa3059764490bb2ab32027393c51c0ca9` | 2026-10-28 | [Court Should Curb Abuse of Grand Jury Subpoenas Targeting Social …](../../data/real/real-v2/raw/eff-deeplinks/7b558e446bf6037bd71b38db7c5e78fb6a63ffd37b0577d015ac14e3637b12f9.txt) |
| 59120c10 | `59120c1035a6371bea07403e4efa389edb0fc84e379415906ac6ebbf6c552218` | 2026-10-08 | [Super Micro Computer, Inc.: 8-K filed 2026-10-08](../../data/real/real-v2/raw/edgar-supermicro/dd6218bf7ad99e46ff04205ef2fe7ab36724ec21c5912dea09cfda3e062af7b8.txt) |
| 5a093fbb | `5a093fbb919c5edd82ce68d40874c1f62d254a85825e7fa1b667fa43a9624fd5` | 2026-10-08 | [TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD: 6-K filed 2026-10-08](../../data/real/real-v2/raw/edgar-tsmc/78913207dc761e1e6a0676c86d53b826499f176a4d2c873c44486bcf17dc222a.txt) |
| 5bef2525 | `5bef2525a9a8bc2b83809a4a1fbb66814e1a0768b5252504eee1e4571ca74d8f` | 2026-10-29 | [Samsung Electronics Announces Third Quarter 2026 Results](../../data/real/real-v2/raw/samsung-news/82a9390ed7fb4d57e1d213ae1bd5728f9dcf14b03a956eb2daa8da6a0d2ad2e1.txt) |
| 5de0ff1b | `5de0ff1b6c6f485042e4ccd44fb141782d885c44b17921a61c92090e16ea4fb2` | 2026-10-28 | [Alphabet Inc.: 8-K filed 2026-10-28](../../data/real/real-v2/raw/edgar-alphabet/6dc339680c870462c61e2a281b9ffa7bbf239bbe895b47f72bd6c9343558627c.txt) |
| 5ee625bf | `5ee625bf0e74cf8c3c787bd66215fc443897dc769d25b258195b608ba0d0df7a` | 2026-11-12 | [Marvell Technology, Inc.: 8-K filed 2026-11-12: exhibit a20261112pressrelease.htm](../../data/real/real-v2/raw/edgar-marvell/15793134b19049f7d298409e116671433eb5f32ba42d7520c8b18fb6c36047d8.txt) |
| 5fa2f857 | `5fa2f857e1e2f466c5006bb776694a150c17f56d70c6671fbabebb53cfc8099a` | 2026-11-05 | [Meta Platforms, Inc.: 8-K filed 2026-11-05](../../data/real/real-v2/raw/edgar-meta/758c066688ad4dd095a41fdc723a041528697840f2c34146d50a679020f17755.txt) |
| 60ce7dcd | `60ce7dcdc7a9185d693a82d67a4266c7841390d84d090be28f805ba4f411fc4d` | 2026-10-28 | [Former Army Official Pleads Guilty to Conspiracy, Bribery, and Major …](../../data/real/real-v2/raw/doj-news/324a9516d96e40028155fe4f5b39ea9e35b2b714f1d22088e441871eb5ca4c94.txt) |
| 62dae3fa | `62dae3fa9fdbfc1e285d25e8a2311ff6d9cd1063c7adbfeddd900f7f8b695601` | 2026-11-05 | [Beyond the Medal: Samsung Helps Young Athletes Explore What Comes …](../../data/real/real-v2/raw/samsung-news/3fe3e8b6a8c102ca46771431bab8962aee1cd737fa0da559be645aa52d1b79b1.txt) |
| 66b41ebe | `66b41ebef1028fc285926a811ca3b53fdbab9e4baf84e74bd6fc469e0dcd130b` | 2026-10-07 | [NVIDIA, Microsoft Kick Off a New Beginning for Windows PCs …](../../data/real/real-v2/raw/nvidia-blog/39e218ac09a4c1b6dbd2bfb3037c224a791be7485b3f765d4d20fb86c7cf52a3.txt) |
| 68bc4819 | `68bc481960f7506f075ad344e0ae64b7fff0cf01476cc03589bc1c1847cba88f` | 2026-10-01 | [INTERNATIONAL BUSINESS MACHINES CORP: 8-K filed 2026-10-01: exhibit ex991pressreleasedatedocto.htm](../../data/real/real-v2/raw/edgar-ibm/e1ecd1dcde7a13f8272743e12ae328f01dbf35e8cb73d0592202175d645e1eaf.txt) |
| 692eaf47 | `692eaf473852f2f09dcce1336ae22e836b23882381eb3d104a64037ad61e9500` | 2026-10-28 | [Victory! You Can Now Exclude Apps from Siri AI](../../data/real/real-v2/raw/eff-deeplinks/05133bf4ffe5b0b2ad41018069ad0b885e8e6c716c1d1f819ef1ef81f09d76a7.txt) |
| 69cf9e2d | `69cf9e2de96e8504cb30e3263c301d07194bf4b4f36dbcbe4b770b7a285d6768` | 2026-11-10 | [Pyrite: Building and Benchmarking Protein-Ligand Pose Ranking Agents](../../data/real/real-v2/raw/arxiv-general/c0f909258ad78a86ae2830e1f25b1a6d0bc61d1b0d3f312c2348ba3726cead28.txt) |
| 6b8d9dee | `6b8d9dee5ceca018525f789c7b638826953c05c9c1fef98c40fb3f7b4ace51b0` | 2026-11-12 | [An open letter to every family’s designated IT support](../../data/real/real-v2/raw/mozilla-blog/8cd23f4fc5f07c1a29dfbee631e9a7f5209ca671cce23e234efb9b037d10a939.txt) |
| 6bbb2a8b | `6bbb2a8b7c9d11813e2db157e2299cdd276de42083f971070d0f3a324ed37fbb` | 2026-11-09 | [U.S. Supreme Court Deals Final Blow to Corporate Human Rights …](../../data/real/real-v2/raw/eff-deeplinks/21ed9992722b85bed4a2fd8034b7baafd4d5a2104cd412763e186ced40619fa3.txt) |
| 6c5f9d64 | `6c5f9d64995b4f82d3157e94af8ab6249ce5bcb5a8f4ea00b8cb5682072e5486` | 2026-11-12 | [Federal Reserve Board announces pricing, effective January 1, 2027, for …](../../data/real/real-v2/raw/federal-reserve/b37ec7d169209cfcf371dd0dd84a2fd42691744818bed6c027fab1abbc139b0d.txt) |
| 6c9efc49 | `6c9efc491c588c786390c2e9317bff72e56faddc25fb0e082a90b50805fc35fb` | 2026-11-02 | [Palantir Technologies Inc.: 8-K filed 2026-11-02: exhibit a2026q3ex991pressrelease.htm](../../data/real/real-v2/raw/edgar-palantir/1723c5aac59b70ed5fa64660b08af7cc261f0d4880dafdf19fc37aad7d68becd.txt) |
| 6d389204 | `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7` | 2026-10-29 | [AMAZON COM INC: 8-K filed 2026-10-29: exhibit amzn-20260930xex991.htm](../../data/real/real-v2/raw/edgar-amazon/83f3fbc8efe77441b01fdaf6d872a01e09dfb432191db5b1d4fe2587cbfe1150.txt) |
| 6e8793cc | `6e8793cc9a062cdffa8e4654e31e60b828cf872b37ba873773f7cd36c66e0f19` | 2026-10-27 | [Skip the busywork with Smart Window](../../data/real/real-v2/raw/mozilla-blog/6d8e947819742d864a8d75749145f639b905e43188c4e0029c5512991d4fff7f.txt) |
| 6efa7d34 | `6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2` | 2026-11-12 | [NVIDIA CORP: 8-K filed 2026-11-12: exhibit nvidiaannouncesceotransiti.htm](../../data/real/real-v2/raw/edgar-nvidia/9ae403af5f64cf758d691f125831924a71789dcdf0e907326d2533d78bb8dab1.txt) |
| 6f669344 | `6f669344430cdbcdf915101529260e127a18d2be23c7a5241853e1ea9c6a5b2a` | 2026-11-12 | [Federal Reserve announces revised tentative schedule of Federal Open Market …](../../data/real/real-v2/raw/federal-reserve/5eec6c2ee3a25418febc524349618c391fd13a0cbf684789901dc801ac51e3e1.txt) |
| 6f93879f | `6f93879fd979646b2d3ed6b566f70bf422a447c4c34801804de39199e8a9cff4` | 2026-11-10 | [Final recommendation that the Secretary of State replace the Assimilated …](../../data/real/real-v2/raw/uk-cma/b9d641a978231d1b92006199d41055b5a536da703f2f7074a4d5239a553c0725.txt) |
| 7174e2bb | `7174e2bb239c1b56fc3a63fb5d222fe3ddc89ecb8696d45bc97a977d2c648c22` | 2026-11-12 | [Samsung Announces December Release for Intelligent Eyewear, Bringing a Smarter …](../../data/real/real-v2/raw/samsung-news/46f7fa7e5316d17eca0122a57618e508fd9b0a60c2f2b3083417b76a09a7f4cb.txt) |
| 73eb9276 | `73eb92764ef9659fb44b00f774453e84b4a6a45cbdd55bc185b3a558a8c41f4c` | 2026-11-12 | [Finding the Perfect TV: A Guide to Samsung TVs](../../data/real/real-v2/raw/samsung-news/a5ff5408fa8ec9c1296ad9799674c5a2751fcdba64ae2ebd2ac05b7d4ebb6382.txt) |
| 759f3904 | `759f3904626735fe696c3678fa5af6f57e44eb9e47aa77438ffda41e42621d1f` | 2026-11-10 | [Discovering Equations for the Thermodynamics of South Asian Monsoon Precipitation](../../data/real/real-v2/raw/arxiv-general/d401c7f97855ca4af9a63f04c40dbcc13ff31e48a77d563de0275a9a153d1be5.txt) |
| 75ee4f31 | `75ee4f31c6181f87deb587c5c0aabee0762ed7058ee60d01aa78fb9ecf6b4644` | 2026-11-02 | [Marvell Technology, Inc.: 8-K filed 2026-11-02](../../data/real/real-v2/raw/edgar-marvell/2c0a944c6fa65badba75c49d36b76b6db3e353e55bcd4f4a4e1c6e83b5f244e5.txt) |
| 76535d0b | `76535d0ba0292de9d795447c0304d3f28c061dd1d5d6bdf1db6dea612b108f97` | 2026-09-28 | [ADVANCED MICRO DEVICES INC: 8-K filed 2026-09-28](../../data/real/real-v2/raw/edgar-amd/30cd026eb1e9cc8e38d1a845d58866101f9689bf734dded4ecacfbb6164ef26d.txt) |
| 77af2cde | `77af2cdeb7897efafbbc9234021b526cd003908d57c03b43b907d8f452f2427d` | 2026-11-09 | [Teaching the Harness: Student-Aware Skill Transfer for LLM Agents](../../data/real/real-v2/raw/arxiv-entities/1434be7a31d076e6bea0cefdc1c251a311df85643880a15dc558ee6dfaa777a6.txt) |
| 796f85ac | `796f85accd3273903f02d8da1f4200e0b13163e2f1713014b29d2c74ef0a188b` | 2026-10-07 | [Agent Lightning v1.0: A 3,500-Line Lightweight Agentic RL Framework for …](../../data/real/real-v2/raw/microsoft-research/865c8dbea58f3dba1068e6799d8de73016b85c94f0a5119db16ad1e53089cab8.txt) |
| 7a4b80e2 | `7a4b80e2e778f3a9ef1aa9d633bab26a50d7425b315d80e1b5ea54780ea276c2` | 2026-10-02 | [Snowflake Inc.: 8-K filed 2026-10-02](../../data/real/real-v2/raw/edgar-snowflake/c29d8ea5a1ef63fef047eabd4095f27f54ccb53e255f91071c1929061563b847.txt) |
| 7a85fbb1 | `7a85fbb1e42a5762d291e6fecca24e63e628cb08d9af0f4a3f4a241dc78476f6` | 2026-10-27 | [NIST Report Provides Guidelines for Transition to Post-Quantum Cryptography Standards](../../data/real/real-v2/raw/nist-news/f387096ce424c615127981c54692de4a9006789f2216103b0d2d9a29b7aa4569.txt) |
| 7b9fc55d | `7b9fc55d9e7385ea759c186d1f62be95db784a36f2b644c017d0335a82516c73` | 2026-11-09 | [Embodied First Exam](../../data/real/real-v2/raw/arxiv-entities/e856c1aa1e14e108da713d0def65fdbe9d92ab2f4505d7eaa5e1516c4627f391.txt) |
| 7c85619d | `7c85619db50f418944649b19391d9165d7bb8658fcfedd93e17d1d60780c9f9a` | 2026-11-03 | [Super Micro Computer, Inc.: 8-K filed 2026-11-03](../../data/real/real-v2/raw/edgar-supermicro/42505b9ae9c975a91f9e7ffe81113b7b2ba5db2c95d5d64801497e7baffb336a.txt) |
| 7c9eebcf | `7c9eebcf5b8d6103406eb11eb7ce2240ad3f2854930c28010d541fd587a3256d` | 2026-10-14 | [ASML HOLDING NV: 6-K filed 2026-10-14: exhibit financial_statementsxusx.htm](../../data/real/real-v2/raw/edgar-asml/6cd1080a791470b7e96b4ed7c0865371db09b6e3d2d61741a31839b1641f536b.txt) |
| 7f207a76 | `7f207a76773540d5b311e8a45558eac01264f0923b5aef092a03d608649c56c8` | 2026-09-23 | [SEC Charges South Florida Resident and His Company for Alleged …](../../data/real/real-v2/raw/sec-releases/81ce91d9adcb94192423efc489fdddcd3da28bdafb066d863b5dddd000951275.txt) |
| 7fd29352 | `7fd29352a9320282f107ab68c8a1ee878270437ce19c7f2acbf0b56b7bf03235` | 2026-11-09 | [HyPLM Technical Report](../../data/real/real-v2/raw/arxiv-entities/3104cdb1e0a1aaf16f4c51879c9fc10310c8d614e12c674109ebf019625ad0ea.txt) |
| 80b4295f | `80b4295fbd53d86404ecab7323ba0ce142b10c42517b7edd0d3546df56c0b077` | 2026-10-15 | [TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD: 6-K filed 2026-10-15: exhibit a3q26e_withguidancexfinal.htm](../../data/real/real-v2/raw/edgar-tsmc/50755cc3f5cb27a781745623ac49c3056698cd106108a243fb04362a7e9cff75.txt) |
| 820a5281 | `820a528105d33fb3e04fc6de1794dd40fbb4d18c0c2df73da67ebc071516d6f3` | 2026-10-12 | [Microsoft to expand Azure Maia system to multi-gigawatt deployments](../../data/real/real-v2/raw/microsoft-blog/094a4c2db559fc538b7789763f449cf7d6071e0ae0b4f487455f14cf01508e91.txt) |
| 830d165f | `830d165fb617f2834ab457283c7b98ed54da05d8a037571f1f653d5595bcb20e` | 2026-11-12 | [Marvell Technology, Inc.: 8-K filed 2026-11-12](../../data/real/real-v2/raw/edgar-marvell/71edb48827701b05243442932f10ee1b6fb83ea08ef6af49dc835f75cf80dd9f.txt) |
| 839e05d9 | `839e05d90c26441e88a812ec71c77163c0090c595032ff2e5852ec8fa38092cc` | 2026-11-05 | [Alphabet Inc.: 8-K filed 2026-11-05](../../data/real/real-v2/raw/edgar-alphabet/e95ace5937bd9b4c94aa444efafd7e864e2377ce031c940dfe5ec451437a0b28.txt) |
| 8c4e7a8f | `8c4e7a8f3c674cf510a625e5fa9b55b47c70f5197821b954507e9920b74051a2` | 2026-11-04 | [SEC Adopts Amendments to Update Definitions of Small Entity for …](../../data/real/real-v2/raw/sec-releases/f746d9d5a8340f3ee3a5afafb6a551ee016f071ec45bd8aeb42b7338e893cec4.txt) |
| 8dcb1e89 | `8dcb1e896d8dfbe9103cd7da711cbf757d034ddcf5656fab533e2c3f43d1b77e` | 2026-10-09 | [CISCO SYSTEMS, INC.: 8-K filed 2026-10-09](../../data/real/real-v2/raw/edgar-cisco/7ff2024a9027e4ea05c5eb8fc45186aebbf517f68ab3ae57922331f5465b44f2.txt) |
| 8e63b58e | `8e63b58e407b6cce912aefd1eb66293f9963a2af95108424017ff37f42c110f3` | 2026-11-09 | [AuDiR: Diagnosing Audio Reasoning with Rule and Percept Interventions](../../data/real/real-v2/raw/arxiv-entities/93774dc1fa5375ac74e7289072e05ef596fdd6f038eff653d61538896094a7d5.txt) |
| 8f651811 | `8f65181129c1b7f8a9e052504cb3b154562d29b1bfe8352356d441b85f7ac5f5` | 2026-10-27 | [Social Media When Elections Are Close: Doing the Impossible Better](../../data/real/real-v2/raw/eff-deeplinks/6ed93ce0d1c0279f2da64c9db43c7fae216c2b58cc53997a530b9854d4ae1194.txt) |
| 8faa6a57 | `8faa6a570793c3ac0fadfeed24a0aa5b685f16baf40aaa2b6958aa2e9ef81be3` | 2026-11-10 | [IFRS Compliance Verification: An Open Multi-LLM Benchmark and Content-Conditioned Ensemble …](../../data/real/real-v2/raw/arxiv-entities/54313f79386f8ac91b43efdebf26c6a43fe809eb2057de5517342f8df46e8e52.txt) |
| 90445a7a | `90445a7a69984ea7c580a299973b27c95f4334aa720227c68ebb98900c6d9549` | 2026-10-08 | [Samsung Electronics Announces Earnings Guidance for Third Quarter 2026](../../data/real/real-v2/raw/samsung-news/c323a099bdf8266a755b79709abffb86bc20343513c855585361537eeaeac3e6.txt) |
| 904be74c | `904be74c369c5aca07128b34b5b75d42e1604e00f0cadc1381c4d0f0d12926c6` | 2026-10-27 | [Broadcom Inc.: 8-K filed 2026-10-27](../../data/real/real-v2/raw/edgar-broadcom/c8989b298017773ff92ee1d4d85f492a121d1f7654458aecef5b853d0ad97ab8.txt) |
| 9294de0c | `9294de0c2d6e2d11fcd628d632318e167116710e60f833f47c088c10ca87d9d5` | 2026-09-23 | [SEC Publishes Updated Market Statistics, Highlighting Increase in IPOs and …](../../data/real/real-v2/raw/sec-releases/ec979764e52a25c2a7508a9341c201de121ebc1a74308e9c04cd2aeba6d2b52a.txt) |
| 937dcced | `937dcced2e0897e7154e3389ace27123acbc29bebabff09796caffd6ea91f57f` | 2026-09-21 | [5 Companies Using NVIDIA AI for Clean Energy](../../data/real/real-v2/raw/nvidia-blog/70fab35d43419d7a84d91b265962a878d6cef0f9e2713a043eac85ddbecc766c.txt) |
| 939a45ab | `939a45abea94969be385ebcde7c5920deab6d3a88414947961de03e915371404` | 2026-11-06 | [Statement of the Department of Justice Antitrust Division on the …](../../data/real/real-v2/raw/doj-news/cda9e3fc8b4bdda897a0425c560bb09d339619517825059f763e4a67421bad23.txt) |
| 93a879f7 | `93a879f75d01bc41426b47b7e286eddae767d7759af728909e412d74bc51c017` | 2026-09-21 | [Improving synthesis prediction of small molecules at scale with RetroChimera](../../data/real/real-v2/raw/microsoft-research/e69f7e54b136db9b5084388f3591eaf174f0fd5cc568ebb0e07548336493990d.txt) |
| 941f0ba7 | `941f0ba7b604163f3582a17d05323bd1434e30a7c0b31822550ea54bf0cf7f1c` | 2026-10-27 | [Five Firefox updates you might have missed, and a look …](../../data/real/real-v2/raw/mozilla-blog/e6c63caa6244bae3c0e72f16d8769f3df88458f1424073f0fb2964d53dad9f62.txt) |
| 9509c40e | `9509c40e72f112667a63e5add85e821959f8161c9de63978634c49b08c2d486a` | 2026-11-10 | [One Policy for 100 Household Tasks: Our Solution for the …](../../data/real/real-v2/raw/arxiv-general/08bec5f7186ef350798ae6b2c3d482a31f054c8f8d8a5c81eda1108d046de9b7.txt) |
| 95530714 | `9553071426ca46d879df4053183f0e62bdf333a3989969bc3cd0f74ec5d6f4b2` | 2026-11-09 | [Reliability of Claude Code as an Agentic AI Grading System …](../../data/real/real-v2/raw/arxiv-entities/3d47bcd28dad1b927245a1aeecf845419ce1f93f6e2f13ab49bceeb2ef361fc5.txt) |
| 957e8680 | `957e8680803ad8738070f32300b148e17d369f32bc51240ca97850b3dcddf5cc` | 2026-11-09 | [Apple Inc.: 8-K filed 2026-11-09](../../data/real/real-v2/raw/edgar-apple/518bc7a59f7b8cd55fe02d46ebbb7d8adc3b64ff88750946434a5bd783f1f7c6.txt) |
| 99de9e9e | `99de9e9e4c70c3f0cf9df97ea03e15e7dd7448e2aefd296331794c078ba0e1a9` | 2026-10-21 | [Meta Platforms, Inc.: 8-K filed 2026-10-21: exhibit meta-09302026xexhibit991.htm](../../data/real/real-v2/raw/edgar-meta/1fc196fda5266eb4b392554f8b96ee37fb5d07a8e0acb64f5ab465cf214be961.txt) |
| 99e3e5da | `99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d` | 2026-10-12 | [OCP Global Summit: Amid Ecosystem Adoption, NVIDIA Opens Vera Rubin …](../../data/real/real-v2/raw/nvidia-blog/ec806da628554a3fff77a79ec93b3d757c95ece41c127c3d562b009c4fa5a46a.txt) |
| 9b2692ab | `9b2692ab25854802754db158af72ad426ffef1a7077e74fd680511cda4c058cd` | 2026-11-10 | [SkipLane: Write-Once, Conflict-Free Accumulation for Zero-Skipping CNN Engines on FPGAs](../../data/real/real-v2/raw/arxiv-general/602696f6da58a035bf6b5cc096953a55479974b107c8f7c0549c14605035af85.txt) |
| 9bd2920f | `9bd2920f6fee3d473ccd11c07759516a3a077914d7dc1c63b2155419afc1f120` | 2026-10-27 | [The platform approach to becoming Frontier](../../data/real/real-v2/raw/microsoft-blog/dff627c499b17641d082075564cd0ee61dc51be026e22190d7874ffba657ecc0.txt) |
| 9d7eb9c6 | `9d7eb9c66bf2ce344c35ee82990a3de770430c123e58984fd77391bd8a951b96` | 2026-11-10 | [Medical Image Segmentation: Foundation Model Adaptation versus Task-Specific Training](../../data/real/real-v2/raw/arxiv-general/1244d10c6014e33e81812f92b9999174ea884d74a9aa49a878865280a78fcdf3.txt) |
| 9fcaeedc | `9fcaeedc9708cea93a1c2b876f124f647ad5f10f4af1401b8de4256123844892` | 2026-11-05 | [Google’s mobile platform](../../data/real/real-v2/raw/uk-cma/025a9ef1b4e0bcd4caa63dc96d3eb1328e7f37b12d088566b5aaa29bdc46b606.txt) |
| a10e6051 | `a10e605161385b47171d929c40c348c3731471737e78cfeb8fc0948953dadb3d` | 2026-11-12 | [From AI ambition to business impact](../../data/real/real-v2/raw/microsoft-blog/b074ebf56d5e68e98c6d41c1d89cafefaf05e04c04728a97573218d2f5a04c45.txt) |
| a1da460c | `a1da460c619401d4cfcbba32ea146e5dfa5c5dd486591cda957db4e7aef2ea4a` | 2026-11-09 | [ExpertCrowd-SWE: Measuring Frontier Coding Agents on Expert-Authored Engineering Tasks in …](../../data/real/real-v2/raw/arxiv-entities/ccd1264d9c4956aad136703ab5978687d3401ba8a3b5fa7338827196d36c8c84.txt) |
| a253c6c5 | `a253c6c56f596c5081863c3220df9c178e675b2435eb5f2830606f3cc9b12898` | 2026-10-21 | [Meta Platforms, Inc.: 8-K filed 2026-10-21](../../data/real/real-v2/raw/edgar-meta/62171dac030ec227b7fa429b88893d01fce8e02e5c8ee03bba2f5b5a117285c3.txt) |
| a2830602 | `a283060223e079afee4a5aa94c87eea16e795f0f8c167cec94d0554cec6945e6` | 2026-09-24 | [Contain the Chaos: ‘CONTROL Resonant’ Launches on GeForce NOW](../../data/real/real-v2/raw/nvidia-blog/0be6f8e97a068c72af9753e80707afca7f45982e0f73d0d4642877e84d448111.txt) |
| a80f73b9 | `a80f73b98e4f893eb7b03a8cf7fe78cf373612fdc451692a98520cf025b13703` | 2026-11-12 | [Federal Reserve Board issues enforcement action with former employee of …](../../data/real/real-v2/raw/federal-reserve/e68461450dcdbf42519e1e4445901dfda1e3711247424b48dd818141543fbc8a.txt) |
| a86bd392 | `a86bd3921ee6552002fca2e439130bf0e92af422a64122993054674a2a72c55d` | 2026-10-29 | [Meta Platforms, Inc.: 8-K filed 2026-10-29](../../data/real/real-v2/raw/edgar-meta/87ffaa491116119f85710a441c32985c7f2bdd2c0cef85dc8f4f2da18b90b2f9.txt) |
| a91dcd5b | `a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5` | 2026-10-21 | [Bringing the Spark to Europe: Local Intelligence Powers Next Wave …](../../data/real/real-v2/raw/nvidia-blog/ff63e4c81519398264ac34d98c47d4118988d4ea7891379ac6ce425e5704acd3.txt) |
| abdb6870 | `abdb6870e58e5fd3d4fe78331b46811327c412ea9304543badc53d26266768c2` | 2026-09-30 | [Hewlett Packard Enterprise Co: 8-K filed 2026-09-30](../../data/real/real-v2/raw/edgar-hpe/2e7713a0fbe6d0b4c51be30401be46e358f52571783bd47c505076bab8e65873.txt) |
| abeb6228 | `abeb6228c70c108d70cf34fb390113c7080092c6d0498570f017013a259da0eb` | 2026-11-10 | [HandsOnAid: Building and Evaluating an Offline First-Aid Assistant for Emergency …](../../data/real/real-v2/raw/arxiv-entities/6faa5238f7719f047a8b5387d5c156f6e046cbd8f170b656fcde90f55dc9dba5.txt) |
| acb0bb57 | `acb0bb57fbfb59366ef1c11699d8aefa7102bff01672088ff6a8a8a29ce4ce02` | 2026-10-28 | [ORACLE CORP: 8-K filed 2026-10-28: exhibit d75538dex991.htm](../../data/real/real-v2/raw/edgar-oracle/4153e0c5d9bb9eeec33ab37ebf7eaa43d418ff1cdcc3e274188603fc3d01dace.txt) |
| af0b17e2 | `af0b17e21e5eb868637444b343ecb83326789a28c16fd409d36ca559c0ac5436` | 2026-10-26 | [Lessons Learned From 'AdFection' and What To Do Next](../../data/real/real-v2/raw/eff-deeplinks/574c014d4c442dc278c2c906e2ba2fc0dd6c282d1f0c7b19fca0db7688281c2b.txt) |
| af60f5ac | `af60f5ac895f01bfb9c7e606dadf2508ea16d9808daac4ed736f9d8a7f4e724f` | 2026-11-10 | [TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD: 6-K filed 2026-11-10](../../data/real/real-v2/raw/edgar-tsmc/5fd4117150ccc2a0e00ee61d74fdb88faaad4929543ce5ba2802d70ff69f995f.txt) |
| b12b6e7e | `b12b6e7ea3206a00ecc4e3e58334f04a77579cbd067d009ec2e665d69b050889` | 2026-10-15 | [TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD: 6-K filed 2026-10-15: exhibit a3q26presentatione.htm](../../data/real/real-v2/raw/edgar-tsmc/6aa56fbfb6a569b65ccdb4dd6c852027a0c8e787350141d7a6b176019c433d0e.txt) |
| b2727e77 | `b2727e77c3e99a2c4d6793369a6e9a297d3c323e86290c216c198bdf906ca96b` | 2026-11-12 | [CISCO SYSTEMS, INC.: 8-K filed 2026-11-12: exhibit exhibit991pressrelease-q1f.htm](../../data/real/real-v2/raw/edgar-cisco/606837a83d9c6b88ea31f5631323e314e1796072d952f784b53b7ab04672ab69.txt) |
| b5bb5bd8 | `b5bb5bd83fb3c105642f9d6eeb66af0f8549bb30c167d2346943a3ec53fcc435` | 2026-10-20 | [Salesforce, Inc.: 8-K filed 2026-10-20](../../data/real/real-v2/raw/edgar-salesforce/66e818ea42c85a773e42add846231fa2df1657a77d370b8944550076614e60eb.txt) |
| b622243b | `b622243b309b18db73b59296a706fc54475bf1f6fb08f22b0d5f18e6ecbea261` | 2026-10-21 | [INTERNATIONAL BUSINESS MACHINES CORP: 8-K filed 2026-10-21: exhibit ibm-20261021xex991.htm](../../data/real/real-v2/raw/edgar-ibm/f5b17a5b51e3e79e503d518cd9703c82516a8bd1f69e26ad73b1b35a43c0e4e4.txt) |
| b64c2e06 | `b64c2e063a2e875e36fd7c5d02f75b57f6fba73c1e96016a6144781a22f0aa3a` | 2026-11-03 | [ADVANCED MICRO DEVICES INC: 8-K filed 2026-11-03: exhibit q32026991.htm](../../data/real/real-v2/raw/edgar-amd/826687e972d35d19100c0c8f785bbb37d7067b9428b255b0d08a73ff5b2b9829.txt) |
| b8b52c86 | `b8b52c864bb0447c7d335ed4b8484b50d21907e2cbc21a4e88a4614a66eb1769` | 2026-11-09 | [Why Fewer People Are Challenging Bad Patents](../../data/real/real-v2/raw/eff-deeplinks/1ba32b82786083aea33ff072fe6c4c63c50698bd5d898df0dfce52e23609ed89.txt) |
| b9715cb4 | `b9715cb4956b68865bf76e3d6c33543ee69785d5d2bd08283d5d3779801c72f2` | 2026-11-04 | [ARM HOLDINGS PLC /UK: 6-K filed 2026-11-04](../../data/real/real-v2/raw/edgar-arm/b5a56d939c0c8953bc40b5293635912748247d52cbd7277449c7aa8809284a53.txt) |
| bbb7958f | `bbb7958f9bc3bd3f5fcdd4747eda950db26cf3eb00c6c3f2e9911309f4a300a1` | 2026-11-03 | [Privacy's Defenders Podcast: The Secret Room](../../data/real/real-v2/raw/eff-deeplinks/996d759b47ba9257cc1cb2b7c9b801edd839ce29ce6c417aacbd143fc35d6151.txt) |
| bc277f19 | `bc277f198536389f5c29912ec0216b3022b2674e70e645578654dce8a6d13200` | 2026-11-10 | [ARE-bench: Benchmarking Agents' Research Ability in Real-World Researcher Sessions and …](../../data/real/real-v2/raw/arxiv-general/f6dc575c42eb11ab67f847d413fc6baa76d477b2475aaf5a92d53d3c6c2db3a8.txt) |
| bd102c5f | `bd102c5f9abb129083c19e08a58a4ed22c3b8f3dbd5d7acf255cb1ad95c1f355` | 2026-09-30 | [MICRON TECHNOLOGY INC: 8-K filed 2026-09-30](../../data/real/real-v2/raw/edgar-micron/1ae35869c5a13270aa20e1ccee2d4d9ddcf040e2ed305def8832e7c5ee832576.txt) |
| be81cefa | `be81cefa327d287bd0ec3bc5f57046523d2a4d8fee8047fbe25ae52f6397e56c` | 2026-11-10 | [Earlybird: Predictive Streaming Speech Recognition in 29M Parameters](../../data/real/real-v2/raw/arxiv-general/67c689ef1e8cf041477aff056f7970dd523288b761573f7543351ad41bf81f4e.txt) |
| bf2ae3ba | `bf2ae3ba2e44abdaae4be055020ca7e12ddf14eda310d8dd3bfaf8cdbb36c6d9` | 2026-10-20 | [Why is the CMA asking us to choose the furniture …](../../data/real/real-v2/raw/mozilla-blog/1d4e188ce8a127a7fbff1b8990c795cf0c0eaefb0c72c04c28cd224fc756a19b.txt) |
| c161a652 | `c161a6520afa0aac77ecb67809daabf2d1f6cf650b3e39ea2bace35e68bd9b44` | 2026-11-10 | [AI Isn't Getting Dumber, We're Getting Pickier: Rising Standards in …](../../data/real/real-v2/raw/arxiv-general/96c2102081efbcb33e287443d50dafcb4fc6880b0dccadf2437bc33123bb89ea.txt) |
| c2cadf01 | `c2cadf01ae33f8990f0fe4cb2ba520dac1a3f4586a104e0a8b57a85a060095ea` | 2026-11-09 | [One-Sided Expert-Parallel All-to-All for Mixture-of-Experts Inference over NVLink](../../data/real/real-v2/raw/arxiv-entities/7b4778c63231c9ad1990b0a0002ccdabb795761eea6cdfb0c6e5b3c6f9bbd9fe.txt) |
| c3bff6e2 | `c3bff6e201fc436ed7164260ef4aee00b6f55eeaada9e36f9029c2fb32504262` | 2026-10-20 | [Super Micro Computer, Inc.: 8-K filed 2026-10-20](../../data/real/real-v2/raw/edgar-supermicro/4fbdc979297ab4022281791e952023587fae0fbc92da0c04be9f0366f4753e70.txt) |
| c46a4c1e | `c46a4c1e6eeef424abd19fb7e3ace7b9bf447665823e9fec8ecd059823f9637c` | 2026-10-30 | [Why VPNs Are Worth Defending](../../data/real/real-v2/raw/eff-deeplinks/13ab7bdce96001c053dc7daad32b2693c9432775fac61bfff84ba16077267dac.txt) |
| c4bbb8b3 | `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144` | 2026-11-02 | [Marvell Technology, Inc.: 8-K filed 2026-11-02: exhibit d81187dex992.htm](../../data/real/real-v2/raw/edgar-marvell/bc306c9177535abd667a8b7aba6cdfa71c67fa163e80c257bd4bbc83870dfc1d.txt) |
| c64e11d2 | `c64e11d22be54d42f190426bd3d425a12ab99fb48b227749a5cc304df69aee22` | 2026-10-26 | [[Interview] Sound That Connects: 80 Years of Audio and the …](../../data/real/real-v2/raw/samsung-news/cbe59b80b0b4b5cd4f5facf63e0576f89e78547a6bd807e0309e9e89bdb84aa6.txt) |
| c7708a09 | `c7708a0929b01374ff889e603fe9946a34b825bc478f266e3950bd019472f2a5` | 2026-10-23 | [Kazakhstan Expands Compute for Its AI Future](../../data/real/real-v2/raw/nvidia-blog/bebcedd220cbbb683826923513552691f3d606c8787642341f62431427d5240c.txt) |
| c88e556c | `c88e556cdb1cdbecb17c6cf6b0ee293d9e62037884354a0e1fb95a73b09628e2` | 2026-11-03 | [ADVANCED MICRO DEVICES INC: 8-K filed 2026-11-03: exhibit amdq32026earningsslidesf.htm](../../data/real/real-v2/raw/edgar-amd/510f3ca13a9490ac98749fd68df461004f062b946bdcd3e81ab6c3cb19f174d2.txt) |
| c95ca17e | `c95ca17e1526693b55ac7df7682690baa77c8a38f82cc19aee6bd9da7928ccae` | 2026-11-10 | [Lazare, veni foras: Reprogramming Dormant Neurons to Backdoor AI Agents](../../data/real/real-v2/raw/microsoft-research/1c7a1d951e6c52add3d95e2e427c22469ced9e40872bcae12e304f0111650463.txt) |
| cbca4caf | `cbca4caf7812befeea30708db0c8b051ffca45803a3ee9bbef97893757cf3bc2` | 2026-10-14 | [ASML HOLDING NV: 6-K filed 2026-10-14: exhibit pressreleasefinancialresul.htm](../../data/real/real-v2/raw/edgar-asml/abe2db3e394a73768ac69e926b9714a2f5e38d3203880bbc0df381ad6dbf9e4e.txt) |
| cd9a0000 | `cd9a0000bf14536f61050273a6fcc184d1720de20b44bfc6f12df46eafafcff3` | 2026-11-10 | [MOAI: Module-Optimizing Architecture for non-interactive secure transformer Inference](../../data/real/real-v2/raw/arxiv-entities/5c4cce2c1840e8f956925d804c4adcf94ef0a2ec6ebd2d6d76badfb60de55cd0.txt) |
| cefc0930 | `cefc09303bac0a09c7fcbd15f2680243a5ee4079e9358e01de52265ce2bdedd7` | 2026-11-09 | [A Lattice-Based HMM Approach to Aruz Scansion of Ottoman Poetry](../../data/real/real-v2/raw/arxiv-entities/fb80e8f38efca42a0055271df69a22b0723b01eea5b301068b78ca52d2abac88.txt) |
| d02369ad | `d02369ad64bc04f34a4d2a50cb97c8bcb8de31f300e3b017e4763f406fb1d99b` | 2026-11-10 | [Application of the Chapter I prohibition in the Competition Act …](../../data/real/real-v2/raw/uk-cma/8e6060e26010b2cb4621485752d968bf9ac0de538ef869a551cd709dbbc939a6.txt) |
| d0d4e232 | `d0d4e23249b050907087131a0d7f1e8267c1dd4e4b1aa8a269b3398873511073` | 2026-10-21 | [Dell Technologies Inc.: 8-K filed 2026-10-21](../../data/real/real-v2/raw/edgar-dell/660dcfba4d7022a24f99756060742bae874fc90b2b571a1ddd245b11c83ffb06.txt) |
| d1ccfe31 | `d1ccfe31627c9fcae62ecdc09ff32ef571ac1778ca10f1dcd0cd3f9d90db9405` | 2026-11-10 | [Sable: A Small-Field Sumcheck Argument for Bit-Exact Inference of Large …](../../data/real/real-v2/raw/arxiv-entities/870875a97bf41aa007a20591c65e16dcfd3144483a711ca7841376d074ad307f.txt) |
| d210bc08 | `d210bc08b89adc4b61ef78bda8b0b2882d290e0d163dfa9d5d2534b4b4ac441e` | 2026-10-02 | [Snowflake Inc.: 8-K filed 2026-10-02: exhibit exhibit992-pricingpressrel.htm](../../data/real/real-v2/raw/edgar-snowflake/dd1d27f962be29ccb9d2a3606ed037c786244aa6408559452fb81314f1af563a.txt) |
| d36750f8 | `d36750f823f521a1de4eedaf13521fd16f7e4de9a07ad00188b542ce7d8e89fd` | 2026-11-12 | [Scaling AI value without losing control: Lessons from Frontier Firms](../../data/real/real-v2/raw/microsoft-blog/2a9ca51a7124d760851d55497dcad6e5f8fca3a9bbc4b95995a772fea19d21ee.txt) |
| d3ebd001 | `d3ebd0012e800aaa6ea8a9fdb1558e474cefb414f58a52ec4640e30aab9e3af8` | 2026-10-07 | [100 days later: Microsoft still steers Windows and Copilot users …](../../data/real/real-v2/raw/mozilla-blog/1fc6d330446df50db8d1e01b59cdd13f03486b4bf68166a7499bff9e1f3dbafd.txt) |
| d4b07883 | `d4b078838b480fcdf2d5440cbd958f76b746030cea6e06454c09d079d2a4ff3c` | 2026-10-29 | [Slice Into GFN Thursday: ‘Phantom Blade Zero’ Launches on GeForce …](../../data/real/real-v2/raw/nvidia-blog/890470ba402b5f309e5db5a5c8ee01722c33a62136a9d761bf0ae89ac993fc62.txt) |
| d6a7f8e2 | `d6a7f8e2cb772dc532f88d9a0c6a848997c29c7dc7fd70244a0e6ec273aa964c` | 2026-11-10 | [When Does the Real Wiring Win? Testing connectome structure-function claims …](../../data/real/real-v2/raw/arxiv-general/0dfeab233468b9773345e2615d1756ec06acd49bd6dfafc58fc49f256b7e164f.txt) |
| d7cd170f | `d7cd170feb71b9a76380b8371c4711a4c5f57b118bb2016d1daad0b960878f4f` | 2026-11-10 | [Cognitive Mapping of Learning by Thinking Mechanisms in Large Language …](../../data/real/real-v2/raw/arxiv-general/7e2ea3b44ebed102d89e3a07068d104e085365a4a63a6c85dd8cfde7ba838538.txt) |
| d7d93a71 | `d7d93a71e2fe2357ff59d5cb80c4c404a841a26e4327f92a4b9ccd68a763c020` | 2026-11-10 | [Emergent Biological Capabilities in a Foundation Model for Molecular Interactions](../../data/real/real-v2/raw/arxiv-general/7f652053a1db60a634c0e1bb9428353e6071182c2b1d96cca96bb5b61826780d.txt) |
| da5cc113 | `da5cc1136c7e124d299210ad7d03fe3954cb90fe81c89d4a6b2d56c63abf8207` | 2026-11-12 | [NVIDIA CORP: 8-K filed 2026-11-12](../../data/real/real-v2/raw/edgar-nvidia/478dd08a4c86138891d0deea91e22b4e4cadc3708af3236f4446a569570c9319.txt) |
| db84505a | `db84505aa67f3532daa0f918101e50511ca6fb51f23b4ca0abb4eaaa5f4fbf97` | 2026-11-10 | [Uncovering the Memory Hierarchy of Modern NVIDIA GPUs for Accurate …](../../data/real/real-v2/raw/arxiv-entities/83127eb2202c89d59273f9ba54c18c63539ce4b203c231c726a131afe0bcf215.txt) |
| db9ea866 | `db9ea866803b8d8ed413a70159f316e12d7cd5c85dc3ba01debd91d352bc9537` | 2026-11-10 | [When Should Agents Remember? Falsification-Gated Self-Evolution for LLM Agents](../../data/real/real-v2/raw/arxiv-general/e84ff8913e8bb76832da30bfa57ca3396a9f1f1f160a138915b6d10b7a12a168.txt) |
| dcfca97c | `dcfca97c5e1931a1a6d8dd21b38437ed1d94b879851dcc75ec5500adf708024a` | 2026-09-25 | [Introducing the new Copilot with Home, Code and Autopilot](../../data/real/real-v2/raw/microsoft-blog/2cb7239a986f90f5d25f2ddc3691021db19b084123f8a9658689454560c234c5.txt) |
| dd3202e0 | `dd3202e03bdaeed244093abcbae46df900f505304a0017977b38c93cd35ea572` | 2026-11-10 | [SLIC: Reinforcement Fine-Tuning Small LMs for Multi-Turn Analog Circuit Optimization](../../data/real/real-v2/raw/arxiv-entities/5f8535bb206b0608bbcc07726a30723cd014b0f179bcb4d232954855ad2cda99.txt) |
| e1698167 | `e1698167cc6ab26dd7b881a44c79a188a90f80f3ede820e731bb24622d4e448c` | 2026-10-15 | [NVIDIA Expands Advanced Technology Access for Europe’s Scientific Community Through …](../../data/real/real-v2/raw/nvidia-blog/b63e95648ab076cca111f2ae136dbd1a73e4cb4c2fde68ba9b4d71ba3ace49ec.txt) |
| e1eb2e37 | `e1eb2e3747448f44f6939458dea6ed041943e62b6d87b0acfb430221eef69b0e` | 2026-09-30 | [Hewlett Packard Enterprise Co: 8-K filed 2026-09-30: exhibit hpenetworkinginvestorday20.htm](../../data/real/real-v2/raw/edgar-hpe/3533473a5cee5f154eb66d6f23fb13aaf655883575cd8a4a51009e3141e035ad.txt) |
| e36b2ca0 | `e36b2ca04daa1afd081dcb7a55c240269c0fce6d3ef918483c789cf696baa573` | 2026-10-22 | [How Companies Are Using NVIDIA DSX to Break the Power …](../../data/real/real-v2/raw/nvidia-blog/76227b87124fa8afbad22bc6f12223c152bbcf5f610f2a0dcf61d3e3e6bc5ba7.txt) |
| e3d671e8 | `e3d671e8862f261f0919b410d9d17bd4a0c6e68c7c775a833788de84f5c386a5` | 2026-10-02 | [NVIDIA DGX Spark 64GB Gives Developers More Ways to Build …](../../data/real/real-v2/raw/nvidia-blog/9cb4f63089345d046221a7bc85a56f746c3f61567895afd59fad3bad0ac26897.txt) |
| e6a19626 | `e6a19626d1b6c490513f09d90a9af7311c6bdd53dd341daee418a161a0b1a428` | 2026-11-03 | [Super Micro Computer, Inc.: 8-K filed 2026-11-03: exhibit exhibit991_20260930.htm](../../data/real/real-v2/raw/edgar-supermicro/1f096faf59833dcb655d37948a655882296b5ee4fb43b6d48124c2763189bfdf.txt) |
| e7241da1 | `e7241da13d8e5e6b849d94cbb2208781e22313d6d0f51f0d975197ac431d6ba4` | 2026-09-29 | [SEC Charges Multiple Entities in Fraud Schemes Totaling at Least …](../../data/real/real-v2/raw/sec-releases/a1bc0e4e2feb421363e2418300fec319af373fd73d000d74f3cea942eb7ad9a2.txt) |
| e8ca2bd5 | `e8ca2bd55dab33e56ccca0997625a7e27bb5402ae0ec6234682935fedf277502` | 2026-10-05 | [From Scan to Treatment Plan, AI Helps Close Breast Cancer’s …](../../data/real/real-v2/raw/nvidia-blog/b7f6e5fff59d228fb8d6d1abb80ea7e1f6f0488caf0d5ae36e2f630af4188776.txt) |
| e90047dd | `e90047ddd8a8e1eab04380a38ba7c4719698ca34ba571d1f15f262ac4353d9c2` | 2026-11-05 | [MICRON TECHNOLOGY INC: 8-K filed 2026-11-05: exhibit tm2629062d1_ex99-1.htm](../../data/real/real-v2/raw/edgar-micron/9ed63dc062bb4c5d54e3eba6678f3219ced3b237dcc61ae53d10d621397928e0.txt) |
| ea94630d | `ea94630d241d08389f31391e9a33c3e69f93d89eb1e36f4356f15816450c0476` | 2026-11-12 | [Meta Platforms, Inc.: 8-K filed 2026-11-12](../../data/real/real-v2/raw/edgar-meta/30794f05ff1d206803f5109f742bd81e50c0f16f886d7ffa51f8b577c416f24f.txt) |
| eaf3b2d2 | `eaf3b2d2638c832bdf17569746e79bc96370f461a9b3c434358bd5729510cf29` | 2026-10-06 | [What AI gets wrong and what failure teaches us](../../data/real/real-v2/raw/microsoft-research/6a71628463d6d3848b7c035a1e7d98bf10c554e826ad7ee76bc5831501f3a706.txt) |
| ebc9a045 | `ebc9a0451f76baca43774ffeca595435590daacf30ecff9948c36e6b926524c4` | 2026-09-30 | [Forecasting space weather risks on power grids](../../data/real/real-v2/raw/microsoft-research/6540706c718f1ba1fd52d2d5d9381265112dc5874a59c02afd3fa90ba4cf700c.txt) |
| ed092e93 | `ed092e93db5f17d4aca915b6e80a3aca958e7c984a43e19040c959ae05ca677f` | 2026-11-04 | [ARM HOLDINGS PLC /UK: 6-K filed 2026-11-04: exhibit exhibit992fye27q230-sepx26.htm](../../data/real/real-v2/raw/edgar-arm/8f5e6d628a9bd2abf82e8544235b29293ff78c3a75b5a889ecb1e5246a840545.txt) |
| ef70a066 | `ef70a0662c5714d2a0ae1174851dcf7b67bf2d0bf2fde9c4cc36c1c3755c43e6` | 2026-09-30 | [MICRON TECHNOLOGY INC: 8-K filed 2026-09-30: exhibit a2026q4ex991-pressrelease.htm](../../data/real/real-v2/raw/edgar-micron/242a1305e2024400802436ae850190b1ad94fd1d6d7382686181cb25282c6d7c.txt) |
| f22f6cac | `f22f6caccdc3acf3d4ec2082ccce1f82e723aa04701fc7f6336dbce187c0e950` | 2026-11-02 | [Marvell Technology, Inc.: 8-K filed 2026-11-02: exhibit d81187dex991.htm](../../data/real/real-v2/raw/edgar-marvell/262c5af9be130d130fa5547d0c6bc9d78246ed060710aa4106c94befc4b88fcc.txt) |
| f2a83ce1 | `f2a83ce11ec5238244ab591962d8f758e358bfe9b550ccb9d010b09814fc89de` | 2026-09-24 | [How Open Science Can Help Researchers Prepare for the Next …](../../data/real/real-v2/raw/nvidia-blog/5a417eb5c022f8fd3942e33ce2dca7856ed4762b5658bacbd4bd0db4484699b8.txt) |
| f2ab8644 | `f2ab86448cb46008a6050feedfeedabee50ae1784f43a33e9de08056824ef0a9` | 2026-10-27 | [[Hands-On] Comfort, Convenience, and More: A Day With Galaxy Buds …](../../data/real/real-v2/raw/samsung-news/fca890b5c6c4680a1dfe54fa8427847805c69810a940358eb96563df9833b9eb.txt) |
| f436d43a | `f436d43ada2797c22edf6dfe8f015c35ae0d35b11383cc7a01e992629b3304b9` | 2026-10-28 | [Alphabet Inc.: 8-K filed 2026-10-28: exhibit googexhibit991q32026.htm](../../data/real/real-v2/raw/edgar-alphabet/93c1d9b55761e7a4391616e6e0af1e52ebb1ee18f2018b5a0a83399169428426.txt) |
| f54782d9 | `f54782d9d5bed24c5a11c77fd02007f42b6909b0480876c2aba0d5e8d66759ff` | 2026-11-09 | [Agentic-OPD: Recovering Forgotten Agent Capabilities via On-Policy Distillation for Agentic …](../../data/real/real-v2/raw/arxiv-entities/74552e957196c333fd186a0354ea907b88458784f912aa638613d05167c3d2fb.txt) |
| f5aca3fd | `f5aca3fd3254ddeff838af8cf22f9adfd38880cda66e76d228dae00f99d992ab` | 2026-11-10 | [LM-SimBench: A Unified Framework, Dataset, and Benchmark for Large Language …](../../data/real/real-v2/raw/arxiv-general/a960ffd9eaee17ae03fe90fca8b83374c526b62d8ae4130b9fb17c586ff4d47b.txt) |
| f7860b03 | `f7860b035016f1b681bbacc3f319e27bcea9c3d120cd1318d8ee31f2331ea525` | 2026-11-10 | [Guidance: Technology transfer agreements and competition law](../../data/real/real-v2/raw/uk-cma/b6f3a6b7be59cd582b2f50f6d0d33ac6c8549a3081ec6554fb461ed77b88d138.txt) |
| f8764769 | `f876476941539b9c23d2aed3470c7922858d076a31a9bba394e394593d87be18` | 2026-11-04 | [QUALCOMM INC/DE: 8-K filed 2026-11-04: exhibit qcom092726erex991.htm](../../data/real/real-v2/raw/edgar-qualcomm/d6af8b4eb5c75fe62749728c256b3b9f4989e8cddcff3ac120cc8c18018d7410.txt) |
| f9343678 | `f9343678ab052a20cd4cab484141134141d113b20ef12d365c4f8c66113b46f7` | 2026-10-21 | [NVIDIA Agent Toolkit Expands, Grounding Enterprise Agents in Company Data](../../data/real/real-v2/raw/nvidia-blog/71920b89cff53a87a6cad72218974090d544ed71fe3c088a030a03b6885dcbd2.txt) |
| f9f2e072 | `f9f2e07205e8d3d5ed323c7843226c80638a5ac198197aa57bb7f6ac9613b7ae` | 2026-11-10 | [C$^2$-Routing: Complementary Cropping and Compression for Efficient Vision-Language Inference](../../data/real/real-v2/raw/arxiv-general/7239d9fdfba79751283079bc192972a75c46a0b97d145a1267d9567ec4bf0545.txt) |
| fc43365a | `fc43365ad835e7d7d715fe5bb6701f3fbbcf7038bbe5ed53b4022627a565861d` | 2026-10-29 | [INTEL CORP: 8-K filed 2026-10-29: exhibit q326earningsrelease.htm](../../data/real/real-v2/raw/edgar-intel/292c83f05c204def74bdad6272d02483031a62d7aa15dd3524d89798581c4d5b.txt) |
| fc9686b0 | `fc9686b0165a8630c10c2b4470ee8f1f2f1d69fff25120f691d21c8835c4de02` | 2026-09-21 | [Why Deploying Physical AI at Scale Demands Safety at Every …](../../data/real/real-v2/raw/nvidia-blog/f2f6d570108d39bca335135214e7e29ffa1ec8645ff1faa811f99f80e95daada.txt) |
| fd7933fb | `fd7933fb4e2efd78dbd589bde0d7ea156221ca94605679b322f6bf83adcb4c2e` | 2026-11-09 | [BAIR at CoRL 2026](../../data/real/real-v2/raw/bair-research/c1e088dd01c8bb6df12f660da2c29ee3fbc35d4da97077928494d7eb45b41f51.txt) |
| fe02a290 | `fe02a290db4386d391730fa9c3403f7f98c877269a493b3f19aa21f6e93f9b8c` | 2026-10-20 | [Salesforce, Inc.: 8-K filed 2026-10-20: exhibit d516983dex991.htm](../../data/real/real-v2/raw/edgar-salesforce/23adc83e8588d8d65fe8c9b4134bdb753e1452c657930cb23e712df90ce0babb.txt) |
| ff7dd746 | `ff7dd746527bbe1905847651f9601cfed51779aceac4f43e1eb2fa0d7dfb8c55` | 2026-11-10 | [The Unused Input: The Initial State as a Conditioning Interface …](../../data/real/real-v2/raw/arxiv-general/cf45332da6d775e153e604b1cc82664a775e16b9c9485960c382eee287889479.txt) |
