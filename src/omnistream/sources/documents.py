import hashlib
import io
from pathlib import PurePath

from pypdf import PdfReader

from omnistream.models import RawItem
from omnistream.sources import UnsupportedDocumentError


def _snap_forward(text: str, pos: int, limit: int) -> int:
    """Move pos to the start of the next word, if one begins before limit."""
    if pos <= 0 or text[pos - 1].isspace():
        return pos
    i = pos
    while i < limit and not text[i].isspace():
        i += 1
    while i < limit and text[i].isspace():
        i += 1
    return i if i < limit else pos


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split into chunks of at most `size` chars with ~`overlap` chars shared.

    Prefers paragraph breaks, then whitespace, then a hard split.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    overlap = max(0, min(overlap, size // 2))
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    n = len(text)
    while True:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            floor = size // 2
            cut = window.rfind("\n\n")
            if cut < floor:
                cut = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
            if cut >= floor:
                end = start + cut
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        next_start = _snap_forward(text, end - overlap, end)
        start = next_start if next_start > start else end
    return chunks


def _extract_text(filename: str, data: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")
    raise UnsupportedDocumentError(f"unsupported document type: {ext or filename!r}")


def load_document(
    source_id: str,
    filename: str,
    data: bytes,
    size: int,
    overlap: int,
    bubble_ids: list[str] | None,
) -> list[RawItem]:
    text = _extract_text(filename, data)
    chunks = chunk_text(text, size, overlap)
    digest = hashlib.sha256(data).hexdigest()[:16]
    n = len(chunks)
    return [
        RawItem(
            source_id=source_id,
            url=f"doc://{digest}#chunk-{i}",
            title=f"{filename} (part {i + 1}/{n})",
            text=chunk,
            bubble_ids_override=bubble_ids,
        )
        for i, chunk in enumerate(chunks)
    ]
