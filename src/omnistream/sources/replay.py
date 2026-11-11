"""Snapshot recording and replay of polled RawItems (spec §13 reproducibility).

One JSON object per line in ``<data_dir>/snapshots/<name>.jsonl``, in polled
order; `published_at` is preserved so replay reproduces original dating.
"""

from pathlib import Path

from omnistream.models import RawItem


def snapshot_path(data_dir: str | Path, name: str) -> Path:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid snapshot name: {name!r}")
    return Path(data_dir) / "snapshots" / f"{name}.jsonl"


class SnapshotRecorder:
    def __init__(self, data_dir: str | Path, name: str) -> None:
        self.path = snapshot_path(data_dir, name)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, items: list[RawItem]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            for item in items:
                f.write(item.model_dump_json() + "\n")


def load_snapshot(data_dir: str | Path, name: str) -> list[RawItem]:
    path = snapshot_path(data_dir, name)
    with path.open(encoding="utf-8") as f:
        return [RawItem.model_validate_json(line) for line in f if line.strip()]
