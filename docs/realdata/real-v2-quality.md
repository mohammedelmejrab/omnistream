# real-v2 corpus quality report

**HOLD — point 5 numeric verdict: HOLD**

Window: 2026-09-18 through 2026-11-13 inclusive UTC; verified 2026-11-13T01:09:42.057956+00:00.

## Headline results

- Accepted: 350; bubbles: {'research': 120, 'news': 115, 'finance': 115}.
- Words: {'min': 38, 'median': 564.5, 'p90': 2136.3, 'max': 75459}.
- Full/likely article text: 66.6%; complete abstracts: 29.1%; combined: 95.7%.
- Content classes: {'abstract': 102, 'full_text_likely': 107, 'full_text_fetched': 126, 'summary_or_unknown': 14, 'summary_or_truncated': 1}.
- LLM calls: 0; provider-reported cost $0.000000; token-priced cost $0.000000 at $0.15/$0.60 per million input/output tokens.
- Cross-bubble entity and alias statistics: NOT MEASURED for the complete corpus; LLM extraction is incomplete.
- Verified changed facts: 25; validation errors: [].

## Changes since real-v1

V1 remains unchanged. V2 drops NASA, NVIDIA teasers and biomedical abstracts; adds scoped documented-API access, on-theme arXiv queries, 24 EDGAR issuers including foreign 6-K, EX-99 exhibit documents, licensed/public-domain news candidates, content label flags and displayed event-date checks. arXiv query variants count as one publisher for the source cap. V2 replay and caches are isolated under data/real/real-v2/. No C3 routing, retrieval or answering changes.

## Requirements and limitations

- research: arxiv has 102/120 items, exceeding 25% source cap.
- LLM extraction missing for 350 items; overlap unavailable for these items.
- 30-item entity precision audit incomplete.

Abstracts are complete API abstracts, not full papers. Full-text-likely remains a proxy (400 words and three HTML paragraphs); fetched bodies use explicit source selectors and require at least 120 words to count as full-text depth; shorter retrieved landing pages/briefs remain unknown. Missing LLM extractions are not replaced with local NER estimates. Source hints remain provisional.

## Per-source accounting and text depth

