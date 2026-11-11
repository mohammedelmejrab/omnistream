"""End to end: RSS (respx) -> pipeline with real MiniLM embedder -> Neo4j container."""

import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from neo4j import AsyncGraphDatabase
from sqlmodel import select

from omnistream.db import Repository
from omnistream.db.tables import SeenItemRow
from omnistream.embed import SentenceTransformerEmbedder
from omnistream.graph.extract import Extractor
from omnistream.graph.resolve import EntityResolver
from omnistream.graph.write import FactWriter
from omnistream.ingest.pipeline import IngestPipeline
from omnistream.ingest.scheduler import IngestScheduler
from omnistream.models import (
    Bubble,
    ExtractedTriple,
    Extraction,
    Source,
)
from omnistream.router.bubbles import BubbleService
from omnistream.router.router import BubbleChoice, Router
from omnistream.store.neo4j_store import Neo4jStore
from tests.conftest import FakeLLM

pytestmark = pytest.mark.integration

DIM = 384
FEEDS = Path(__file__).parent.parent / "fixtures" / "feeds"
NEWS_URL = "https://news.test/feed.xml"
FINANCE_URL = "https://finance.test/feed.xml"
NOW = datetime(2026, 11, 10, tzinfo=UTC)


def _t(s, st, r, o, ot, exclusive=False):
    return ExtractedTriple(
        subject=s,
        subject_type=st,
        relation=r,
        object=o,
        object_type=ot,
        exclusive=exclusive,
    )


# title -> (bubble ids, triples). Mentions appear literally in the feed texts.
SCRIPT: dict[str, tuple[list[str], list[ExtractedTriple]]] = {
    "Harbor council approves new ferry terminal": (
        ["news", "finance"],
        [_t("Harbor council", "ORG", "APPROVED", "new ferry terminal", "OTHER")],
    ),
    "Lighthouse museum names new director": (
        ["news"],
        [_t("Marta Okafor", "PERSON", "DIRECTOR_OF", "Lighthouse Museum", "ORG", True)],
    ),
    "Fish market moves to Pier 4": (
        ["news"],
        [_t("weekly fish market", "OTHER", "RELOCATES_TO", "Pier 4", "LOCATION")],
    ),
    "Apple Inc. expands Harbor City campus": (
        ["finance"],
        [_t("Apple Inc.", "ORG", "INVESTS_IN", "Harbor City", "LOCATION")],
    ),
    "Fjord Components posts record profit": (
        ["finance"],
        [_t("Fjord Components", "ORG", "SUPPLIES", "Apple", "ORG")],
    ),
    "Orchard Bank lifts dividend": (
        ["finance"],
        [_t("Orchard Bank", "ORG", "RAISED", "quarterly dividend", "OTHER")],
    ),
}


def _title(user: str) -> str:
    return user.split("Title: ", 1)[1].splitlines()[0]


def _route(user: str) -> BubbleChoice:
    return BubbleChoice(bubble_ids=SCRIPT[_title(user)][0], confidence=0.9)


def _extract(user: str) -> Extraction:
    return Extraction(triples=SCRIPT[_title(user)][1])


@pytest.fixture(scope="session")
def real_embedder():
    # Load before any respx mock is active so HuggingFace is never intercepted.
    prior = os.environ.get("HF_HUB_OFFLINE")
    cached = (
        Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
        / "hub"
        / "models--sentence-transformers--all-MiniLM-L6-v2"
    ).exists()
    if cached:
        os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield SentenceTransformerEmbedder("all-MiniLM-L6-v2")
    finally:
        if prior is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = prior


async def _fresh_store(container) -> Neo4jStore:
    s = Neo4jStore(
        container.get_connection_url(),
        container.username,
        container.password,
        embed_dim=DIM,
    )
    # The vector index dimension is fixed at creation; other suites use dim 8.
    await s._run("DROP INDEX entity_embedding IF EXISTS")
    await s._run("MATCH (n) DETACH DELETE n")
    await s.init_schema()
    return s


@pytest.fixture
async def env(neo4j_container, real_embedder, tmp_path):
    store = await _fresh_store(neo4j_container)
    db_path = str(tmp_path / "app.db")
    repo = Repository.from_path(db_path)
    for bid in ("news", "finance"):
        await BubbleService(repo, real_embedder).create(
            Bubble(id=bid, name=bid, description=f"{bid} topics", updated_at=NOW)
        )
    await repo.upsert_source(
        Source(id="news-src", type="rss", url=NEWS_URL, credibility=0.7)
    )
    await repo.upsert_source(
        Source(id="fin-src", type="rss", url=FINANCE_URL, credibility=0.9)
    )

    def build(st: Neo4jStore, rp: Repository = repo) -> IngestScheduler:
        llm = FakeLLM({BubbleChoice: _route, Extraction: _extract})
        pipe = IngestPipeline(
            rp,
            Router(llm, "m", real_embedder),
            Extractor(llm, "m"),
            EntityResolver(st, real_embedder, 0.88, 90),
            FactWriter(st),
            grounding_threshold=85,
        )
        return IngestScheduler(rp, pipe, http)

    async with httpx.AsyncClient() as http:
        build.db_path = db_path
        build.repo = repo
        yield store, build, neo4j_container
    await store.close()
    # Leave no 384-dim index behind for the dim-8 contract tests.
    cleanup = Neo4jStore(
        neo4j_container.get_connection_url(),
        neo4j_container.username,
        neo4j_container.password,
        embed_dim=DIM,
    )
    await cleanup._run("DROP INDEX entity_embedding IF EXISTS")
    await cleanup._run("MATCH (n) DETACH DELETE n")
    await cleanup.close()


