# real-v2 question repairs

Reviewed and repaired 13 November 2026 using only local corpus texts. All 87 records remain; gold IDs and evidence quotes are unchanged. No LLM API calls or commits. This supersedes the author report's pending-verification and mixed-side-bridge claims.

## Scoring policy

The loader returns scored questions in `questions` and retained exclusions in `excluded_questions`. Strict date-only scoring excludes the two same-date probes; their event-text ordering can be analysed separately. The historical freshness probe is excluded from the scored freshness set. Recall@10 remains gold-only; MRR/Hits@1 accept gold or acceptable_evidence. Incidental organisation mentions are recorded even for accepted alternatives and excluded records; actual cross-split gold-versus-evidence overlap is forbidden.

### Split rule before/after

Before: Decided before writing. Each organisation or research topic belongs to exactly one split; an item belongs to the split of its publisher or primary entity. Items that mention entities of both splits are not used as bridges. Dev and test share no gold item (checked by scripts/realdata/check_questions.py).

After: Decided before writing. Each organisation or research topic belongs to exactly one split; primary publisher/entity determines item ownership. Mixed-side mentions are permitted and recorded in split_overlap. Gold and accepted evidence must not overlap the other split's gold or evidence IDs; incidental mentions alone are not leakage.

## Every changed question

### rq-d-001

- `acceptable_evidence` before: `null`
  After: `["321561f3ed881e6ce4981b3ece28e394a904037bb5a085db9a4bcd738b0b6e85"]`
- `split_overlap` before: `null`
  After: `[{"item": "321561f3ed881e6ce4981b3ece28e394a904037bb5a085db9a4bcd738b0b6e85", "other_split_org": "TSMC"}]`

Evidence and reasons:

- `321561f3ed881e6ce4981b3ece28e394a904037bb5a085db9a4bcd738b0b6e85`: “Total net sales between €14.2 billion and €15.2 billion” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `321561f3ed881e6ce4981b3ece28e394a904037bb5a085db9a4bcd738b0b6e85`: “TSMC” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-d-003

- `key_facts` before: `["Christopher Garcia", "effective 1 February 2027"]`
  After: `["Christopher Garcia (also acceptable: Christopher A. Garcia)", "effective 1 February 2027"]`

Evidence and reasons:

- `d0d4e23249b050907087131a0d7f1e8267c1dd4e4b1aa8a269b3398873511073`: “effective as of February 1, 2027” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-d-005

- `key_facts` before: `["$133.19 billion (versus $37.38 billion the year before)"]`
  After: `["$133.19 billion"]`

Evidence and reasons:

- `ef70a0662c5714d2a0ae1174851dcf7b67bf2d0bf2fde9c4cc36c1c3755c43e6`: “Revenue of $133.19 billion versus $37.38 billion for the prior year” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-d-006

- `key_facts` before: `["1.5 times"]`
  After: `["1.5 times as much variance (equivalently, 50% more variance)"]`

Evidence and reasons:

- `759f3904626735fe696c3678fa5af6f57e44eb9e47aa77438ffda41e42621d1f`: “Our best equation explains 1.5 times as much precipitation variance” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-d-009

- `split_overlap` before: `null`
  After: `[{"item": "f876476941539b9c23d2aed3470c7922858d076a31a9bba394e394593d87be18", "other_split_org": "Apple"}, {"item": "f876476941539b9c23d2aed3470c7922858d076a31a9bba394e394593d87be18", "other_split_org": "Amazon"}]`

Evidence and reasons:

- `f876476941539b9c23d2aed3470c7922858d076a31a9bba394e394593d87be18`: “Apple” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `f876476941539b9c23d2aed3470c7922858d076a31a9bba394e394593d87be18`: “Amazon” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-d-010

- `key_facts` before: `["€6 billion aggregate principal amount", "closed 5 November 2026"]`
  After: `["€6 billion aggregate principal amount"]`

Evidence and reasons:

- `839e05d90c26441e88a812ec71c77163c0090c595032ff2e5852ec8fa38092cc`: “closed its underwritten public offering of €6 billion aggregate principal amount” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-d-011

- `exclude_from_scoring` before: `null`
  After: `true`
- `exclusion_reason` before: `null`
  After: `"The classroom Gemini text does not identify its version as Gemini-3.8-flash; the proposed bridge assumes model equivalence."`

Evidence and reasons:

