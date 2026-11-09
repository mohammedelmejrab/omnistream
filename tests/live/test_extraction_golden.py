"""Golden eval against the real model. Costs money: needs ANTHROPIC_API_KEY.

Run: ANTHROPIC_API_KEY=... uv run pytest -m live -v -s
If recall is low, tune EXTRACTION_SYSTEM, never the thresholds below.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from rapidfuzz import fuzz, utils

from omnistream.config import Settings
from omnistream.embed import SentenceTransformerEmbedder
from omnistream.ingest.extract import Extractor
from omnistream.ingest.grounding import is_grounded
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.ingest.resolve import EntityResolver
from omnistream.ingest.route import Router
from omnistream.ingest.write import FactWriter
from omnistream.llm import build_llm_client
from omnistream.models import Bubble, RawItem, Source
from omnistream.store.memory import InMemoryStore

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"
    ),
]

ARTICLES = Path(__file__).parent.parent / "fixtures" / "golden" / "articles.jsonl"
RECALL_MIN = 0.8
ROUTING_MIN = 5
NAME_MATCH = 90


def _load() -> list[dict]:
    return [json.loads(line) for line in ARTICLES.read_text().splitlines() if line]


def _names(entity) -> list[str]:
    return [entity.canonical_name, *entity.aliases]


def _found(store: InMemoryStore, name: str, type_: str) -> bool:
    return any(
        e.type == type_
        and any(
            fuzz.token_sort_ratio(name, n, processor=utils.default_process)
            >= NAME_MATCH
            for n in _names(e)
        )
        for e in store._entities.values()
    )


async def test_golden_extraction():
    settings = Settings()
    store = InMemoryStore()
    embedder = SentenceTransformerEmbedder(settings.embed_model)
    llm = build_llm_client(settings)
    now = datetime(2026, 4, 1).astimezone()
    for bid, desc in (
        ("news", "General world, local and breaking news"),
        ("finance", "Companies, markets, banks, earnings and executive changes"),
    ):
        await store.create_bubble(
            Bubble(id=bid, name=bid, description=desc, updated_at=now)
        )
    source = Source(id="golden", type="rss", url="https://golden.test/feed")
    await store.upsert_source(source)
    pipeline = IngestPipeline(
        store,
        Router(llm, settings.anthropic_model_route),
        Extractor(llm, settings.anthropic_model_extract),
        EntityResolver(
            store, embedder, settings.embed_match_threshold,
            settings.fuzzy_match_threshold,
        ),
        FactWriter(store),
        settings.grounding_threshold,
    )

    articles = _load()
    texts: dict[str, str] = {}
    routing_ok = 0
    expected_total = found_total = 0
    # LLMClient does not expose token usage, so the table omits it.
    print("\nid | routing (got vs expected) | entities found / missed")
    for a in articles:
        item = RawItem(
            source_id="golden",
            url=f"https://golden.test/{a['id']}",
            title=a["title"],
            text=a["text"],
            published_at=datetime.fromisoformat(a["published_at"]),
        )
        result = await pipeline.process(item, source)
        assert result.status == "ingested", (a["id"], result)
        texts[a["id"]] = f"{a['title']}\n{a['text']}"
        route_match = set(result.bubble_ids) == set(a["expected_bubbles"])
        routing_ok += route_match
        found = [
            e["name"] for e in a["expected_entities"]
            if _found(store, e["name"], e["type"])
        ]
        missed = [
            e["name"] for e in a["expected_entities"] if e["name"] not in found
        ]
        expected_total += len(a["expected_entities"])
        found_total += len(found)
        print(
            f"{a['id']} | {sorted(result.bubble_ids)} vs {a['expected_bubbles']}"
            f" {'OK' if route_match else 'MISMATCH'} | found={found} missed={missed}"
        )

    recall = found_total / expected_total
    print(f"entity recall={recall:.2f} routing={routing_ok}/{len(articles)}")
    assert recall >= RECALL_MIN
    assert routing_ok >= ROUTING_MIN

    # Every stored name must be grounded in at least one source article.
    ungrounded = [
        n
        for e in store._entities.values()
        for n in _names(e)
        if not any(
            is_grounded(n, t, settings.grounding_threshold) for t in texts.values()
        )
    ]
    assert ungrounded == []

    # Article 5 (older CEO fact) arrives after article 4 (newer): 4 stays active.
    by_id = store._entities
    facts = [f for b in ("news", "finance") for f in await store.list_facts(b)]

    def ceo_fact(person: str):
        for f in facts:
            names = [n for i in (f.subject_id, f.object_id) for n in _names(by_id[i])]
            if any("acme" in n.casefold() for n in names) and any(
                person in n for n in names
            ):
                return f
        return None

    newer, older = ceo_fact("Whitfield"), ceo_fact("Patel")
    assert newer is not None and older is not None
    assert newer.status == "VERIFIED"
    assert older.status == "HISTORICAL"

    apples = [
        e for e in by_id.values()
        if e.type == "ORG" and any(n.casefold().startswith("apple") for n in _names(e))
    ]
    assert len(apples) == 1
