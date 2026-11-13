# real-v2 implementation and review log

Read real-v1-quality.md and the project improvement log before implementation.
This log stays in the assigned realdata ownership area; the shared top-level
IMPROVEMENT_LOG.md was left for the supervisor to update.

- Added documented API exceptions scoped by exact HTTPS endpoint and matching terms URL.
  Sequential connection and minimum three-second host delay remain enforced; ordinary
  pages and redirect destinations outside API scope still require robots permission.
- Added arXiv category/entity query builder and query provenance. Categories cover
  cs.AI/cs.LG/cs.CL/cs.AR/cs.DC; 120 Research items include 102 complete abstracts.
  Query variants are grouped as one arXiv source, yielding an honest 85% concentration.
- Expanded EDGAR to 24 issuers and 6-K; fetched EX-99 documents separately with accession
  and document linkage. Real indexes exposed iXBRL viewer links, now safely unwrapped
  only to document paths under the same accession (fixture regression).
- Fixed DOJ feed discovery and narrowed its body selector after a generic selector
  matched an Archived News banner. Limited theme matching to technology/entities rather
  than treating all antitrust/competition coverage as on-theme.
- Added permitted EFF, Mozilla, FTC, DOJ, NIST and CMA collection. Current EFF and
  post-2024 Wikinews licences were verified as CC BY 4.0, correcting older assumptions.
  Source list and quality report record actual terms URLs and failures.
- Avoided redundant page requests for sufficiently deep full RSS text, preserved stricter
  robots crawl delays, and stopped fetching article bodies after a source cap is reached.
- Isolated all v2 replay snapshots and intake files beneath data/real/real-v2/. Fresh
  intake databases make interrupted runs recoverable without deleting stored originals.
  Cached HTTP responses make subsequent collection deterministic.
- Added reviewed event-date overrides and conservative URL date/month-upper-bound hints.
  Excluded the supervisor-flagged MSRA Singapore post and a TSMC filing solely describing
  August events; preserved September/October disclosures. Excluded an arXiv title/body
  mismatch discovered in direct sample review rather than inventing repaired metadata.
- Conservatively kept fetched bodies under 120 words in unknown-depth classes. The
  38-word CMA guidance landing page is not counted as full guidance text.
- Added Settings/project-LLM JSON extraction, exact observed-surface validation, per-item
  cache and usage/cost accounting. No key was present in process settings, and the private
  credential request timed out. No local NER substitute or fabricated precision was used.
- Directly reviewed 25 changed financial/product/leadership attributes, with old/new values,
  accepted IDs, publication dates, event dates where useful, and <=15-word evidence per
  side. Twenty-one concern TSMC monthly disclosures; these are 25 distinct attributes,
  not 25 independent event narratives. The validator passes all 25 records.
- Regenerated fixed-seed 30-item sample and recorded text prefix/ending notes. The requested
  entity precision review remains explicitly blocked, because extraction has not run.
- Final: 350 items (News 115, Finance 115, Research 120), no exact duplicates, zero
  integrity errors. Full/likely articles 66.6%, complete abstracts 29.1%, combined 95.7%.
  Verdict HOLD: arXiv exceeds the strict source cap and LLM suitability evidence is missing.
- Validation: 1009 passed, 1 skipped, 21 deselected; repository-wide Ruff and diff checks clean.
  See real-v2-validation.md for pasted command output.
