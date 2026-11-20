"""Serves the real FastAPI app for the browser tests (web/e2e).

Seeded SQLite database in a fresh temporary folder, the fake model runtime from
tests/unit/ui_support.py (no network, no models, no Neo4j), and the built React app
under /app. Usage: python serve_e2e.py <port>

OMNISTREAM_E2E_RETRIEVE_DELAY_MS slows the own retrieval so a run stays live long
enough to watch it stream.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import uvicorn  # noqa: E402

from omnistream.api.app import create_app  # noqa: E402
from omnistream.config import Settings  # noqa: E402
from omnistream.db import Repository  # noqa: E402
from omnistream.db.tables import ItemRow  # noqa: E402
from omnistream.ingest.intake import Intake  # noqa: E402
from omnistream.models import Bubble  # noqa: E402
from omnistream.router.bubbles import BubbleLifecycle  # noqa: E402
from tests.conftest import FakeChunks, FakeEmbedder  # noqa: E402
from tests.unit.ui_support import FakeDispatcher, FakeRetriever, FakeRuntime, GraphOps, fake_scheduler  # noqa: E402


class DelayedRetriever(FakeRetriever):
    def retrieve(self, question, **kwargs):  # type: ignore[override]
        delay_ms = float(os.environ.get("OMNISTREAM_E2E_RETRIEVE_DELAY_MS", "0") or 0)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
        return super().retrieve(question, **kwargs)


async def seed(repo: Repository) -> None:
    now = datetime.now(UTC)
    for bubble_id, name in (("news", "News"), ("finance", "Finance")):
        await repo.create_bubble(Bubble(id=bubble_id, name=name, description=f"{name} desk", updated_at=now))
    await repo.create_item(
        ItemRow(id="i1", source_id="src", url="https://example.test/i1", title="Item one", status="written")
    )


def build(data_dir: Path):
    settings = Settings(_env_file=None, llm_api_key="sk-e2e-not-a-real-key")
    repo = Repository.from_path(str(data_dir / "omni.db"), settings=settings)
    asyncio.run(seed(repo))
    lifecycle = BubbleLifecycle(repo, FakeEmbedder(), SimpleNamespace(), GraphOps(), FakeChunks())
    retriever = DelayedRetriever()
    return create_app(
        repo,
        fake_scheduler(),
        lifecycle,
        Intake(repo, str(data_dir), 0),
        settings,
        runtime_factory=lambda _s, _r: FakeRuntime(
            dispatcher=FakeDispatcher(retriever), settings=settings
        ),
        web_dist=REPO / "web" / "dist",
    )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    with tempfile.TemporaryDirectory(prefix="omnistream-e2e-") as tmp:
        app = build(Path(tmp))
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
