import hashlib
from datetime import UTC, datetime

import feedparser
import httpx
from bs4 import BeautifulSoup

from omnistream.ingest.sources import SourceFetchError
from omnistream.models import RawItem, Source


def _strip_html(html: str) -> str:
    # Wrapping in a tag avoids bs4's MarkupResemblesLocatorWarning on plain text.
    soup = BeautifulSoup(f"<div>{html}</div>", "html.parser")
    return " ".join(soup.get_text(" ").split())


async def fetch_rss(source: Source, http: httpx.AsyncClient) -> list[RawItem]:
    assert source.url is not None
    response = await http.get(source.url, timeout=20.0)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise SourceFetchError(f"{source.url}: HTTP {e.response.status_code}") from e

    feed = feedparser.parse(response.content)
    if feed.bozo and not feed.entries:
        raise SourceFetchError(
            f"{source.url}: unparseable feed ({feed.bozo_exception})"
        )

    items: list[RawItem] = []
    for entry in feed.entries:
        title = entry.get("title", "") or ""
        url = entry.get("link") or (
            f"rss://{source.id}/"
            f"{entry.get('id') or hashlib.sha256(title.encode()).hexdigest()[:16]}"
        )
        content = entry.get("content")
        raw = content[0].get("value", "") if content else ""
        if not raw:
            raw = entry.get("summary", "") or ""
        text = _strip_html(raw)
        if not text:
            continue
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        published = datetime(*parsed[:6], tzinfo=UTC) if parsed else None
        items.append(
            RawItem(
                source_id=source.id,
                url=url,
                title=title,
                text=text,
                published_at=published,
            )
        )
    return items
