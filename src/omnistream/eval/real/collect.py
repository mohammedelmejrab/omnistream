"""Collect through C1 into an isolated C2 intake store; never touch the graph.

HTTP payloads and clean originals stay under data/. The committed manifest has
metadata only. Cached responses make repeated collection reproducible/offline.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from langdetect import DetectorFactory, LangDetectException, detect_langs

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.ingest.intake import Intake
from omnistream.ingest.normalize import content_hash, normalize_text
from omnistream.models import Source
from omnistream.sources import SourceFetchError
from omnistream.sources.api import fetch_api
from omnistream.sources.replay import SnapshotRecorder, load_snapshot, snapshot_path
from omnistream.sources.rss import fetch_rss

UA = "omnistream-research/0.1 (local academic project)"
PACKAGE = Path(__file__).resolve().parent
DetectorFactory.seed = 20261113


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def read_jsonl(path: Path) -> list[dict]:
    return (
        [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s]
        if path.exists()
        else []
    )


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def corpus_paths(name: str, root: Path = Path(".")) -> tuple[Path, Path, Path]:
    if not re.fullmatch(r"real-[a-zA-Z0-9][a-zA-Z0-9_-]*", name):
        raise ValueError(
            "corpus name must start real- and contain only letters, numbers, _ or -"
        )
    return (
        root / "data" / "real" / name,
        root / "src/omnistream/eval/real" / f"{name}-manifest.jsonl",
        root / "docs/realdata",
    )


def language(text: str) -> tuple[str, float]:
    try:
        result = detect_langs(text[:12000])[0]
        return result.lang, round(result.prob, 4)
    except LangDetectException:
        return "unknown", 0.0


def clean_html(raw: str) -> str:
    soup = BeautifulSoup(f"<div>{raw}</div>", "html.parser")
    for node in soup.select(
        "script,style,nav,footer,header,form,noscript,svg,[hidden]"
    ):
        node.decompose()
    for node in soup.find_all(["ix:header", "ix:hidden"]):
        node.decompose()
    for node in soup.select('[style*="display:none"],[style*="display: none"]'):
        node.decompose()
    return " ".join(soup.get_text(" ").split())


def content_kind(text: str, policy: str, raw: str = "") -> str:
    if policy == "abstract":
        return "abstract"
    if re.search(
        r"\[\s*\.\.\.\s*\]|Ã¢â‚¬Â¦\s*$|\.\.\.\s*$|read more|continue reading",
        text,
        re.IGNORECASE,
    ):
        return "summary_or_truncated"
    # Feed content is not evidence of completeness. Conservative proxy only.
    if len(text.split()) >= 400 and len(re.findall(r"<p\b", raw, re.IGNORECASE)) >= 3:
        return "full_text_likely"
    return "summary_or_unknown"


def rejection(item, since: date, until: date, *, lang: str) -> str | None:
    if len(item.text.strip()) < 200:
        return "too_short"
    if item.published_at is None:
        return "no_date"
    day = item.published_at.astimezone(UTC).date()
    if day > until or item.published_at > datetime.now(UTC) + timedelta(hours=1):
        return "future_or_after_window"
    if day < since:
        return "before_window"
    if lang not in ("en", "unknown"):
        return "non_english"
    if lang == "unknown":
        return "language_unknown"
    if re.search(
        r"access denied|enable javascript.*continue|just a moment|verify you are human",
        item.text,
        re.IGNORECASE,
    ):
        return "boilerplate"
    return None


class PublicHTTP:
    """Fail-closed robots checks, per-host delay, bounded response cache.

    Redirects are followed manually so permission and delay apply to EACH host.
    robots 404/410 means absent; other failures mean deny. No cookie/login flow.
    """

    def __init__(
        self, folder: Path, *, transport=None, sleep=asyncio.sleep, clock=time.monotonic
    ):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient(
            headers={"User-Agent": UA}, transport=transport, follow_redirects=False
        )
        self.sleep, self.clock = sleep, clock
        self.last: dict[str, float] = {}
        self.robots: dict[str, RobotFileParser | None] = {}
        self.events: list[dict] = []

    async def close(self):
        await self.client.aclose()

    async def _wire(self, url: str, delay: float) -> httpx.Response:
        host = urlsplit(url).netloc
        wait = max(0, self.last.get(host, -1e10) + max(3, delay) - self.clock())
        if wait:
            await self.sleep(wait)
        self.last[host] = self.clock()
        response = await self.client.get(url, timeout=30)
        self.events.append(
            {
                "url": url,
                "status": response.status_code,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        return response

    async def _robots(self, url: str, delay: float):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            cache = self.folder / (
                hashlib.sha256((origin + "/robots.txt").encode()).hexdigest() + ".json"
            )
            if cache.exists():
                d = json.loads(cache.read_text(encoding="utf8"))
                status, body = d["status"], d["body"]
            else:
                response = await self._wire(origin + "/robots.txt", delay)
                status, body = response.status_code, response.text
                write_json(
                    cache,
                    {"url": origin + "/robots.txt", "status": status, "body": body},
                )
            parser = RobotFileParser()
            if status in (404, 410):
                parser.parse([])
            elif status == 200:
                parser.parse(body.splitlines())
            else:
                parser = None
            self.robots[origin] = parser
        parser = self.robots[origin]
        if parser is None or not parser.can_fetch(UA, url):
            raise PermissionError(f"robots disallows or unavailable: {url}")
        return max(delay, parser.crawl_delay(UA) or parser.crawl_delay("*") or 0)

    async def get(
        self, url: str, *, delay: float = 3, allowed_hosts=None, **_kwargs
    ) -> httpx.Response:
        for _ in range(6):
            if (
                allowed_hosts is not None
                and urlsplit(url).hostname not in allowed_hosts
            ):
                raise PermissionError("redirect leaves opted-in article hosts")
            delay = await self._robots(url, delay)
            cache = self.folder / (hashlib.sha256(url.encode()).hexdigest() + ".json")
            if cache.exists():
                d = json.loads(cache.read_text(encoding="utf8"))
                import base64

                body = (
                    base64.b64decode(d["body_b64"])
                    if "body_b64" in d
                    else d["body"].encode("utf8")
                )
                r = httpx.Response(
                    d["status"],
                    content=body,
                    headers={
                        k: v
                        for k, v in d.get("headers", {}).items()
                        if k.lower() not in {"content-encoding", "content-length"}
                    },
                    request=httpx.Request("GET", url),
                )
            else:
                r = await self._wire(url, delay)
                # Preserve bytes exactly rather than round-trip an incorrect charset.
                import base64

                write_json(
                    cache,
                    {
                        "url": url,
                        "status": r.status_code,
                        "body_b64": base64.b64encode(r.content).decode(),
                        "headers": dict(r.headers),
                        "at": datetime.now(UTC).isoformat(),
                    },
                )
            if cache.exists() and "body_b64" in (
                d := json.loads(cache.read_text(encoding="utf8"))
            ):
                import base64

                r = httpx.Response(
                    d["status"],
                    content=base64.b64decode(d["body_b64"]),
                    headers={
                        k: v
                        for k, v in d.get("headers", {}).items()
                        if k.lower() not in {"content-encoding", "content-length"}
                    },
                    request=httpx.Request("GET", url),
                )
            if r.is_redirect:
                from urllib.parse import urljoin

                url = urljoin(url, r.headers["location"])
                continue
            r.raise_for_status()
            return r
        raise ValueError("too many redirects")


class SourceHTTP:
    def __init__(self, http: PublicHTTP, delay: float):
        self.http, self.delay = http, delay

    async def get(self, url, **kwargs):
        return await self.http.get(url, delay=self.delay, **kwargs)


class SECSubmissionHTTP(SourceHTTP):
    """Adapt EDGAR's parallel arrays for the existing C1 JSONPath reader.

    Untouched official JSON stays in PublicHTTP's cache. Only public material
    event 8-K filings in the requested window become collection candidates.
    """

    def __init__(self, http, delay, since, until):
        super().__init__(http, delay)
        self.since, self.until = since, until

    async def get(self, url, **kwargs):
        response = await super().get(url, **kwargs)
        payload = response.json()
        columns = payload["filings"]["recent"]
        required = ["accessionNumber", "filingDate", "form", "primaryDocument"]
        if len({len(columns[k]) for k in required}) != 1:
            raise ValueError("SEC submission columns have inconsistent lengths")
        entries = []
        for i, day in enumerate(columns["filingDate"]):
            if (
                columns["form"][i] not in {"8-K", "8-K/A"}
                or not self.since <= day <= self.until
            ):
                continue
            accession = columns["accessionNumber"][i].replace("-", "")
            title = f"{payload['name']}: {columns['form'][i]} filed {day}"
            entries.append(
                {
                    "title": title,
                    "body": title,
                    "date": day,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(payload['cik'])}/{accession}/{columns['primaryDocument'][i]}",
                }
            )
        return httpx.Response(200, json={"items": entries}, request=response.request)


async def collect(
    name: str,
    since: str | None = None,
    until: str | None = None,
    *,
    root: Path = Path("."),
    source_file: Path | None = None,
) -> dict:
    folder, manifest_path, _ = corpus_paths(name, root)
    source_file = source_file or PACKAGE / f"sources-{name}.json"
    config = json.loads(source_file.read_text(encoding="utf8"))
    lower, upper = (
        date.fromisoformat(since or config["since"]),
        date.fromisoformat(until or config["until"]),
    )
    if lower > upper:
        raise ValueError("since must be <= until")
    folder.mkdir(parents=True, exist_ok=True)
    old_run = folder / "collection.json"
    if old_run.exists():
        old = json.loads(old_run.read_text(encoding="utf8"))
        if old["since"] != lower.isoformat() or old["until"] != upper.isoformat():
            raise ValueError("A recorded corpus window is immutable; use a new name")
    settings = Settings(_env_file=None, data_dir=str(folder))
    repo = Repository.from_path(str(folder / "intake.db"), settings=settings)
    intake = Intake(repo, str(folder), 200)
    http = PublicHTTP(folder / "http")
    previous = read_jsonl(manifest_path)
    accepted = {r["id"]: r for r in previous}
    previous_ids = set(accepted)
    # A second run re-verifies cached candidates without adding duplicate rows.
    seen: set[str] = set()
    exact: set[str] = set()
    outcomes, statuses, raw_items = [], [], []
    accepted_raw = {}
    if snapshot_path(root / "data", name).exists():
        accepted_raw = {
            content_hash(item.url, item.text): item
            for item in load_snapshot(root / "data", name)
            if content_hash(item.url, item.text) in accepted
        }
    counts = Counter()
    try:
        for cfg in config["sources"]:
            sid = cfg["id"]
            status = {
                "source": sid,
                "enabled": cfg["enabled"],
                "errors": [],
                "pages": 0,
                "polled": 0,
            }
            statuses.append(status)
            if not cfg["enabled"]:
                status["errors"].append(cfg["disabled_reason"])
                continue
            source_count = 0
            for page in range(1, cfg.get("pages", 1) + 1):
                url = cfg["url"].format(
                    since=lower.isoformat(),
                    until=upper.isoformat(),
                    since_compact=lower.strftime("%Y%m%d"),
                    until_compact=upper.strftime("%Y%m%d"),
                )
                if page > 1:
                    url += ("&" if "?" in url else "?") + f"paged={page}"
                source = Source(
                    id=sid,
                    type=cfg["type"],
                    url=url,
                    credibility=cfg["credibility"],
                    bubble_ids=[cfg["bubble_hint"]],
                    max_items_per_hour=10000,
                    api_mapping=cfg.get("api_mapping"),
                )
                client = SourceHTTP(
                    http, cfg.get("delay_override", cfg.get("delay_seconds", 3))
                )
                if cfg.get("adapter") == "sec_submissions":
                    client = SECSubmissionHTTP(
                        http,
                        cfg.get("delay_seconds", 3),
                        lower.isoformat(),
                        upper.isoformat(),
                    )
                try:
                    items = await (
                        fetch_rss(source, client, include_empty=True)
                        if source.type == "rss"
                        else fetch_api(source, client)
                    )
                    status["pages"] += 1
                except (
                    httpx.HTTPError,
                    PermissionError,
                    ValueError,
                    OSError,
                    SourceFetchError,
                ) as exc:
                    status["errors"].append(f"{type(exc).__name__}: {str(exc)[:250]}")
                    break
                status["polled"] += len(items)
                if not items:
                    break
                all_old = True
                for item in items:
                    item.bubble_ids_override = [cfg["bubble_hint"]]
                    raw_items.append(item.model_copy(deep=True))
                    # Content-only C1 leaves the raw payload intact; remove scripts/nav.
                    if item.raw_ext == "html" and item.raw_content:
                        item.text = clean_html(item.raw_content)
                    if item.published_at and item.published_at.date() >= lower:
                        all_old = False
                    lang, confidence = (
                        language(item.text) if len(item.text) >= 200 else ("unknown", 0)
                    )
                    reason = rejection(item, lower, upper, lang=lang)
                    fetched_article = False
                    # An explicit public-domain opt-in, never a general web scraper.
                    if cfg["full_text_policy"] in {
                        "fetch_public_domain",
                        "fetch_public_filing",
                    } and reason not in (
                        "no_date",
                        "future_or_after_window",
                        "before_window",
                    ):
                        try:
                            if urlsplit(item.url).hostname not in cfg.get(
                                "article_hosts", [urlsplit(url).hostname]
                            ):
                                raise PermissionError(
                                    "article must stay on explicitly opted-in source host"
                                )
                            response = await http.get(
                                item.url,
                                delay=cfg.get("delay_seconds", 3),
                                allowed_hosts=cfg.get(
                                    "article_hosts", [urlsplit(url).hostname]
                                ),
                            )
                            soup = BeautifulSoup(response.content, "html.parser")
                            body = next(
                                (
                                    soup.select_one(s)
                                    for s in cfg["article_selectors"]
                                    if soup.select_one(s)
                                ),
                                None,
                            )
                            if body is None:
                                raise ValueError(
                                    "no opted-in article body selector matched"
                                )
                            item.raw_content, item.raw_ext = str(body), "html"
                            item.text = clean_html(str(body))
                            lang, confidence = language(item.text)
                            reason = rejection(item, lower, upper, lang=lang)
                            fetched_article = True
                        except (
                            httpx.HTTPError,
                            PermissionError,
                            ValueError,
                            OSError,
                        ) as exc:
                            status["errors"].append(
                                f"article {item.url}: {type(exc).__name__}: {str(exc)[:150]}"
                            )
                    key = content_hash(item.url, item.text)
                    digest = hashlib.sha256(item.text.encode()).hexdigest()
                    norm_digest = hashlib.sha256(
                        normalize_text(item.text).encode()
                    ).hexdigest()
                    if key in seen or norm_digest in exact:
                        reason = "duplicate"
                    seen.add(key)
                    if reason is None and source_count >= cfg["max_items"]:
                        reason = "source_cap"
                    outcome = {
                        "id": key,
                        "source": sid,
                        "url": item.url,
                        "published_at": item.published_at.isoformat()
                        if item.published_at
                        else None,
                        "reason": reason or "accepted",
                        "language": lang,
                        "language_confidence": confidence,
                    }
                    outcomes.append(outcome)
                    if reason:
                        counts[reason] += 1
                        # Let the real C2 prefilter record short/no-date candidates too.
                        if reason in ("too_short", "no_date"):
                            await intake.accept(
                                item,
                                source,
                                (item.raw_content or item.text).encode(),
                                item.raw_ext,
                            )
                        continue
                    exact.add(norm_digest)
                    raw = (item.raw_content or item.text).encode()
                    row = await intake.accept(item, source, raw, item.raw_ext)
                    if row is None and key not in previous_ids:
                        outcome["reason"] = "intake_rejected"
                        counts["intake_rejected"] += 1
                        continue
                    if row is None:
                        record = dict(accepted[key])
                        record["bubble_hint"] = cfg["bubble_hint"]
                    else:
                        record = {
                            "id": key,
                            "source": sid,
                            "url": item.url,
                            "title": item.title,
                            "published_at": item.published_at.astimezone(
                                UTC
                            ).isoformat(),
                            "sha256": digest,
                            "normalised_text_sha256": norm_digest,
                            "char_count": len(item.text),
                            "word_count": len(item.text.split()),
                            "bubble_hint": cfg["bubble_hint"],
                            "content_kind": "full_text_fetched"
                            if fetched_article
                            else content_kind(
                                item.text,
                                cfg["full_text_policy"],
                                item.raw_content or "",
                            ),
                            "language": lang,
                            "language_confidence": confidence,
                            "raw_path": Path(row.raw_path).relative_to(root).as_posix(),
                            "text_path": Path(row.text_path)
                            .relative_to(root)
                            .as_posix(),
                        }
                    accepted[key] = record
                    accepted_raw[key] = item
                    source_count += 1
                    counts["accepted"] += 1
                if all_old or source_count >= cfg["max_items"]:
                    break
            print(
                f"{sid}: {source_count} accepted / {status['polled']} polled; {len(status['errors'])} errors",
                flush=True,
            )
    finally:
        await repo.close()
        await http.close()
    # Recompute the manifest from this pass: cleaner changes must not retain
    # stale versions of the same candidate from an earlier, unapproved pass.
    current_ids = {o["id"] for o in outcomes if o["reason"] == "accepted"}
    records = sorted(
        (v for k, v in accepted.items() if k in current_ids),
        key=lambda x: (x["source"], x["published_at"], x["id"]),
    )
    accepted_raw = {k: v for k, v in accepted_raw.items() if k in current_ids}
    write_jsonl(manifest_path, records)
    write_jsonl(folder / "outcomes.jsonl", outcomes)
    # Rebuild, never append, the accepted replay snapshot. All polled records also retained.
    for snapshot_name, items in [
        (name, list(accepted_raw.values())),
        (name + "-polled", raw_items),
    ]:
        path = snapshot_path(root / "data", snapshot_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf8")
        SnapshotRecorder(root / "data", snapshot_name).record(items)
    result = {
        "name": name,
        "since": lower.isoformat(),
        "until": upper.isoformat(),
        "collected_at": datetime.now(UTC).isoformat(),
        "source_list_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
        "counts": dict(counts),
        "sources": statuses,
        "http_events": http.events,
        "manifest_count": len(records),
        "no_graph_ingestion": True,
        "llm_calls": 0,
        "llm_cost_usd": 0,
    }
    write_json(old_run, result)
    return result
