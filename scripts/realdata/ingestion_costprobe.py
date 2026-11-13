"""Bounded ten-item ingestion measurement; never constructs a full snapshot.

Provide LLM_API_KEY in the environment (never reads .env). NEO4J_PASSWORD must
also be set. Results survive cleanup in docs/realdata/real-v2-costprobe.json.
"""

import asyncio
import json
import logging
import random
import shutil
import time
from pathlib import Path

from neo4j import GraphDatabase

from omnistream.config import Settings
from omnistream.db import Repository
from omnistream.eval.resources import UsageMeter
from omnistream.eval.snapshot import SnapshotBuilder, save, snapshot_path
from omnistream.sources.documents import split_episodes

NAME = "real-v2-costprobe"
SEED = 20261113
OUTPUT = Path("docs/realdata/real-v2-costprobe.json")


def sample(rows):
    """Source and length strata, chosen without reference to question answers."""
    rng = random.Random(SEED)

    def choose(pool, n):
        return rng.sample(sorted(pool, key=lambda r: r["id"]), n)

    news = [r for r in rows if r["bubble_hint"] == "news"]
    finance = [r for r in rows if r["bubble_hint"] == "finance"]
    research = [r for r in rows if r["bubble_hint"] == "research"]
    selected = choose(
        [r for r in news if "blog" in r["source"] and r["word_count"] >= 1500], 2
    )
    selected += choose([r for r in news if r["word_count"] < 600], 1)
    exhibits = [
        r
        for r in finance
        if r["source"].startswith("edgar-") and ": exhibit " in r["title"]
    ]
    selected += choose([r for r in exhibits if r["word_count"] < 1500], 1)
    selected += choose([r for r in exhibits if r["word_count"] >= 1500], 1)
    selected += choose(
        [r for r in finance if r not in exhibits and r["word_count"] < 700], 1
    )
    selected += choose(
        [
            r
            for r in research
            if r["content_kind"] == "abstract" and r["word_count"] < 200
        ],
        1,
    )
    selected += choose(
        [
            r
            for r in research
            if r["content_kind"] == "abstract" and r["word_count"] >= 200
        ],
        1,
    )
    selected += choose(
        [
            r
            for r in research
            if r["content_kind"] != "abstract" and r["word_count"] < 1500
        ],
        1,
    )
    selected += choose(
        [
            r
            for r in research
            if r["content_kind"] != "abstract" and r["word_count"] >= 1500
        ],
        1,
    )
    assert len({r["id"] for r in selected}) == 10
    return selected


class BudgetMeter(UsageMeter):
    """Reserve worst-case request cost before sending, including concurrent calls.

    UTF-8 bytes conservatively bound input token counts. Reservations use the
    existing requested output limit; no prompts or model parameters are changed.
    Missing usage and failed requests retain the reservation as a conservative
    charge. Stop at $0.55, leaving $0.05 headroom below the task cap.
    """

    def __init__(self):
        super().__init__()
        self.charged = 0.0
        self.pending = 0.0

    def reserve(self, kwargs):
        if kwargs["model"] != "deepseek/deepseek-v4.1-flash-1017":
            raise RuntimeError("unexpected model in probe")
        output = kwargs.get("max_completion_tokens") or kwargs.get("max_tokens")
        if not output:
            raise RuntimeError("cannot bound request without output limit")
        input_bound = (
            len(json.dumps(kwargs, ensure_ascii=False, default=str).encode()) + 1024
        )
        reserve = (input_bound * 0.15 + output * 0.60) / 1_000_000
        with self.lock:
            if self.charged + self.pending + reserve > 0.55:
                raise RuntimeError("probe budget guard stopped request")
            self.pending += reserve
        return reserve

    def settle(self, reserve, response=None):
        usage = getattr(response, "usage", None)
        reported = (getattr(usage, "model_extra", None) or {}).get("cost")
        with self.lock:
            self.pending -= reserve
            self.charged += float(reported) if reported is not None else reserve

    def __enter__(self):
        super().__enter__()
        from openai.resources.chat.completions import AsyncCompletions, Completions

        metered_sync, metered_async = Completions.create, AsyncCompletions.create

        def sync(client, *args, **kwargs):
            reserve = self.reserve(kwargs)
            response = None
            try:
                response = metered_sync(client, *args, **kwargs)
                return response
            finally:
                self.settle(reserve, response)

        async def async_(client, *args, **kwargs):
            reserve = self.reserve(kwargs)
            response = None
            try:
                response = await metered_async(client, *args, **kwargs)
                return response
            finally:
                self.settle(reserve, response)

        Completions.create, AsyncCompletions.create = sync, async_
        return self


