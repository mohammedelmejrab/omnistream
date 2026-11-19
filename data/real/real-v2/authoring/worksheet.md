# real-v2 question authoring worksheet (working notes, not a deliverable)

## Split assignment (decided before writing)
TEST clusters: NVIDIA, TSMC, Apple (+CMA Apple page, EFF Siri item), Amazon (+FTC), Meta, AMD, IBM, Marvell,
  Cisco (+EFF Cisco/ATS item), Arm, Oracle, Snowflake, Broadcom, Palantir (+EFF Medicare item), DOJ, NIST,
  SEC enforcement releases, EFF (non-Google posts), arXiv items naming NVIDIA / Claude / GPT / IBM / TSMC / Llama etc.
DEV clusters: Alphabet/Google (+CMA Google pages, EFF Google posts, arXiv Gemini/Google papers), Microsoft
  (blog, MSR, filings), Samsung, Qualcomm, Intel, Micron, ASML, Supermicro, Salesforce, HPE, Dell, Mozilla,
  Federal Reserve, SEC rule/policy releases, CMA technology-transfer pages, selected arXiv-general items.
Rule: an item belongs to the split of its publisher/primary entity. Items that mention both sides are not used as cross-split bridges.

## Verified bridges (ids are 8-char prefixes)
- a1da460c (EC-SWE: Claude Opus 5.5 top 67.3%) -> 6d389204 (Amazon: "Anthropic's Claude ... Opus 5.5") -> af60f5ac (TSMC board: Anthropic IPO shares <= US$500M; OpenAI preferred <= US$500M)
- 95530714 (Claude Code exam grader r=0.97) <-> 6d389204 (Amazon Continuum into Claude Code)
- dd3202e0 (SLIC, TSMC 65nm PDK 49.9%) -> 80b4295f (TSMC Q3: 2nm = 8% wafer revenue)
- 27a499f3 (IBM Heron ibm_kobe) -> b622243b (IBM Q3)
- c2cadf01 (NVLinkOneSided on Blackwell) -> 4f4e68d2 (HBM per GPU +~3% Blackwell Ultra -> Vera Rubin)
- c7708a09 (Jensen Huang, Astana 23 Oct) -> da5cc113 (Jen-Hsun Huang resigned 11 Nov; Kress interim; Harvey C. Jones Chair)  ALIAS
- 6bbb2a8b (EFF: Cisco Systems v. Doe I) -> 8dcb1e89 (Cisco director Girish D. Rishi)
- 378b27e8 (CMA Apple NFC consultation 20 Oct 2026) -> 30589f0e (Apple Q4 FY26: $114.5B, CEO John Ternus)
- 99e3e5da (OCP: Meta+NVIDIA Spectrum-X; AMD/Google/Meta ODC spec v0.7) -> 99de9e9e (Meta $9.89B charge) / 76535d0b (AMD World Labs ~$8.2B) ALIAS AMD
- f9343678 (NVIDIA Agent Toolkit: Palantir Foundry; Snowflake Notebooks) -> 6c9efc49 / d210bc08
- 4d5cc1c4 (EFF Medicare: Zyter uses Palantir) -> 6c9efc49 / 0b99019f (SEC: pre-IPO Palantir fund)
- 0e8e1a03 (FTC Amazon ads) -> 6d389204
DEV:
- 7174e2bb (Samsung eyewear: Snapdragon AR1 Gen 1, Gemini) -> f8764769 (Qualcomm FY26)  ALIAS
- 532cf528 (CMA Google search CRs) -> f436d43a (Alphabet Q3)  ALIAS
- 2c5be933 (Google Research TabFM) -> 839e05d9 (Alphabet EUR 6bn notes) ALIAS
- 23e20026 (EFF: Gemini for 150M K-12 students) -> 8e63b58e (AuDiR Gemini-3.8-flash 98.5%)
- 1ff30f2f (PhyRubric matches Gemini 4 Argon) -> f436d43a (Pichai: Gemini 4 Argon and Carbon)
- 9fcaeedc/532cf528 (CMA Google) -> fc43365a (Intel: Googlebook devices on Core Ultra Series 3)
- 8faa6a57 (IFRS benchmark, SEC EDGAR) -> 510738e2 (SEC roundtable)
- 38e066dd (MS leadership: Roslansky leaving) ; d3ebd001 (Mozilla on Microsoft/Edge)

## Time-sensitive candidates
TEST: NVIDIA CEO (verified file); TSMC monthly x4 (verified file); WoW Forever on GFN (verified file);
  DGX Spark 64GB date (e3d671e8 -> a91dcd5b); Snowflake $3.5B -> $3.75B (017deb85 -> d210bc08);
  Meta latest notes (5fa2f857 -> ea94630d); Oracle plan -> done (acb0bb57 -> 16e9a090); AMD pending deals (76535d0b -> b64c2e06); Arm stats (to check)
DEV: Samsung Q3 estimate -> actual, op profit (verified file); Supermicro Q1 FY27 guidance -> prelim -> actual, CFO; Microsoft Roslansky; Mozilla/Micron (to check)