- `8e63b58e407b6cce912aefd1eb66293f9963a2af95108424017ff37f42c110f3`: “98.5% with the observations also supplied” — The classroom Gemini text does not identify its version as Gemini-3.8-flash; the proposed bridge assumes model equivalence.

### rq-d-013

- `exclude_from_scoring` before: `null`
  After: `true`
- `exclusion_reason` before: `null`
  After: `"Invalid strict multi-hop probe (R2): the question supplies Microsoft and the harness event, so the GitHub answer needs only one item."`

Evidence and reasons:

- `092ccea5ebc08633f9116b0db24218e74c5b387a9d09331fb1f33593fd6b5a1f`: “the GitHub engineering team built a best-in-class, truly multi-model harness” — Invalid strict multi-hop probe (R2): the question supplies Microsoft and the harness event, so the GitHub answer needs only one item.

### rq-d-014

- `split_overlap` before: `null`
  After: `[{"item": "509b5324b6063966ebd64480734d2a81565b76ec383f526801c5c118508e8e1e", "other_split_org": "OpenAI"}]`

Evidence and reasons:

- `509b5324b6063966ebd64480734d2a81565b76ec383f526801c5c118508e8e1e`: “OpenAI” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-d-015

- `key_facts` before: `["Microsoft Cloud revenue $63.9 billion", "growth of 30%"]`
  After: `["Microsoft Cloud revenue $63.9 billion"]`
- `split_overlap` before: `null`
  After: `[{"item": "509b5324b6063966ebd64480734d2a81565b76ec383f526801c5c118508e8e1e", "other_split_org": "OpenAI"}]`

Evidence and reasons:

- `509b5324b6063966ebd64480734d2a81565b76ec383f526801c5c118508e8e1e`: “OpenAI” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `509b5324b6063966ebd64480734d2a81565b76ec383f526801c5c118508e8e1e`: “Microsoft Cloud revenue of $63.9 billion” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-d-022

- `question` before: `"Before its final first-quarter fiscal 2027 results, what gross margin had Supermicro estimated for that quarter?"`
  After: `"Before its final first-quarter fiscal 2027 results, what gross margin did Supermicro give in its most recent preliminary update for that quarter?"`

Evidence and reasons:

- `e6a19626d1b6c490513f09d90a9af7311c6bdd53dd341daee418a161a0b1a428`: “Gross margin of 12.7% versus 17.5% in Q4'26” — Disambiguate the requested measure/period without changing gold.

### rq-d-026

- `exclude_from_scoring` before: `null`
  After: `true`
- `exclusion_reason` before: `null`
  After: `"Invalid freshness probe: the May 2026 commencement fact was public before the corpus window, so November publication does not establish freshness."`
- `exclude_from_freshness_scoring` before: `null`
  After: `true`

Evidence and reasons:

- `6f93879fd979646b2d3ed6b566f70bf422a447c4c34801804de39199e8a9cff4`: “1 May 2026 Technology Transfer Block Exemption Order (TTBEO) 2026 comes into force” — Invalid freshness probe: the May 2026 commencement fact was public before the corpus window, so November publication does not establish freshness.

### rq-d-027

- `key_facts` before: `["140 MHz", "using 21.1k LUTs"]`
  After: `["140 MHz"]`

Evidence and reasons:

- `9b2692ab25854802754db158af72ad426ffef1a7077e74fd680511cda4c058cd`: “Six engines meet 140 MHz on a PYNQ-Z2 using 21.1k LUTs” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-t-002

- `distractors` before: `["c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144"]`
  After: `[]`
- `acceptable_evidence` before: `null`
  After: `["c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "75ee4f31c6181f87deb587c5c0aabee0762ed7058ee60d01aa78fb9ecf6b4644"]`
- `split_overlap` before: `null`
  After: `[{"item": "c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "other_split_org": "Qualcomm"}, {"item": "c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "other_split_org": "Microsoft"}, {"item": "c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "other_split_org": "Supermicro"}, {"item": "c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "other_split_org": "Dell"}, {"item": "c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "other_split_org": "HPE"}, {"item": "c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "other_split_org": "Salesforce"}, {"item": "c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "other_split_org": "Intel"}, {"item": "c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144", "other_split_org": "Micron"}]`

Evidence and reasons:

- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: “4.500 shares of Marvell common stock for each share of Lumentum common stock” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `75ee4f31c6181f87deb587c5c0aabee0762ed7058ee60d01aa78fb9ecf6b4644`: “4.500 shares of common stock” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: “Qualcomm” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: “Supermicro” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: “Dell” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: “HPE” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: “Salesforce” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: ?Intel? ? Incidental opposite-split organisation mention in accepted evidence.

