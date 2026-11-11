"""Text/URL/relation normalization and content hashing for dedup."""

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
_DROP_PARAMS = {"fbclid", "gclid"}


def normalize_text(text: str) -> str:
    """NFKC, casefold, collapse whitespace runs to one space, strip."""
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(url: str) -> str:
    """Canonicalize http(s) URLs; return other schemes completely unchanged."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        return url
    host = (parts.hostname or "").lower()
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parts.port
    netloc = (
        host if port is None or port == _DEFAULT_PORTS[scheme] else f"{host}:{port}"
    )
    if parts.username:
        userinfo = parts.username + (f":{parts.password}" if parts.password else "")
        netloc = f"{userinfo}@{netloc}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    params = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _DROP_PARAMS
    )
    return urlunsplit((scheme, netloc, path, urlencode(params), ""))


def content_hash(url: str, text: str) -> str:
    """Lowercase hex sha256 of normalized url + newline + normalized text."""
    payload = normalize_url(url) + "\n" + normalize_text(text)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_relation(rel: str) -> str:
    """Uppercase snake case over alphanumeric words, e.g. 'is CEO of' -> 'IS_CEO_OF'."""
    return "_".join(re.findall(r"[A-Za-z0-9]+", rel)).upper()
