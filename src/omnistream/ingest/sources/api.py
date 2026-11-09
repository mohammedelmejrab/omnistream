from datetime import UTC, datetime
from typing import Any

import httpx

from omnistream.ingest.sources import SourceFetchError
from omnistream.models import RawItem, Source

_MISSING = object()


def _resolve(obj: Any, path: str) -> Any:
    """Follow a dotted path through nested dicts; empty path is the object itself."""
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return _MISSING
    return obj


def _text_value(item: Any, path: str) -> str | None:
    value = _resolve(item, path)
    if value is _MISSING or value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def fetch_api(source: Source, http: httpx.AsyncClient) -> list[RawItem]:
    assert source.url is not None and source.api_config is not None
    cfg = source.api_config
    response = await http.get(source.url, headers=cfg.headers, timeout=20.0)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise SourceFetchError(f"{source.url}: HTTP {e.response.status_code}") from e
    try:
        payload = response.json()
    except ValueError as e:
        raise SourceFetchError(f"{source.url}: invalid JSON") from e

    entries = _resolve(payload, cfg.items_path)
    if not isinstance(entries, list):
        raise SourceFetchError(
            f"{source.url}: items_path {cfg.items_path!r} did not resolve to a list"
        )

    items: list[RawItem] = []
    for entry in entries:
        text = _text_value(entry, cfg.text_field)
        url = _text_value(entry, cfg.url_field)
        if text is None or url is None:
            continue
        title = (_text_value(entry, cfg.title_field) if cfg.title_field else None) or ""
        published = None
        if cfg.published_field:
            published = _parse_date(_resolve(entry, cfg.published_field))
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
