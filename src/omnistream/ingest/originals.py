"""Original store (spec §4.2): raw bytes and clean text on disk, never deleted.

Layout: ``<data_dir>/raw/<source_id>/<sha256>.<ext>`` for the raw bytes and
``<sha256>.txt`` alongside for the clean text. Document parts (episodes) share
one original and each get ``<sha256>.part<N>.txt``.
"""

import hashlib
from pathlib import Path

PREVIEW_CHARS = 500
RAW_EXTS = {"html", "json", "pdf", "docx", "txt", "md"}


def store_original(
    data_dir: str | Path,
    source_id: str,
    raw_bytes: bytes,
    ext: str,
    title: str,
    text: str,
    *,
    store_full_text: bool = True,
    part: int | None = None,
) -> tuple[Path, Path, bool]:
    """Write raw + clean text; return (raw_path, text_path, truncated).

    The raw file is written once per distinct content (idempotent). With
    `store_full_text` false only title + the first 500 chars are kept as clean
    text and `truncated` is True.
    """
    ext = ext.lower().lstrip(".")
    if ext not in RAW_EXTS:
        raise ValueError(f"unsupported original extension: {ext!r}")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    folder = Path(data_dir) / "raw" / source_id
    folder.mkdir(parents=True, exist_ok=True)
    raw_path = folder / f"{digest}.{ext}"
    if not raw_path.exists():
        raw_path.write_bytes(raw_bytes)
    text_name = f"{digest}.txt" if part is None else f"{digest}.part{part}.txt"
    text_path = folder / text_name
    truncated = not store_full_text
    clean = f"{title}\n\n{text[:PREVIEW_CHARS]}" if truncated else text
    text_path.write_text(clean, encoding="utf-8")
    return raw_path, text_path, truncated
