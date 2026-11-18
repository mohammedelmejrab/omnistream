"""Backfill tool: merge source-evidenced alias/abbreviation splits (ingestion item 3).

Reads Episodic nodes (their content) and their MENTIONS entities from Neo4j for a
set of group ids, finds source-stated ``(full, short)`` pairs that are stored as
separate GlobalEntities, and plans the merge.  Dry run is the default and writes a
JSON + Markdown plan to ``docs/diagnostics/alias-merge-dryrun-<groups>.{json,md}``.

``--apply`` performs the merges (re-pointing SAME_AS edges to the surviving
GlobalEntity, recording aliases, and tagging every changed node/relationship with
``alias_merge_run``); ``--revert <run id>`` undoes a previous apply from its
manifest.  This task only ever *plans*; do not run ``--apply`` here.

Neo4j is read-only unless ``--apply``/``--revert`` is given.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from omnistream.config import PROJECT_ROOT, Settings
from omnistream.graph.aliases import (
    extract_alias_pairs,
    name_key,
    names_differ_by_number,
    types_compatible,
)

DOCS_DIR = PROJECT_ROOT / "docs" / "diagnostics"

_MERGE = "merge"
_ALREADY = "already_merged"
_MISSING = "missing_side"
_REFUSED_TYPE = "refused_type_conflict"
_REFUSED_NUMBER = "refused_number_token"
_REFUSED_AMBIGUITY = "refused_ambiguity"


@dataclass
class EpisodeRec:
    uuid: str
    group_id: str
    content: str
    item_id: str | None = None


@dataclass
class EntityRec:
    uuid: str
    name: str
    type: str
    global_id: str | None = None


@dataclass
class GlobalRec:
    uuid: str
    name: str
    type: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class PairMatch:
    full: str
    short: str
    source: str
    full_entities: list[str] = field(default_factory=list)
    short_entities: list[str] = field(default_factory=list)
    full_global: str | None = None
    short_global: str | None = None
    full_type: str | None = None
    short_type: str | None = None
    decision: str = _MERGE
    same_as_edges_changed: int = 0
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "full": self.full,
            "short": self.short,
            "source": self.source,
            "full_entities": self.full_entities,
            "short_entities": self.short_entities,
            "full_global": self.full_global,
            "short_global": self.short_global,
            "full_type": self.full_type,
            "short_type": self.short_type,
            "decision": self.decision,
            "same_as_edges_changed": self.same_as_edges_changed,
            "reason": self.reason,
        }


@dataclass
class MergePlan:
    groups: list[str]
    pairs: list[PairMatch] = field(default_factory=list)

    def merges(self) -> list[PairMatch]:
        return [p for p in self.pairs if p.decision == _MERGE]

    def refusals(self) -> list[PairMatch]:
        return [p for p in self.pairs if p.decision.startswith("refused_")]

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for p in self.pairs:
            counts[p.decision] = counts.get(p.decision, 0) + 1
        edges = sum(p.same_as_edges_changed for p in self.merges())
        return {
            "groups": self.groups,
            "pairs_found": len(self.pairs),
            "merges": len(self.merges()),
            "same_as_edges_to_change": edges,
            "already_merged": counts.get(_ALREADY, 0),
            "missing_side": counts.get(_MISSING, 0),
            "refused_type_conflict": counts.get(_REFUSED_TYPE, 0),
            "refused_number_token": counts.get(_REFUSED_NUMBER, 0),
            "refused_ambiguity": counts.get(_REFUSED_AMBIGUITY, 0),
        }


def _type_of(rec: GlobalRec | EntityRec | None) -> str | None:
    return getattr(rec, "type", None) or None


def plan_alias_merges(
    episodes: list[EpisodeRec],
    entities: list[EntityRec],
    globals: list[GlobalRec],
) -> MergePlan:
    """Plan source-evidenced alias merges (pure; testable against a fake store)."""
    groups = sorted({e.group_id for e in episodes})
    plan = MergePlan(groups=groups)

    by_name: dict[str, list[EntityRec]] = {}
    for ent in entities:
        by_name.setdefault(name_key(ent.name), []).append(ent)

    gmap = {g.uuid: g for g in globals}

    # Extract pairs per episode, tracking the source (episode uuid / item id).
    raw_pairs: list[tuple[str, str, str]] = []
    for ep in episodes:
        for full, short in extract_alias_pairs(ep.content):
            raw_pairs.append((full, short, ep.item_id or ep.uuid))

    # Deduplicate identical (full, short) pairs, keeping the first source.
    unique: dict[tuple[str, str], tuple[str, str, str]] = {}
    for full, short, src in raw_pairs:
        key = (name_key(full), name_key(short))
        unique.setdefault(key, (full, short, src))
    ordered = list(unique.values())

    # Ambiguity: a short form that maps to more than one distinct full name.
    short_to_fulls: dict[str, set[str]] = {}
    full_to_shorts: dict[str, set[str]] = {}
    for full, short, _src in ordered:
        short_to_fulls.setdefault(name_key(short), set()).add(name_key(full))
        full_to_shorts.setdefault(name_key(full), set()).add(name_key(short))
    ambiguous_shorts = {s for s, fs in short_to_fulls.items() if len(fs) > 1}
    ambiguous_fulls = {f for f, ss in full_to_shorts.items() if len(ss) > 1}

    def side_global(recs: list[EntityRec]) -> tuple[str | None, str | None]:
        gids = {r.global_id for r in recs if r.global_id}
        gid = next(iter(gids)) if len(gids) == 1 else None
        typ = None
        if gid and gid in gmap:
            typ = gmap[gid].type
        elif recs:
            typ = recs[0].type
        return gid, typ

    for full, short, src in ordered:
        full_recs = by_name.get(name_key(full), [])
        short_recs = by_name.get(name_key(short), [])
        match = PairMatch(full=full, short=short, source=src)
        match.full_entities = sorted(r.uuid for r in full_recs)
        match.short_entities = sorted(r.uuid for r in short_recs)
        match.full_global, match.full_type = side_global(full_recs)
        match.short_global, match.short_type = side_global(short_recs)

        if not full_recs or not short_recs:
            match.decision = _MISSING
            match.reason = (
                "missing " + ("full" if not full_recs else "short") + " entity side"
            )
        elif match.full_global and match.full_global == match.short_global:
            match.decision = _ALREADY
            match.reason = "already share a GlobalEntity"
        elif (
            name_key(short) in ambiguous_shorts or name_key(full) in ambiguous_fulls
        ):
            match.decision = _REFUSED_AMBIGUITY
            match.reason = "short form matches more than one full name"
        elif names_differ_by_number(full, short):
            match.decision = _REFUSED_NUMBER
            match.reason = "names differ by a number token"
        elif (
            match.full_type
            and match.short_type
            and not types_compatible(match.full_type, match.short_type)
        ):
            match.decision = _REFUSED_TYPE
            match.reason = (
                f"type conflict {match.full_type!r} vs {match.short_type!r}"
            )
        else:
            surviving = match.full_global or match.short_global
            if surviving == match.full_global:
                match.same_as_edges_changed = len(match.short_entities)
            elif surviving == match.short_global:
                match.same_as_edges_changed = len(match.full_entities)
            else:
                match.same_as_edges_changed = 0
                match.reason = "no surviving GlobalEntity on either side"
        plan.pairs.append(match)
    return plan


# --------------------------------------------------------------------------
# Neo4j read (read-only) and apply/revert
# --------------------------------------------------------------------------


def _entity_type(labels: list[str]) -> str:
    return next(
        (label for label in sorted(labels) if label != "Entity"), "Entity"
    )


def load_neo4j(driver, groups: list[str]):
    """Read episodes (content + MENTIONS), entities and GlobalEntities."""
    episodes: list[EpisodeRec] = []
    entities: list[EntityRec] = []
    globals_by_id: dict[str, GlobalRec] = {}

    with driver.session() as session:
        for row in session.run(
            "MATCH (ep:Episodic) WHERE ep.group_id IN $groups "
            "RETURN ep.uuid AS uuid, ep.group_id AS group_id, ep.content AS content, "
            "ep.item_id AS item_id ORDER BY ep.uuid",
            groups=groups,
        ):
            episodes.append(
                EpisodeRec(
                    row["uuid"], row["group_id"], row["content"] or "", row["item_id"]
                )
            )
        for row in session.run(
            "MATCH (e:Entity) WHERE e.group_id IN $groups "
            "OPTIONAL MATCH (e)-[:SAME_AS]->(g:GlobalEntity) "
            "RETURN e.uuid AS uuid, e.name AS name, labels(e) AS labels, "
            "g.uuid AS global_id ORDER BY e.uuid",
            groups=groups,
        ):
            entities.append(
                EntityRec(
                    row["uuid"],
                    row["name"],
                    _entity_type(list(row["labels"])),
                    row["global_id"],
                )
            )
        for row in session.run(
            "MATCH (e:Entity)-[:SAME_AS]->(g:GlobalEntity) "
            "WHERE e.group_id IN $groups "
            "RETURN DISTINCT g.uuid AS uuid, g.name AS name, g.type AS type, "
            "g.aliases AS aliases",
            groups=groups,
        ):
            globals_by_id[row["uuid"]] = GlobalRec(
                row["uuid"],
                row["name"],
                row["type"] or "Entity",
                list(row["aliases"] or []),
            )
    return episodes, entities, list(globals_by_id.values())


def make_run_id() -> str:
    return datetime.now(UTC).strftime("alias-merge-%Y%m%dT%H%M%SZ")


def apply_plan(driver, plan: MergePlan, run_id: str) -> str:
    """Execute the planned merges; returns the manifest path.

    Re-points the non-surviving side's SAME_AS edges to the surviving
    GlobalEntity, records aliases, and tags every changed node/relationship with
    ``alias_merge_run``.  A manifest is written so ``--revert`` can undo it.
    """
    merges = plan.merges()
    manifest = {
        "run_id": run_id,
        "groups": plan.groups,
        "created_at": datetime.now(UTC).isoformat(),
        "merges": [],
    }
    for m in merges:
        surviving = m.full_global or m.short_global
        if not surviving:
            continue
        repoint = (
            m.short_entities
            if surviving == m.full_global
            else m.full_entities
        )
        alias = m.short if surviving == m.full_global else m.full
        entry = {
            "full": m.full,
            "short": m.short,
            "surviving_global": surviving,
            "repointed": [],
            "aliases_added": [],
        }
        with driver.session() as session:
            for ent in repoint:
                old = session.run(
                    "MATCH (e:Entity {uuid: $e})-[r:SAME_AS]->(g:GlobalEntity) "
                    "RETURN g.uuid AS g",
                    e=ent,
                ).single()
                old_gid = old["g"] if old else None
                if old_gid and old_gid != surviving:
                    session.run(
                        "MATCH (e:Entity {uuid: $e})-[r:SAME_AS]->(g:GlobalEntity) "
                        "DELETE r",
                        e=ent,
                    )
                session.run(
                    "MATCH (e:Entity {uuid: $e}), (g:GlobalEntity {uuid: $g}) "
                    "MERGE (e)-[r:SAME_AS]->(g) SET r.alias_merge_run = $run",
                    e=ent,
                    g=surviving,
                    run=run_id,
                )
                entry["repointed"].append(
                    {"entity": ent, "old_global": old_gid}
                )
            added = session.run(
                "MATCH (g:GlobalEntity {uuid: $g}) "
                "WITH g, [a IN coalesce(g.aliases, []) | toLower(a)] AS known "
                "WHERE NOT toLower($alias) IN known "
                "SET g.aliases = coalesce(g.aliases, []) + $alias, "
                "g.alias_merge_run = $run "
                "RETURN g.aliases AS aliases",
                g=surviving,
                alias=alias,
                run=run_id,
            ).single()
            if added is not None:
                entry["aliases_added"].append(alias)
        manifest["merges"].append(entry)
    path = DOCS_DIR / f"alias-merge-run-{run_id}.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return str(path)


def revert_run(driver, run_id: str) -> int:
    """Undo a previous ``--apply`` from its manifest; returns edges reverted."""
    path = DOCS_DIR / f"alias-merge-run-{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no manifest at {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    with driver.session() as session:
        for m in manifest.get("merges", []):
            surviving = m["surviving_global"]
            for item in m["repointed"]:
                ent, old = item["entity"], item["old_global"]
                session.run(
                    "MATCH (e:Entity {uuid: $e})-[r:SAME_AS]->(g:GlobalEntity) "
                    "WHERE r.alias_merge_run = $run DELETE r",
                    e=ent,
                    run=run_id,
                )
                if old:
                    session.run(
                        "MATCH (e:Entity {uuid: $e}), (g:GlobalEntity {uuid: $g}) "
                        "MERGE (e)-[:SAME_AS]->(g)",
                        e=ent,
                        g=old,
                    )
                n += 1
            for alias in m["aliases_added"]:
                session.run(
                    "MATCH (g:GlobalEntity {uuid: $g}) "
                    "SET g.aliases = [a IN coalesce(g.aliases, []) "
                    "WHERE a <> $alias] REMOVE g.alias_merge_run",
                    g=surviving,
                    alias=alias,
                )
    return n


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _slug(groups: list[str]) -> str:
    return "-".join(re.sub(r"[^A-Za-z0-9._-]+", "-", g) for g in groups)


def render_markdown(plan: MergePlan) -> str:
    s = plan.summary()
    lines = [
        "# Alias-merge dry run",
        "",
        f"- groups: {', '.join(plan.groups)}",
        f"- source-stated pairs found: {s['pairs_found']}",
        f"- planned merges: {s['merges']}",
        f"- SAME_AS edges that would change: {s['same_as_edges_to_change']}",
        f"- already merged: {s['already_merged']}",
        f"- missing side: {s['missing_side']}",
        f"- refusals (type conflict): {s['refused_type_conflict']}",
        f"- refusals (number token): {s['refused_number_token']}",
        f"- refusals (ambiguity): {s['refused_ambiguity']}",
        "",
        "## Planned merges",
        "",
        "| full | short | surviving global | edges | source |",
        "|---|---|---|---|---|",
    ]
    for m in plan.merges():
        lines.append(
            f"| {m.full} | {m.short} | {m.full_global or m.short_global} | "
            f"{m.same_as_edges_changed} | {m.source} |"
        )
    lines += ["", "## Refusals", ""]
    for r in plan.refusals():
        lines.append(f"- **{r.full}** / **{r.short}**: {r.decision} — {r.reason}")
    return "\n".join(lines) + "\n"


def write_plan(plan: MergePlan) -> tuple[Path, Path]:
    slug = _slug(plan.groups)
    json_path = DOCS_DIR / f"alias-merge-dryrun-{slug}.json"
    md_path = DOCS_DIR / f"alias-merge-dryrun-{slug}.md"
    json_path.write_text(
        json.dumps(
            {
                "summary": plan.summary(),
                "pairs": [p.as_dict() for p in plan.pairs],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(plan), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", required=True, help="comma-separated group ids")
    parser.add_argument("--apply", action="store_true", help="execute the merges")
    parser.add_argument("--revert", metavar="RUN_ID", help="revert a previous apply")
    args = parser.parse_args(argv)

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    if not groups:
        parser.error("--groups must name at least one group id")

    settings = Settings()
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        if args.revert:
            n = revert_run(driver, args.revert)
            print(f"reverted {n} SAME_AS edges for run {args.revert}")
            return 0
        episodes, entities, globals = load_neo4j(driver, groups)
        plan = plan_alias_merges(episodes, entities, globals)
        json_path, md_path = write_plan(plan)
        print(json.dumps(plan.summary(), indent=2))
        print(f"plan: {json_path}")
        print(f"plan: {md_path}")
        if args.apply:
            run_id = make_run_id()
            manifest = apply_plan(driver, plan, run_id)
            print(f"applied merges under run {run_id}; manifest {manifest}")
        else:
            print("dry run — no writes. pass --apply to execute.")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