- `c4bbb8b3ce671cbfb43738fab7b6cd1d90121e7344178e3621cdb0e351550144`: ?Micron? ? Incidental opposite-split organisation mention in accepted evidence.

### rq-t-004

- `acceptable_evidence` before: `null`
  After: `["b9715cb4956b68865bf76e3d6c33543ee69785d5d2bd08283d5d3779801c72f2"]`
- `split_overlap` before: `null`
  After: `[{"item": "b9715cb4956b68865bf76e3d6c33543ee69785d5d2bd08283d5d3779801c72f2", "other_split_org": "Qualcomm"}]`

Evidence and reasons:

- `b9715cb4956b68865bf76e3d6c33543ee69785d5d2bd08283d5d3779801c72f2`: “773 $ 515 50 %” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `b9715cb4956b68865bf76e3d6c33543ee69785d5d2bd08283d5d3779801c72f2`: “Qualcomm” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-t-014

- `question` before: `"Where did the single-policy vision-language-action entry finish on the final leaderboard of the 2026 BEHAVIOR Challenge, and what did it score across all 100 tasks?"`
  After: `"What final-leaderboard place did the authors report for their 2026 BEHAVIOR Challenge entry, and what Q score did their learned single policy alone achieve across all 100 tasks, excluding Astra results from the public submission?"`
- `reference_answer` before: `"9th place, with a score (Q) of 0.392"`
  After: `"The authors reported 9th place for their entry; the learned policy alone scored Q = 0.392 across all 100 tasks."`
- `notes` before: `"0.371 is the score on the 50 tasks shared with 2025."`
  After: `"0.371 is the score on the 50 tasks shared with 2025. The public submission also included some Astra results and scored Q = 0.446; the policy-only score is a separate measurement."`

Evidence and reasons:

- `9509c40e72f112667a63e5add85e821959f8161c9de63978634c49b08c2d486a`: “across all 100 tasks it scores 0.392” — Disambiguate the requested measure/period without changing gold.

### rq-t-016

- `key_facts` before: `["Harvey C. Jones (also acceptable: Harvey Jones)", "appointed Chair of the Board on 11 November 2026"]`
  After: `["Harvey C. Jones (also acceptable: Harvey Jones)"]`
- `distractors` before: `["6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2"]`
  After: `[]`
- `acceptable_evidence` before: `null`
  After: `["6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2"]`
- `split_overlap` before: `null`
  After: `[{"item": "6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2", "other_split_org": "Microsoft"}]`

Evidence and reasons:

- `6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2`: “appointed Harvey C. Jones as its first-ever Chair of the Board” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `da5cc1136c7e124d299210ad7d03fe3954cb90fe81c89d4a6b2d56c63abf8207`: “the Board appointed Harvey C. Jones, age 73, as Chair of the Board” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-t-017

- `split_overlap` before: `null`
  After: `[{"item": "4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876", "other_split_org": "HPE"}, {"item": "4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876", "other_split_org": "Dell"}]`

Evidence and reasons:

