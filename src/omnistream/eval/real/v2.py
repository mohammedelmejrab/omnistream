"""Round-two policy and metadata helpers. No production retrieval dependencies."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

# Endpoint scope is deliberately code-reviewed rather than caller-controlled.
API_SCOPES = {
    "export.arxiv.org": (r"/api/query", "https://info.arxiv.org/help/api/tou.html"),
    "data.sec.gov": (
        r"/submissions/CIK\d+\.json",
        "https://www.sec.gov/about/developer-resources",
    ),
    "www.sec.gov": (
        r"/Archives/edgar/data/\d+/\d+/[^/]+",
        "https://www.sec.gov/about/developer-resources",
    ),
    "www.ebi.ac.uk": (
        r"/europepmc/webservices/rest/.*",
        "https://europepmc.org/RestfulWebService",
    ),
    "www.federalregister.gov": (
        r"/api/v1/.*",
        "https://www.federalregister.gov/developers/documentation/api/v1",
    ),
    "api.govinfo.gov": (r"/.*", "https://www.govinfo.gov/developers/api"),
}


def documented_api_allows(policy, url):
    if not policy or policy.get("access") != "documented_api":
        return False
    parts = urlsplit(url)
    scope = API_SCOPES.get(parts.hostname)
    return bool(
        parts.scheme == "https"
        and parts.port in (None, 443)
        and not parts.username
        and scope
        and policy.get("terms_url") == scope[1]
        and re.fullmatch(scope[0], parts.path)
    )


def arxiv_query(
    since,
    until,
    *,
    categories=("cs.AI", "cs.LG", "cs.CL", "cs.AR", "cs.DC"),
    names=(),
    start=0,
    limit=100,
):
    datetime.strptime(since, "%Y-%m-%d")
    datetime.strptime(until, "%Y-%m-%d")
    if since > until or not 1 <= limit <= 2000 or start < 0:
        raise ValueError("invalid arXiv range")
    if any(not re.fullmatch(r"cs\.[A-Z]{2}", c) for c in categories):
        raise ValueError("invalid category")
    query = "(" + " OR ".join("cat:" + c for c in categories) + ")"
    query += f" AND submittedDate:[{since.replace('-', '')}0000 TO {until.replace('-', '')}2359]"
    if names:
        if any(not re.fullmatch(r"[\w .-]+", n) for n in names):
            raise ValueError("invalid search name")
        query += " AND (" + " OR ".join(f'all:"{n}"' for n in names) + ")"
    return "https://export.arxiv.org/api/query?" + urlencode(
        {
            "search_query": query,
            "start": start,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )


def exhibit_links(html, filing_url):
    """Use the official filing index's document type, never filename guesses."""
    base = filing_url.rsplit("/", 1)[0] + "/"
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for row in soup.select("tr"):
        cells = row.find_all("td")
        if not any(
            re.fullmatch(r"EX-99(?:\.\d+)?", c.get_text(strip=True), re.IGNORECASE)
            for c in cells
        ):
            continue
        for link in row.select("a[href]"):
            url = urljoin(base, link["href"])
            parsed = urlsplit(url)
            if parsed.hostname == "www.sec.gov" and parsed.path in {
                "/ix",
                "/ixviewer/doc/action",
            }:
                document = parse_qs(parsed.query).get("doc", [""])[0]
                if document.startswith("/Archives/edgar/data/"):
                    url = urljoin("https://www.sec.gov", document)
            if url.startswith(base) and urlsplit(url).path.lower().endswith(
                (".htm", ".html", ".txt")
            ):
                result.append(url)
    return list(dict.fromkeys(result))


async def expand_exhibits(items, http, errors):
    expanded = []
    for item in items:
        expanded.append(item)
        accession = item.url.split("/")[-2]
        dashed = accession[:10] + "-" + accession[10:12] + "-" + accession[12:]
        index = item.url.rsplit("/", 1)[0] + "/" + dashed + "-index.html"
        try:
            response = await http.get(index)
            response.raise_for_status()
            for url in exhibit_links(response.text, item.url):
                expanded.append(
                    item.model_copy(
                        update={
                            "url": url,
                            "title": item.title + ": exhibit " + url.rsplit("/", 1)[-1],
                        }
                    )
                )
        except (httpx.HTTPError, PermissionError, ValueError, OSError) as exc:
            errors.append(
                f"exhibit index {index}: {type(exc).__name__}: {str(exc)[:120]}"
            )
    return expanded