def _mock_feeds():
    respx.get(NEWS_URL).respond(200, content=(FEEDS / "news.xml").read_bytes())
    respx.get(FINANCE_URL).respond(200, content=(FEEDS / "finance.xml").read_bytes())


async def _cypher(container, query: str, **params):
    driver = AsyncGraphDatabase.driver(
        container.get_connection_url(), auth=(container.username, container.password)
    )
    try:
        records, _, _ = await driver.execute_query(query, params)
        return records
    finally:
        await driver.close()


@respx.mock
async def test_e2e_feed_to_neo4j(env):
    store, build, c = env
    _mock_feeds()
    sched = build(store)
    results = await sched.poll_source("news-src")
    assert [r.status for r in results] == ["ingested"] * 3

    recs = await _cypher(
        c,
        "MATCH (s:Entity)-[f:FACT]->(o:Entity) "
        "RETURN s.canonical_name AS s, f.relation AS r, o.canonical_name AS o, "
        "f.bubble_id AS b",
    )
    triples = {(r["s"], r["r"], r["o"], r["b"]) for r in recs}
    assert triples == {
        ("Harbor council", "APPROVED", "new ferry terminal", "news"),
        ("Harbor council", "APPROVED", "new ferry terminal", "finance"),
        ("Marta Okafor", "DIRECTOR_OF", "Lighthouse Museum", "news"),
        ("weekly fish market", "RELOCATES_TO", "Pier 4", "news"),
    }
    bad = await _cypher(
        c,
        "MATCH ()-[f:FACT]->() WHERE f.source_id IS NULL OR f.source_url IS NULL "
        "OR f.credibility IS NULL OR f.valid_from IS NULL OR f.ingested_at IS NULL "
        "RETURN count(f) AS n",
    )
    assert bad[0]["n"] == 0
    # Seen-state lives in SQLite now, not Neo4j.
    seen = await _cypher(c, "MATCH (s:SeenItem) RETURN count(s) AS n")
    assert seen[0]["n"] == 0
    assert len(await build.repo._run(lambda s: list(s.exec(select(SeenItemRow))))) == 3


@respx.mock
async def test_e2e_cross_bubble_entity_shared(env):
    store, build, c = env
    _mock_feeds()
    await build(store).poll_source("news-src")
    recs = await _cypher(
        c,
        "MATCH (e:Entity)-[f:FACT]-() "
        "RETURN e.id AS id, collect(DISTINCT f.bubble_id) AS bubbles",
    )
    shared = [r for r in recs if set(r["bubbles"]) == {"news", "finance"}]
    # Subject and object of the dual-routed ferry fact, one node each.
    assert len(shared) == 2
    names = await _cypher(
        c,
        "MATCH (e:Entity) WHERE e.id IN $ids RETURN e.canonical_name AS n",
        ids=[r["id"] for r in shared],
    )
    assert {r["n"] for r in names} == {"Harbor council", "new ferry terminal"}


@respx.mock
async def test_e2e_real_embedder_merges_aliases(env):
    store, build, c = env
    _mock_feeds()
    results = await build(store).poll_source("fin-src")
    assert [r.status for r in results] == ["ingested"] * 3
    recs = await _cypher(
        c,
        "MATCH (e:Entity {type: 'ORG'}) "
        "WHERE e.canonical_name STARTS WITH 'Apple' "
        "OR any(a IN e.aliases WHERE a STARTS WITH 'Apple') "
        "RETURN e.canonical_name AS n, e.aliases AS aliases",
    )
    assert len(recs) == 1
    assert recs[0]["n"] == "Apple Inc."
    assert "Apple" in recs[0]["aliases"]


@respx.mock
async def test_e2e_restart_preserves_dedup(env):
    store, build, c = env
    _mock_feeds()
    first = await build(store).poll_source("news-src")
    assert all(r.status == "ingested" for r in first)
    await store.close()

    restarted = Neo4jStore(
        c.get_connection_url(), c.username, c.password, embed_dim=DIM
    )
    try:
        await restarted.init_schema()
        again = await build(restarted, Repository.from_path(build.db_path)).poll_source(
            "news-src"
        )
        assert [r.status for r in again] == ["duplicate"] * 3
    finally:
        await restarted.close()
