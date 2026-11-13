"""Snapshot construction through C1/C2/C3/C4; no fixed-bubble shortcuts."""

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

from omnistream.embed import SentenceTransformerEmbedder
from omnistream.graph.writer import build_graph_writer
from omnistream.ingest.intake import Intake
from omnistream.ingest.pipeline import ItemProcessor
from omnistream.ingest.queue import WorkerPool
from omnistream.llm import build_llm_client
from omnistream.models import ApiMapping, Bubble, RawItem, Source
from omnistream.router.bubbles import BubbleService
from omnistream.router.router import Router

DESCRIPTIONS = {
    "News": "Corporate leadership news, CEO appointments and replacements, public affairs and confirmed executive announcements. Includes speculative leadership rumors.",
    "Finance": "Business investments, funding agreements, analyst stock price targets and revisions, financial markets and company acquisitions.",
    "Research": "Scientific research, laboratory discoveries, experimental products, benchmark efficiency and publication accession codes.",
}


GENERIC_DESCRIPTIONS = {
    "News": "Public affairs, company announcements, leadership changes, product recalls and community events.",
    "Finance": "Financial markets, company investments, funding agreements, acquisitions and business performance.",
    "Research": "Scientific studies, research institutions, experimental methods and results, and scholarly publications.",
}


def save(path, data):

    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(path)


def snapshot_path(settings, name):

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError(
            "snapshot must be a safe name of 1-64 letters, digits, underscores or hyphens"
        )

    return Path(settings.data_dir).resolve() / "snapshots" / name


LEGACY_DATASETS = {
    "c7483a11f80d548ee71a09ec0d56b3dc11359471d5d3f17ca7239f05f28ee4e3": "eval-v1",
    "736b8035ebb4a9ebf1386bf33e76956a11cde470c575671a9fee51b2bb78634a": "eval-v2",
}


def item_digest(dataset):
    """Bind every item field (including labels/source/freshness), never questions."""
    return hashlib.sha256(
        json.dumps(
            sorted(dataset["items"], key=lambda i: i["id"]), sort_keys=True
        ).encode()
    ).hexdigest()


def bound_dataset(directory, requested=None, *, split=None, background=None):
    from .dataset import load_dataset

    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    name = manifest.get("dataset") or LEGACY_DATASETS.get(
        manifest.get("dataset_sha256")
    )
    if manifest and name is None:
        raise ValueError(
            "Unknown snapshot dataset SHA; explicit verified migration required"
        )
    if requested and name and requested != name:
        raise ValueError("--dataset conflicts with snapshot corpus binding")
    for key, value in (("split", split), ("background", background)):
        if value is not None and key in manifest and manifest[key] != value:
            raise ValueError(f"--{key} conflicts with snapshot binding")
    return load_dataset(
        name or requested or "eval-v1",
        split=manifest.get("split", split),
        background=manifest.get("background", background),
    )


