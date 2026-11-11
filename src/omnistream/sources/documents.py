"""Document sources: PDF, DOCX, TXT, MD -> episodes of ~1,500 tokens.

Token count is estimated as words x 1.3 (no tokenizer dependency; close enough
for sizing episodes). Splitting prefers heading boundaries, then paragraph
boundaries, and hard-splits an oversize paragraph by words as a last resort.
"""

import hashlib
import io
import re
from pathlib import PurePath

from pypdf import PdfReader

from omnistream.models import RawItem
from omnistream.sources import UnsupportedDocumentError

TOKENS_PER_WORD = 1.3
_HEADING = re.compile(r"^#{1,6}\s+\S")
DOCUMENT_EXTS = {".pdf", ".docx", ".txt", ".md"}


def estimate_tokens(text: str) -> int:
    return round(len(text.split()) * TOKENS_PER_WORD)


def document_ext(filename: str) -> str:
    """Lowercase extension without dot; raises for unsupported types."""
    ext = PurePath(filename).suffix.lower()
    if ext not in DOCUMENT_EXTS:
        raise UnsupportedDocumentError(
            f"unsupported document type: {ext or filename!r}"
        )
    return ext[1:]


def _docx_text(data: bytes) -> str:
    from docx import Document

    lines: list[str] = []
    for para in Document(io.BytesIO(data)).paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "") if para.style is not None else ""
        m = re.fullmatch(r"Heading (\d)", style)
        if m or style == "Title":
            lines.append(f"{'#' * int(m.group(1) if m else 1)} {text}")
        else:
            lines.append(text)
    return "\n\n".join(lines)


def extract_text(filename: str, data: bytes) -> str:
    """Clean text; headings are emitted as markdown `#` lines (DOCX styles, MD)."""
    ext = document_ext(filename)
    if ext == "pdf":
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == "docx":
        return _docx_text(data)
    return data.decode("utf-8", errors="replace")


def _sections(text: str) -> list[list[str]]:
    """Paragraph lists, one per heading-led section."""
    sections: list[list[str]] = []
    for para in re.split(r"\n\s*\n", text.strip()):
        para = para.strip()
        if not para:
            continue
        if _HEADING.match(para) or not sections:
            sections.append([])
        sections[-1].append(para)
    return sections


def _hard_split(para: str, max_tokens: int) -> list[str]:
    words = para.split()
    step = max(1, int(max_tokens / TOKENS_PER_WORD))
    return [" ".join(words[i : i + step]) for i in range(0, len(words), step)]


def split_episodes(text: str, max_tokens: int) -> list[str]:
    """Greedy-pack heading sections into episodes of <= max_tokens.

    A section that fits is never split; one that does not is cut at paragraph
    boundaries (only an oversize single paragraph is split mid-text).
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    episodes: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            episodes.append("\n\n".join(current))
        current, current_tokens = [], 0

    for section in _sections(text):
        body = "\n\n".join(section)
        size = estimate_tokens(body)
        if current_tokens + size <= max_tokens:
            current.append(body)
            current_tokens += size
            continue
        flush()
        if size <= max_tokens:
            current, current_tokens = [body], size
            continue
        for para in section:
            pieces = (
                _hard_split(para, max_tokens)
                if estimate_tokens(para) > max_tokens
                else [para]
            )
            for piece in pieces:
                t = estimate_tokens(piece)
                if current_tokens + t > max_tokens:
                    flush()
                current.append(piece)
                current_tokens += t
    flush()
    return episodes


def load_document(
    source_id: str,
    filename: str,
    data: bytes,
    episode_tokens: int,
    bubble_ids: list[str] | None,
) -> list[RawItem]:
    """Parse `data` and split into episode RawItems (one per part)."""
    episodes = split_episodes(extract_text(filename, data), episode_tokens)
    digest = hashlib.sha256(data).hexdigest()[:16]
    n = len(episodes)
    return [
        RawItem(
            source_id=source_id,
            url=f"doc://{digest}#part-{i}",
            title=f"{filename} (part {i + 1}/{n})",
            text=ep,
            bubble_ids_override=bubble_ids,
            raw_ext=document_ext(filename),
        )
        for i, ep in enumerate(episodes)
    ]