- `4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876`: “HPE” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876`: “Dell” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-t-019

- `key_facts` before: `["$114.5 billion (USD 114.5bn)"]`
  After: `["$114.5 billion rounded (also acceptable: $114.477 billion or $114,477 million)"]`
- `split_overlap` before: `null`
  After: `[{"item": "378b27e8577fe9de8595f8d763dfcf5f452b9d6d15d51c6ba90bfe8a7aecc98d", "other_split_org": "Google"}]`

Evidence and reasons:

- `378b27e8577fe9de8595f8d763dfcf5f452b9d6d15d51c6ba90bfe8a7aecc98d`: “Google” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `30589f0ec53590d9caa0274a226c6d03fab0b8c477971cbe6d8ea7a0b1392aea`: “The Company posted quarterly revenue of $114.5 billion” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-t-020

- `question` before: `"At the October 2026 OCP Global Summit one hyperscaler was credited with advancing open AI networking together with NVIDIA on Spectrum-X Ethernet SuperNICs. How large a charge did that hyperscaler book in the third quarter of 2026 for its agreement with state attorneys general?"`
  After: `"At the October 2026 OCP Global Summit one hyperscaler was credited with advancing open AI networking together with NVIDIA on Spectrum-X Ethernet SuperNICs. How large an expense charge (rather than the total settlement amount) did that hyperscaler book in the third quarter of 2026 for its agreement with state attorneys general?"`
- `split_overlap` before: `null`
  After: `[{"item": "99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d", "other_split_org": "Google"}, {"item": "99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d", "other_split_org": "Microsoft"}]`

Evidence and reasons:

- `99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d`: “Google” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `99de9e9e4c70c3f0cf9df97ea03e15e7dd7448e2aefd296331794c078ba0e1a9`: “includes a $9.89 billion charge related to this agreement” — Disambiguate the requested measure/period without changing gold.

### rq-t-021

- `split_overlap` before: `null`
  After: `[{"item": "99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d", "other_split_org": "Google"}, {"item": "99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d", "other_split_org": "Microsoft"}]`

Evidence and reasons:

- `99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d`: “Google” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `99e3e5da7420d0635813c233f5dc304a984840110fe0e798ff9af0e3827d009d`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-t-022

- `split_overlap` before: `null`
  After: `[{"item": "f9343678ab052a20cd4cab484141134141d113b20ef12d365c4f8c66113b46f7", "other_split_org": "Dell"}]`

Evidence and reasons:

- `f9343678ab052a20cd4cab484141134141d113b20ef12d365c4f8c66113b46f7`: “Dell” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-t-023

- `key_facts` before: `["$8.530 - $8.534 billion", "also acceptable: about 91% year-over-year growth"]`
  After: `["$8.530 - $8.534 billion"]`

Evidence and reasons:

- `6c9efc491c588c786390c2e9317bff72e56faddc25fb0e082a90b50805fc35fb`: “raising our revenue guidance to between $8.530 - $8.534 billion” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-t-024

- `question` before: `"One data-platform vendor is letting customers run NVIDIA's Kumo Engine and Kumo Relational models inside its notebook environment. What net proceeds did that vendor estimate from the convertible notes it priced on 28 September 2026?"`
  After: `"One data-platform vendor is letting customers run NVIDIA's Kumo Engine and Kumo Relational models inside its notebook environment. What estimated net proceeds, excluding the optional additional notes, did that vendor expect from the convertible notes it priced on 28 September 2026?"`
- `distractors` before: `["017deb85fa5bc04f88f836deb23b217ce61a179cad7b67c5d5c875af91e26e65", "7a4b80e2e778f3a9ef1aa9d633bab26a50d7425b315d80e1b5ea54780ea276c2"]`
  After: `["017deb85fa5bc04f88f836deb23b217ce61a179cad7b67c5d5c875af91e26e65"]`
- `acceptable_evidence` before: `null`
  After: `["7a4b80e2e778f3a9ef1aa9d633bab26a50d7425b315d80e1b5ea54780ea276c2"]`
- `split_overlap` before: `null`
  After: `[{"item": "f9343678ab052a20cd4cab484141134141d113b20ef12d365c4f8c66113b46f7", "other_split_org": "Dell"}]`

Evidence and reasons:

- `7a4b80e2e778f3a9ef1aa9d633bab26a50d7425b315d80e1b5ea54780ea276c2`: “net proceeds from the Offering were approximately $3.70 billion” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `f9343678ab052a20cd4cab484141134141d113b20ef12d365c4f8c66113b46f7`: “Dell” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `d210bc08b89adc4b61ef78bda8b0b2882d290e0d163dfa9d5d2534b4b4ac441e`: “net proceeds from the offering will be approximately $3.70 billion” — Disambiguate the requested measure/period without changing gold.

### rq-t-025

- `key_facts` before: `["not to exceed US$500 million", "at the IPO price per share", "developer is Anthropic"]`
  After: `["not to exceed US$500 million", "at the IPO price per share"]`
- `split_overlap` before: `null`
  After: `[{"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Samsung"}, {"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Qualcomm"}, {"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Salesforce"}]`

Evidence and reasons:

- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Samsung” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Qualcomm” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Salesforce” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `af60f5ac895f01bfb9c7e606dadf2508ea16d9808daac4ed736f9d8a7f4e724f`: “in an amount not to exceed US$500 million to acquire Anthropic” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

### rq-t-026

- `key_facts` before: `["Pearson r = 0.97", "also acceptable: mean absolute error 0.85 marks"]`
  After: `["Pearson r = 0.97"]`
- `split_overlap` before: `null`
  After: `[{"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Samsung"}, {"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Qualcomm"}, {"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Salesforce"}]`
- `exclude_from_scoring` before: `null`
  After: `true`
- `exclusion_reason` before: `null`
  After: `"Invalid strict multi-hop probe (R3): the uniquely described grading study alone supplies Pearson r; the Amazon hop is unnecessary."`

Evidence and reasons:

- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Samsung” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Qualcomm” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Salesforce” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `9553071426ca46d879df4053183f0e62bdf333a3989969bc3cd0f74ec5d6f4b2`: “agreed strongly with human grading on totals (r = 0.97; MAE = 0.85 marks)” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.
- `9553071426ca46d879df4053183f0e62bdf333a3989969bc3cd0f74ec5d6f4b2`: “agreed strongly with human grading on totals (r = 0.97; MAE = 0.85 marks)” — Invalid strict multi-hop probe (R3): the uniquely described grading study alone supplies Pearson r; the Amazon hop is unnecessary.

### rq-t-029

- `question` before: `"The FTC and 22 states accuse an online retailer of secretly inflating prices in its search-advertising auctions. What growth in advertising revenue does that retailer itself expect for the fourth quarter of 2026?"`
  After: `"The FTC and 22 states accuse an online retailer of secretly inflating prices in its search-advertising auctions. What year-over-year growth in advertising revenue does that retailer itself expect for the fourth quarter of 2026?"`
- `split_overlap` before: `null`
  After: `[{"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Samsung"}, {"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Qualcomm"}, {"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Salesforce"}]`

Evidence and reasons:

- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Samsung” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Qualcomm” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Salesforce” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “advertising revenue to grow in the high teens in fourth quarter 2026” — Disambiguate the requested measure/period without changing gold.

### rq-t-030

- `split_overlap` before: `null`
  After: `[{"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Samsung"}, {"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Qualcomm"}, {"item": "6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7", "other_split_org": "Salesforce"}, {"item": "b64c2e063a2e875e36fd7c5d02f75b57f6fba73c1e96016a6144781a22f0aa3a", "other_split_org": "Google"}, {"item": "b64c2e063a2e875e36fd7c5d02f75b57f6fba73c1e96016a6144781a22f0aa3a", "other_split_org": "Microsoft"}, {"item": "b64c2e063a2e875e36fd7c5d02f75b57f6fba73c1e96016a6144781a22f0aa3a", "other_split_org": "HPE"}]`
- `exclude_from_scoring` before: `null`
  After: `true`
- `exclusion_reason` before: `null`
  After: `"Invalid strict multi-hop probe (R1): the question names AMD Helios and its release directly supplies the GPU series."`

Evidence and reasons:

- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Samsung” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Qualcomm” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `6d38920496a9f847158d2714d94aeda9ddc1061c252425f543c7f5e8466ea2d7`: “Salesforce” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `b64c2e063a2e875e36fd7c5d02f75b57f6fba73c1e96016a6144781a22f0aa3a`: “Google” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `b64c2e063a2e875e36fd7c5d02f75b57f6fba73c1e96016a6144781a22f0aa3a`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `b64c2e063a2e875e36fd7c5d02f75b57f6fba73c1e96016a6144781a22f0aa3a`: “HPE” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `b64c2e063a2e875e36fd7c5d02f75b57f6fba73c1e96016a6144781a22f0aa3a`: “powered by AMD Instinct MI450 Series GPUs” — Invalid strict multi-hop probe (R1): the question names AMD Helios and its release directly supplies the GPU series.

### rq-t-032

- `split_overlap` before: `null`
  After: `[{"item": "692eaf473852f2f09dcce1336ae22e836b23882381eb3d104a64037ad61e9500", "other_split_org": "Google"}, {"item": "692eaf473852f2f09dcce1336ae22e836b23882381eb3d104a64037ad61e9500", "other_split_org": "Samsung"}]`
- `exclude_from_scoring` before: `null`
  After: `true`
- `exclusion_reason` before: `null`
  After: `"Invalid retrieval-isolated multi-hop probe: iOS identifies Apple by general knowledge and the CEO can be recalled without the bridge."`

Evidence and reasons:

- `692eaf473852f2f09dcce1336ae22e836b23882381eb3d104a64037ad61e9500`: “Google” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `692eaf473852f2f09dcce1336ae22e836b23882381eb3d104a64037ad61e9500`: “Samsung” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `30589f0ec53590d9caa0274a226c6d03fab0b8c477971cbe6d8ea7a0b1392aea`: “said John Ternus, Apple’s CEO” — Invalid retrieval-isolated multi-hop probe: iOS identifies Apple by general knowledge and the CEO can be recalled without the bridge.

### rq-t-034

- `question` before: `"Among the model builders NVIDIA lists as recently shipping NVFP4 checkpoints, one is a social-media company. What were that company's capital expenditures in the third quarter of 2026?"`
  After: `"Among the model builders NVIDIA lists as recently shipping NVFP4 checkpoints, one is a social-media company. What were that company's capital expenditures, including principal payments on finance leases, in the third quarter of 2026?"`
- `split_overlap` before: `null`
  After: `[{"item": "4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876", "other_split_org": "HPE"}, {"item": "4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876", "other_split_org": "Dell"}]`

Evidence and reasons:

- `4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876`: “HPE” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `4f4e68d2920712b67e0446669b0c51698cbcef7d4006e0334a9f5879210d1876`: “Dell” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `99de9e9e4c70c3f0cf9df97ea03e15e7dd7448e2aefd296331794c078ba0e1a9`: “including principal payments on finance leases, were $34.91 billion” — Disambiguate the requested measure/period without changing gold.

### rq-t-036

- `acceptable_evidence` before: `null`
  After: `["6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2"]`
- `split_overlap` before: `null`
  After: `[{"item": "6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2", "other_split_org": "Microsoft"}]`

Evidence and reasons:

- `6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2`: “Colette Kress, current Executive Vice President and Chief Financial Officer of NVIDIA” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `6efa7d34961196a57a1382eaae17c4a64c6c4ae4c18b7082ab6492ec1d449bb2`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-t-037

- `notes` before: `"Verified changed fact. Answering 'Colette Kress' is the stale-direction error."`
  After: `"Verified changed fact. Answering 'Colette Kress' is the stale-direction error. Alternative October CEO sources support the as-of answer; answer correctness alone does not demonstrate temporal retrieval."`
- `acceptable_evidence` before: `null`
  After: `["66b41ebef1028fc285926a811ca3b53fdbab9e4baf84e74bd6fc469e0dcd130b", "4f3416cdcd60ce1ebc7567a6e950f4ba90470d91fb5f4cb2ce34dcd39a10fb87", "a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5"]`
- `split_overlap` before: `null`
  After: `[{"item": "66b41ebef1028fc285926a811ca3b53fdbab9e4baf84e74bd6fc469e0dcd130b", "other_split_org": "Microsoft"}, {"item": "a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5", "other_split_org": "Dell"}, {"item": "a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5", "other_split_org": "Microsoft"}, {"item": "66b41ebef1028fc285926a811ca3b53fdbab9e4baf84e74bd6fc469e0dcd130b", "other_split_org": "Dell"}, {"item": "4f3416cdcd60ce1ebc7567a6e950f4ba90470d91fb5f4cb2ce34dcd39a10fb87", "other_split_org": "Google"}, {"item": "a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5", "other_split_org": "Supermicro"}]`

Evidence and reasons:

- `66b41ebef1028fc285926a811ca3b53fdbab9e4baf84e74bd6fc469e0dcd130b`: “NVIDIA founder and CEO Jensen Huang” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `4f3416cdcd60ce1ebc7567a6e950f4ba90470d91fb5f4cb2ce34dcd39a10fb87`: “NVIDIA founder and CEO Jensen Huang” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5`: “NVIDIA founder and CEO Jensen Huang” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `66b41ebef1028fc285926a811ca3b53fdbab9e4baf84e74bd6fc469e0dcd130b`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5`: “Dell” — Incidental opposite-split organisation mention; primary-entity split ownership retained.
- `a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