| Source | Bubble | Accepted | Words min / median / p90 / max | Classes |
|---|---|---:|---|---|
| nvidia-blog | news | 26 | 277 / 940.0 / 1466.0 / 2139 | {'full_text_likely': 25, 'summary_or_unknown': 1} |
| microsoft-blog | news | 11 | 351 / 1145.0 / 2136.0 / 2824 | {'summary_or_truncated': 1, 'full_text_likely': 9, 'summary_or_unknown': 1} |
| samsung-news | news | 26 | 89 / 724.0 / 1309.0 / 1600 | {'full_text_likely': 20, 'summary_or_unknown': 6} |
| sec-releases | finance | 22 | 192 / 332.5 / 550.3000000000001 / 5501 | {'full_text_fetched': 22} |
| microsoft-research | research | 17 | 985 / 1505.0 / 6492.0 / 7668 | {'full_text_likely': 17} |
| bair-research | research | 1 | 2666 / 2666.0 / 2666.0 / 2666 | {'full_text_likely': 1} |
| federal-reserve | finance | 5 | 78 / 98.0 / 255.60000000000002 / 340 | {'summary_or_unknown': 3, 'full_text_fetched': 2} |
| ftc-news | news | 1 | 555 / 555.0 / 555.0 / 555 | {'full_text_fetched': 1} |
| doj-news | news | 2 | 466 / 791.0 / 1051.0 / 1116 | {'full_text_fetched': 2} |
| nist-news | news | 1 | 836 / 836.0 / 836.0 / 836 | {'full_text_fetched': 1} |
| eff-deeplinks | news | 26 | 232 / 770.0 / 1396.5 / 2538 | {'full_text_likely': 21, 'full_text_fetched': 5} |
| mozilla-blog | news | 16 | 311 / 799.5 / 1122.5 / 1380 | {'full_text_likely': 14, 'summary_or_unknown': 2} |
| uk-cma | news | 6 | 38 / 1378.5 / 2005.0 / 2121 | {'full_text_fetched': 5, 'summary_or_unknown': 1} |
| ec-press | news | 0 | 0 / 0 / 0 / 0 | {} |
| commerce-news | news | 0 | 0 / 0 / 0 / 0 | {} |
| wikinews | news | 0 | 0 / 0 / 0 / 0 | {} |
| conversation-tech | news | 0 | 0 / 0 / 0 / 0 | {} |
| edgar-nvidia | finance | 2 | 509 / 555.5 / 592.7 / 602 | {'full_text_fetched': 2} |
| edgar-microsoft | finance | 6 | 441 / 1129.5 / 13477.0 / 24102 | {'full_text_fetched': 6} |
| edgar-alphabet | finance | 3 | 860 / 1056.0 / 3207.2000000000003 / 3745 | {'full_text_fetched': 3} |
| edgar-amazon | finance | 3 | 352 / 639.0 / 4956.6 / 6036 | {'full_text_fetched': 3} |
| edgar-meta | finance | 5 | 1060 / 3245.0 / 3671.8 / 3687 | {'full_text_fetched': 5} |
| edgar-apple | finance | 3 | 559 / 1220.0 / 1506.4 / 1578 | {'full_text_fetched': 3} |
| edgar-amd | finance | 4 | 577 / 2211.5 / 4590.3 / 4950 | {'full_text_fetched': 4} |
| edgar-intel | finance | 2 | 631 / 3006.0 / 4906.0 / 5381 | {'full_text_fetched': 2} |
| edgar-ibm | finance | 5 | 272 / 908.0 / 2985.6000000000004 / 4068 | {'full_text_fetched': 5} |
| edgar-broadcom | finance | 1 | 796 / 796.0 / 796.0 / 796 | {'full_text_fetched': 1} |
| edgar-qualcomm | finance | 2 | 545 / 2476.5 / 4021.7000000000003 / 4408 | {'full_text_fetched': 2} |
| edgar-micron | finance | 4 | 471 / 531.5 / 2211.7000000000003 / 2926 | {'full_text_fetched': 4} |
| edgar-tsmc | finance | 8 | 228 / 721.0 / 811.4 / 845 | {'full_text_fetched': 8} |
| edgar-asml | finance | 4 | 335 / 1975.0 / 2950.5 / 3309 | {'full_text_fetched': 4} |
| edgar-oracle | finance | 3 | 552 / 950.0 / 1097.2 / 1134 | {'full_text_fetched': 3} |
| edgar-salesforce | finance | 3 | 575 / 768.0 / 1843.2 / 2112 | {'full_text_fetched': 3} |
| edgar-cisco | finance | 3 | 773 / 1522.0 / 4008.4 / 4630 | {'full_text_fetched': 3} |
| edgar-dell | finance | 1 | 579 / 579.0 / 579.0 / 579 | {'full_text_fetched': 1} |
| edgar-hpe | finance | 3 | 533 / 796.0 / 1029.6 / 1088 | {'full_text_fetched': 3} |
| edgar-arm | finance | 6 | 152 / 3750.0 / 50191.5 / 75459 | {'full_text_fetched': 6} |
| edgar-marvell | finance | 6 | 800 / 3090.0 / 4157.5 / 4741 | {'full_text_fetched': 6} |
| edgar-supermicro | finance | 6 | 577 / 756.5 / 2015.5 / 3130 | {'full_text_fetched': 6} |
| edgar-palantir | finance | 2 | 566 / 1983.5 / 3117.5 / 3401 | {'full_text_fetched': 2} |
| edgar-snowflake | finance | 3 | 1820 / 2673.0 / 3790.6 / 4070 | {'full_text_fetched': 3} |
| arxiv-general | research | 51 | 130 / 225.0 / 281.0 / 299 | {'abstract': 51} |
| arxiv-entities | research | 51 | 121 / 225.0 / 274.0 / 286 | {'abstract': 51} |
| bis-news | news | 0 | 0 / 0 / 0 / 0 | {} |

## Source permissions, access and failures

