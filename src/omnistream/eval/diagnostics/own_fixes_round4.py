"""Frozen eval-v2 passage seed ablation. Run from repository root."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openai.resources.chat.completions import AsyncCompletions, Completions

from omnistream.config import Settings
from omnistream.embeddings import EmbeddingService
from omnistream.eval.diagnostics.own_fixes import fixed_routes
from omnistream.eval.diagnostics.own_fixes_round3 import forbidden
from omnistream.eval.diagnostics.run import DATA, GROUPS, IDS, SNAP, read
from omnistream.eval.metrics import retrieval_metrics
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.retrieval.classic import ClassicRetriever, make_chroma_client
from omnistream.retrieval.models import TimeScope
from omnistream.retrieval.own_algorithm.passages import PassageSource
from omnistream.retrieval.own_algorithm.pipeline import OwnRetriever

OUT = Path("data/diagnostics/own-fixes-round4")
MODES = ("round3", "passage", "passage_specificity")


def measure(graph, embeddings, classic, frozen):
    routes = fixed_routes()
    source = PassageSource(classic, graph)
    retrievers = {
        mode: OwnRetriever(
            graph,
            embeddings,
            now=lambda: frozen,
            half_lives=dict(zip(GROUPS, (3, 30, 365))),
            passage_source=source if mode != "round3" else None,
            specificity_restart=mode == "passage_specificity",
        )
        for mode in MODES
    }
    for question in DATA["questions"]:
        raw, origin = routes[question["id"]]
        scope = raw.get("time_scope")
        if scope:
            scope = TimeScope(
                **{
                    k: datetime.fromisoformat(v) if v else None
                    for k, v in scope.items()
                }
            )
        gold = {IDS[g] for g in question["gold"]}
        for routing, bubbles in (("current", raw["bubbles"]), ("oracle", GROUPS)):
            for mode, retriever in retrievers.items():
                result = retriever.retrieve(
                    question["question"],
                    bubbles=bubbles,
                    time_scope=scope,
                    excluded_bubbles=raw.get("excluded_bubbles", ()),
                )
                ids = list(
                    dict.fromkeys(
                        i
                        for f in result.facts
                        for i in (f.fact.item_id, *f.fact.item_ids)
                    )
                )
                recall = len(gold.intersection(ids)) / len(gold)
                yield dict(
                    question_id=question["id"],
                    type=question["type"],
                    routing=routing,
                    route_source=origin,
                    variant=mode,
                    recall_any=recall,
                    full_coverage=int(recall == 1),
                    **retrieval_metrics(ids, gold),
                    retrieved_item_ids=ids,
                    seed_ids=[s.id for s in result.seeds],
                )
        print(question["id"], flush=True)


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    cfg = Settings(_env_file=None)
    frozen = datetime.fromisoformat(read("metadata")[0]["time"])
    OUT.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(Completions, "create", forbidden),
        patch.object(AsyncCompletions, "create", forbidden),
        TemporaryDirectory() as tmp,
    ):
        copied = shutil.copytree(SNAP / "chroma", Path(tmp) / "chroma")
        client = make_chroma_client(copied)
        graph = Neo4jGraphStore.from_settings(cfg)
        graph.exact_search = True
        graph.now = lambda: frozen
        embeddings = EmbeddingService(cfg)
        classic = ClassicRetriever(client, embeddings)
        try:
            with (OUT / "offline.jsonl").open("w", encoding="utf-8") as journal:
                for row in measure(graph, embeddings, classic, frozen):
                    journal.write(json.dumps(row) + "\n")
                    journal.flush()
        finally:
            graph.driver.close()
            client.close()


if __name__ == "__main__":
    main()
