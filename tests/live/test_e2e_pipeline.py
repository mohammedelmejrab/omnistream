"""Live C1-C5 contract, isolated from application data; run with -m live -rP."""

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

import pytest

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.embed import SentenceTransformerEmbedder
from omnistream.graph.writer import build_graph_writer
from omnistream.ingest.intake import Intake
from omnistream.ingest.pipeline import ItemProcessor
from omnistream.ingest.queue import WorkerPool
from omnistream.llm import build_llm_client
from omnistream.models import Bubble, RawItem, Source
from omnistream.retrieval.runtime import build_query_runtime
from omnistream.router.bubbles import BubbleService
from omnistream.router.router import Router

pytestmark = pytest.mark.live

CONFIGURATIONS = [
    ("classic", False),
    ("graphiti", False),
    ("own", False),
    ("own", True),
    ("classic", True),
]


def test_external_baseline():
    pytest.skip(
        "external LlamaIndex baseline belongs to C7; five implemented configurations tested below"
    )


async def test_e2e_pipeline(monkeypatch):
    prefix = "live-" + uuid4().hex[:12]
    with TemporaryDirectory(prefix=prefix) as directory:
        monkeypatch.setenv("OMNI_DATA_DIR", directory)
        settings = Settings()
        assert settings.has_llm_credentials, (
            "live run requires configured LLM credentials"
        )
        assert settings.neo4j_password.get_secret_value(), (
            "live run requires NEO4J_PASSWORD"
        )
        assert Path(settings.data_dir).resolve() == Path(directory).resolve()
        repo = Repository.from_path(
            str(Path(directory) / "state.db"), settings=settings
        )
        embedder = SentenceTransformerEmbedder(settings.embed_model)
        llm = build_llm_client(settings)
        writer = runtime = None
        groups = {
            name: prefix + "-" + name.lower()
            for name in ("News", "Finance", "Research")
        }
        rows = []
        table = []
        try:
            service = BubbleService(repo, embedder)
            descriptions = {
                "News": "Corporate leadership news, CEO appointments and replacements at fictional companies.",
                "Finance": "Business investments and financial funding of fictional companies and research laboratories.",
                "Research": "Scientific research, laboratory discoveries and experimental products.",
            }
            for name, group in groups.items():
                bubble = await service.create(
                    Bubble(id=group, name=name, description=descriptions[name])
                )
                assert len(bubble.description_embedding) == settings.embed_dim
            writer = await build_graph_writer(settings, repo, embedder, llm)
            router = Router(
                llm,
                settings.llm_model,
                embedder,
                settings.router_threshold,
                settings.router_top_k,
            )
            pool = WorkerPool(
                repo,
                ItemProcessor(repo, router, writer).process_item,
                workers=1,
                max_attempts=3,
                backoff_base=0,
            )
            intake = Intake(repo, directory, settings.prefilter_min_chars)
            # Chronological queue processing ensures the replacement can invalidate the old fact.
            corpus = [
                (
                    "News",
                    "2026-01-01",
                    "Original chief executive",
                    "As of January 1, 2026, Mira Velquin is the CEO of Zorvanta Labs. Zorvanta Labs is a fictional technology company. This dated corporate leadership bulletin establishes Mira Velquin as its serving chief executive officer.",
                    True,
                ),
                (
                    "Finance",
                    "2026-02-01",
                    "Research funding",
                    "On February 1, 2026, Zorvanta Labs signed an investment agreement to fund Pelvoria Institute for scientific research. Zorvanta Labs funds Pelvoria Institute. This fictional financial bulletin records the funding relationship between Zorvanta Labs and Pelvoria Institute for scientific research.",
                    True,
                ),
                (
                    "Research",
                    "2026-03-01",
                    "Laboratory discovery",
                    "On March 1, 2026, Pelvoria Institute announced that it developed the experimental Nuvex Prism product. Pelvoria Institute developed the Nuvex Prism. This fictional scientific research bulletin identifies Pelvoria Institute as the laboratory that developed the experimental Nuvex Prism product.",
                    False,
                ),
                (
                    "News",
                    "2026-04-01",
                    "Replacement chief executive",
                    "On April 1, 2026, Taren Vosquil replaced Mira Velquin as CEO of Zorvanta Labs. Mira Velquin is no longer CEO of Zorvanta Labs. Taren Vosquil is now the CEO of Zorvanta Labs. This fictional leadership bulletin records the replacement effective April 1, 2026.",
                    True,
                ),
            ]
            for index, (bubble, date, title, text, explicit) in enumerate(corpus):
                assert len(text) >= 200
                source = Source(
                    id=f"{prefix}-source-{index}",
                    type="rss",
                    url=f"https://fixture.invalid/{prefix}/{index}",
                    credibility=0.9,
                )
                await repo.upsert_source(source)
                raw = RawItem(
                    source_id=source.id,
                    url=source.url,
                    title=title,
                    text=text,
                    published_at=datetime.fromisoformat(date).replace(tzinfo=UTC),
                    bubble_ids_override=[groups[bubble]] if explicit else [],
                )
                row = await intake.accept(raw, source, text.encode(), "txt")
                assert row is not None
                assert await intake.accept(raw, source, text.encode(), "txt") is None
                for _ in range(3):
                    assert await pool.run_once()
                    stored = await repo.get_item(row.id)
                    if stored.status == "written":
                        break
                assert stored.status == "written", (
                    f"{index}: {stored.status}: {stored.error}"
                )
                assert stored.bubble_ids == [groups[bubble]]
                assert stored.route_confidence >= settings.router_threshold
                if explicit:
                    assert stored.route_confidence == 1.0
                assert all(
                    (
                        stored.polled_at,
                        stored.deduplicated_at,
                        stored.routed_at,
                        stored.extracted_at,
                        stored.written_at,
                    )
                )
                rows.append(stored)
                print(f"Ingested {index + 1}/4: {title}", flush=True)
            jobs = await repo.list_jobs("done")
            assert len(jobs) == len(rows)
            print(
                "Queue attempts: " + ", ".join(str(job.attempts) for job in jobs),
                flush=True,
            )
            edges = await writer.ops._q(
                "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id IN $groups RETURN properties(r) AS r",
                groups=list(groups.values()),
            )
            assert edges
            ids = {row.id for row in rows}
            for record in edges:
                edge = record["r"]
                assert edge.get("item_id") in ids
                assert edge.get("published_at") is not None
                assert isinstance(edge.get("grounded"), bool)
            links = await writer.ops._q(
                "MATCH (e:Entity)-[:SAME_AS]->(g:GlobalEntity) WHERE e.group_id IN $groups "
                "WITH g, collect(DISTINCT e.group_id) AS groups WHERE size(groups) >= 2 "
                "RETURN g.name AS name, groups",
                groups=list(groups.values()),
            )
            assert links, "no shared cross-bubble GlobalEntity"
            old = [
                r["r"]
                for r in edges
                if rows[0].id in r["r"].get("item_ids", [])
                and "Mira" in r["r"].get("fact", "")
                and any(
                    term in r["r"].get("fact", "").lower()
                    for term in ("ceo", "chief executive")
                )
            ]
            assert old and any(e.get("status") == "HISTORICAL" for e in old), [
                (r["r"].get("fact"), r["r"].get("status"), r["r"].get("item_ids"))
                for r in edges
            ]
            for group in groups.values():
                assert await writer.chunks.count(group) > 0
            runtime = build_query_runtime(settings, repo, embeddings=embedder)
            originals = {
                r.id: Path(r.text_path).read_text(encoding="utf-8") for r in rows
            }
            questions = [
                (
                    "single",
                    "What product did Pelvoria Institute develop?",
                    [groups["Research"]],
                ),
                (
                    "cross",
                    "Which company funds Pelvoria Institute, and what product did Pelvoria Institute develop?",
                    [],
                ),
                ("now", "Who is the CEO of Zorvanta Labs now?", [groups["News"]]),
            ]
            bridge_rows = await writer.ops._q(
                "MATCH (a:Entity)-[:SAME_AS]->(:GlobalEntity)<-[:SAME_AS]-(b:Entity) "
                "WHERE a.group_id IN $groups AND b.group_id IN $groups "
                "RETURN a.uuid AS a, b.uuid AS b",
                groups=list(groups.values()),
            )
            bridges = {frozenset((r["a"], r["b"])) for r in bridge_rows}
            for mode, agents in CONFIGURATIONS:
                for kind, question, pins in questions:
                    started = perf_counter()
                    result = await runtime.answer(
                        question, mode=mode, subagents=agents, pin=pins
                    )
                    elapsed = perf_counter() - started
                    answer = result.answer
                    assert answer.text.strip()
                    assert answer.citations, (mode, agents, kind, answer.text)
                    assert not answer.invalid_citations
                    assert result.routing.bubbles and set(pins) <= set(
                        result.routing.bubbles
                    )
                    for citation in answer.citations:
                        assert citation.item_id in ids
                        assert citation.spans, (mode, kind, citation)
                        original = originals[citation.item_id]
                        for start, end in citation.spans:
                            assert 0 <= start < end <= len(original)
                            assert original[start:end].strip()
                    span_texts = {
                        c.item_id: " | ".join(
                            originals[c.item_id][a:b] for a, b in c.spans
                        )
                        for c in answer.citations
                    }
                    bridge_used = (
                        any(
                            frozenset((a, b)) in bridges
                            for f in result.retrieval.facts
                            for a, b in zip(f.path, f.path[1:])
                        )
                        if result.retrieval
                        else False
                    )
                    if kind == "now":
                        assert rows[3].id in {c.item_id for c in answer.citations}, (
                            answer
                        )
                        assert "Taren Vosquil" in answer.text, answer.text
                        assert not re.search(
                            r"Mira Velquin (?:is|remains) (?:the )?(?:current )?CEO",
                            answer.text,
                            re.IGNORECASE,
                        )
                        current = span_texts[rows[3].id]
                        assert (
                            "Taren Vosquil is now the CEO" in current
                            or "Taren Vosquil replaced Mira Velquin as CEO" in current
                        ), current
                    if kind == "single" or kind == "cross":
                        assert "Nuvex Prism" in answer.text, answer.text
                        developed = span_texts.get(rows[2].id, "")
                        assert any(
                            "Pelvoria Institute" in sentence
                            and "developed" in sentence
                            and "Nuvex Prism" in sentence
                            for sentence in developed.split(".")
                        ), span_texts
                    if kind == "cross" and mode != "classic":
                        assert {rows[1].id, rows[2].id} <= set(span_texts), answer
                        if mode == "own":
                            assert bridge_used, result.retrieval
                    calls = (
                        sum(f.tool_calls_used for f in result.multi_hop.findings)
                        if result.multi_hop
                        else 0
                    )
                    if agents:
                        assert calls > 0
                        assert all(not f.error for f in result.multi_hop.findings), (
                            result.multi_hop
                        )
                    label = mode + ("+subagents" if agents else "")
                    snippet = " ".join(answer.text.split())[:95]
                    cited = ",".join(
                        str(rows.index(next(r for r in rows if r.id == c.item_id)) + 1)
                        for c in answer.citations
                    )
                    table.append(
                        f"{label:19} | {kind:6} | {snippet:95} | {cited:7} | {elapsed:6.2f}s | {calls} | SAME_AS={bridge_used} | spans={span_texts}"
                    )
                    print(table[-1], flush=True)
            print(
                "\nconfiguration       | query  | answer                                                                                          | items   | latency | tools"
            )
            print("\n".join(table))
        finally:
            if runtime is not None:
                await runtime.close()
            if writer is not None:
                try:
                    for group in groups.values():
                        await writer.ops.delete_group(group)
                        await writer.chunks.drop(group)
                finally:
                    await writer._graphiti.close()
                    await asyncio.to_thread(writer.chunks._client.close)
            client = getattr(llm, "_client", None)
            if client is not None:
                await client.close()
            await repo.close()