Case-insensitive word-boundary ANY keyword match on title plus clean body; government and open news sources carry explicit theme_keywords. Company/research/issuer sources are theme-scoped at selection. arXiv queries grouped as one source for concentration. Sources with theme_filter_before_fetch require the same keyword match in syndicated title/body before article retrieval. For prefer_complete_feed, full-text-likely RSS bodies are kept without a redundant page request. For NVIDIA, discovery covers the whole window before seeded selection of up to 26 items, prioritising weekly cloud release updates and the already-confirmed leadership anchor; no source is duplicated to evade balance limits. The one-year MSRA Singapore post identified by the supervisor in v1 is excluded by an explicit reviewed body-date override; this is a conservative corpus exclusion, not an inferred publication date. Direct review also excludes TSMC?s September 24 filing reporting only August month-end events (event-date override August 31), while September/October monthly revenue disclosures remain eligible.

Reviewed title/body metadata exclusions: {'https://arxiv.org/abs/2611.13578v1': 'Direct review: title says POEM/block-sparse prefilling while supplied abstract describes TERM/jailbreak defence. Excluded rather than guessing repaired metadata.'}

### nvidia-blog

- Terms: [https://www.nvidia.com/en-us/about-nvidia/legal-info/](https://www.nvidia.com/en-us/about-nvidia/legal-info/)
- Licence: NVIDIA terms 3.1: local personal noncommercial use. RSS is purposely made available; no article scraping under 3.2(f).
- Access: robots_checked; policy: feed_only. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'too_short': 2, 'bubble_target': 47, 'before_window': 15}

### microsoft-blog

- Terms: [https://www.microsoft.com/en-us/legal/terms-of-use](https://www.microsoft.com/en-us/legal/terms-of-use)
- Licence: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised.
- Access: robots_checked; policy: feed_only. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'event_before_window': 19}

### samsung-news

- Terms: [https://news.samsung.com/global/terms](https://news.samsung.com/global/terms)
- Licence: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised.
- Access: robots_checked; policy: feed_only. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'source_cap': 24}

### sec-releases

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: SEC staff authored press-release text is US government public-domain material (17 USC 105); third-party material excepted. Public-domain article-body retrieval opted in, robots checked per request.
- Access: robots_checked; policy: fetch_public_domain. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'source_cap': 3}

### microsoft-research

- Terms: [https://www.microsoft.com/en-us/legal/terms-of-use](https://www.microsoft.com/en-us/legal/terms-of-use)
- Licence: Publisher copyright; intentionally syndicated RSS only; private local research; redistribution not authorised.
- Access: robots_checked; policy: feed_only. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'event_before_window': 1, 'before_window': 12}

### bair-research

- Terms: [https://bair.berkeley.edu/blog/](https://bair.berkeley.edu/blog/)
- Licence: BAIR blog copyright; full text intentionally syndicated in RSS; per-post licence not assumed; private local research only.
- Access: robots_checked; policy: feed_only. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'event_before_window': 9}

### federal-reserve

- Terms: [https://www.federalreserve.gov/disclaimer.htm](https://www.federalreserve.gov/disclaimer.htm)
- Licence: US federal agency authored text is generally public domain (17 USC 105); third-party material excepted. Fetch public press release body only with robots permission.
- Access: robots_checked; policy: fetch_public_domain. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'source_cap': 15}

### ftc-news

- Terms: [https://www.ftc.gov/site-information/website-policy](https://www.ftc.gov/site-information/website-policy)
- Licence: US government authored prose: public domain; third-party material excluded.
- Access: robots_checked; policy: fetch_open_licence. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'off_theme': 9}

### doj-news

- Terms: [https://www.justice.gov/legalpolicies](https://www.justice.gov/legalpolicies)
- Licence: DOJ prose public domain unless otherwise indicated; attribution retained.
- Access: robots_checked; policy: fetch_open_licence. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'off_theme': 22, 'before_window': 1}

### nist-news

- Terms: [https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications](https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications)
- Licence: NIST authored works generally public domain; exclude standard reference data and third-party works.
- Access: robots_checked; policy: fetch_open_licence. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'off_theme': 30, 'before_window': 1, 'event_before_window': 8}

### eff-deeplinks

- Terms: [https://www.eff.org/copyright](https://www.eff.org/copyright)
- Licence: EFF original prose CC BY 4.0 International unless otherwise stated; third-party material excepted.
- Access: robots_checked; policy: fetch_open_licence. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'off_theme': 4, 'source_cap': 20}