- `66b41ebef1028fc285926a811ca3b53fdbab9e4baf84e74bd6fc469e0dcd130b`: ?Dell? ? Incidental opposite-split organisation mention in accepted evidence.

- `4f3416cdcd60ce1ebc7567a6e950f4ba90470d91fb5f4cb2ce34dcd39a10fb87`: ?Google? ? Incidental opposite-split organisation mention in accepted evidence.

- `a91dcd5be4c8758e5e5d0b1e9b335689c7a548443f95c3747a3d4e24758daeb5`: ?Supermicro? ? Incidental opposite-split organisation mention in accepted evidence.

### rq-t-044

- `exclude_from_scoring` before: `null`
  After: `true`
- `exclusion_reason` before: `null`
  After: `"Strict date-based changed-fact scoring unavailable: both versions have the same release and manifest dates; only textual event order is known."`
- `date_order_unavailable` before: `null`
  After: `true`

Evidence and reasons:

- `d210bc08b89adc4b61ef78bda8b0b2882d290e0d163dfa9d5d2534b4b4ac441e`: “and $1.75 billion aggregate principal amount of its 0.00% Convertible Senior Notes due 2031” — Strict date-based changed-fact scoring unavailable: both versions have the same release and manifest dates; only textual event order is known.

### rq-t-047

