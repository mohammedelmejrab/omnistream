# real-v1 corpus quality report

**HOLD - not approved for benchmark construction**

Window: 2026-09-18 through 2026-11-13 inclusive UTC. Verified 2026-11-13T00:22:25.591322+00:00.

## Headline results

- Accepted: 228; per bubble: {'research': 58, 'finance': 60, 'news': 110}.
- Words: {'min': 41, 'median': 437.0, 'p90': 1426.8000000000002, 'max': 7668}; likely/full-text share: 63.6%. Abstracts are NOT counted as full papers.
- Candidate outcomes: {'accepted': 228, 'too_short': 1046, 'source_cap': 71, 'before_window': 72, 'duplicate': 61, 'non_english': 2, 'boilerplate': 1}.
- Exact duplicate clusters after dedup: 0; canonical URL revision clusters: 14; BGE candidate pairs: 30 in 11 clusters.
- Entities in >=2 bubbles: 55; all 3: 3; distinct cross-bubble item pairs: 1237.
- Entities with candidate changed facts on multiple dates: 40. These are signals, not verified fact revisions.
- LLM calls: 0; LLM cost: $0.00. Local NER/BGE only.

## Requirements and limitations

- Size 228 outside target 250-400.
- finance: a source exceeds the approximate 25% cap (30% tolerance).
- research: a source exceeds the approximate 25% cap (30% tolerance).
- research: fewer than half of items are likely/full article texts (19/58).
- Changed-fact candidates require manual confirmation of actual old/new facts; freshness injection and no-context LLM check remain later tasks.

Manual NER spot-check: 90/138 candidate names valid (65.2%); 15/30 items have documented missed-name examples. This is prefix-level name precision, not full-document recall or RAG entity accuracy. Raw overlap counts below contain false positives and must not be used as gold labels.

### Manual suitability findings

- Samsung earnings results occur inside the News-hinted Samsung feed; C3/manual bubble labelling is required before source hints are treated as evaluation gold.
- NVIDIA releases feed syndicates many product/blog summaries; it is assigned News, not Finance.
- NVIDIA technical blog contains engineering tutorials and release notes rather than exclusively academic research; retain with caveat.
- NASA news broadens the theme, and some entries have older dates in their body; feed publication recency is not proof of novel facts.
- Confirmed organisation anchor **nvidia**: {'news': 40, 'finance': 1, 'research': 17}.
- Confirmed organisation anchor **microsoft**: {'news': 14, 'finance': 4, 'research': 18}.
- Surname collision: finance Jen-Hsun Huang/Jensen Huang and Research Qiming Huang are different people; do not treat this as a shared person identity. News refers to Jensen Huang.