### mozilla-blog

- Terms: [https://www.mozilla.org/en-US/foundation/licensing/website-content/](https://www.mozilla.org/en-US/foundation/licensing/website-content/)
- Licence: Mozilla prose CC BY-SA 3.0 or later unless otherwise indicated.
- Access: robots_checked; policy: fetch_open_licence. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: ["article https://blog.mozilla.org/en/mozilla/ai/trustworthy-ai-map/: HTTPStatusError: Client error '403 Forbidden' for url 'https://blog.mozilla.org/en/mozilla/ai/trustworthy-ai-map/'\nFor more information check: https://developer.mozill", "article https://blog.mozilla.org/en/mozilla/palaniappan-parry-jones/: HTTPStatusError: Client error '403 Forbidden' for url 'https://blog.mozilla.org/en/mozilla/palaniappan-parry-jones/'\nFor more information check: https://developer.mozi"]
- Rejections: {'off_theme': 2, 'before_window': 2}

### uk-cma

- Terms: [https://www.gov.uk/help/reuse-govuk-content](https://www.gov.uk/help/reuse-govuk-content)
- Licence: Crown copyright Open Government Licence v3; attribution retained.
- Access: robots_checked; policy: fetch_open_licence. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'off_theme': 14}

### ec-press

- Terms: [https://commission.europa.eu/legal-notice_en](https://commission.europa.eu/legal-notice_en)
- Licence: European Commission reuse with attribution, CC BY 4.0 unless otherwise indicated.
- Access: robots_checked; policy: fetch_open_licence. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'off_theme': 10}

### commerce-news

- Terms: [https://www.commerce.gov/about/policies](https://www.commerce.gov/about/policies)
- Licence: US federal prose; terms endpoint returned 403; excluded pending verifiable access.
- Access: robots_checked; policy: feed_only. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: ['US federal prose; terms endpoint returned 403; excluded pending verifiable access.']
- Rejections: {}

### wikinews

- Terms: [https://en.wikinews.org/wiki/Wikinews:Copyright](https://en.wikinews.org/wiki/Wikinews:Copyright)
- Licence: Wikinews text after 2024-12-16 is CC BY 4.0; attribution to Wikinews retained. Third-party fair-use content excluded.
- Access: robots_checked; policy: fetch_open_licence. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: ['PermissionError: robots disallows or unavailable: https://en.wikinews.org/w/index.php?title=Special:NewsFeed&feed=rss&categories=Science_and_technology&notcategories=Disputed&namespace=0&count=100']
- Rejections: {}

### conversation-tech

- Terms: [https://theconversation.com/republishing-guidelines](https://theconversation.com/republishing-guidelines)
- Licence: Republishing policy could not be retrieved; no full article access enabled.
- Access: robots_checked; policy: feed_only. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: ['Republishing policy could not be retrieved; no full article access enabled.']
- Rejections: {}

### edgar-nvidia

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-microsoft

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-alphabet

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-amazon

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-meta

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-apple

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-amd

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-intel

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-ibm

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-broadcom

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-qualcomm

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-micron

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-tsmc

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'event_before_window': 1}

### edgar-asml

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-oracle

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-salesforce

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-cisco

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-dell

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-hpe

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-arm

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-marvell

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'source_cap': 3}

### edgar-supermicro

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-palantir

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### edgar-snowflake

- Terms: [https://www.sec.gov/about/developer-resources](https://www.sec.gov/about/developer-resources)
- Licence: Public EDGAR filing access under SEC fair-access policy; issuer text may be copyrighted; private research only. Generic declared research User-Agent, one request per 3 seconds per host.
- Access: documented_api; policy: fetch_public_filing. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {}

### arxiv-general

- Terms: [https://info.arxiv.org/help/api/tou.html](https://info.arxiv.org/help/api/tou.html)
- Licence: arXiv descriptive metadata CC0 1.0; abstracts retained as abstracts, not full papers. API research use allowed, minimum 3 seconds.
- Access: documented_api; policy: abstract. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'abstract_too_short': 1, 'bubble_target': 4, 'source_cap': 124}

### arxiv-entities

- Terms: [https://info.arxiv.org/help/api/tou.html](https://info.arxiv.org/help/api/tou.html)
- Licence: arXiv descriptive metadata CC0 1.0; abstracts retained as abstracts, not full papers. API research use allowed, minimum 3 seconds.
- Access: documented_api; policy: abstract. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: none
- Rejections: {'duplicate': 5, 'bubble_target': 14, 'abstract_too_short': 1, 'reviewed_source_metadata_mismatch': 1, 'source_cap': 108}

### bis-news

- Terms: [https://www.bis.gov/website-policies](https://www.bis.gov/website-policies)
- Licence: US federal authored prose generally public domain; actual site policy could not be retrieved; excluded.
- Access: robots_checked; policy: feed_only. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.
- Failures/exclusions: ['Policy endpoint inaccessible; no permission-qualified feed established.']
- Rejections: {}

## Dates, language and cleanliness

Languages: {'en': 350}. Heuristic cleanliness flags: {'javascript': 11, 'table_or_code': 3, 'very_long': 3}. Date histogram is recorded in quality JSON. All accepted publication dates and reviewed event hints passed the inclusive UTC window checks.

## Duplicate audit

Exact duplicate clusters: 0; canonical URL revision clusters: 0. Near-duplicate details in quality JSON. Integrity errors: [].

Feed/API publication date is preserved. A displayed leading body date or dated URL becomes event_date_hint; month-only URLs use the last day as a conservative upper bound. Older-than-window content is rejected. Historical dates mentioned in prose are not assumed to be event dates. label_basis=source_hint is explicit; content_bubbles supplies transparent keyword review flags, not gold labels.

## Cross-bubble entity suitability

Extraction: project omnistream.llm JSON mode, cached per item; exact-surface validation. Missing items: 350. Canonical identity is model-proposed; only verbatim observed aliases survive. Multiple surface forms ignore case-only variants; this is a suitability statistic, not production entity resolution.

30-item audit: 30-item text prefix/ending review complete; LLM entity precision audit BLOCKED: credentials unavailable (private request timed out); precision: None.

| Canonical entity | News | Finance | Research | Observed surfaces |
|---|---:|---:|---:|---|

## Changed facts

Fact entity distribution: {'NVIDIA': 1, 'Samsung Electronics': 2, 'World of Warcraft: Forever': 1, 'TSMC': 11, 'TSMC Development': 2, 'TSMC China': 3, 'TSMC Nanjing': 3, 'TSMC Global': 2}. Twenty-one of the 25 reviewed facts come from the two TSMC monthly disclosures, so this satisfies a count of distinct changed financial attributes, not 25 independent event narratives.

25 directly reviewed records in src/omnistream/eval/real/real-v2-changed-facts.json. Each record requires old/new values, increasing publication dates, accepted item IDs and verbatim evidence quotes <=15 words per side. Validation confirms references and quotation presence; it cannot establish semantic supersession by itself. Signals are not promoted to verified facts.

## Reproduction and storage

```powershell
.venv/Scripts/omni.exe realdata collect --name real-v2
.venv/Scripts/python.exe -m omnistream.eval.real.entities_v2 --name real-v2
.venv/Scripts/omni.exe realdata verify --name real-v2
```

Use process environment credentials or the extraction command’s --secret-file private path; settings always use _env_file=None. Never read .env. Texts, HTTP payloads, intake database and replay snapshots remain under data/real/real-v2/. Metadata-only committed manifest, entities, sample and report carry no article bodies. Exhibits are separate items with the same accession and different document names. No production DB, graph or old snapshots opened or modified.

## C1 findings and fixes

No retrieval/answering changes. Collection-specific helpers implement endpoint policy, filing index exhibit discovery, arXiv query escaping and fact-reference validation; local fixtures cover them.

## Next options before corpus approval

Run the cached LLM pass with privately supplied OpenRouter credentials, then directly check entity precision for the fixed 30-item sample. Research needs more independent publishers to meet the strict 25% source cap; query/category partitions of arXiv cannot solve that requirement. No corpus approval or benchmark question writing should proceed while these gates fail.

## Recorded validation

See real-v2-validation.md for exact command output.

## Final verdict

HOLD