def verify_item_store(directory, manifest, dataset):
    """Read-only DB/raw comparison before accepting a legacy content digest."""
    import sqlite3

    with sqlite3.connect(
        (directory / "state.db").resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        db.row_factory = sqlite3.Row
        stored = {r["id"]: r for r in db.execute("SELECT * FROM items")}
        sources = {r["id"]: r for r in db.execute("SELECT * FROM sources")}
    entries = manifest["items"]
    if set(entries) != {i["id"] for i in dataset["items"]} or len(stored) != len(
        entries
    ):
        raise ValueError("snapshot content mismatch: item IDs")
    for item in dataset["items"]:
        entry = entries[item["id"]]
        row = stored.get(entry["runtime_id"])
        source_id = directory.name + "-" + item["id"]
        source = sources.get(source_id)
        if row is None or source is None:
            raise ValueError("snapshot content mismatch: " + item["id"])
        matches = (
            row["source_id"] == source_id,
            row["url"] == item["url"] + "?snapshot=" + directory.name,
            row["title"] == item["title"],
            datetime.fromisoformat(row["published_at"]).replace(tzinfo=None)
            == datetime.fromisoformat(item["published_at"]).replace(tzinfo=None),
            source["url"] == item["url"],
            source["credibility"] == item["credibility"],
            set(json.loads(row["bubble_ids"])) == set(entry["bubbles"]),
            bool(item["freshness"]) == (item["id"] in manifest["freshness"]),
            Path(row["text_path"]).read_text(encoding="utf-8") == item["text"],
            Path(row["raw_path"]).read_text(encoding="utf-8") == item["text"],
        )
        if not all(matches):
            raise ValueError("snapshot content mismatch: " + item["id"])
    return item_digest(dataset)


def migrate_manifest(directory, dataset):
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    name = manifest.get("dataset") or LEGACY_DATASETS.get(
        manifest.get("dataset_sha256")
    )
    if name is None:
        raise ValueError("Unknown legacy dataset SHA")
    legacy_items = {
        "eval-v1": "13a4a0f75917bbf99741098f9e679c2ebdb9d6dfd918dd3ca7f09d9da5fdd85d",
        "eval-v2": "53c2e8cc0a96a622584986b5d5b7d8884e0042553d8c652d47476b4ac1103e68",
    }
    if (
        manifest.get("dataset_sha256") in LEGACY_DATASETS
        and item_digest(dataset) != legacy_items[name]
    ):
        raise ValueError("Legacy item content/labels changed; refusing migration")
    digest = verify_item_store(directory, manifest, dataset)
    if manifest.get("item_content_sha256") not in (None, digest):
        raise ValueError("snapshot content digest mismatch")
    manifest.update(dataset=name, item_content_sha256=digest)
    save(path, manifest)
    return f"{directory.name}: verified {len(dataset['items'])} DB/raw items; dataset={name}; item_content_sha256={digest}; no re-ingestion"


class SnapshotBuilder:
    def __init__(self, settings, repo, dataset, name, progress):

        self.settings, self.repo, self.dataset, self.name, self.progress = (
            settings,
            repo,
            dataset,
            name,
            progress,
        )

        self.path = snapshot_path(settings, name)
        self.path.mkdir(parents=True, exist_ok=True)

        self.manifest_path = self.path / "manifest.json"

        digest = hashlib.sha256(
            json.dumps(dataset, sort_keys=True).encode()
        ).hexdigest()

        self.manifest = (
            json.loads(self.manifest_path.read_text())
            if self.manifest_path.exists()
            else {
                "dataset_sha256": digest,
                "dataset": dataset.get("corpus")
                or ("eval-v2" if dataset["version"].startswith("2") else "eval-v1"),
                **{
                    k: dataset[k]
                    for k in (
                        "split",
                        "background",
                        "selection_seed",
                        "selected_item_ids",
                        "selected_item_ids_sha256",
                    )
                    if k in dataset
                },
                "item_content_sha256": item_digest(dataset),
                "construction_started_at": time.time(),
                "items": {},
                "frozen": False,
                "freshness": {},
            }
        )

        if "item_content_sha256" not in self.manifest:
            message = migrate_manifest(self.path, dataset)
            print(message, flush=True)
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if self.manifest["item_content_sha256"] != item_digest(dataset):
            raise ValueError(
                "dataset changed: item content differs; use a new snapshot"
            )
        for key in (
            "split",
            "background",
            "selected_item_ids",
            "selected_item_ids_sha256",
        ):
            if key in dataset and self.manifest.get(key) != dataset[key]:
                raise ValueError("snapshot selection binding mismatch: " + key)

        self.local_settings = settings.model_copy(
            update={"data_dir": str(self.path), "llm_max_concurrency": 2}
        )

        self.embedder = SentenceTransformerEmbedder(settings.embed_model)

        self.groups = {name: f"{self.name}-{name.lower()}" for name in DESCRIPTIONS}

        self.writer = None
        self.llm = None

    async def verify_frozen(self):
        """Freeze a complete matching snapshot without invoking any ingestion code."""
        entries = self.manifest["items"]
        expected = {i["id"] for i in self.dataset["items"]}
        if set(entries) != expected:
            if self.manifest.get("frozen"):
                raise ValueError("frozen snapshot item set is incomplete")
            return False
        missing_freshness = {
            i["id"] for i in self.dataset["items"] if i["freshness"]
        } - self.manifest["freshness"].keys()
        if missing_freshness:
            if self.manifest.get("frozen"):
                raise ValueError("frozen snapshot lacks recorded freshness measurements")
            return False
        stored = {i.id: i for i in await self.repo.list_items()}
        jobs = await self.repo.list_jobs()
        if len(stored) != len(expected) or any(
            e.get("status") != "written"
            or e["runtime_id"] not in stored
            or stored[e["runtime_id"]].status != "written"
            or not any(j.item_id == e["runtime_id"] and j.state == "done" for j in jobs)
            for e in entries.values()
        ):
            raise ValueError("snapshot is incomplete: refusing automatic re-ingestion")
        digest = verify_item_store(self.path, self.manifest, self.dataset)
        if digest != self.manifest["item_content_sha256"]:
            raise ValueError("snapshot content digest mismatch")
        self.manifest.setdefault("frozen_at", time.time())
        self.manifest["frozen"] = True
        save(self.manifest_path, self.manifest)
        return True

    async def initialize(self):

        service = BubbleService(self.repo, self.embedder)

        for name, desc in (
            GENERIC_DESCRIPTIONS
            if self.dataset["version"].startswith("2")
            else DESCRIPTIONS
        ).items():
            if await self.repo.get_bubble(self.groups[name]) is None:
                await service.create(
                    Bubble(
                        id=self.groups[name],
                        name=name,
                        description=desc,
                        half_life_days={"News": 3, "Finance": 30, "Research": 365}[
                            name
                        ],
                    )
                )

        self.llm = build_llm_client(self.local_settings)

        self.writer = await build_graph_writer(
            self.local_settings, self.repo, self.embedder, self.llm
        )

        router = Router(
            self.llm,
            self.settings.llm_model,
            self.embedder,
            self.settings.router_threshold,
            self.settings.router_top_k,
        )

        # Catalog isolation is necessary when an application database contains other bubbles.

        processor = ItemProcessor(self.repo, router, self.writer)

        self.pool = WorkerPool(
            self.repo, processor.process_item, workers=1, max_attempts=3, backoff_base=1
        )

        self.intake = Intake(
            self.repo, str(self.path), self.settings.prefilter_min_chars
        )

    async def ingest(self, item):

        if self.manifest.get("frozen"):
            raise ValueError("cannot ingest into a frozen snapshot")

        existing = self.manifest["items"].get(item["id"])

        if existing:
            stored = await self.repo.get_item(existing["runtime_id"])

            if stored and stored.status in ("written", "unsorted", "failed"):
                return stored

        from .resources import stage

        stage_token = stage.set("ingestion:" + item["id"])
        source = Source(
            id=f"{self.name}-{item['id']}",
            type="api",
            url=item["url"],
            credibility=item["credibility"],
            api_mapping=ApiMapping(
                items="$[*]", body="$.text", url="$.url", date="$.published_at"
            ),
            bubble_ids=[],
            poll_interval=self.settings.poll_interval_minutes * 60,
            max_items_per_hour=1000,
        )

        await self.repo.upsert_source(source)

        raw = RawItem(
            source_id=source.id,
            url=item["url"] + "?snapshot=" + self.name,
            title=item["title"],
            text=item["text"],
            published_at=datetime.fromisoformat(item["published_at"]),
        )

        start = time.time()

        row = await self.intake.accept(raw, source, item["text"].encode(), "txt")

        if row is None:
            candidates = [
                r for r in await self.repo.list_items() if r.source_id == source.id
            ]

            if not candidates:
                raise RuntimeError("deduplicated item has no record")

            row = candidates[0]

        self.manifest["items"][item["id"]] = {
            "runtime_id": row.id,
            "injected_at": start,
        }

        save(self.manifest_path, self.manifest)

        import asyncio

        # The snapshot uses an isolated SQLite queue; run the real worker retry path.

        await self.repo.requeue_running_jobs()

        for attempt in range(100):
            await self.pool.run_once()

            stored = await self.repo.get_item(row.id)

            jobs = [j for j in await self.repo.list_jobs() if j.item_id == row.id]

            if jobs[-1].state in ("done", "failed"):
                break

            await asyncio.sleep(0.5)

        stored = await self.repo.get_item(row.id)

        entry = self.manifest["items"][item["id"]]

        entry.update(
            status=stored.status,
            bubbles=stored.bubble_ids,
            route_confidence=stored.route_confidence,
            queue_attempts=jobs[-1].attempts,
            write_lag_seconds=time.time() - start
            if stored.status == "written"
            else None,
        )

        if getattr(self, "meter", None):
            entry["usage"] = self.meter.summary().get("ingestion:" + item["id"])
        save(self.manifest_path, self.manifest)
        stage.reset(stage_token)

        await self.progress(
            f"Ingested {len(self.manifest['items'])}/{len(self.dataset['items'])}: {item['id']} ({stored.status})"
        )

        return stored

    async def base(self):

        if self.manifest.get("frozen"):
            return

        for item in sorted(
            (i for i in self.dataset["items"] if not i["freshness"]),
            key=lambda i: (i["published_at"], i["id"]),
        ):
            await self.ingest(item)

    async def close(self):

        if self.writer is not None:
            await self.writer._graphiti.close()

            await __import__("asyncio").to_thread(self.writer.chunks._client.close)

        if self.llm is not None:
            await self.llm._client.close()