News describes Jensen Huang as NVIDIA founder and CEO at an October 23 Kazakhstan visit; the November 12 8-K reports acceptance of Jen-Hsun Huang resignation effective November 11 and appointment of Colette M. Kress. This is a real dated leadership-change candidate; event date and filing/publication date are distinct. No evaluation question was written.
- [NVIDIA CORP: 8-K filed 2026-11-12](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000082/nvda-20261111.htm) (2026-11-12T00:00:00+00:00)
- [Kazakhstan Expands Compute for Its AI Future](https://blogs.nvidia.com/blog/kazakhstan-ai-compute-ecosystem/) (2026-10-23T02:00:13+00:00)

Older dates near the start of clean bodies (review signals, not automatically inferred publication dates):
- [One year in: How Microsoft Research Asia – Singapore is advancing research, partnership and talent for real-world impact](https://www.microsoft.com/en-us/research/blog/one-year-in-how-microsoft-research-asia-singapore-is-advancing-research-partnership-and-talent-for-real-world-impact/): body hint 2025-07-24, feed date 2026-09-28T21:00:00+00:00.
- [NASA to Welcome Expedition 74 Astronauts Home at Space Center Houston](https://www.nasa.gov/news-release/nasa-to-welcome-expedition-74-astronauts-home-at-space-center-houston/): body hint 2026-03-15, feed date 2026-11-10T18:06:33+00:00.
- [Scotland’s Flow Country](https://science.nasa.gov/earth/earth-observatory/scotlands-flow-country/): body hint 2024-03-04, feed date 2026-11-12T05:01:00+00:00.

8-K completeness means the retrieved primary filing body, not its complete exhibit/earnings packet. Linked exhibits were not fetched. Filing date is recorded at UTC midnight when the API gives a date without a time; it is not assumed to be the effective event date.

Source balance counts individual issuer/channel sources. Several sources share one publisher or distribution platform (NVIDIA blog/technical/releases; SEC filings from eight issuers). This does not constitute independent publisher diversity. The 50% full-text check is a conservative operational QA gate, not a numeric requirement from the specification.

Duplicate rejection counts include repeated feed entries from archive parameters that returned the same current issue, particularly NVIDIA releases; they are not counts of unique syndicated stories. Near-duplicate clusters also include repeated cover-page/legal boilerplate in filings and full-post/summary pairs. Review before selecting evidence.

The theme is AI, cloud computing and semiconductors. Overlap is measured below rather than assumed. Financial agency items broaden Finance beyond that theme; company press-release hints can include product news. Bubble hints are provisional source labels and have not been run through C3. No retrieval/answering code, production graph, or old evaluation snapshots were changed. No questions were written.

The recent window reduces prior-knowledge risk but does not prove absence from training data. A later no-context evaluation is required. Relevance/changed-fact verification must precede question writing. No near-duplicate candidate is silently deleted.

## Per-source accounting and text depth

| Source | Bubble | Accepted | Words min / median / p90 / max | Likely full share | Verdict |
|---|---|---:|---|---:|---|
| nvidia-blog | news | 28 | 134 / 776 / 1343.6 / 2174 | 79% | keep with caveat |
| microsoft-blog | news | 11 | 351 / 1145 / 2136 / 2824 | 82% | keep with caveat |
| google-blog | news | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| samsung-news | news | 28 | 89 / 799 / 1263 / 1600 | 79% | keep with caveat |
| aws-blog | news | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| nvidia-releases | news | 16 | 41 / 56 / 56 / 56 | 0% | keep with caveat |
| ibm-releases | finance | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| amd-releases | finance | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| cnbc-tech | finance | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| yahoo-finance | finance | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| sec-releases | finance | 23 | 192 / 335 / 549.6 / 5501 | 100% | keep |
| intel-releases | finance | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| microsoft-research | research | 18 | 985 / 1510 / 6485.5 / 7668 | 100% | keep with caveat |
| google-research | research | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| bair-research | research | 1 | 2666 / 2666 / 2666 / 2666 | 100% | keep |
| huggingface-blog | research | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| arxiv-ai | research | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| federal-reserve | finance | 20 | 63 / 121 / 363.2 / 585 | 100% | keep with caveat |
| treasury | finance | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| fdic | finance | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| nasa-news | news | 27 | 72 / 637 / 1285.4 / 1396 | 48% | keep with caveat |
| nvidia-technical | research | 28 | 73 / 81 / 91.8 / 98 | 0% | keep with caveat |
| europe-pmc | research | 11 | 146 / 246 / 343 / 353 | 0% | keep with caveat |
| arxiv-rss | research | 0 | 0 / 0 / 0 / 0 | 0% | drop |
| edgar-nvidia | finance | 1 | 602 / 602 / 602 / 602 | 100% | keep |
| edgar-microsoft | finance | 4 | 441 / 713 / 1214.1 / 1341 | 100% | keep |
| edgar-amd | finance | 2 | 577 / 624.5 / 662.5 / 672 | 100% | keep |
| edgar-intel | finance | 1 | 631 / 631 / 631 / 631 | 100% | keep |
| edgar-alphabet | finance | 2 | 860 / 958 / 1036.4 / 1056 | 100% | keep |
| edgar-ibm | finance | 2 | 869 / 888.5 / 904.1 / 908 | 100% | keep |
| edgar-amazon | finance | 1 | 639 / 639 / 639 / 639 | 100% | keep |
| edgar-meta | finance | 4 | 1060 / 2338 / 3527.8 / 3649 | 100% | keep |

Full text is a conservative proxy: >=400 words and >=3 HTML paragraphs, without explicit truncation markers; explicit successful public-domain body retrieval is counted separately as fetched full text. This cannot certify completeness; summaries/unknown and abstracts are separate classes in JSON. A literal ellipsis inside an article is not automatically treated as truncation; end ellipsis and Read more/Continue reading markers are.

### nvidia-blog

- Source: https://blogs.nvidia.com/feed/
- Licence/terms: NVIDIA terms 3.1: local personal noncommercial use. RSS is purposely made available; no article scraping under 3.2(f). Terms: https://www.nvidia.com/en-us/about-nvidia/legal-info/
- Full-text policy: feed_only; verdict: **keep with caveat**.
- Rejections: {'too_short': 1, 'source_cap': 7}; content classes: {'full_text_likely': 22, 'summary_or_truncated': 2, 'summary_or_unknown': 4}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### microsoft-blog

- Source: https://blogs.microsoft.com/feed/
- Licence/terms: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised. Terms: https://www.microsoft.com/en-us/legal/terms-of-use
- Full-text policy: feed_only; verdict: **keep with caveat**.
- Rejections: {'before_window': 19}; content classes: {'summary_or_truncated': 1, 'full_text_likely': 9, 'summary_or_unknown': 1}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### google-blog

- Source: https://blog.google/rss/
- Licence/terms: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised. Terms: https://policies.google.com/terms
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {'too_short': 20}; content classes: {}; cleanliness: {}.

### samsung-news

- Source: https://news.samsung.com/global/feed
- Licence/terms: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised. Terms: https://news.samsung.com/global/terms
- Full-text policy: feed_only; verdict: **keep with caveat**.
- Rejections: {'source_cap': 10, 'before_window': 12}; content classes: {'full_text_likely': 22, 'summary_or_unknown': 6}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### aws-blog

- Source: https://aws.amazon.com/blogs/aws/feed/
- Licence/terms: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised. Terms: https://aws.amazon.com/terms/
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {}; content classes: {}; cleanliness: {}.
- Source failure/exclusion: AWS Site Terms prohibit data mining and robots; excluded conservatively, including further feed collection.

### nvidia-releases

- Source: https://nvidianews.nvidia.com/releases.xml
- Licence/terms: NVIDIA personal noncommercial local use; syndicated feed only, no article scraping. Product announcements may be weak Finance labels. Live feed includes product news/blog syndication; assigned News rather than assuming Finance. Terms: https://www.nvidia.com/en-us/about-nvidia/legal-info/
- Full-text policy: feed_only; verdict: **keep with caveat**.
- Rejections: {'too_short': 3, 'duplicate': 61}; content classes: {'summary_or_unknown': 16}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### ibm-releases

- Source: https://newsroom.ibm.com/announcements?pagetemplate=rss&item_count=100
- Licence/terms: IBM copyright; syndicated feed only, no article fetching; local informational use, not redistribution. Terms: https://www.ibm.com/legal
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {'too_short': 5}; content classes: {}; cleanliness: {}.

### amd-releases

- Source: https://ir.amd.com/news-events/press-releases/rss
- Licence/terms: Terms endpoint returned site shell, permission for article scraping unverified. Feed only; empty bodies expected. Terms: https://www.amd.com/en/legal/terms-and-conditions.html
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {'too_short': 10}; content classes: {}; cleanliness: {}.

### cnbc-tech

- Source: https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114
- Licence/terms: Copyright NBCUniversal. Feed summaries only; no article scraping, no redistribution. Technology market coverage; provisional Finance hint. Terms: https://www.cnbc.com/nbcuniversal-terms-of-service/
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {}; content classes: {}; cleanliness: {}.
- Source failure/exclusion: PermissionError: robots disallows or unavailable: https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114

### yahoo-finance

- Source: https://finance.yahoo.com/rss/headline?s=NVDA,MSFT,GOOG,AMD,INTC,IBM
- Licence/terms: Yahoo/syndicator copyright. RSS summaries only, private research; article fetching prohibited/permission unverified. Terms: https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {}; content classes: {}; cleanliness: {}.
- Source failure/exclusion: PermissionError: robots disallows or unavailable: https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA,MSFT,GOOG,AMD,INTC,IBM&region=US&lang=en-US

### sec-releases

- Source: https://www.sec.gov/news/pressreleases.rss
- Licence/terms: SEC staff authored press-release text is US government public-domain material (17 USC 105); third-party material excepted. Public-domain article-body retrieval opted in, robots checked per request. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_domain; verdict: **keep**.
- Rejections: {'before_window': 2}; content classes: {'full_text_fetched': 23}; cleanliness: {}.

Short excerpt ([SEC Proposes Amendments to Expand Responsible Retailization of Private Markets](https://www.sec.gov/newsroom/press-releases/2026-96-sec-proposes-amendments-expand-responsible-retailization-private-markets)): The Securities and Exchange Commission today voted to propose rule amendments that would facilitate capital formation in the public and private markets by expanding retail investor choice and promoting innovation in regulated fund structures while preserving appropriate investor protections and safe

Short excerpt ([SEC Censures OTC Link LLC for Repeated Compliance Failures Related to Regulation SCI](https://www.sec.gov/newsroom/press-releases/2026-91-sec-censures-otc-link-llc-repeated-compliance-failures-related-regulation-sci)): The Securities and Exchange Commission today censured New York-based broker dealer OTC Link LLC and ordered it to pay a $575,000 civil penalty for longstanding violations of Regulation Systems Compliance and Integrity (SCI). According to the SEC’s settled order, between August 2016 and March 2025, O

### intel-releases

- Source: https://www.intc.com/news-events/press-releases/rss
- Licence/terms: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised. Terms: https://www.intel.com/content/www/us/en/legal/terms-of-use.html
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {}; content classes: {}; cleanliness: {}.
- Source failure/exclusion: Intel terms 4.1.14 and 4.1.16 prohibit automated scraping and text mining without written permission.

### microsoft-research

- Source: https://www.microsoft.com/en-us/research/feed/
- Licence/terms: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised. Terms: https://www.microsoft.com/en-us/legal/terms-of-use
- Full-text policy: feed_only; verdict: **keep with caveat**.
- Rejections: {'before_window': 12}; content classes: {'full_text_likely': 18}; cleanliness: {'javascript': 2, 'table_or_code': 2}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### google-research

- Source: https://research.google/blog/rss/
- Licence/terms: Google copyright; RSS category descriptions are not abstracts. No full-page fetching without explicit content licence. Terms: https://policies.google.com/terms
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {'too_short': 100}; content classes: {}; cleanliness: {}.

### bair-research

- Source: https://bair.berkeley.edu/blog/feed.xml
- Licence/terms: BAIR blog copyright; full text intentionally syndicated in RSS; per-post licence not assumed; private local research only. Terms: https://bair.berkeley.edu/blog/
- Full-text policy: feed_only; verdict: **keep**.
- Rejections: {'before_window': 9}; content classes: {'full_text_likely': 1}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### huggingface-blog

- Source: https://huggingface.co/blog/feed.xml
- Licence/terms: Hugging Face proprietary blog, no blanket open licence assumed. Feed only; empty descriptions expected. Terms: https://huggingface.co/terms-of-service
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {'too_short': 906}; content classes: {}; cleanliness: {}.

### arxiv-ai

- Source: https://export.arxiv.org/api/query?search_query=cat:cs.AI+AND+submittedDate:[{since_compact}0000+TO+{until_compact}2359]&start=0&max_results=100&sortBy=submittedDate&sortOrder=descending
- Licence/terms: arXiv descriptive metadata CC0 1.0; abstracts retained as abstracts, not full papers. API research use allowed, minimum 3 seconds. Terms: https://info.arxiv.org/help/api/tou.html
- Full-text policy: abstract; verdict: **drop**.
- Rejections: {}; content classes: {}; cleanliness: {}.
- Source failure/exclusion: PermissionError: robots disallows or unavailable: https://export.arxiv.org/api/query?search_query=cat:cs.AI+AND+submittedDate:[202609180000+TO+202611132359]&start=0&max_results=100&sortBy=submittedDate&sortOrder=descending

### federal-reserve

- Source: https://www.federalreserve.gov/feeds/press_all.xml
- Licence/terms: US federal agency authored text is generally public domain (17 USC 105); third-party material excepted. Fetch public press release body only with robots permission. Terms: https://www.federalreserve.gov/disclaimer.htm
- Full-text policy: fetch_public_domain; verdict: **keep with caveat**.
- Rejections: {}; content classes: {'full_text_fetched': 20}; cleanliness: {'javascript': 1}.

Short excerpt ([Federal Reserve Board issues enforcement action with Ontario Bancorporation, Inc.](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20261002a.htm)): October 02, 2026 Federal Reserve Board issues enforcement action with Ontario Bancorporation, Inc. For release at 11:00 a.m. EDT Share The Federal Reserve Board on Friday announced the execution of the following enforcement action listed below: Ontario Bancorporation, Inc., Ontario, Wisconsin Writte

Short excerpt ([Minutes of the Board's discount rate meetings on August 17, September 9, and September 16, 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20261013a.htm)): October 13, 2026 Minutes of the Board's discount rate meetings on August 17, September 9, and September 16, 2026 For release at 2:00 p.m. EDT Share The Federal Reserve Board on Tuesday released the minutes from its recent meetings to review and determine the discount rates provided to depository ins

### treasury

- Source: https://home.treasury.gov/news/press-releases/rss
- Licence/terms: US federal agency authored text is generally public domain (17 USC 105); third-party material excepted. Fetch public press release body only with robots permission. Terms: https://home.treasury.gov/utility/privacy-policy
- Full-text policy: fetch_public_domain; verdict: **drop**.
- Rejections: {}; content classes: {}; cleanliness: {}.
- Source failure/exclusion: HTTPStatusError: Client error '404 Not Found' for url 'https://home.treasury.gov/news/press-releases/rss'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404

### fdic

- Source: https://public.govdelivery.com/topics/USFDIC_26/feed.rss
- Licence/terms: Official FDIC feed linked by fdic.gov/news/press-releases, hosted by GovDelivery; US federal agency text generally public domain; no article scraping. Terms: https://www.fdic.gov/policies
- Full-text policy: feed_only; verdict: **drop**.
- Rejections: {}; content classes: {}; cleanliness: {}.
- Source failure/exclusion: PermissionError: robots disallows or unavailable: https://public.govdelivery.com/topics/USFDIC_26/feed.rss

### nasa-news

- Source: https://www.nasa.gov/feed/
- Licence/terms: US NASA authored text generally public domain; third-party credits excepted. Full-text public RSS, attribution via item URL; no external articles fetched. Terms: https://www.nasa.gov/nasa-brand-center/images-and-media/
- Full-text policy: feed_only; verdict: **keep with caveat**.
- Rejections: {'non_english': 2, 'boilerplate': 1}; content classes: {'full_text_likely': 13, 'summary_or_unknown': 9, 'summary_or_truncated': 5}; cleanliness: {'repeated_intro': 1}.

Short excerpt ([Scotland’s Flow Country](https://science.nasa.gov/earth/earth-observatory/scotlands-flow-country/)): Earth Observatory March 4, 2024 Compared to ecosystems in many other parts of the world, the blanket bogs of the Flow Country in northern Scotland are unassuming—soggy, treeless landscapes dominated by hummocky mosses, grasses, and heathers. Yet, to ecologists, the seemingly desolate areas are nothi

Short excerpt ([Ozone Hole Reaches Its 2026 Maximum](https://science.nasa.gov/earth/earth-observatory/ozone-hole-reaches-its-2026-maximum/)): Earth Observatory This data visualization shows the area and shape of the ozone hole on September 18, 2026, the day of its annual maximum extent. Scientists define the ozone hole as the area in which ozone concentrations drop below the historical threshold of 220 Dobson units. NASA Earth Observatory

### nvidia-technical

- Source: https://developer.nvidia.com/blog/feed/
- Licence/terms: NVIDIA technical blog syndicated feed; local personal noncommercial use. Tutorials and engineering posts, not necessarily peer-reviewed research. No article scraping. Terms: https://www.nvidia.com/en-us/about-nvidia/legal-info/
- Full-text policy: feed_only; verdict: **keep with caveat**.
- Rejections: {'source_cap': 54, 'before_window': 18}; content classes: {'summary_or_unknown': 28}; cleanliness: {'repeated_intro': 28}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### europe-pmc

- Source: https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(TITLE_ABS:%22large%20language%20model%22%20OR%20TITLE_ABS:%22artificial%20intelligence%22)%20AND%20FIRST_PDATE:[{since}%20TO%20{until}]%20AND%20OPEN_ACCESS:Y&format=json&resultType=core&pageSize=100&sort_date:y
- Licence/terms: Europe PMC API for open-access scholarly metadata and abstracts; article-specific licences vary. Abstracts retained, no full-paper licence assumed; no excerpts republished. Terms: https://europepmc.org/RestfulWebService
- Full-text policy: abstract; verdict: **keep with caveat**.
- Rejections: {'too_short': 1}; content classes: {'abstract': 11}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### arxiv-rss

- Source: https://rss.arxiv.org/rss/cs.AI
- Licence/terms: arXiv descriptive metadata CC0; abstracts only, no full papers. Live RSS may have an empty daily issue. Terms: https://info.arxiv.org/help/api/tou.html
- Full-text policy: abstract; verdict: **drop**.
- Rejections: {}; content classes: {}; cleanliness: {}.

### edgar-nvidia

- Source: https://data.sec.gov/submissions/CIK0001045810.json
- Licence/terms: Public SEC EDGAR issuer disclosure; issuer-authored 8-K material-event filings (not assumed public domain). Local noncommercial research only, no article excerpts or text redistributed. Official submissions API and archive; each host robots checked. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_filing; verdict: **keep**.
- Rejections: {}; content classes: {'full_text_fetched': 1}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### edgar-microsoft

- Source: https://data.sec.gov/submissions/CIK0000789019.json
- Licence/terms: Public SEC EDGAR issuer disclosure; issuer-authored 8-K material-event filings (not assumed public domain). Local noncommercial research only, no article excerpts or text redistributed. Official submissions API and archive; each host robots checked. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_filing; verdict: **keep**.
- Rejections: {}; content classes: {'full_text_fetched': 4}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### edgar-amd

- Source: https://data.sec.gov/submissions/CIK0000002488.json
- Licence/terms: Public SEC EDGAR issuer disclosure; issuer-authored 8-K material-event filings (not assumed public domain). Local noncommercial research only, no article excerpts or text redistributed. Official submissions API and archive; each host robots checked. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_filing; verdict: **keep**.
- Rejections: {}; content classes: {'full_text_fetched': 2}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### edgar-intel

- Source: https://data.sec.gov/submissions/CIK0000050863.json
- Licence/terms: Public SEC EDGAR issuer disclosure; issuer-authored 8-K material-event filings (not assumed public domain). Local noncommercial research only, no article excerpts or text redistributed. Official submissions API and archive; each host robots checked. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_filing; verdict: **keep**.
- Rejections: {}; content classes: {'full_text_fetched': 1}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### edgar-alphabet

- Source: https://data.sec.gov/submissions/CIK0001652044.json
- Licence/terms: Public SEC EDGAR issuer disclosure; issuer-authored 8-K material-event filings (not assumed public domain). Local noncommercial research only, no article excerpts or text redistributed. Official submissions API and archive; each host robots checked. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_filing; verdict: **keep**.
- Rejections: {}; content classes: {'full_text_fetched': 2}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### edgar-ibm

- Source: https://data.sec.gov/submissions/CIK0000051143.json
- Licence/terms: Public SEC EDGAR issuer disclosure; issuer-authored 8-K material-event filings (not assumed public domain). Local noncommercial research only, no article excerpts or text redistributed. Official submissions API and archive; each host robots checked. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_filing; verdict: **keep**.
- Rejections: {}; content classes: {'full_text_fetched': 2}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### edgar-amazon

- Source: https://data.sec.gov/submissions/CIK0001018724.json
- Licence/terms: Public SEC EDGAR issuer disclosure; issuer-authored 8-K material-event filings (not assumed public domain). Local noncommercial research only, no article excerpts or text redistributed. Official submissions API and archive; each host robots checked. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_filing; verdict: **keep**.
- Rejections: {}; content classes: {'full_text_fetched': 1}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

### edgar-meta

- Source: https://data.sec.gov/submissions/CIK0001326801.json
- Licence/terms: Public SEC EDGAR issuer disclosure; issuer-authored 8-K material-event filings (not assumed public domain). Local noncommercial research only, no article excerpts or text redistributed. Official submissions API and archive; each host robots checked. Terms: https://www.sec.gov/about/developer-resources
- Full-text policy: fetch_public_filing; verdict: **keep**.
- Rejections: {}; content classes: {'full_text_fetched': 4}; cleanliness: {}.

Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.

## Dates, language and cleanliness

Accepted invalid date share: 0.0%; timezone policy: RSS feedparser parsed offsets into UTC; API naive ISO dates default UTC (C1). UTC inclusive calendar date window; no inferred publication dates.

Languages: {'en': 228}; langdetect 1.0.9 deterministic seed, heuristic confidence (not calibrated). Short text is filtered before language classification.

Cleanliness flags: {'javascript': 3, 'table_or_code': 2, 'repeated_intro': 29}; integrity errors: []. Flags are heuristic candidates; tables and code can be legitimate research content. Counts and item IDs are in JSON.

| UTC publication day | Items |
|---|---:|
| 2026-09-18 | 1 |
| 2026-09-19 | 0 |
| 2026-09-20 | 0 |
| 2026-09-21 | 1 |
| 2026-09-22 | 1 |
| 2026-09-23 | 4 |
| 2026-09-24 | 1 |
| 2026-09-25 | 2 |
| 2026-09-26 | 0 |
| 2026-09-27 | 0 |
| 2026-09-28 | 3 |
| 2026-09-29 | 4 |
| 2026-09-30 | 6 |
| 2026-10-01 | 5 |
| 2026-10-02 | 3 |
| 2026-10-03 | 0 |
| 2026-10-04 | 0 |
| 2026-10-05 | 2 |
| 2026-10-06 | 5 |
| 2026-10-07 | 2 |
| 2026-10-08 | 3 |
| 2026-10-09 | 4 |
| 2026-10-10 | 0 |
| 2026-10-11 | 0 |
| 2026-10-12 | 2 |
| 2026-10-13 | 2 |
| 2026-10-14 | 3 |
| 2026-10-15 | 4 |
| 2026-10-16 | 1 |
| 2026-10-17 | 0 |
| 2026-10-18 | 0 |
| 2026-10-19 | 3 |
| 2026-10-20 | 6 |
| 2026-10-21 | 7 |
| 2026-10-22 | 9 |
| 2026-10-23 | 3 |
| 2026-10-24 | 0 |
| 2026-10-25 | 0 |
| 2026-10-26 | 3 |
| 2026-10-27 | 8 |
| 2026-10-28 | 7 |
| 2026-10-29 | 9 |
| 2026-10-30 | 7 |
| 2026-10-31 | 0 |
| 2026-11-01 | 0 |
| 2026-11-02 | 6 |
| 2026-11-03 | 7 |
| 2026-11-04 | 6 |
| 2026-11-05 | 17 |
| 2026-11-06 | 4 |
| 2026-11-07 | 0 |
| 2026-11-08 | 0 |
| 2026-11-09 | 25 |
| 2026-11-10 | 18 |
| 2026-11-11 | 4 |
| 2026-11-12 | 20 |
| 2026-11-13 | 0 |

## Duplicate audit

1200-character nonoverlapping chunks, mean pooled and L2 normalized; cosine >=0.92; candidate similarity, not proof of syndication

BGE is local BAAI/bge-small-en-v1.5 through the project EmbeddingService. Normalized-text SHA-256 is also checked independently of canonical URL. Cosine similarity is a review signal, not a calibrated syndication classifier. The JSON includes all candidate pairs, scores and connected clusters.

- Cluster: [MICROSOFT CORP: 8-K filed 2026-11-05](https://www.sec.gov/Archives/edgar/data/789019/000119312526448357/d177209d8k.htm) (edgar-microsoft); [MICROSOFT CORP: 8-K filed 2026-10-28](https://www.sec.gov/Archives/edgar/data/789019/000119312526436122/msft-20261028.htm) (edgar-microsoft); [MICROSOFT CORP: 8-K filed 2026-10-28](https://www.sec.gov/Archives/edgar/data/789019/000119312526436149/msft-20261028.htm) (edgar-microsoft)
- Cluster: [Curiosity Blog, Sols 5050-5055: It’s Nazca, Our 49th Drill Hole](https://science.nasa.gov/blog/curiosity-blog-sols-5050-5055-its-nazca-our-49th-drill-hole/) (nasa-news); [Curiosity Blog, Sols 5063-5069 Rocks and Chips](https://science.nasa.gov/blog/curiosity-blog-sols-5063-5069-rocks-and-chips/) (nasa-news); [Curiosity Blog, Sols 5056-5062: Charging Back Up!](https://science.nasa.gov/blog/curiosity-blog-sols-5056-5062-charging-back-up/) (nasa-news)
- Cluster: [From Chips to Skills, NVIDIA and Korea Expand Sovereign AI Collaboration](https://blogs.nvidia.com/blog/korea-sovereign-ai-collaboration/) (nvidia-releases); [From Chips to Skills, NVIDIA and Korea Expand Sovereign AI Collaboration](https://blogs.nvidia.com/blog/korea-sovereign-ai-collaboration/) (nvidia-blog); [NVIDIA Announces New Planned Investments in Korean Startups at the MSIT-NVIDIA AI Startup Partnership Forum](https://blogs.nvidia.com/blog/korean-startup-investments-msit/) (nvidia-releases)
- Cluster: [Samsung Presents ‘Design Is an Act of Love’ at Seoul Design Week 2026](https://news.samsung.com/global/samsung-presents-design-is-an-act-of-love-at-seoul-design-week-2026) (samsung-news); [[Photo] Inside Samsung’s ‘Design Is an Act of Love’ Exhibition at Seoul Design Week 2026](https://news.samsung.com/global/photo-inside-samsungs-design-is-an-act-of-love-exhibition-at-seoul-design-week-2026) (samsung-news)
- Cluster: [MICROSOFT CORP: 8-K filed 2026-11-04](https://www.sec.gov/Archives/edgar/data/789019/000119312526447173/d178557d8k.htm) (edgar-microsoft); [INTERNATIONAL BUSINESS MACHINES CORP: 8-K filed 2026-10-01](https://www.sec.gov/Archives/edgar/data/51143/000005114326000086/ibm-20261001.htm) (edgar-ibm); [Alphabet Inc.: 8-K filed 2026-10-28](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000080/goog-20261028.htm) (edgar-alphabet); [Meta Platforms, Inc.: 8-K filed 2026-11-05](https://www.sec.gov/Archives/edgar/data/1326801/000119312526450074/d166273d8k.htm) (edgar-meta); [INTERNATIONAL BUSINESS MACHINES CORP: 8-K filed 2026-10-21](https://www.sec.gov/Archives/edgar/data/51143/000005114326000093/ibm-20261021.htm) (edgar-ibm); [Alphabet Inc.: 8-K filed 2026-11-05](https://www.sec.gov/Archives/edgar/data/1652044/000119312526449835/d174184d8k.htm) (edgar-alphabet); [AMAZON COM INC: 8-K filed 2026-10-29](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000038/amzn-20261029.htm) (edgar-amazon); [Meta Platforms, Inc.: 8-K filed 2026-10-21](https://www.sec.gov/Archives/edgar/data/1326801/000162828026066700/meta-20261019.htm) (edgar-meta); [Meta Platforms, Inc.: 8-K filed 2026-10-29](https://www.sec.gov/Archives/edgar/data/1326801/000119312526438017/d183592d8k.htm) (edgar-meta); [Meta Platforms, Inc.: 8-K filed 2026-11-12](https://www.sec.gov/Archives/edgar/data/1326801/000119312526458525/d177728d8k.htm) (edgar-meta)
- Cluster: [NVIDIA Dynamo Recipes Bring Korea’s Leading Open Models to Production](https://blogs.nvidia.com/blog/nvidia-dynamo-korea-open-models/) (nvidia-releases); [NVIDIA Dynamo Recipes Bring Korea’s Leading Open Models to Production](https://blogs.nvidia.com/blog/nvidia-dynamo-korea-open-models/) (nvidia-blog)
- Cluster: [Microsoft Research Focus – Edition #97](https://www.microsoft.com/en-us/research/podcast/microsoft-research-focus-edition-97/) (microsoft-research); [Microsoft Research Focus – Edition #98](https://www.microsoft.com/en-us/research/podcast/microsoft-research-focus-edition-98/) (microsoft-research)
- Cluster: [Learn the rules: The hacker mindset](https://www.microsoft.com/en-us/research/podcast/learn-the-rules-the-hacker-mindset/) (microsoft-research); [Called to serve: Tech, research, and positive impact](https://www.microsoft.com/en-us/research/podcast/called-to-serve-tech-research-and-positive-impact-with-chris-white/) (microsoft-research)
- Cluster: [ADVANCED MICRO DEVICES INC: 8-K filed 2026-11-03](https://www.sec.gov/Archives/edgar/data/2488/000000248826000188/amd-20261103.htm) (edgar-amd); [ADVANCED MICRO DEVICES INC: 8-K filed 2026-09-28](https://www.sec.gov/Archives/edgar/data/2488/000000248826000182/amd-20260926.htm) (edgar-amd)
- Cluster: [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/) (nvidia-blog); [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/) (nvidia-blog); [A New Dawn in the Cloud: ‘Warhammer 40,000: Dawn of War IV’ Is Coming to GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-warhammer-dawn-of-war-iv-coming/) (nvidia-blog); [Slice Into GFN Thursday: ‘Phantom Blade Zero’ Launches on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-phantom-blade-zero/) (nvidia-blog)
- Cluster: [The platform approach to becoming Frontier](https://blogs.microsoft.com/blog/2026/10/27/the-platform-approach-to-becoming-frontier/) (microsoft-blog); [From AI ambition to business impact](https://blogs.microsoft.com/blog/2026/11/12/from-ai-ambition-to-business-impact/) (microsoft-blog); [Scaling AI value without losing control: Lessons from Frontier Firms](https://blogs.microsoft.com/blog/2026/11/12/scaling-ai-value-without-losing-control-lessons-from-frontier-firms/) (microsoft-blog)

## Cross-bubble entity suitability

spaCy en_core_web_sm 3.8.0; ORG/PERSON/PRODUCT; fixed common-organisation EntityRuler, technical-acronym exclusion list, deterministic alias map; no LLM. QA only, not used by the RAG system.

Small general-domain NER misses products and acronyms, may label generic phrases as organisations. Counts are estimates, not graph entity-linking ground truth.

Aliases are conservative and explicit: e.g. Microsoft Corporation -> Microsoft, Amazon Web Services -> AWS. Alphabet is not merged into Google; subsidiaries are not merged into parents. Distinct item pairs are counted once even if they share several entities. Full per-item extracted entities are in the metadata-only entities JSONL.

| Entity | News items | Finance items | Research items |
|---|---:|---:|---:|
| nvidia | 40 | 1 | 17 |
| microsoft | 14 | 4 | 18 |
| huang | 1 | 1 | 1 |
| nasa | 29 | 0 | 1 |
| sec | 0 | 24 | 1 |
| company | 1 | 8 | 0 |
| copilot | 5 | 0 | 2 |
| github | 4 | 0 | 3 |
| kubernetes | 2 | 0 | 5 |
| notes | 1 | 6 | 0 |
| dynamo | 5 | 0 | 1 |
| meta | 1 | 4 | 0 |
| the international space station | 4 | 0 | 1 |
| youtube | 1 | 0 | 4 |
| foundry | 3 | 0 | 1 |
| frontier | 3 | 0 | 1 |
| hugging face | 3 | 0 | 1 |
| ibm | 2 | 2 | 0 |
| max | 3 | 0 | 1 |
| siemens | 3 | 0 | 1 |
| alphabet | 0 | 2 | 1 |
| amazon | 2 | 1 | 0 |
| black forest labs | 2 | 0 | 1 |
| linkedin | 2 | 0 | 1 |
| neo | 2 | 0 | 1 |
| openai | 2 | 0 | 1 |
| operations | 2 | 1 | 0 |
| super intelligence | 1 | 2 | 0 |
| williams | 2 | 1 | 0 |
| av | 1 | 0 | 1 |
| byte | 1 | 0 | 1 |
| claude | 1 | 0 | 1 |
| corl | 1 | 0 | 1 |
| dgx | 1 | 0 | 1 |
| eth zurich | 1 | 0 | 1 |
| intel | 1 | 1 | 0 |
| ken goldberg | 1 | 0 | 1 |
| kim | 1 | 1 | 0 |
| kubernetes recipes | 1 | 0 | 1 |
| mcp | 1 | 0 | 1 |

### Manual extraction spot-check

See real-v1-ner-audit.json for item IDs, audit scope, manually recorded judgements and errors.

{
  "status": "completed manual spot-check",
  "reviewer": "implementation agent, direct reading; no LLM extraction/judge calls",
  "seed": 20261113,
  "manifest_sha256": "edf451ad7b0d322f0474685433365fa0050a315564b0315a003e2a2c922dda03",
  "items_reviewed": 30,
  "scope": "First 1100 clean-text characters of each fixed-seed sample item; complete text for shorter summaries. Full-document predicted names restricted to whole-name presence in that prefix. Titles excluded from entity scoring. Validity requires an organisation, person or product referent in context; partial names and aliases counted as valid when unambiguous, duplicates not penalised. Missed-name examples are qualitative, not exhaustive; no recall claim. This is not a held-out NER benchmark.",
  "predicted_names_reviewed": 138,
  "valid_prediction_names": 90,
  "invalid_prediction_names": 48,
  "name_precision": 0.6521739130434783,
  "items_with_missed_name_examples": 15,
  "conclusion": "Organisation anchors are useful, but product recall, alias fragmentation and cover-page/legal boilerplate errors prevent treating raw overlap counts as gold entity-linking labels. Manually validate entities used for future questions.",
  "items": [
    {
      "id": "2ffe9df2063e2be383620fc52127dc32953abea0aca6b1a90fcae7ed0c84bf1b",
      "index": 1,
      "source": "nvidia-technical",
      "predicted_names": [
        "nvidia"
      ],
      "valid_predictions": [
        "nvidia"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [
        "NVIDIA Cosmos",
        "Cosmos Framework"
      ],
      "quality_note": "Truncated technical summary repeats its opening; Cosmos product names are missed by NER."
    },
    {
      "id": "0633c8f2cf909ec8236dfb15eae101679fe36ff41b633858103e77fd235cbd08",
      "index": 2,
      "source": "nvidia-blog",
      "predicted_names": [],
      "valid_predictions": [],
      "invalid_predictions": [],
      "missed_name_examples": [],
      "quality_note": "Readable long announcement; opening is general semiconductor commentary rather than item-specific facts."
    },
    {
      "id": "f381a9f7d2287f4bfbfcedce29edd600710bd621c33140780eff6ad489f5beeb",
      "index": 3,
      "source": "nvidia-technical",
      "predicted_names": [
        "ai factory",
        "kubernetes",
        "kubernetes recipes",
        "nvidia",
        "nvke",
        "nvkr"
      ],
      "valid_predictions": [
        "kubernetes",
        "kubernetes recipes",
        "nvidia",
        "nvke",
        "nvkr"
      ],
      "invalid_predictions": [
        "ai factory"
      ],
      "missed_name_examples": [
        "NVIDIA Kubernetes Engine"
      ],
      "quality_note": "Truncated engineering summary with concrete product releases; opening repeats and one generic phrase is mislabelled."
    },
    {
      "id": "233392c77e81be53babb8c459fe74beb5bf30376bfb8e6821a3f27916a9a23b4",
      "index": 4,
      "source": "sec-releases",
      "predicted_names": [
        "sec",
        "securities and exchange commission",
        "zoe financial",
        "zoe financial inc",
        "zoe wealth"
      ],
      "valid_predictions": [
        "sec",
        "securities and exchange commission",
        "zoe financial",
        "zoe financial inc",
        "zoe wealth"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [],
      "quality_note": "Clean full SEC enforcement release; clear named firm and dated allegation, not a finding of guilt."
    },
    {
      "id": "7174e2bb239c1b56fc3a63fb5d222fe3ddc89ecb8696d45bc97a977d2c648c22",
      "index": 5,
      "source": "samsung-news",
      "predicted_names": [
        "gemini",
        "gentle monster",
        "google",
        "parker",
        "samsung",
        "samsung electronics",
        "warby parker",
        "wearer"
      ],
      "valid_predictions": [
        "gemini",
        "gentle monster",
        "google",
        "samsung",
        "samsung electronics",
        "warby parker"
      ],
      "invalid_predictions": [
        "parker",
        "wearer"
      ],
      "missed_name_examples": [],
      "quality_note": "Readable full product launch with collaborators and a future release date; promotional claims require attribution."
    },
    {
      "id": "bb1b6f52276714063ad5a40a2441725919db5e94c3140425ff944f59a1be595a",
      "index": 6,
      "source": "samsung-news",
      "predicted_names": [
        "fda",
        "galaxy ring",
        "galaxy watch",
        "korea s ministry of food and drug safety",
        "ring",
        "samsung",
        "samsung electronics",
        "sleep apnea"
      ],
      "valid_predictions": [
        "fda",
        "galaxy ring",
        "galaxy watch",
        "korea s ministry of food and drug safety",
        "ring",
        "samsung",
        "samsung electronics",
        "sleep apnea"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [
        "Samsung Health Monitor"
      ],
      "quality_note": "Full dated regulatory/product update; distinguishes prior approval from newly available device support."
    },
    {
      "id": "019981258bfa52aaabd6711835e956bb65bd37abb4dd57ef975046ef73fd72c7",
      "index": 7,
      "source": "nvidia-blog",
      "predicted_names": [
        "minerva",
        "nvidia"
      ],
      "valid_predictions": [
        "minerva",
        "nvidia"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [],
      "quality_note": "Readable full platform launch; promotional inline announcement link remains in prose."
    },
    {
      "id": "8fe3144b550811b7117d30f0081461ef1d61d6181aca59964bb07d8d73fe07a8",
      "index": 8,
      "source": "europe-pmc",
      "predicted_names": [
        "background objectives prioritizing",
        "esi",
        "hajj",
        "umrah"
      ],
      "valid_predictions": [],
      "invalid_predictions": [
        "background objectives prioritizing",
        "esi",
        "hajj",
        "umrah"
      ],
      "missed_name_examples": [
        "GPT-5.2"
      ],
      "quality_note": "Clean published research abstract about synthetic clinical dialogues; the corpus item itself is a real paper, not generated benchmark data."
    },
    {
      "id": "0d5790a56622735cd9d35817d19f2f1f611d6b001f5a8a8f460482962aa4baa5",
      "index": 9,
      "source": "nvidia-blog",
      "predicted_names": [
        "3.5 transcribe",
        "asus",
        "dlss",
        "hp",
        "lenovo",
        "microsoft",
        "msi",
        "nemotron",
        "nvidia",
        "phantom blade zero",
        "rtx spark",
        "s-game"
      ],
      "valid_predictions": [
        "asus",
        "dlss",
        "hp",
        "lenovo",
        "microsoft",
        "msi",
        "nemotron",
        "nvidia",
        "phantom blade zero",
        "rtx spark",
        "s-game"
      ],
      "invalid_predictions": [
        "3.5 transcribe"
      ],
      "missed_name_examples": [
        "Dell",
        "NVIDIA Blackwell RTX",
        "NVIDIA Grace",
        "NVIDIA CUDA",
        "NVIDIA App",
        "LFM3",
        "Windows",
        "Minecraft",
        "RTX Remix1.6"
      ],
      "quality_note": "Substantial hardware/software update with recurring manufacturers and model versions; product NER recall is weak."
    },
    {
      "id": "9dfe7447f2e15f3cdc8107935ade12e84bbb91d7f2e117bed3c751ae2fa0c938",
      "index": 10,
      "source": "nvidia-technical",
      "predicted_names": [
        "black forest labs"
      ],
      "valid_predictions": [
        "black forest labs"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [
        "FLUX 3 Image Klein"
      ],
      "quality_note": "Truncated model-engineering summary repeats its introduction and misses the model name in NER."
    },
    {
      "id": "fd786cfe1cbea7cba8c6b7a7fdc5686e821bf301ce4a75b12d7f1ee6cc3c3941",
      "index": 11,
      "source": "nvidia-technical",
      "predicted_names": [],
      "valid_predictions": [],
      "invalid_predictions": [],
      "missed_name_examples": [],
      "quality_note": "Truncated technical summary; body omits the Holoscan name supplied by the title, limiting item-specific evidence."
    },
    {
      "id": "14e7a4c2cd7c1aa99d7f79718934c568fb452ffe9b4cbd51d3457ed96da27da1",
      "index": 12,
      "source": "microsoft-research",
      "predicted_names": [
        "magnetar",
        "microsoft"
      ],
      "valid_predictions": [
        "magnetar",
        "microsoft"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [
        "Rust",
        "Go",
        "C",
        "Microsoft Research"
      ],
      "quality_note": "Full technical research explanation with quantified performance; named language/tool recall is incomplete."
    },
    {
      "id": "0c02d7097be582777533f5c206f10929fa96870bde69b6fcb7692ced8024fede",
      "index": 13,
      "source": "nasa-news",
      "predicted_names": [
        "curiosity",
        "curiosity blog",
        "jpl-caltech",
        "nasa",
        "nazca",
        "planetary mineralogy",
        "susanne p. schwenzer",
        "the open university",
        "utc"
      ],
      "valid_predictions": [
        "curiosity",
        "jpl-caltech",
        "nasa",
        "susanne p. schwenzer",
        "the open university"
      ],
      "invalid_predictions": [
        "curiosity blog",
        "nazca",
        "planetary mineralogy",
        "utc"
      ],
      "missed_name_examples": [
        "Mastcam",
        "MSSS"
      ],
      "quality_note": "Readable mission update with author and observation date; some navigation/title repetition remains."
    },
    {
      "id": "77e0f3a4dd52b04c24ae81522d0bb0d0468d490f3ef6db56b7843b5829d8fff3",
      "index": 14,
      "source": "europe-pmc",
      "predicted_names": [
        "mt-dmn",
        "stable diffusion"
      ],
      "valid_predictions": [
        "stable diffusion"
      ],
      "invalid_predictions": [
        "mt-dmn"
      ],
      "missed_name_examples": [],
      "quality_note": "Clean research abstract; concrete Stable Diffusion use, with a neural-network anatomical abbreviation falsely typed as an entity."
    },
    {
      "id": "0c1f5103614a251ebb81983815a560c5942a95d6fbc23e20f2b12540f47f5b99",
      "index": 15,
      "source": "microsoft-research",
      "predicted_names": [
        "kls",
        "microsoft"
      ],
      "valid_predictions": [
        "microsoft"
      ],
      "invalid_predictions": [
        "kls"
      ],
      "missed_name_examples": [],
      "quality_note": "Readable research claim; KLS is a conjecture, outside requested organisation/person/product types."
    },
    {
      "id": "a38c4413d6248494f6614bb24541f4531a393af35f594bed53d72ff094f4b73e",
      "index": 16,
      "source": "nvidia-technical",
      "predicted_names": [
        "nccl",
        "nvidia"
      ],
      "valid_predictions": [
        "nccl",
        "nvidia"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [
        "NVIDIA Attribution"
      ],
      "quality_note": "Truncated diagnostic-tool summary repeats its opening; tool name should be recovered for entity linking."
    },
    {
      "id": "18e81a569cd52be5c5173f3f2373d762793de386c97875fe483ff0e271fab461",
      "index": 17,
      "source": "sec-releases",
      "predicted_names": [
        "ipo",
        "n.e",
        "reg cf",
        "regulation crowdfunding",
        "regulation crowdfunding reg cf",
        "sec",
        "securities and exchange commission"
      ],
      "valid_predictions": [
        "sec",
        "securities and exchange commission"
      ],
      "invalid_predictions": [
        "ipo",
        "n.e",
        "reg cf",
        "regulation crowdfunding",
        "regulation crowdfunding reg cf"
      ],
      "missed_name_examples": [
        "Small Business Capital Formation Advisory Committee"
      ],
      "quality_note": "Clean full meeting notice; useful event timing, but regulatory terms and address fragments produce false entity labels."
    },
    {
      "id": "add6a228ed4d9e57f37595604003495291f8664d37120579e610b2b688a984f7",
      "index": 18,
      "source": "nvidia-blog",
      "predicted_names": [
        "earth2studio",
        "earthmover",
        "eu",
        "eumetsat",
        "meteosat",
        "nvidia",
        "stormscope"
      ],
      "valid_predictions": [
        "earth2studio",
        "earthmover",
        "eumetsat",
        "meteosat",
        "nvidia",
        "stormscope"
      ],
      "invalid_predictions": [
        "eu"
      ],
      "missed_name_examples": [
        "NVIDIA Earth-2",
        "StormScope EU"
      ],
      "quality_note": "Full weather-model announcement with dated model additions; promotional inline link and product variants need careful parsing."
    },
    {
      "id": "5bef2525a9a8bc2b83809a4a1fbb66814e1a0768b5252504eee1e4571ca74d8f",
      "index": 19,
      "source": "samsung-news",
      "predicted_names": [
        "business",
        "company",
        "krw",
        "memory business",
        "qoq",
        "samsung",
        "samsung electronics",
        "the ds division",
        "the memory business"
      ],
      "valid_predictions": [
        "memory business",
        "samsung",
        "samsung electronics",
        "the ds division",
        "the memory business"
      ],
      "invalid_predictions": [
        "business",
        "company",
        "krw",
        "qoq"
      ],
      "missed_name_examples": [],
      "quality_note": "Full earnings release is a Finance item within a News-hinted source; bubble label needs review and figures are issuer-reported."
    },
    {
      "id": "08abce7384db4c7bfbd4fff63dc583ce881248036a59f84ae68e26381ea313ad",
      "index": 20,
      "source": "europe-pmc",
      "predicted_names": [
        "transformer"
      ],
      "valid_predictions": [],
      "invalid_predictions": [
        "transformer"
      ],
      "missed_name_examples": [],
      "quality_note": "Clean research review abstract; broad scope and no named organisation/person/product in inspected prefix."
    },
    {
      "id": "57761b2867eb4d4b3bbf2c1fcfb359b65b3bf9866b58bf4fd0ab263de780d943",
      "index": 21,
      "source": "edgar-microsoft",
      "predicted_names": [
        "001-37845",
        "cfr 240.14a-12",
        "irs employer identification no",
        "microsoft",
        "pre",
        "pre-commencement",
        "securities and exchange commission",
        "the securities exchange act",
        "the securities exchange act of",
        "united states",
        "washington",
        "written"
      ],
      "valid_predictions": [
        "microsoft",
        "securities and exchange commission"
      ],
      "invalid_predictions": [
        "001-37845",
        "cfr 240.14a-12",
        "irs employer identification no",
        "pre",
        "pre-commencement",
        "the securities exchange act",
        "the securities exchange act of",
        "united states",
        "washington",
        "written"
      ],
      "missed_name_examples": [],
      "quality_note": "Authoritative primary 8-K, but inspected prefix is legal cover-page boilerplate and NER has many false positives."
    },
    {
      "id": "99602e36a5dec8b2f9d9576f72580a0752e9e9c47ff69f83906a392e3322f54e",
      "index": 22,
      "source": "nvidia-releases",
      "predicted_names": [],
      "valid_predictions": [],
      "invalid_predictions": [],
      "missed_name_examples": [],
      "quality_note": "Short truncated summary provides generic agent-computing context while the Vera product is only in the title."
    },
    {
      "id": "04993caf723bf947093ffd7cb1701bc7fa06ef093d3f5d995a9f78b6b2ff4171",
      "index": 23,
      "source": "edgar-microsoft",
      "predicted_names": [
        "001-37845",
        "irs employer identification no",
        "microsoft",
        "securities and exchange commission",
        "the securities exchange act",
        "the securities exchange act of",
        "united states",
        "washington"
      ],
      "valid_predictions": [
        "microsoft",
        "securities and exchange commission"
      ],
      "invalid_predictions": [
        "001-37845",
        "irs employer identification no",
        "the securities exchange act",
        "the securities exchange act of",
        "united states",
        "washington"
      ],
      "missed_name_examples": [],
      "quality_note": "Authoritative primary 8-K; event date is November 4 while filing date is November 5, and cover-page NER is noisy."
    },
    {
      "id": "be50e4a475ad4c9f5ac64f787fd3a18731288726c9cbfcf246612a508fccff4f",
      "index": 24,
      "source": "microsoft-research",
      "predicted_names": [
        "harnessed agentic rl",
        "kubernetes",
        "microsoft",
        "verified"
      ],
      "valid_predictions": [
        "kubernetes",
        "microsoft"
      ],
      "invalid_predictions": [
        "harnessed agentic rl",
        "verified"
      ],
      "missed_name_examples": [
        "Agent Lightning",
        "Microsoft Research Asia",
        "Qwen3.5-9B",
        "SWE-bench Verified"
      ],
      "quality_note": "Full research-framework release with explicit version and benchmark change; NER misses several central product/model names."
    },
    {
      "id": "c64e11d22be54d42f190426bd3d425a12ab99fb48b227749a5cc304df69aee22",
      "index": 25,
      "source": "samsung-news",
      "predicted_names": [
        "armin prommersberger",
        "bowers wilkins",
        "dave rogers",
        "harman",
        "innovation q",
        "jbl",
        "jbl and bowers wilkins",
        "samsung",
        "samsung electronics",
        "the lifestyle division"
      ],
      "valid_predictions": [
        "armin prommersberger",
        "bowers wilkins",
        "dave rogers",
        "harman",
        "jbl",
        "samsung",
        "samsung electronics",
        "the lifestyle division"
      ],
      "invalid_predictions": [
        "innovation q",
        "jbl and bowers wilkins"
      ],
      "missed_name_examples": [],
      "quality_note": "Readable attributed corporate interview with named people and brands; not independent market reporting."
    },
    {
      "id": "dc4af69a7462cd7986285e0cfffb5c58994584ccdd4f279bc7dbb3a2c11d5486",
      "index": 26,
      "source": "nvidia-technical",
      "predicted_names": [
        "nvidia",
        "snapshot"
      ],
      "valid_predictions": [
        "nvidia",
        "snapshot"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [
        "NVIDIA DSX AI Factory Platform"
      ],
      "quality_note": "Truncated technical release with repeated introduction; parent platform name is missed by NER."
    },
    {
      "id": "c88766c52f7261051f3ccebef694e29444279aa81fe2e5df1b9010a6032b2855",
      "index": 27,
      "source": "nvidia-releases",
      "predicted_names": [
        "aim intelligence",
        "hyundai motor group",
        "nvidia",
        "openshell"
      ],
      "valid_predictions": [
        "aim intelligence",
        "hyundai motor group",
        "nvidia",
        "openshell"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [
        "NVIDIA NemoClaw",
        "Starfort"
      ],
      "quality_note": "Specific but truncated ecosystem announcement; organisations recur naturally and product-name recall is incomplete."
    },
    {
      "id": "58a3aa221819515c7fba9712174aef6560c9e005b36b28c1e4dcc9c9cb31b721",
      "index": 28,
      "source": "samsung-news",
      "predicted_names": [
        "harman",
        "jbl",
        "samsung"
      ],
      "valid_predictions": [
        "harman",
        "jbl",
        "samsung"
      ],
      "invalid_predictions": [],
      "missed_name_examples": [],
      "quality_note": "Brief infographic introduction; substantive evidence may be in excluded image content, so retain only with caveat."
    },
    {
      "id": "9bd2920f6fee3d473ccd11c07759516a3a077914d7dc1c63b2155419afc1f120",
      "index": 29,
      "source": "microsoft-blog",
      "predicted_names": [
        "copilot",
        "frontier",
        "frontier transformation",
        "microsoft"
      ],
      "valid_predictions": [
        "copilot",
        "microsoft"
      ],
      "invalid_predictions": [
        "frontier",
        "frontier transformation"
      ],
      "missed_name_examples": [
        "Microsoft IQ",
        "Agent 365"
      ],
      "quality_note": "Full strategy announcement mixes named products with broad transformation language; not all prose is factual evidence."
    },
    {
      "id": "ca81f2df3addd0a8a16d9363f72769b0a3d4b83e27354cafa63cfb1b1d981c43",
      "index": 30,
      "source": "microsoft-blog",
      "predicted_names": [
        "digital",
        "microsoft",
        "sovereign cloud"
      ],
      "valid_predictions": [
        "microsoft",
        "sovereign cloud"
      ],
      "invalid_predictions": [
        "digital"
      ],
      "missed_name_examples": [],
      "quality_note": "Readable full sovereignty announcement; generic terms produce false entities and product aliases remain fragmented."
    }
  ]
}

## Candidate changed facts

At least two publication days per entity and a change verb in the same sentence as an entity mention. Publication dates are not effective fact dates. These lists are raw material; they do not demonstrate a contradiction, closure, or revised value. Full candidate item IDs, dates, URLs and signal verbs are in JSON.

- **art store**: 2026-10-06 [Samsung Art Store Expands Its Collection With 30 Exclusive Works From the British Museum](https://news.samsung.com/global/samsung-art-store-expands-its-collection-with-30-exclusive-works-from-the-british-museum); 2026-10-20 [Samsung Art Store Unveils Curated Collection From Art Basel Paris 2026](https://news.samsung.com/global/samsung-art-store-unveils-curated-collection-from-art-basel-paris-2026)
- **coding**: 2026-10-29 [Microsoft Research Focus – Edition #97](https://www.microsoft.com/en-us/research/podcast/microsoft-research-focus-edition-97/); 2026-11-12 [Microsoft Research Focus – Edition #98](https://www.microsoft.com/en-us/research/podcast/microsoft-research-focus-edition-98/)
- **commission**: 2026-10-19 [SEC Announces Roundtable on Machine-Understandable Data in the Age of Super Intelligence](https://www.sec.gov/newsroom/press-releases/2026-106-sec-announces-roundtable-machine-understandable-data-age-super-intelligence); 2026-10-23 [SEC Announces Fiscal Year 2027 Examination Priorities](https://www.sec.gov/newsroom/press-releases/2026-109-sec-announces-fiscal-year-2027-examination-priorities); 2026-10-30 [SEC Issues Exemptive Relief from Treasury Clearing Requirements for Certain Inter-Affiliate and Non-U.S. Repo Transactions](https://www.sec.gov/newsroom/press-releases/2026-111-sec-issues-exemptive-relief-treasury-clearing-requirements-certain-inter-affiliate-non-us-repo); 2026-11-10 [SEC Announces Enforcement Annual Results for Fiscal Year 2026](https://www.sec.gov/newsroom/press-releases/2026-113-sec-announces-enforcement-annual-results-fiscal-year-2026)
- **committee**: 2026-10-07 [Minutes of the Federal Open Market Committee, September 15-16, 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20261007a.htm); 2026-11-12 [Federal Reserve announces revised tentative schedule of Federal Open Market Committee meetings in 2027](https://www.federalreserve.gov/newsevents/pressreleases/monetary20261112a.htm)
- **company**: 2026-09-28 [ADVANCED MICRO DEVICES INC: 8-K filed 2026-09-28](https://www.sec.gov/Archives/edgar/data/2488/000000248826000182/amd-20260926.htm); 2026-10-21 [Meta Platforms, Inc.: 8-K filed 2026-10-21](https://www.sec.gov/Archives/edgar/data/1326801/000162828026066700/meta-20261019.htm); 2026-10-28 [MICROSOFT CORP: 8-K filed 2026-10-28](https://www.sec.gov/Archives/edgar/data/789019/000119312526436149/msft-20261028.htm); 2026-10-29 [Meta Platforms, Inc.: 8-K filed 2026-10-29](https://www.sec.gov/Archives/edgar/data/1326801/000119312526438017/d183592d8k.htm); 2026-10-29 [Samsung Electronics Announces Third Quarter 2026 Results](https://news.samsung.com/global/samsung-electronics-announces-third-quarter-2026-results); 2026-11-04 [MICROSOFT CORP: 8-K filed 2026-11-04](https://www.sec.gov/Archives/edgar/data/789019/000119312526447173/d178557d8k.htm); 2026-11-05 [Meta Platforms, Inc.: 8-K filed 2026-11-05](https://www.sec.gov/Archives/edgar/data/1326801/000119312526450074/d166273d8k.htm); 2026-11-05 [MICROSOFT CORP: 8-K filed 2026-11-05](https://www.sec.gov/Archives/edgar/data/789019/000119312526448357/d177209d8k.htm)
- **control resonant**: 2026-10-22 [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/); 2026-11-05 [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/)
- **crimson desert**: 2026-10-22 [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/); 2026-11-05 [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/)
- **division**: 2026-10-23 [SEC Announces Fiscal Year 2027 Examination Priorities](https://www.sec.gov/newsroom/press-releases/2026-109-sec-announces-fiscal-year-2027-examination-priorities); 2026-11-10 [SEC Announces Enforcement Annual Results for Fiscal Year 2026](https://www.sec.gov/newsroom/press-releases/2026-113-sec-announces-enforcement-annual-results-fiscal-year-2026)
- **dlss**: 2026-10-28 [Thin, Light and Built for Everything: NVIDIA RTX Spark Windows Laptops Gain New Models, Agent Tools and Games](https://blogs.nvidia.com/blog/local-ai-rtx-spark-laptops-updates-models-agents-games/); 2026-11-12 [A New Dawn in the Cloud: ‘Warhammer 40,000: Dawn of War IV’ Is Coming to GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-warhammer-dawn-of-war-iv-coming/)
- **eu**: 2026-10-20 [Advancing digital sovereignty with greater control and choice](https://blogs.microsoft.com/blog/2026/10/20/advancing-digital-sovereignty-with-greater-control-and-choice/); 2026-10-22 [Pioneers Across Europe Deploy NVIDIA Earth-2 Open Models to Power Real-World Weather and Climate Prediction](https://blogs.nvidia.com/blog/europe-earth-2-open-models-weather-climate-prediction/)
- **federal open market committee**: 2026-10-07 [Minutes of the Federal Open Market Committee, September 15-16, 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20261007a.htm); 2026-11-12 [Federal Reserve announces revised tentative schedule of Federal Open Market Committee meetings in 2027](https://www.federalreserve.gov/newsevents/pressreleases/monetary20261112a.htm)
- **federal reserve**: 2026-09-25 [Federal Reserve Board announces approval of application by Peoples Bancorp Inc.](https://www.federalreserve.gov/newsevents/pressreleases/orders20260925a.htm); 2026-10-02 [Federal Reserve Board issues enforcement action with Ontario Bancorporation, Inc.](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20261002a.htm); 2026-10-02 [Federal Reserve Board announces it will extend, until November 4, the comment period on its proposal to modernize Regulation O](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20261002a.htm); 2026-10-02 [Federal Reserve Board announces approval of application by Fleur Capital Corporation](https://www.federalreserve.gov/newsevents/pressreleases/orders20261002a.htm); 2026-10-05 [Federal Reserve Board announces approval of application by Isabella Bank Corporation](https://www.federalreserve.gov/newsevents/pressreleases/orders20261005a.htm); 2026-10-07 [Minutes of the Federal Open Market Committee, September 15-16, 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20261007a.htm); 2026-10-08 [Federal Reserve Board announces enforcement action against American Express Company to address, among other things, the firm’s failure to sufficiently detect and report certain suspicious activity related to money laundering](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20261008a.htm); 2026-10-09 [Federal Reserve Board releases results of the 2025 Survey of Consumer Finances, which provides the public and policymakers with detailed insights into the economic condition of American families](https://www.federalreserve.gov/newsevents/pressreleases/other20261009a.htm)
- **geforce**: 2026-10-22 [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/); 2026-10-29 [Slice Into GFN Thursday: ‘Phantom Blade Zero’ Launches on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-phantom-blade-zero/); 2026-11-05 [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/); 2026-11-12 [A New Dawn in the Cloud: ‘Warhammer 40,000: Dawn of War IV’ Is Coming to GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-warhammer-dawn-of-war-iv-coming/)
- **geforce now**: 2026-10-22 [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/); 2026-10-29 [Slice Into GFN Thursday: ‘Phantom Blade Zero’ Launches on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-phantom-blade-zero/); 2026-11-05 [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/); 2026-11-12 [A New Dawn in the Cloud: ‘Warhammer 40,000: Dawn of War IV’ Is Coming to GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-warhammer-dawn-of-war-iv-coming/)
- **gfn**: 2026-10-29 [Slice Into GFN Thursday: ‘Phantom Blade Zero’ Launches on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-phantom-blade-zero/); 2026-11-12 [A New Dawn in the Cloud: ‘Warhammer 40,000: Dawn of War IV’ Is Coming to GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-warhammer-dawn-of-war-iv-coming/)
- **gfn thursdays**: 2026-10-22 [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/); 2026-10-29 [Slice Into GFN Thursday: ‘Phantom Blade Zero’ Launches on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-phantom-blade-zero/); 2026-11-05 [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/); 2026-11-12 [A New Dawn in the Cloud: ‘Warhammer 40,000: Dawn of War IV’ Is Coming to GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-warhammer-dawn-of-war-iv-coming/)
- **hathaway**: 2026-11-09 [CHAPEA Mission 2 Crew Reflects After 378 Days on Simulated Mars](https://www.nasa.gov/centers-and-facilities/johnson/chapea-mission-2-crew-reflects-after-378-days-on-simulated-mars/); 2026-11-10 [NASA to Welcome Expedition 74 Astronauts Home at Space Center Houston](https://www.nasa.gov/news-release/nasa-to-welcome-expedition-74-astronauts-home-at-space-center-houston/)
- **huang**: 2026-09-28 [One year in: How Microsoft Research Asia – Singapore is advancing research, partnership and talent for real-world impact](https://www.microsoft.com/en-us/research/blog/one-year-in-how-microsoft-research-asia-singapore-is-advancing-research-partnership-and-talent-for-real-world-impact/); 2026-10-23 [Kazakhstan Expands Compute for Its AI Future](https://blogs.nvidia.com/blog/kazakhstan-ai-compute-ecosystem/); 2026-11-12 [NVIDIA CORP: 8-K filed 2026-11-12](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000082/nvda-20261111.htm)
- **inc**: 2026-10-29 [Meta Platforms, Inc.: 8-K filed 2026-10-29](https://www.sec.gov/Archives/edgar/data/1326801/000119312526438017/d183592d8k.htm); 2026-11-05 [Meta Platforms, Inc.: 8-K filed 2026-11-05](https://www.sec.gov/Archives/edgar/data/1326801/000119312526450074/d166273d8k.htm); 2026-11-12 [Meta Platforms, Inc.: 8-K filed 2026-11-12](https://www.sec.gov/Archives/edgar/data/1326801/000119312526458525/d177728d8k.htm)
- **jbl**: 2026-10-23 [Inside JBL Playback Gallery: 80 Years of Sound Innovation](https://news.samsung.com/global/inside-jbl-playback-gallery-80-years-of-sound-innovation); 2026-10-26 [[Interview] Sound That Connects: 80 Years of Audio and the Future of Connected Experiences](https://news.samsung.com/global/interview-sound-that-connects-80-years-of-audio-and-the-future-of-connected-experiences)
- **kls**: 2026-10-21 [Solving a 31-year-old grand challenge in mathematics – the KLS conjecture](https://www.microsoft.com/en-us/research/blog/solving-a-31-year-old-grand-challenge-in-mathematics-the-kls-conjecture/); 2026-11-12 [Microsoft Research Focus – Edition #98](https://www.microsoft.com/en-us/research/podcast/microsoft-research-focus-edition-98/)
- **llc**: 2026-10-01 [INTERNATIONAL BUSINESS MACHINES CORP: 8-K filed 2026-10-01](https://www.sec.gov/Archives/edgar/data/51143/000005114326000086/ibm-20261001.htm); 2026-11-05 [Federal Reserve Board announces termination of enforcement action with Allegiant United Holdings, LLC, Nano Financial Holdings, Inc., and Nano Banc](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20261105a.htm); 2026-11-10 [SEC Announces Enforcement Annual Results for Fiscal Year 2026](https://www.sec.gov/newsroom/press-releases/2026-113-sec-announces-enforcement-annual-results-fiscal-year-2026)
- **max**: 2026-11-09 [MAX POWER: NASA’s Inaugural Aerospace Expo Ignites America’s Future](https://www.nasa.gov/general/max-power-nasas-inaugural-aerospace-expo-ignites-americas-future/); 2026-11-12 [Microsoft Research Focus – Edition #98](https://www.microsoft.com/en-us/research/podcast/microsoft-research-focus-edition-98/)
- **microsoft**: 2026-09-23 [Offloaded inference for real-world physical AI robotics](https://www.microsoft.com/en-us/research/blog/offloaded-inference-for-real-world-physical-ai-robotics/); 2026-09-28 [One year in: How Microsoft Research Asia – Singapore is advancing research, partnership and talent for real-world impact](https://www.microsoft.com/en-us/research/blog/one-year-in-how-microsoft-research-asia-singapore-is-advancing-research-partnership-and-talent-for-real-world-impact/); 2026-09-30 [Forecasting space weather risks on power grids](https://www.microsoft.com/en-us/research/blog/forecasting-space-weather-risks-on-power-grids/); 2026-10-20 [Advancing digital sovereignty with greater control and choice](https://blogs.microsoft.com/blog/2026/10/20/advancing-digital-sovereignty-with-greater-control-and-choice/); 2026-10-21 [Solving a 31-year-old grand challenge in mathematics – the KLS conjecture](https://www.microsoft.com/en-us/research/blog/solving-a-31-year-old-grand-challenge-in-mathematics-the-kls-conjecture/); 2026-11-10 [Lazare, veni foras: Reprogramming Dormant Neurons to Backdoor AI Agents](https://www.microsoft.com/en-us/research/blog/lazare-veni-foras-reprogramming-dormant-neurons-to-backdoor-ai-agents/)
- **nasa**: 2026-11-09 [CHAPEA Mission 2 Crew Reflects After 378 Days on Simulated Mars](https://www.nasa.gov/centers-and-facilities/johnson/chapea-mission-2-crew-reflects-after-378-days-on-simulated-mars/); 2026-11-09 [MAX POWER: NASA’s Inaugural Aerospace Expo Ignites America’s Future](https://www.nasa.gov/general/max-power-nasas-inaugural-aerospace-expo-ignites-americas-future/); 2026-11-09 [Newest Sample, Oldest Rock?](https://science.nasa.gov/blog/newest-sample-oldest-rock/); 2026-11-10 [Autumn Mornings Bring Valley Fog](https://science.nasa.gov/earth/earth-observatory/autumn-mornings-bring-valley-fog/); 2026-11-10 [NASA Invites Media, Public to Join Voyager 1 One-Light Day Activities](https://www.nasa.gov/news-release/nasa-invites-media-public-to-join-voyager-1-one-light-day-activities/); 2026-11-12 [Curiosity Blog, Sols 5063-5069 Rocks and Chips](https://science.nasa.gov/blog/curiosity-blog-sols-5063-5069-rocks-and-chips/); 2026-11-12 [NASA’s Hubble Offers Cosmic Sampler of Targets for Roman](https://science.nasa.gov/missions/hubble/nasas-hubble-offers-cosmic-sampler-of-targets-for-roman/)
- **nemotron**: 2026-10-22 [NVIDIA Transforms European Retail, From Digital Discovery to Physical Operations](https://blogs.nvidia.com/blog/european-retail-open-models-robotics/); 2026-11-05 [More Performance From Every Byte: How Full-Stack Codesign Solves AI’s Memory Challenge](https://blogs.nvidia.com/blog/memory-full-stack-codesign/)
- **notes**: 2026-11-05 [Meta Platforms, Inc.: 8-K filed 2026-11-05](https://www.sec.gov/Archives/edgar/data/1326801/000119312526450074/d166273d8k.htm); 2026-11-12 [Meta Platforms, Inc.: 8-K filed 2026-11-12](https://www.sec.gov/Archives/edgar/data/1326801/000119312526458525/d177728d8k.htm)
- **nvidia**: 2026-10-22 [Pioneers Across Europe Deploy NVIDIA Earth-2 Open Models to Power Real-World Weather and Climate Prediction](https://blogs.nvidia.com/blog/europe-earth-2-open-models-weather-climate-prediction/); 2026-10-22 [NVIDIA Transforms European Retail, From Digital Discovery to Physical Operations](https://blogs.nvidia.com/blog/european-retail-open-models-robotics/); 2026-10-22 [NVIDIA Unveils Minerva to Bring End-to-End Observability for AI Factories](https://blogs.nvidia.com/blog/minerva-platform-infrastructure/); 2026-10-23 [Kazakhstan Expands Compute for Its AI Future](https://blogs.nvidia.com/blog/kazakhstan-ai-compute-ecosystem/); 2026-10-28 [Thin, Light and Built for Everything: NVIDIA RTX Spark Windows Laptops Gain New Models, Agent Tools and Games](https://blogs.nvidia.com/blog/local-ai-rtx-spark-laptops-updates-models-agents-games/); 2026-11-03 [Cities Worldwide Build and Scale AI Services With NVIDIA Physical and Agentic AI](https://blogs.nvidia.com/blog/cities-physical-agentic-ai-applications/); 2026-11-05 [More Performance From Every Byte: How Full-Stack Codesign Solves AI’s Memory Challenge](https://blogs.nvidia.com/blog/memory-full-stack-codesign/); 2026-11-05 [Into the Omniverse: How Developers Turn Ideas Into Simulations With Frontier AI Agents](https://blogs.nvidia.com/blog/developers-simulation-frontier-ai-agents/)
- **registrant**: 2026-09-28 [ADVANCED MICRO DEVICES INC: 8-K filed 2026-09-28](https://www.sec.gov/Archives/edgar/data/2488/000000248826000182/amd-20260926.htm); 2026-10-01 [INTERNATIONAL BUSINESS MACHINES CORP: 8-K filed 2026-10-01](https://www.sec.gov/Archives/edgar/data/51143/000005114326000086/ibm-20261001.htm); 2026-10-21 [INTERNATIONAL BUSINESS MACHINES CORP: 8-K filed 2026-10-21](https://www.sec.gov/Archives/edgar/data/51143/000005114326000093/ibm-20261021.htm); 2026-10-21 [Meta Platforms, Inc.: 8-K filed 2026-10-21](https://www.sec.gov/Archives/edgar/data/1326801/000162828026066700/meta-20261019.htm); 2026-10-28 [Alphabet Inc.: 8-K filed 2026-10-28](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000080/goog-20261028.htm); 2026-10-29 [AMAZON COM INC: 8-K filed 2026-10-29](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000038/amzn-20261029.htm); 2026-10-29 [Meta Platforms, Inc.: 8-K filed 2026-10-29](https://www.sec.gov/Archives/edgar/data/1326801/000119312526438017/d183592d8k.htm); 2026-11-03 [ADVANCED MICRO DEVICES INC: 8-K filed 2026-11-03](https://www.sec.gov/Archives/edgar/data/2488/000000248826000188/amd-20261103.htm)
- **samsung**: 2026-10-06 [Samsung Art Store Expands Its Collection With 30 Exclusive Works From the British Museum](https://news.samsung.com/global/samsung-art-store-expands-its-collection-with-30-exclusive-works-from-the-british-museum); 2026-10-06 [Samsung Introduces ‘SmartThings Now’ in New Platform Update That Brings More Intuitive User Experiences](https://news.samsung.com/global/samsung-introduces-smartthings-now-in-new-platform-update-that-brings-more-intuitive-user-experiences); 2026-10-14 [Samsung Health Makes Sleep Coaching Easier To Start and Tailors Weekly Guidance](https://news.samsung.com/global/samsung-health-makes-sleep-coaching-easier-to-start-and-tailors-weekly-guidance); 2026-10-15 [Samsung Hosts Silicon Valley Future Wireless Summit 2026](https://news.samsung.com/global/samsung-hosts-silicon-valley-future-wireless-summit-2026); 2026-10-15 [Samsung Presents ‘Design Is an Act of Love’ at Seoul Design Week 2026](https://news.samsung.com/global/samsung-presents-design-is-an-act-of-love-at-seoul-design-week-2026); 2026-10-20 [Samsung Art Store Unveils Curated Collection From Art Basel Paris 2026](https://news.samsung.com/global/samsung-art-store-unveils-curated-collection-from-art-basel-paris-2026); 2026-10-23 [Inside JBL Playback Gallery: 80 Years of Sound Innovation](https://news.samsung.com/global/inside-jbl-playback-gallery-80-years-of-sound-innovation); 2026-10-27 [[Hands-On] Comfort, Convenience, and More: A Day With Galaxy Buds On](https://news.samsung.com/global/hands-on-comfort-convenience-and-more-a-day-with-galaxy-buds-on)
- **samsung electronics**: 2026-10-06 [Samsung Art Store Expands Its Collection With 30 Exclusive Works From the British Museum](https://news.samsung.com/global/samsung-art-store-expands-its-collection-with-30-exclusive-works-from-the-british-museum); 2026-10-06 [Samsung Introduces ‘SmartThings Now’ in New Platform Update That Brings More Intuitive User Experiences](https://news.samsung.com/global/samsung-introduces-smartthings-now-in-new-platform-update-that-brings-more-intuitive-user-experiences); 2026-10-08 [Samsung Electronics Announces Earnings Guidance for Third Quarter 2026](https://news.samsung.com/global/samsung-electronics-announces-earnings-guidance-for-third-quarter-2026); 2026-10-14 [Samsung Health Makes Sleep Coaching Easier To Start and Tailors Weekly Guidance](https://news.samsung.com/global/samsung-health-makes-sleep-coaching-easier-to-start-and-tailors-weekly-guidance); 2026-10-15 [Samsung Hosts Silicon Valley Future Wireless Summit 2026](https://news.samsung.com/global/samsung-hosts-silicon-valley-future-wireless-summit-2026); 2026-10-15 [Samsung Presents ‘Design Is an Act of Love’ at Seoul Design Week 2026](https://news.samsung.com/global/samsung-presents-design-is-an-act-of-love-at-seoul-design-week-2026); 2026-10-20 [Samsung Art Store Unveils Curated Collection From Art Basel Paris 2026](https://news.samsung.com/global/samsung-art-store-unveils-curated-collection-from-art-basel-paris-2026); 2026-10-23 [Inside JBL Playback Gallery: 80 Years of Sound Innovation](https://news.samsung.com/global/inside-jbl-playback-gallery-80-years-of-sound-innovation)
- **sec**: 2026-09-28 [SEC Charges Registered Investment Adviser Zoe Financial for Failure to Disclose Conflict of Interest](https://www.sec.gov/newsroom/press-releases/2026-94-sec-charges-registered-investment-adviser-zoe-financial-failure-disclose-conflict-interest); 2026-09-30 [SEC Charges Two Individuals With Orchestrating Fraud Scheme That Targeted Veterans](https://www.sec.gov/newsroom/press-releases/2026-97-sec-charges-two-individuals-orchestrating-fraud-scheme-targeted-veterans); 2026-10-06 [SEC to Host Virtual National Compliance Outreach Seminar for Investment Companies and Investment Advisers](https://www.sec.gov/newsroom/press-releases/2026-102-sec-host-virtual-national-compliance-outreach-seminar-investment-companies-investment-advisers); 2026-10-14 [SEC Small Business Advisory Committee to Discuss IPO Modernization and Regulation Crowdfunding](https://www.sec.gov/newsroom/press-releases/2026-105-sec-small-business-advisory-committee-discuss-ipo-modernization-regulation-crowdfunding); 2026-10-19 [SEC Announces Roundtable on Machine-Understandable Data in the Age of Super Intelligence](https://www.sec.gov/newsroom/press-releases/2026-106-sec-announces-roundtable-machine-understandable-data-age-super-intelligence); 2026-10-20 [SEC and AMF Announce Supervisory MOU To Enhance Cooperation for Investment Advisers and Investment Service Providers](https://www.sec.gov/newsroom/press-releases/2026-108-sec-amf-announce-supervisory-mou-enhance-cooperation-investment-advisers-investment-service); 2026-10-23 [SEC Announces Fiscal Year 2027 Examination Priorities](https://www.sec.gov/newsroom/press-releases/2026-109-sec-announces-fiscal-year-2027-examination-priorities); 2026-10-29 [Meta Platforms, Inc.: 8-K filed 2026-10-29](https://www.sec.gov/Archives/edgar/data/1326801/000119312526438017/d183592d8k.htm)
- **securities and exchange commission**: 2026-09-28 [SEC Charges Registered Investment Adviser Zoe Financial for Failure to Disclose Conflict of Interest](https://www.sec.gov/newsroom/press-releases/2026-94-sec-charges-registered-investment-adviser-zoe-financial-failure-disclose-conflict-interest); 2026-09-30 [SEC Charges Two Individuals With Orchestrating Fraud Scheme That Targeted Veterans](https://www.sec.gov/newsroom/press-releases/2026-97-sec-charges-two-individuals-orchestrating-fraud-scheme-targeted-veterans); 2026-10-06 [SEC to Host Virtual National Compliance Outreach Seminar for Investment Companies and Investment Advisers](https://www.sec.gov/newsroom/press-releases/2026-102-sec-host-virtual-national-compliance-outreach-seminar-investment-companies-investment-advisers); 2026-10-14 [SEC Small Business Advisory Committee to Discuss IPO Modernization and Regulation Crowdfunding](https://www.sec.gov/newsroom/press-releases/2026-105-sec-small-business-advisory-committee-discuss-ipo-modernization-regulation-crowdfunding); 2026-10-19 [SEC Announces Roundtable on Machine-Understandable Data in the Age of Super Intelligence](https://www.sec.gov/newsroom/press-releases/2026-106-sec-announces-roundtable-machine-understandable-data-age-super-intelligence); 2026-10-20 [SEC and AMF Announce Supervisory MOU To Enhance Cooperation for Investment Advisers and Investment Service Providers](https://www.sec.gov/newsroom/press-releases/2026-108-sec-amf-announce-supervisory-mou-enhance-cooperation-investment-advisers-investment-service); 2026-10-23 [SEC Announces Fiscal Year 2027 Examination Priorities](https://www.sec.gov/newsroom/press-releases/2026-109-sec-announces-fiscal-year-2027-examination-priorities)
- **si**: 2026-10-19 [SEC Announces Roundtable on Machine-Understandable Data in the Age of Super Intelligence](https://www.sec.gov/newsroom/press-releases/2026-106-sec-announces-roundtable-machine-understandable-data-age-super-intelligence); 2026-11-10 [SEC Announces Enforcement Annual Results for Fiscal Year 2026](https://www.sec.gov/newsroom/press-releases/2026-113-sec-announces-enforcement-annual-results-fiscal-year-2026)
- **super intelligence**: 2026-10-19 [SEC Announces Roundtable on Machine-Understandable Data in the Age of Super Intelligence](https://www.sec.gov/newsroom/press-releases/2026-106-sec-announces-roundtable-machine-understandable-data-age-super-intelligence); 2026-11-10 [SEC Announces Enforcement Annual Results for Fiscal Year 2026](https://www.sec.gov/newsroom/press-releases/2026-113-sec-announces-enforcement-annual-results-fiscal-year-2026)
- **the**: 2026-10-21 [Meta Platforms, Inc.: 8-K filed 2026-10-21](https://www.sec.gov/Archives/edgar/data/1326801/000162828026066700/meta-20261019.htm); 2026-10-29 [Meta Platforms, Inc.: 8-K filed 2026-10-29](https://www.sec.gov/Archives/edgar/data/1326801/000119312526438017/d183592d8k.htm)
- **williams**: 2026-09-23 [SEC Charges South Florida Resident and His Company for Alleged Investment Scheme Defrauding Law Enforcement](https://www.sec.gov/newsroom/press-releases/2026-92-sec-charges-south-florida-resident-his-company-alleged-investment-scheme-defrauding-law-enforcement); 2026-11-10 [NASA to Welcome Expedition 74 Astronauts Home at Space Center Houston](https://www.nasa.gov/news-release/nasa-to-welcome-expedition-74-astronauts-home-at-space-center-houston/)
- **xbox**: 2026-10-22 [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/); 2026-11-05 [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/)
- **xbox play anywhere**: 2026-10-22 [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/); 2026-11-05 [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/)
- **zoo 2**: 2026-10-22 [Cloud Deployment Incoming: ‘Call of Duty: Modern Warfare 4’ Arrives on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-call-of-duty-modern-warfare-4/); 2026-11-05 [‘Hogwarts Legacy’ Gets a Magical NVIDIA DLSS 5 Upgrade on GeForce NOW](https://blogs.nvidia.com/blog/geforce-now-thursday-hogwarts-legacy-dlss-5/)

## Reproduction and storage

```powershell
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
omni realdata collect --name real-v1 --since 2026-09-18 --until 2026-11-13
omni realdata verify --name real-v1
```

Collector reuses fetch_rss/fetch_api, isolated Intake and store_original, normalized SHA-256 + canonical URL, and SnapshotRecorder. Data, cached HTTP responses, all polled RawItems, and accepted replay JSONL remain under data/. Accepted snapshot is data/snapshots/real-v1.jsonl; all polled is real-v1-polled.jsonl. Intake queues only in data/real/real-v1/intake.db; no workers run. Production database is never opened. Later replay requires registering sources from the committed source list before using omni replay; no registration/ingestion is done here.

Cached requests make a rerun deterministic. Use a new corpus name/source file to collect a different window or refresh upstream content; the recorded window is immutable. Client: omnistream-research/0.1 (local academic project). At least 3 s between network requests per host, larger robots crawl-delay respected, and redirect destinations checked independently. Robots failures other than 404/410 deny access. Cache hits make no network requests. No login/paywall handling. All settings are constructed with _env_file=None; .env is never read.

## C1 findings and fixes


Initial reachability probes preceded the complete robots/terms review. Those probe responses are not corpus inputs unless separately fetched by the policy-enforcing collector. The collection client denies blocked sources and never uses the prohibited discovery responses as backfill.

- RSS empty markup content now falls back to a nonempty summary (regression tested).
- Official API HTML body fields now become readable clean text while original JSON is preserved (Europe PMC regression).
- Shared RSS/API HTML cleaner removes navigation, hidden blocks and script/style nodes (regression tested).
- Opt-in include_empty permits auditing empty-body feed records; default C1 behaviour remains to skip them.

## Next options before corpus approval

- Prefer additional feeds/APIs that explicitly publish complete licensed text, particularly earnings/filings. Obtain permission for restricted publishers rather than scraping their articles.
- For SEC, use an approved organisational client identity/access route if the generic research client is blocked; do not evade the block.
- Expand archive/API access under permitted source policies to improve source balance and date coverage; keep a separate corpus version.
- Manually validate Finance bubble labels, source-body completeness and actual changed facts; then freeze the approved corpus before any evaluation questions are authored.


## Recorded validation

See [validation output](real-v1-validation.md) for pasted test output and byte-identical recollection checks, and [corpus charts](real-v1-overview.html) for bubble/date counts.
