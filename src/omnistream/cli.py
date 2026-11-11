import argparse
import asyncio
import os
import sys
from pathlib import Path

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.db.repository import bubble_half_life
from omnistream.ingest.intake import Intake
from omnistream.models import ApiMapping, Bubble, Source
from omnistream.router.bubbles import BubbleService
from omnistream.sources.replay import load_snapshot

SEED_BUBBLES = [
    (
        "news",
        "News",
        (
            "Current world events and breaking news: politics, conflicts, diplomacy, "
            "disasters, elections and public affairs reported by news outlets."
        ),
        3,
    ),
    (
        "finance",
        "Finance",
        (
            "Financial markets and business: stocks, bonds, currencies, commodities, "
            "company earnings, central banks, mergers and economic indicators."
        ),
        30,
    ),
    (
        "research",
        "Research",
        (
            "Academic and scientific research: machine learning, natural language "
            "processing, papers, methods, benchmarks and technical findings."
        ),
        365,
    ),
]

FINNHUB_URL = "https://finnhub.io/api/v1/news?category=general&token=${FINNHUB_API_KEY}"
SEED_SOURCES = [
    ("bbc-world", "https://feeds.bbci.co.uk/news/world/rss.xml", "news", 0.8),
    ("guardian-world", "https://www.theguardian.com/world/rss", "news", 0.8),
    (
        "cnbc-markets",
        (
            "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"
        ),
        "finance",
        0.7,
    ),
    ("arxiv-cs-cl", "https://rss.arxiv.org/rss/cs.CL", "research", 0.9),
]


def _db_path(settings: Settings) -> str:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    return str(Path(settings.data_dir) / "omnistream.db")


async def seed(
    settings: Settings, repo: Repository | None = None, embedder=None
) -> int:
    """Create the starter bubbles and sources; idempotent."""
    repo = repo or Repository.from_path(_db_path(settings))
    if embedder is None:
        from omnistream.embed import SentenceTransformerEmbedder

        embedder = SentenceTransformerEmbedder(settings.embed_model)
    service = BubbleService(repo, embedder)
    try:
        have = {b.id for b in await repo.list_bubbles()}
        for bid, name, desc, _half_life in SEED_BUBBLES:
            if bid not in have:
                await service.create(
                    Bubble(
                        id=bid,
                        name=name,
                        description=desc,
                        half_life_days=bubble_half_life(name, settings),
                    )
                )
        sources = [
            Source(id=sid, type="rss", url=url, bubble_ids=[bubble], credibility=cred)
            for sid, url, bubble, cred in SEED_SOURCES
        ]
        if os.environ.get("FINNHUB_API_KEY"):
            sources.append(
                Source(
                    id="finnhub-news",
                    type="api",
                    url=FINNHUB_URL,
                    bubble_ids=["finance"],
                    credibility=0.7,
                    api_mapping=ApiMapping(
                        items="$[*]",
                        title="$.headline",
                        body="$.summary",
                        date="$.datetime",
                        url="$.url",
                    ),
                )
            )
        else:
            print("warning: FINNHUB_API_KEY not set; skipping Finnhub source")
        existing = {s.id for s in await repo.list_sources()}
        for s in sources:
            if s.id not in existing:
                await repo.upsert_source(s)
        print(f"seeded {len(SEED_BUBBLES)} bubbles and {len(sources)} sources")
    finally:
        await repo.close()
    return 0


async def serve(settings: Settings, host: str, port: int) -> int:
    import uvicorn

    from omnistream.api.app import app_from_components, build_components

    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    app = app_from_components(await build_components(settings), settings)
    await uvicorn.Server(uvicorn.Config(app, host=host, port=port)).serve()
    return 0


async def replay(name: str, settings: Settings) -> int:
    """Re-inject a recorded snapshot through intake, in polled order."""
    repo = Repository.from_path(_db_path(settings))
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
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sub.add_parser("replay").add_argument("name")
    args = parser.parse_args(argv)
    settings = Settings()
    if args.command == "replay":
        return asyncio.run(replay(args.name, settings))
    if args.command == "seed":
        return asyncio.run(seed(settings))
    if args.command == "serve":
        return asyncio.run(serve(settings, args.host, args.port))
    print(f"unknown command {args.command}", file=sys.stderr)
    return 1
