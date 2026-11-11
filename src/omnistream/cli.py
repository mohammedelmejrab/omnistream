import argparse
import asyncio
import sys
from pathlib import Path

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.ingest.intake import Intake
from omnistream.sources.replay import load_snapshot


async def replay(name: str, settings: Settings) -> int:
    """Re-inject a recorded snapshot through intake, in polled order."""
    repo = Repository.from_path(str(Path(settings.data_dir) / "omnistream.db"))
    intake = Intake(repo, settings.data_dir, settings.prefilter_min_chars)
    accepted = 0
    try:
        for item in load_snapshot(settings.data_dir, name):
            source = await repo.get_source(item.source_id)
            if source is None:
                print(f"skipping {item.url}: unknown source {item.source_id}")
                continue
            raw = item.raw_content if item.raw_content is not None else item.text
            row = await intake.accept(item, source, raw.encode("utf-8"), item.raw_ext)
            accepted += row is not None
    finally:
        await repo.close()
    print(f"replayed {name}: {accepted} item(s) queued")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omni")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    sub.add_parser("serve")
    sub.add_parser("replay").add_argument("name")
    args = parser.parse_args(argv)
    if args.command == "replay":
        return asyncio.run(replay(args.name, Settings()))
    print(f"omni {args.command}: not implemented yet", file=sys.stderr)
    return 1
