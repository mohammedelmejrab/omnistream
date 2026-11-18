"""Offline BGE-large cutover for persisted vectors. Stop ingestion and queries first."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from time import perf_counter

from neo4j import GraphDatabase, RoutingControl

from omnistream.config import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    PROJECT_ROOT,
    Settings,
)
from omnistream.embeddings import EmbeddingService
from omnistream.graph.ops import GLOBAL_INDEX
from omnistream.retrieval.classic import (
    EMBEDDING_SIGNATURE_KEY,
    collection_name,
    make_chroma_client,
)

DIM = DEFAULT_EMBEDDING_DIM
BATCH = 32
STAGED_FOR = "reembed_staged_for"
SOURCES = {
    ("NODE", "Entity", "name_embedding"): ("MATCH (e:Entity)", "name"),
    ("NODE", "GlobalEntity", "name_embedding"): ("MATCH (e:GlobalEntity)", "name"),
    ("NODE", "Community", "name_embedding"): ("MATCH (e:Community)", "name"),
    ("RELATIONSHIP", "RELATES_TO", "fact_embedding"): (
        "MATCH ()-[e:RELATES_TO]->()",
        "fact",
    ),
}


def graph_inventory(driver):
    """Discover list-of-float properties, including lists that are not embeddings."""
    rows = []
    for kind, match, labels in (
        ("NODE", "MATCH (e)", "labels(e)"),
        ("RELATIONSHIP", "MATCH ()-[e]->()", "[type(e)]"),
    ):
        records = driver.execute_query(
            match + " UNWIND keys(e) AS property "
            "WITH e, property, valueType(e[property]) AS value_type "
            "WHERE value_type STARTS WITH 'LIST<FLOAT' OR value_type STARTS WITH 'VECTOR' "
            f"RETURN {labels} AS labels, e.group_id AS group_id, property, "
            "size(e[property]) AS dimension, count(*) AS count "
            "ORDER BY labels, group_id, property, dimension",
            routing_=RoutingControl.READ,
        ).records
        rows.extend({"kind": kind, **dict(row)} for row in records)
    return rows


def vector_indexes(driver):
    return [
        dict(row)
        for row in driver.execute_query(
            "SHOW INDEXES YIELD name, type, state, entityType, labelsOrTypes, "
            "properties, options WHERE type = 'VECTOR' RETURN * ORDER BY name",
            routing_=RoutingControl.READ,
        ).records
    ]


def rewrite_graph(driver, embeddings, groups, counts):
    for (_, label, prop), (match, source) in SOURCES.items():
        where = f" WHERE e.{prop} IS NOT NULL AND size(e.{prop}) <> $dim"
        if groups and label != "GlobalEntity":
            where += " AND e.group_id IN $groups"
        records = driver.execute_query(
            match
            + where
            + f" RETURN elementId(e) AS id, e.{source} AS text ORDER BY id",
            dim=DIM,
            groups=groups,
            routing_=RoutingControl.READ,
        ).records
        if any(
            not isinstance(row["text"], str) or not row["text"].strip()
            for row in records
        ):
            raise ValueError(f"{label}.{prop} has missing or blank source text")
        key = f"{label}.{prop}"
        counts[key] = 0
        for batch in batched(records, BATCH):
            # Entity and RELATES_TO ingestion takes Graphiti's batch path
            # (raw name/fact). Community uses generate_name_embedding.
            texts = [row["text"] for row in batch]
            inputs = (
                [t.replace("\n", " ") for t in texts] if label == "Community" else texts
            )
            vectors = embeddings.embed_documents(inputs).tolist()
            updates = [
                {"id": row["id"], "text": row["text"], "vector": vector}
                for row, vector in zip(batch, vectors, strict=True)
            ]

            with driver.session() as session:
                session.execute_write(write_graph_batch, match, source, prop, updates)
            counts[key] += len(batch)
            if counts[key] % 320 == 0 or counts[key] == len(records):
                print(f"{key}: {counts[key]}/{len(records)}", flush=True)


def write_graph_batch(tx, match, source, prop, updates):
    result = tx.run(
        "UNWIND $rows AS row "
        + match
        + f" WHERE elementId(e) = row.id AND e.{source} = row.text"
        + f" SET e.{prop} = row.vector RETURN count(*) AS count",
        rows=updates,
    ).single(strict=True)
    if result["count"] != len(updates):
        raise RuntimeError(f"{match}.{prop} changed during migration")


def quoted(identifier):
    return "`" + identifier.replace("`", "``") + "`"


def rebuild_indexes(driver, settings, indexes):
    expected = {
        settings.entity_index_name: ("NODE", "Entity", "name_embedding"),
        settings.fact_index_name: ("RELATIONSHIP", "RELATES_TO", "fact_embedding"),
        GLOBAL_INDEX: ("NODE", "GlobalEntity", "name_embedding"),
    }
    existing = {row["name"]: row for row in indexes}
    for name, row in existing.items():
        (label,), (prop,) = row["labelsOrTypes"], row["properties"]
        schema = (row["entityType"], label, prop)
        if schema not in expected.values():
            expected[name] = schema
        elif name not in expected:
            # Replace legacy names on the three app schemas with configured names.
            driver.execute_query(f"DROP INDEX {quoted(name)} IF EXISTS")
    for name, (kind, label, prop) in expected.items():
        row = existing.get(name)
        options = (row or {}).get("options", {}).get("indexConfig", {})
        if row and (
            options.get("vector.dimensions") != DIM
            or options.get("vector.similarity_function", "").lower() != "cosine"
            or row["entityType"] != kind
            or row["labelsOrTypes"] != [label]
            or row["properties"] != [prop]
        ):
            driver.execute_query(f"DROP INDEX {quoted(name)} IF EXISTS")
        pattern = (
            f"(e:{quoted(label)})" if kind == "NODE" else f"()-[e:{quoted(label)}]-()"
        )
        driver.execute_query(
            f"CREATE VECTOR INDEX {quoted(name)} IF NOT EXISTS "
            f"FOR {pattern} ON (e.{quoted(prop)}) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}",
            dim=DIM,
        )
        driver.execute_query("CALL db.awaitIndex($name, 300)", name=name)


def sqlite_db(path, *, write=False):
    return closing(
        sqlite3.connect(
            path.resolve().as_uri() + ("?mode=rw" if write else "?mode=ro"),
            uri=True,
        )
    )


def chroma_inventory(path):
    database = path / "chroma.sqlite3"
    if not database.is_file():
        return None
    with sqlite_db(database) as conn:
        return [
            {"name": name, "dimension": dim, "count": count, "signature": signature}
            for name, dim, count, signature in conn.execute(
                "SELECT c.name, c.dimension, count(e.id), m.str_value "
                "FROM collections c LEFT JOIN segments s ON s.collection=c.id AND s.scope='METADATA' "
                "LEFT JOIN embeddings e ON e.segment_id=s.id "
                "LEFT JOIN collection_metadata m ON m.collection_id=c.id AND m.key=? "
                "GROUP BY c.id ORDER BY c.name",
                (EMBEDDING_SIGNATURE_KEY,),
            )
        ]


def rewrite_chroma(path, embeddings, groups):
    client = make_chroma_client(path)
    selected = {collection_name(group) for group in groups}
    counts = {}
    try:
        collections = {
            col.name: client.get_collection(col.name, embedding_function=None)
            for col in client.list_collections()
        }
        stages = {}
        for col in collections.values():
            original = (col.metadata or {}).get(STAGED_FOR)
            if original is not None:
                stages[original] = col
        for name in sorted(set(collections) | stages.keys()):
            if (groups and name not in selected) or (
                name in collections
                and name != (collections[name].metadata or {}).get(STAGED_FOR, name)
            ):
                continue
            col = collections.get(name)
            stage = stages.get(name)
            if col is None:
                # An earlier run removed the old collection after staging all rows.
                stage.modify(name=name)
                col = stage
                stage = None
            metadata = dict(col.metadata or {})
            already_migrated = (
                metadata.get(EMBEDDING_SIGNATURE_KEY) == embeddings.index_signature
            )
            if not already_migrated:
                if stage is not None:
                    client.delete_collection(stage.name)
                stage_name = "reembed-" + hashlib.sha256(name.encode()).hexdigest()
                metadata.update(
                    {
                        EMBEDDING_SIGNATURE_KEY: embeddings.index_signature,
                        STAGED_FOR: name,
                    }
                )
                metadata.pop("hnsw:space", None)
                stage = client.create_collection(
                    stage_name,
                    embedding_function=None,
                    metadata=metadata,
                    configuration={"hnsw": {"space": "cosine"}},
                )
                count = col.count()
                for offset in range(0, count, BATCH):
                    page = col.get(
                        limit=BATCH,
                        offset=offset,
                        include=["documents", "metadatas", "uris"],
                    )
                    if any(text is None for text in page["documents"]):
                        raise ValueError(
                            f"{path}/{name} contains entries without documents"
                        )
                    stage.add(
                        ids=page["ids"],
                        documents=page["documents"],
                        metadatas=page["metadatas"],
                        uris=page["uris"],
                        embeddings=embeddings.embed_documents(
                            page["documents"]
                        ).tolist(),
                    )
                if stage.count() != count:
                    raise RuntimeError(
                        f"Chroma staging count mismatch for {path}/{name}"
                    )
                client.delete_collection(name)
                stage.modify(name=name)
                col = stage
                counts[name] = count
                print(f"{path}/{name}: {count}", flush=True)
            if STAGED_FOR in metadata:
                del metadata[STAGED_FOR]
                col.modify(metadata=metadata)
    finally:
        client.close()
    return counts


def bubble_rows(path):
    if not path.is_file():
        return []
    with sqlite_db(path) as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='bubbles'"
        ).fetchone():
            return []
        return conn.execute(
            "SELECT id, name, description, json_array_length(description_embedding) "
            "FROM bubbles WHERE json_type(description_embedding) = 'array' ORDER BY id"
        ).fetchall()


def rewrite_bubbles(path, rows, embeddings):
    for batch in batched(rows, BATCH):
        vectors = embeddings.embed_documents(
            [f"{name}: {desc}" for _, name, desc, _ in batch]
        )
        with sqlite_db(path, write=True) as conn, conn:
            for (ident, name, desc, _), vector in zip(batch, vectors, strict=True):
                result = conn.execute(
                    "UPDATE bubbles SET description_embedding=? WHERE id=? AND name=? AND description=?",
                    (json.dumps(vector.tolist()), ident, name, desc),
                )
                if result.rowcount != 1:
                    raise RuntimeError(
                        f"{path}: bubble {ident} changed during migration"
                    )


def validate_inventory(inventory):
    for row in inventory:
        if row["property"] == "credibilities" and row["labels"] == ["RELATES_TO"]:
            continue
        if not any(
            (row["kind"], label, row["property"]) in SOURCES for label in row["labels"]
        ):
            raise ValueError(
                f"Unmapped float-list property, inspect its writer first: {row}"
            )


def migrate(driver, settings, args, report):
    data = Path(settings.data_dir)
    snapshots = {
        p.parent.resolve()
        for base in (data, PROJECT_ROOT / "data")
        for p in (base / "snapshots").glob("*/chroma")
    }
    chroma = [data / "chroma", *(p / "chroma" for p in sorted(snapshots))]
    databases = [data / "omnistream.db", *(p / "state.db" for p in sorted(snapshots))]
    groups = args.groups
    report["graph_before"] = graph_inventory(driver)
    report["indexes_before"] = vector_indexes(driver)
    report["chroma_before"] = {str(p): chroma_inventory(p) for p in chroma}
    bubbles = {p: bubble_rows(p) for p in databases}
    report["bubble_descriptions_before"] = {
        str(p): [{"id": row[0], "dimension": row[3]} for row in rows]
        for p, rows in bubbles.items()
    }
    selected_collections = {collection_name(group) for group in groups}
    if groups:
        graph_groups = {row["group_id"] for row in report["graph_before"]}
        bubble_ids = {row[0] for rows in bubbles.values() for row in rows}
        collection_names = {
            row["name"]
            for rows in report["chroma_before"].values()
            for row in rows or []
        }
        unknown = [
            group
            for group in groups
            if group not in graph_groups
            and group not in bubble_ids
            and collection_name(group) not in collection_names
        ]
        if unknown:
            raise ValueError(f"Unknown migration groups: {unknown}")
    if args.dry_run:
        return

    validate_inventory(report["graph_before"])
    embeddings = EmbeddingService(
        settings,
        model_name=DEFAULT_EMBEDDING_MODEL,
        dimension=DIM,
        batch_size=BATCH,
    )
    # Load and validate the encoder before performing any writes.
    embeddings.embed_documents(["OmniStream embedding migration"])
    start = perf_counter()
    report["graph_updated"] = counts = {}
    rewrite_graph(driver, embeddings, groups, counts)
    report["graph_after"] = graph_inventory(driver)
    if any(
        row["dimension"] != DIM
        for row in report["graph_after"]
        if row["property"] != "credibilities"
        and (not groups or row["group_id"] in groups or "GlobalEntity" in row["labels"])
    ):
        raise RuntimeError(
            "Neo4j still contains incompatible embedding dimensions in scope"
        )
    rebuild_indexes(driver, settings, report["indexes_before"])
    report["indexes_after"] = vector_indexes(driver)
    for row in report["indexes_after"]:
        options = row["options"]["indexConfig"]
        if (
            row["state"] != "ONLINE"
            or options.get("vector.dimensions") != DIM
            or options.get("vector.similarity_function", "").lower() != "cosine"
        ):
            raise RuntimeError(
                f"Unexpected vector index configuration for {row['name']}"
            )
    report["graph_seconds"] = round(perf_counter() - start, 3)

    start = perf_counter()
    report["chroma_updated"] = updated = {}
    report["chroma_after"] = verified = {}
    for path in chroma:
        if report["chroma_before"][str(path)] is not None:
            updated[str(path)] = rewrite_chroma(path, embeddings, groups)
        verified[str(path)] = chroma_inventory(path)
        if any(
            row["signature"] != embeddings.index_signature
            or (row["count"] and row["dimension"] != DIM)
            for row in verified[str(path)] or []
            if not groups or row["name"] in selected_collections
        ):
            raise RuntimeError(
                f"{path} still contains incompatible collections in scope"
            )
    report["chroma_seconds"] = round(perf_counter() - start, 3)

    start = perf_counter()
    report["bubble_descriptions_updated"] = updated = {}
    for path, rows in bubbles.items():
        pending = [
            row for row in rows if row[3] != DIM and (not groups or row[0] in groups)
        ]
        rewrite_bubbles(path, pending, embeddings)
        updated[str(path)] = len(pending)
    report["bubble_descriptions_after"] = {
        str(p): [{"id": row[0], "dimension": row[3]} for row in bubble_rows(p)]
        for p in bubbles
    }
    if any(
        row["dimension"] != DIM
        for rows in report["bubble_descriptions_after"].values()
        for row in rows
        if not groups or row["id"] in groups
    ):
        raise RuntimeError(
            "SQLite still contains incompatible routing vectors in scope"
        )
    report["bubble_descriptions_seconds"] = round(perf_counter() - start, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read inventory without loading a model or changing stores",
    )
    parser.add_argument(
        "--groups",
        nargs="+",
        default=[],
        help="Migrate named groups and shared global entities. Keep the app offline until all groups are migrated.",
    )
    args = parser.parse_args()
    settings = Settings(_env_file=None)
    start = perf_counter()
    report = {
        "dry_run": args.dry_run,
        "groups": args.groups or "all",
        "target": f"{DEFAULT_EMBEDDING_MODEL}:{DIM}",
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = (
        PROJECT_ROOT / "docs" / "diagnostics" / f"reembed-bge-large-{stamp}.json"
    )
    try:
        with GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        ) as driver:
            migrate(driver, settings, args, report)
        report["status"] = "complete"
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        report["seconds"] = round(perf_counter() - start, 3)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(destination, flush=True)


if __name__ == "__main__":
    main()