- `distractors` before: `["c88e556cdb1cdbecb17c6cf6b0ee293d9e62037884354a0e1fb95a73b09628e2"]`
  After: `[]`
- `acceptable_evidence` before: `null`
  After: `["c88e556cdb1cdbecb17c6cf6b0ee293d9e62037884354a0e1fb95a73b09628e2"]`
- `split_overlap` before: `null`
  After: `[{"item": "c88e556cdb1cdbecb17c6cf6b0ee293d9e62037884354a0e1fb95a73b09628e2", "other_split_org": "Microsoft"}]`

Evidence and reasons:

- `c88e556cdb1cdbecb17c6cf6b0ee293d9e62037884354a0e1fb95a73b09628e2`: “Announced agreements to acquire World Labs and Taalas” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.
- `c88e556cdb1cdbecb17c6cf6b0ee293d9e62037884354a0e1fb95a73b09628e2`: “Microsoft” — Incidental opposite-split organisation mention; primary-entity split ownership retained.

### rq-t-048

- `split_overlap` before: `null`
  After: `[{"item": "830d165fb617f2834ab457283c7b98ed54da05d8a037571f1f653d5595bcb20e", "other_split_org": "Intel"}]`
- `acceptable_evidence` before: `null`
  After: `["830d165fb617f2834ab457283c7b98ed54da05d8a037571f1f653d5595bcb20e"]`