def cleanup(settings, directory, result):
    """Delete only probe groups and newly orphaned linked globals."""
    expected = Path(settings.data_dir).resolve() / "snapshots" / NAME
    if directory != expected or directory.name != NAME:
        raise ValueError("unsafe probe cleanup path")
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        with driver.session() as session:
            groups = [NAME + "-" + b for b in ("news", "finance", "research")]
            globals_ = [
                r["id"]
                for r in session.run(
                    "MATCH (e:Entity)-[:SAME_AS]->(g:GlobalEntity) WHERE e.group_id IN $groups RETURN DISTINCT g.uuid AS id",
                    groups=groups,
                )
            ]
            session.run(
                "MATCH (n) WHERE n.group_id IN $groups DETACH DELETE n", groups=groups
            ).consume()
            session.run(
                "MATCH (g:GlobalEntity) WHERE g.uuid IN $ids AND NOT (g)<-[:SAME_AS]-() DETACH DELETE g",
                ids=globals_,
            ).consume()
            result["remaining_prefix_nodes"] = session.run(
                "MATCH (n) WHERE n.group_id STARTS WITH $prefix RETURN count(n) AS n",
                prefix=NAME,
            ).single()["n"]
        if directory.exists():
            shutil.rmtree(directory)
        result["snapshot_directory_removed"] = not directory.exists()
        assert result["remaining_prefix_nodes"] == 0
    finally:
        driver.close()


async def main():
    settings = Settings(_env_file=None)
    if not settings.has_llm_credentials:
        raise RuntimeError("LLM_API_KEY required; .env is never read")
    if settings.llm_model != "deepseek/deepseek-v4.1-flash-1017":
        raise RuntimeError("unexpected configured model")
    directory = snapshot_path(settings, NAME)
    if directory.exists():
        raise RuntimeError("probe directory exists; inspect before retry")
    rows = [
        json.loads(line)
        for line in Path("src/omnistream/eval/real/real-v2-manifest.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    selected = sample(rows)
    items = [
        {
            **r,
            "text": Path(r["text_path"]).read_text(encoding="utf-8"),
            "bubbles": [],
            "freshness": False,
            "credibility": r.get("credibility", 0.5),
        }
        for r in selected
    ]
    result = {
        "seed": SEED,
        "model": settings.llm_model,
        "sample": selected,
        "items": [],
        "status": "running",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    save(OUTPUT, result)
    repo = Repository.from_path(str(directory / "state.db"), settings=settings)

    async def progress(message):
        print(message, flush=True)

    builder = SnapshotBuilder(
        settings,
        repo,
        {"version": "2-real", "corpus": "real-v2", "items": items, "questions": []},
        NAME,
        progress,
    )
    meter = BudgetMeter()
    try:
        with meter:
            builder.meter = meter
            await builder.initialize()
            for item in items:
                started = time.perf_counter()
                before = {
                    g: await builder.writer.ops.group_counts(g)
                    for g in builder.groups.values()
                }
                stored = await builder.ingest(item)
                after = {
                    g: await builder.writer.ops.group_counts(g)
                    for g in builder.groups.values()
                }
                counts = {
                    key: sum(after[g][key] - before[g][key] for g in before)
                    for key in ("episodes", "entities", "facts")
                }
                measured = {
                    "id": item["id"],
                    "title": item["title"],
                    "bubble_hint": item["bubble_hint"],
                    "source": item["source"],
                    "words": len(item["text"].split()),
                    "manifest_words": item["word_count"],
                    "wall_seconds": time.perf_counter() - started,
                    "document_split_episodes": len(
                        split_episodes(item["text"], settings.document_episode_tokens)
                    ),
                    "status": stored.status,
                    "bubbles": stored.bubble_ids,
                    **counts,
                    "usage": meter.summary().get("ingestion:" + item["id"]),
                }
                result["items"].append(measured)
                result["usage_by_stage"] = meter.summary()
                save(OUTPUT, result)
                print(json.dumps(measured), flush=True)
                if stored.status != "written":
                    raise RuntimeError("probe item did not complete")
            result["status"] = "completed"
    except Exception as exc:
        result["status"] = "failed"
        result["error_type"] = type(exc).__name__
        raise
    finally:
        result["usage_by_stage"] = meter.summary()
        result["conservative_budget_charge_usd"] = meter.charged
        try:
            await builder.close()
        finally:
            await repo.close()
            cleanup(settings, directory, result)
            save(OUTPUT, result)


if __name__ == "__main__":
    # Provider/debug logs are not needed for this cost-only measurement.
    logging.basicConfig(level=logging.CRITICAL)
    asyncio.run(main())