def theme_matches(text, cfg):
    keywords = cfg.get("theme_keywords", [])
    return not keywords or any(
        re.search(r"\b" + re.escape(k) + r"\b", text, re.IGNORECASE) for k in keywords
    )


def body_date_hint(text):
    # A displayed date at the start, not an arbitrary historical date in prose.
    match = re.match(
        r"^\s*(?:Published\s*:?\s*)?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2})\b",
        text,
    )
    if match:
        try:
            return datetime.strptime(match[1], "%B %d, %Y").date().isoformat()
        except ValueError:
            pass
    return None


def content_labels(text):
    patterns = {
        "finance": r"\b(earnings|quarterly results|revenue|guidance|8-K|6-K|fiscal)\b",
        "research": r"\b(abstract|researchers|benchmark|arXiv|training algorithm)\b",
        "news": r"\b(announc\w*|launch\w*|introduc\w*|regulat\w*)\b",
    }
    return [
        label
        for label, pattern in patterns.items()
        if re.search(pattern, text, re.IGNORECASE)
    ]


def validate_changed_facts(facts, rows, texts):
    """Validate references and short evidence; direct review establishes semantics."""
    by_id = {r["id"]: r for r in rows}
    errors = []
    if not isinstance(facts, list):
        return ["changed facts must be a JSON array"]
    for i, fact in enumerate(facts):
        if not isinstance(fact, dict) or any(
            not isinstance(fact.get(side), dict) for side in ("old", "new")
        ):
            errors.append(f"{i}: malformed fact record")
            continue
        if not isinstance(fact.get("note"), str) or not fact.get("note"):
            errors.append(f"{i}: missing one-line verification note")
        if (
            not isinstance(fact.get("entity"), str)
            or not fact.get("entity")
            or not isinstance(fact.get("attribute"), str)
            or not fact.get("attribute")
            or fact.get("verified") is not True
        ):
            errors.append(f"{i}: missing entity/attribute/explicit verification")
        for side in ("old", "new"):
            evidence = fact.get(side, {})
            row = by_id.get(evidence.get("item_id"))
            quote = evidence.get("quote", "")
            if not row or evidence.get("date") != row["published_at"][:10]:
                errors.append(f"{i}: invalid {side} reference/date")
            if (
                not isinstance(evidence.get("value"), str)
                or not isinstance(quote, str)
                or not evidence.get("value")
                or not quote
                or len(quote.split()) > 15
            ):
                errors.append(f"{i}: invalid {side} value/quote")
            elif row and quote not in texts[row["id"]]:
                errors.append(f"{i}: {side} quote absent from original")
        old_date, new_date = fact["old"].get("date"), fact["new"].get("date")
        if (
            not isinstance(old_date, str)
            or not isinstance(new_date, str)
            or old_date >= new_date
        ):
            errors.append(f"{i}: dates not increasing")
        if fact.get("old", {}).get("value") == fact.get("new", {}).get("value"):
            errors.append(f"{i}: unchanged value")
    return errors


def url_date_hint(url):
    """Dated article URLs provide a conservative latest date for a month."""
    import calendar

    match = re.search(r"/(20\d{2})/(\d{2})(?:/(\d{2}))?(?:/|$)", urlsplit(url).path)
    if not match:
        return None
    try:
        year, month = int(match[1]), int(match[2])
        day = int(match[3]) if match[3] else calendar.monthrange(year, month)[1]
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def select_balanced(rows, targets, source_limits=None, priority_title_keywords=None):
    """Round-robin sources with seeded date-spread sampling, no invented items."""
    import random
    from collections import defaultdict

    selected = []
    source_limits = source_limits or {}
    priority_title_keywords = priority_title_keywords or {}
    for bubble, target in targets.items():
        pools = defaultdict(list)
        for row in sorted(
            rows, key=lambda r: (r["source"], r["published_at"], r["id"])
        ):
            if row["bubble_hint"] == bubble:
                pools[row["source"]].append(row)
        rng = random.Random(20261113)
        for source, pool in pools.items():
            rng.shuffle(pool)
            keywords = priority_title_keywords.get(source, [])
            pool.sort(
                key=lambda r: any(
                    k.casefold() in r.get("title", "").casefold() for k in keywords
                )
            )
            if source in source_limits:
                pools[source] = pool[-source_limits[source] :]
        n = 0
        while n < target and any(pools.values()):
            for source in sorted(pools):
                if pools[source] and n < target:
                    selected.append(pools[source].pop())
                    n += 1
    return sorted(selected, key=lambda r: (r["source"], r["published_at"], r["id"]))