Evidence and reasons:

- `830d165fb617f2834ab457283c7b98ed54da05d8a037571f1f653d5595bcb20e`: “increase in the size of the Board from seven (7) to ten (10) members” — Alternative supports the requested answer; MRR/Hits@1 accept it, Recall@10 remains gold-only.

- `830d165fb617f2834ab457283c7b98ed54da05d8a037571f1f653d5595bcb20e`: ?Intel? ? Incidental opposite-split organisation mention in accepted evidence.

### rq-t-050

- `exclude_from_scoring` before: `null`
  After: `true`
- `exclusion_reason` before: `null`
  After: `"Strict date-based changed-fact scoring unavailable: both versions have the same release and manifest dates; no intervening dated cutoff exists."`
- `date_order_unavailable` before: `null`
  After: `true`

Evidence and reasons:

- `017deb85fa5bc04f88f836deb23b217ce61a179cad7b67c5d5c875af91e26e65`: “$1.3 billion aggregate principal amount” — Strict date-based changed-fact scoring unavailable: both versions have the same release and manifest dates; no intervening dated cutoff exists.

### rq-t-060

- `key_facts` before: `["from 31.69%", "to 22.24%"]`
  After: `["MAPE decreases from 31.69% to 22.24%; equivalently, 9.45 percentage points or about 29.8% relative reduction"]`

Evidence and reasons:

- `db84505aa67f3532daa0f918101e50511ca6fb51f23b4ca0abb4eaaa5f4fbf97`: “reduces the mean absolute percentage error (MAPE) from 31.69% to 22.24%” — Require only requested quantities; accept equivalent names/units and computed reductions where applicable.

## Final scored counts

| Split | single | multi_hop | time_sensitive | freshness | Total |
|---|---:|---:|---:|---:|---:|
| dev | 8 | 6 | 6 | 4 | 24 |
| test | 15 | 17 | 13 | 10 | 55 |

## Change totals

- Changed questions: 37; retained annotations: 87; scored: 79; excluded: 8.
- Wording clarifications: 6; key-fact repairs/variants: 12; reference-answer clarification: 1; note additions: 2; split-rule revision: 1.
- acceptable_evidence additions: 12 across 9 questions.
- Alternative additions have been checked in actual source passages; Arm explicitly tabulates both revenue and 50% growth. Marvell merger and filing sources specify the exchange conversion. No redundant support was added to gold.

- dev split_overlap: 5 records across 4 questions; scored subset: 5 records.
- test split_overlap: 47 records across 19 questions; scored subset: 36 records.
- Date-order-unavailable: 2. Freshness-specific exclusion: 1 (also excluded from scored questions).
- Cross-split gold-versus-gold/acceptable/evidence overlap: 0.

## Excluded IDs

