import json
import os
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse as parse_jsonpath

from omnistream.models import RawItem, Source
from omnistream.sources import SourceFetchError
from omnistream.sources.rss import _strip_html


def _find(data: Any, path: str) -> list[Any]:
    try:
        return [m.value for m in parse_jsonpath(path).find(data)]
    except JsonPathParserError as e:
        raise SourceFetchError(f"invalid JSONPath {path!r}: {e}") from e


def _text_value(item: Any, path: str) -> str | None:
    found = _find(item, path)
    if not found or found[0] is None:
        return None
    text = str(found[0]).strip()
    return text or None


_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(text: str) -> str:
    """Substitute ${VAR} from the environment at fetch time, so secrets such as
    API tokens are never stored in SQLite (D20)."""
    return _ENV.sub(lambda m: os.environ.get(m.group(1), ""), text)


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, UTC)  # epoch seconds (Finnhub)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def fetch_api(source: Source, http: httpx.AsyncClient) -> list[RawItem]:
    assert source.url is not None and source.api_mapping is not None
    cfg = source.api_mapping
    response = await http.get(
        expand_env(source.url),
        headers={k: expand_env(v) for k, v in cfg.headers.items()},
        timeout=20.0,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise SourceFetchError(f"{source.url}: HTTP {e.response.status_code}") from e
    try:
        payload = response.json()
    except ValueError as e:
        raise SourceFetchError(f"{source.url}: invalid JSON") from e

    # `$.data.items` resolves to one list; `$.data.items[*]` to many entries.
    matches = _find(payload, cfg.items)
    if len(matches) == 1 and isinstance(matches[0], list):
        entries = matches[0]
    elif len(matches) > 1:
        entries = matches
    else:
        raise SourceFetchError(
            f"{source.url}: items path {cfg.items!r} did not resolve to a list"
        )

    items: list[RawItem] = []
    for entry in entries:
        text = _text_value(entry, cfg.body)
        url = _text_value(entry, cfg.url)
        if text is None or url is None:
            continue
        # Official APIs (e.g. Europe PMC) can return HTML in body fields.
        # Keep the original JSON below, but emit readable C1 clean text.
        if re.search(
            r"</?(?:p|div|h[1-6]|section|script|style|br|strong|em|b|i|span|ul|ol|li|table|blockquote)\b",
            text,
            re.IGNORECASE,
        ):
            text = _strip_html(text)
        title = (_text_value(entry, cfg.title) if cfg.title else None) or ""
        published = None
        if cfg.date:
            found = _find(entry, cfg.date)
            published = _parse_date(found[0] if found else None)
        items.append(
            RawItem(
                source_id=source.id,
                url=url,
                title=title,
                text=text,
                published_at=published,
                raw_content=json.dumps(entry, ensure_ascii=False, default=str),
                raw_ext="json",
            )
        )
    return items
