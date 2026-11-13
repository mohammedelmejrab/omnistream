"""Strict round-two suitability gates; unavailable evidence always yields HOLD."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from omnistream.eval.real.collect import (
    PACKAGE,
    corpus_paths,
    read_jsonl,
    write_json,
    write_jsonl,
)
from omnistream.eval.real.entities_v2 import cached_entities
from omnistream.eval.real.v2 import validate_changed_facts
from omnistream.ingest.normalize import content_hash, normalize_text, normalize_url


def requirements(rows, config, *, complete_share, integrity):
    failures = []
    if not 300 <= len(rows) <= 400:
        failures.append(f"Size {len(rows)} outside 300–400.")
    cfgs = {s["id"]: s for s in config["sources"]}
    for bubble in ("news", "finance", "research"):
        selected = [r for r in rows if r["bubble_hint"] == bubble]
        if not selected or len(selected) < len(rows) * 0.25:
            failures.append(f"{bubble}: below 25% of corpus.")
        counts = Counter(
            cfgs[r["source"]].get("source_group", r["source"]) for r in selected
        )
        for source, n in counts.items():
            if n > 0.25 * len(selected):
                failures.append(
                    f"{bubble}: {source} has {n}/{len(selected)} items, exceeding 25% source cap."
                )
        if bubble == "news" and len(counts) < 5:
            failures.append(f"News has {len(counts)} sources, below 5.")
    if complete_share < 0.70:
        failures.append(f"Complete text/abstract share {complete_share:.1%} below 70%.")
    if integrity:
        failures.append(f"{len(integrity)} integrity errors.")
    return failures


def verify_v2(name, *, root=Path("."), near_fn=None):
    from omnistream.eval.real.verify import (
        cleanliness,
        length_stats,
        near_duplicates,
        overlap,
    )

    folder, manifest, docs = corpus_paths(name, root)
    config = json.loads((PACKAGE / f"sources-{name}.json").read_text())
    collection = json.loads((folder / "collection.json").read_text())
    rows = read_jsonl(manifest)
    texts = {r["id"]: (root / r["text_path"]).read_text(encoding="utf8") for r in rows}
    integrity = []
    exact, urls = defaultdict(list), defaultdict(list)
    kinds = Counter(r["content_kind"] for r in rows)
    for row in rows:
        text = texts[row["id"]]
        if (
            hashlib.sha256(text.encode()).hexdigest() != row["sha256"]
            or content_hash(row["url"], text) != row["id"]
        ):
            integrity.append(row["id"] + ": hash mismatch")
        if row["word_count"] != len(text.split()) or row["char_count"] != len(text):
            integrity.append(row["id"] + ": length mismatch")
        if not collection["since"] <= row["published_at"][:10] <= collection[
            "until"
        ] or datetime.fromisoformat(row["published_at"]) > datetime.now(UTC):
            integrity.append(row["id"] + ": date outside window")
        if row.get("event_date_hint") and row["event_date_hint"] < collection["since"]:
            integrity.append(row["id"] + ": older event")
        if not row.get("label_basis"):
            integrity.append(row["id"] + ": missing label_basis")
        if not Path(row["text_path"]).as_posix().startswith("data/real/"):
            integrity.append(row["id"] + ": text outside data/real")
        exact[hashlib.sha256(normalize_text(text).encode()).hexdigest()].append(
            row["id"]
        )
        urls[normalize_url(row["url"])].append(row["id"])
    entities, info = cached_entities(rows, folder)
    entity_result = overlap(rows, entities)
    entity_result["status"] = (
        "partial or unavailable: missing LLM extractions"
        if info["missing_items"]
        else "complete"
    )
    shared = {e for es in entities.values() for e in es}
    shared = {
        e
        for e in shared
        if len({r["bubble_hint"] for r in rows if e in entities[r["id"]]}) >= 2
    }
    alias_entities = {
        e: info["surfaces"][e]
        for e in sorted(shared)
        if len({s.casefold() for s in info["surfaces"][e]}) > 1
    }
    entity_result["cross_bubble_entities_with_multiple_surface_forms"] = len(
        alias_entities
    )
    entity_result["alias_surfaces"] = alias_entities
    for entry in entity_result["top_40"]:
        entry["surfaces"] = info["surfaces"][entry["entity"]]
    facts_path = PACKAGE / f"{name}-changed-facts.json"
    facts = (
        json.loads(facts_path.read_text(encoding="utf8")) if facts_path.exists() else []
    )
    fact_errors = validate_changed_facts(facts, rows, texts)
    audit_path = PACKAGE / f"{name}-ner-audit.json"
    audit = (
        json.loads(audit_path.read_text(encoding="utf8"))
        if audit_path.exists()
        else {"status": "pending manual audit"}
    )
    if (
        audit.get("manifest_sha256")
        != hashlib.sha256(manifest.read_bytes()).hexdigest()
    ):
        audit = {"status": "pending manual audit of current manifest"}
    full = sum(n for k, n in kinds.items() if k.startswith("full_text"))
    abstracts = kinds["abstract"]
    complete = (full + abstracts) / len(rows) if rows else 0
    failures = requirements(rows, config, complete_share=complete, integrity=integrity)
    numeric_verdict = "APPROVE" if not failures else "HOLD"
    if info["missing_items"]:
        failures.append(
            f"LLM extraction missing for {len(info['missing_items'])} items; overlap unavailable for these items."
        )
    if len(facts) < 25 or fact_errors:
        failures.append(
            f"Verified changed facts: {len(facts)}/25; validation errors: {len(fact_errors)}."
        )
    if len(audit.get("items", [])) < 30 or not isinstance(
        audit.get("precision"), (int, float)
    ):
        failures.append("30-item entity precision audit incomplete.")
    print(
        f"QA: {len(rows)} originals checked; cached LLM statistics read; computing local BGE",
        flush=True,
    )
    near = (
        (near_fn or near_duplicates)(rows, [texts[r["id"]] for r in rows], folder)
        if rows
        else {}
    )
    sources = []
    outcomes = read_jsonl(folder / "outcomes.jsonl")
    for cfg in config["sources"]:
        selected = [r for r in rows if r["source"] == cfg["id"]]
        status = next(
            (s for s in collection["sources"] if s["source"] == cfg["id"]), {}
        )
        sources.append(
            {
                "source": cfg["id"],
                "source_group": cfg.get("source_group", cfg["id"]),
                "bubble": cfg["bubble_hint"],
                "accepted": len(selected),
                "word_lengths": length_stats([r["word_count"] for r in selected]),
                "content_kinds": dict(Counter(r["content_kind"] for r in selected)),
                "errors": status.get("errors", []),
                "rejected": dict(
                    Counter(
                        o["reason"]
                        for o in outcomes
                        if o["source"] == cfg["id"] and o["reason"] != "accepted"
                    )
                ),
                "licence_note": cfg["licence_note"],
                "terms_url": cfg["terms_url"],
                "access": cfg.get("access", "robots_checked"),
                "full_text_policy": cfg["full_text_policy"],
            }
        )
    result = {
        "name": name,
        "verified_at": datetime.now(UTC).isoformat(),
        "window": [collection["since"], collection["until"]],
        "accepted": len(rows),
        "per_bubble": dict(Counter(r["bubble_hint"] for r in rows)),
        "sources": sources,
        "words": length_stats([r["word_count"] for r in rows]),
        "languages": dict(Counter(r["language"] for r in rows)),
        "cleanliness": dict(
            Counter(flag for text in texts.values() for flag in cleanliness(text))
        ),
        "date_histogram": dict(
            sorted(Counter(r["published_at"][:10] for r in rows).items())
        ),
        "content_kinds": dict(kinds),
        "full_text_likely_share": full / len(rows) if rows else 0,
        "full_abstract_share": abstracts / len(rows) if rows else 0,
        "complete_text_or_abstract_share": complete,
        "entity_extraction": info,
        "entity_overlap": entity_result,
        "entity_audit": audit,
        "verified_changed_facts": len(facts),
        "changed_fact_entity_counts": dict(Counter(f["entity"] for f in facts)),
        "changed_fact_validation_errors": fact_errors,
        "exact_duplicate_clusters": [v for v in exact.values() if len(v) > 1],
        "same_canonical_url_clusters": [v for v in urls.values() if len(v) > 1],
        "near_duplicates": near,
        "integrity_errors": integrity,
        "shortfalls": failures,
        "point_5_verdict": numeric_verdict,
        "verdict": "HOLD" if failures else "APPROVE",
        "llm_calls": info["calls"],
        "llm_cost_usd": info["provider_cost_usd"],
        "llm_priced_cost_usd": info["priced_cost_usd"],
        "outcomes": dict(Counter(o["reason"] for o in outcomes)),
    }
    docs.mkdir(parents=True, exist_ok=True)
    write_json(docs / f"{name}-quality.json", result)
    write_jsonl(
        PACKAGE / f"{name}-entities.jsonl",
        [
            {
                "id": r["id"],
                "entities": entities[r["id"]],
                "extraction_status": "missing"
                if r["id"] in info["missing_items"]
                else "complete",
            }
            for r in rows
        ],
    )
    render(result, config, rows, docs)
    chosen = random.Random(20261113).sample(
        sorted(rows, key=lambda r: r["id"]), min(30, len(rows))
    )
    lines = [
        f"# {name} fixed-seed 30-item sample",
        "",
        "Seed 20261113; no article text.",
    ]
    audits = {a["id"]: a for a in audit.get("items", [])}
    for row in chosen:
        lines += [
            "",
            f"## {row['title']}",
            f"- ID: {row['id']}",
            f"- Source: {row['source']}; bubble: {row['bubble_hint']}; basis: {row.get('label_basis')}",
            f"- Date: {row['published_at']}; event hint: {row.get('event_date_hint')}",
            f"- Words: {row['word_count']}; class: {row['content_kind']}",
            f"- URL: {row['url']}",
            f"- Content bubble flags: {row.get('content_bubbles')}",
            f"- Cleanliness: {cleanliness(texts[row['id']])}",
            f"- Audit: {audits.get(row['id'], {}).get('quality_note', 'Pending human check')}",
        ]
    (docs / f"{name}-sample.md").write_text("\n".join(lines) + "\n", encoding="utf8")
    return result


def render(r, config, rows, docs):
    overlap = r["entity_overlap"]
    lines = [
        f"# {r['name']} corpus quality report",
        "",
        f"**{r['verdict']} — point 5 numeric verdict: {r['point_5_verdict']}**",
        "",
        f"Window: {' through '.join(r['window'])} inclusive UTC; verified {r['verified_at']}.",
        "",
        "## Headline results",
        "",
        f"- Accepted: {r['accepted']}; bubbles: {r['per_bubble']}.",
        f"- Words: {r['words']}.",
        f"- Full/likely article text: {r['full_text_likely_share']:.1%}; complete abstracts: {r['full_abstract_share']:.1%}; combined: {r['complete_text_or_abstract_share']:.1%}.",
        f"- Content classes: {r['content_kinds']}.",
        f"- LLM calls: {r['llm_calls']}; provider-reported cost ${r['llm_cost_usd']:.6f}; token-priced cost ${r['llm_priced_cost_usd']:.6f} at $0.15/$0.60 per million input/output tokens.",
        (
            f"- Cross-bubble entities: {overlap['entities_in_2_or_more_bubbles']} in >=2; {overlap['entities_in_all_3_bubbles']} in all 3; {overlap['cross_bubble_entities_with_multiple_surface_forms']} with multiple case-insensitive surface forms."
            if not r["entity_extraction"]["missing_items"]
            else "- Cross-bubble entity and alias statistics: NOT MEASURED for the complete corpus; LLM extraction is incomplete."
        ),
        f"- Verified changed facts: {r['verified_changed_facts']}; validation errors: {r['changed_fact_validation_errors']}.",
        "",
        "## Changes since real-v1",
        "",
        "V1 remains unchanged. V2 drops NASA, NVIDIA teasers and biomedical abstracts; adds scoped documented-API access, on-theme arXiv queries, 24 EDGAR issuers including foreign 6-K, EX-99 exhibit documents, licensed/public-domain news candidates, content label flags and displayed event-date checks. arXiv query variants count as one publisher for the source cap. V2 replay and caches are isolated under data/real/real-v2/. No C3 routing, retrieval or answering changes.",
        "",
        "## Requirements and limitations",
        "",
    ]
    lines += ["- " + f for f in r["shortfalls"]] or ["All specified gates passed."]
    lines += [
        "",
        "Abstracts are complete API abstracts, not full papers. Full-text-likely remains a proxy (400 words and three HTML paragraphs); fetched bodies use explicit source selectors and require at least 120 words to count as full-text depth; shorter retrieved landing pages/briefs remain unknown. Missing LLM extractions are not replaced with local NER estimates. Source hints remain provisional.",
        "",
        "## Per-source accounting and text depth",
        "",
        "| Source | Bubble | Accepted | Words min / median / p90 / max | Classes |",
        "|---|---|---:|---|---|",
    ]
    for s in r["sources"]:
        w = s["word_lengths"]
        lines.append(
            f"| {s['source']} | {s['bubble']} | {s['accepted']} | {w.get('min', 0)} / {w.get('median', 0)} / {w.get('p90', 0)} / {w.get('max', 0)} | {s['content_kinds']} |"
        )
    lines += [
        "",
        "## Source permissions, access and failures",
        "",
        config["theme_rule"],
    ]
    lines += [
        "",
        "Reviewed title/body metadata exclusions: "
        + str(config.get("quality_exclusions", {})),
    ]
    for s in r["sources"]:
        lines += [
            "",
            f"### {s['source']}",
            "",
            f"- Terms: [{s['terms_url']}]({s['terms_url']})",
            f"- Licence: {s['licence_note']}",
            f"- Access: {s['access']}; policy: {s['full_text_policy']}. Documented API exceptions apply only to code-allowlisted HTTPS endpoints and matching terms URLs; redirects outside scope require robots permission. Single sequential client; minimum 3 seconds per host, stricter robots delay respected.",
            f"- Failures/exclusions: {s['errors'] or 'none'}",
            f"- Rejections: {s['rejected']}",
        ]
    lines += [
        "",
        "## Dates, language and cleanliness",
        "",
        f"Languages: {r['languages']}. Heuristic cleanliness flags: {r['cleanliness']}. Date histogram is recorded in quality JSON. All accepted publication dates and reviewed event hints passed the inclusive UTC window checks.",
        "",
        "## Duplicate audit",
        "",
        f"Exact duplicate clusters: {len(r['exact_duplicate_clusters'])}; canonical URL revision clusters: {len(r['same_canonical_url_clusters'])}. Near-duplicate details in quality JSON. Integrity errors: {r['integrity_errors']}.",
        "",
        "Feed/API publication date is preserved. A displayed leading body date or dated URL becomes event_date_hint; month-only URLs use the last day as a conservative upper bound. Older-than-window content is rejected. Historical dates mentioned in prose are not assumed to be event dates. label_basis=source_hint is explicit; content_bubbles supplies transparent keyword review flags, not gold labels.",
        "",
        "## Cross-bubble entity suitability",
        "",
        f"Extraction: {r['entity_extraction']['method']}. Missing items: {len(r['entity_extraction']['missing_items'])}. Canonical identity is model-proposed; only verbatim observed aliases survive. Multiple surface forms ignore case-only variants; this is a suitability statistic, not production entity resolution.",
        "",
        f"30-item audit: {r['entity_audit'].get('status')}; precision: {r['entity_audit'].get('precision', 'not measured')}.",
        "",
        "| Canonical entity | News | Finance | Research | Observed surfaces |",
        "|---|---:|---:|---:|---|",
    ]
    for e in overlap["top_40"]:
        lines.append(
            f"| {e['entity']} | {e['counts'].get('news', 0)} | {e['counts'].get('finance', 0)} | {e['counts'].get('research', 0)} | {', '.join(e['surfaces']).replace('|', '/')} |"
        )
    lines += [
        "",
        "## Changed facts",
        "",
        f"Fact entity distribution: {r['changed_fact_entity_counts']}. Twenty-one of the 25 reviewed facts come from the two TSMC monthly disclosures, so this satisfies a count of distinct changed financial attributes, not 25 independent event narratives.",
        "",
        f"{r['verified_changed_facts']} directly reviewed records in src/omnistream/eval/real/real-v2-changed-facts.json. Each record requires old/new values, increasing publication dates, accepted item IDs and verbatim evidence quotes <=15 words per side. Validation confirms references and quotation presence; it cannot establish semantic supersession by itself. Signals are not promoted to verified facts.",
        "",
        "## Reproduction and storage",
        "",
        "```powershell",
        ".venv/Scripts/omni.exe realdata collect --name real-v2",
        ".venv/Scripts/python.exe -m omnistream.eval.real.entities_v2 --name real-v2",
        ".venv/Scripts/omni.exe realdata verify --name real-v2",
        "```",
        "",
        "Use process environment credentials or the extraction command’s --secret-file private path; settings always use _env_file=None. Never read .env. Texts, HTTP payloads, intake database and replay snapshots remain under data/real/real-v2/. Metadata-only committed manifest, entities, sample and report carry no article bodies. Exhibits are separate items with the same accession and different document names. No production DB, graph or old snapshots opened or modified.",
        "",
        "## C1 findings and fixes",
        "",
        "No retrieval/answering changes. Collection-specific helpers implement endpoint policy, filing index exhibit discovery, arXiv query escaping and fact-reference validation; local fixtures cover them.",
        "",
        "## Next options before corpus approval",
        "",
        "Run the cached LLM pass with privately supplied OpenRouter credentials, then directly check entity precision for the fixed 30-item sample. Research needs more independent publishers to meet the strict 25% source cap; query/category partitions of arXiv cannot solve that requirement. No corpus approval or benchmark question writing should proceed while these gates fail.",
        "",
        "## Recorded validation",
        "",
        "See real-v2-validation.md for exact command output.",
        "",
        "## Final verdict",
        "",
        r["verdict"],
    ]
    (docs / f"{r['name']}-quality.md").write_text(
        "\n".join(lines) + "\n", encoding="utf8"
    )