- `rq-d-011`: The classroom Gemini text does not identify its version as Gemini-3.8-flash; the proposed bridge assumes model equivalence.
- `rq-d-013`: Invalid strict multi-hop probe (R2): the question supplies Microsoft and the harness event, so the GitHub answer needs only one item.
- `rq-t-026`: Invalid strict multi-hop probe (R3): the uniquely described grading study alone supplies Pearson r; the Amazon hop is unnecessary.
- `rq-t-030`: Invalid strict multi-hop probe (R1): the question names AMD Helios and its release directly supplies the GPU series.
- `rq-t-032`: Invalid retrieval-isolated multi-hop probe: iOS identifies Apple by general knowledge and the CEO can be recalled without the bridge.
- `rq-t-044`: Strict date-based changed-fact scoring unavailable: both versions have the same release and manifest dates; only textual event order is known.
- `rq-t-050`: Strict date-based changed-fact scoring unavailable: both versions have the same release and manifest dates; no intervening dated cutoff exists.
- `rq-d-026`: Invalid freshness probe: the May 2026 commencement fact was public before the corpus window, so November publication does not establish freshness.

## Validation and tests

Real command output follows below.

The ASML slides use `IBM` for Installed Base Management in financial guidance; this acronym is not treated as an IBM organisation mention. Additional accepted-source mentions were checked in context.

## Implementation changes

- `scripts/realdata/check_questions.py`: validates acceptable IDs, gold/distractor separation, exclusion types and reasons, special exclusion consistency, split-overlap structure/source mentions, and cross-split gold versus evidence leakage. Prints scored counts and annotation totals alongside retained counts.
- `src/omnistream/eval/real/dataset.py`: passes acceptable IDs through, validates evidence/exclusion semantics, blocks cross-split gold versus evidence leakage, filters scored questions, and returns excluded records in `excluded_questions`. Retains their referenced texts and freshness membership for auditability without running their questions as scored probes.
- `tests/unit/test_real_question_repairs.py`: verifies alternative rank scoring without altering gold recall, exclusion filtering/audit retention, real corpus counts, invalid evidence/exclusions, and validator rejection of invalid new fields.
- `src/omnistream/eval/metrics.py`: no repair edit needed; existing gold-or-acceptable MRR/Hits@1 and gold-only Recall@10 semantics verified by regression tests.

Command: `.venv\Scripts\python.exe scripts/realdata/check_questions.py`

```text
[info] test freshness items published 2026-11-09 .. 2026-11-12
[info] dev freshness items published 2026-11-10 .. 2026-11-12
scored questions: 79  test/single=15  test/multi_hop=17  test/time_sensitive=13  test/freshness=10  dev/single=8  dev/multi_hop=6  dev/time_sensitive=6  dev/freshness=4
excluded questions: rq-d-011, rq-d-013, rq-d-026, rq-t-026, rq-t-030, rq-t-032, rq-t-044, rq-t-050
acceptable_evidence additions: 12
split_overlap records: test=47  dev=5
questions: 87  test/single=15  test/multi_hop=20  test/time_sensitive=15  test/freshness=10  dev/single=8  dev/multi_hop=8  dev/time_sensitive=6  dev/freshness=5
alias bridges: test=6 dev=3
gold items: test=69 dev=32 shared=0
routing labels: 80 {'news': 27, 'finance': 27, 'research': 26}; differ from hint: 5
uniqueness search: 87 questions searched; 52 have answer tokens in non-gold items (see table / notes)
WARN count dev/multi_hop: 8 (target 10) -> shortfall 2
WARN count dev/time_sensitive: 6 (target 7) -> shortfall 1
RESULT: PASS (0 failures, 2 warnings)
```

Exit code: 0

Command: `.venv\Scripts\python.exe -m pytest -q tests/unit/test_eval_real.py tests/unit/test_real_question_repairs.py`

```text
.........................                                                [100%]
25 passed in 3.26s
```

Exit code: 0

Command: `.venv\Scripts\python.exe -m ruff check scripts/realdata/check_questions.py src/omnistream/eval/real/dataset.py tests/unit/test_real_question_repairs.py`

```text
All checks passed!
```

Exit code: 0

Command: `.venv\Scripts\python.exe -m pytest -q`

```text
1068 passed, 1 skipped, 21 deselected in 102.45s (0:01:42)
```

Exit code: 0. No failures in repaired files or elsewhere. The offline suite uses the repository's default exclusion of integration and live tests. Final focused loader/repair tests were rerun after the last annotation and validation edits (25 passed).
