"""Offline corpus QA: metadata-only exports, local BGE and spaCy; zero LLM cost."""

from __future__ import annotations

import hashlib
import itertools
import json
import random
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from omnistream.config import Settings
from omnistream.eval.real.collect import (
    PACKAGE,
    corpus_paths,
    read_jsonl,
    write_json,
    write_jsonl,
)
from omnistream.ingest.normalize import content_hash, normalize_text, normalize_url

SEED = 20261113
CHANGE = re.compile(
    r"\b(appointed|resigned|replaced|raised|cut|cancelled|canceled|completed|acquired|version|revised|released|launched|announced|transition|guidance)\b",
    re.IGNORECASE,
)
ALIASES = {
    "nvidia corporation": "nvidia",
    "nvidia corp": "nvidia",
    "nvda": "nvidia",
    "microsoft corporation": "microsoft",
    "microsoft corp": "microsoft",
    "msft": "microsoft",
    "google llc": "google",
    "international business machines": "ibm",
    "ibm corporation": "ibm",
    "advanced micro devices": "amd",
    "advanced micro devices inc": "amd",
    "amazon web services": "aws",
    "amazon.com": "amazon",
    "university of california berkeley": "uc berkeley",
    "university of california at berkeley": "uc berkeley",
    "berkeley artificial intelligence research": "bair",
    "federal reserve board": "federal reserve",
}

# Corpus QA only: these type exclusions and common organisation names do not
# affect C3, graph extraction, retrieval, or answering. Persist them for review.
GENERIC_ENTITIES = {
    "ai",
    "gpu",
    "gpus",
    "cpu",
    "cpus",
    "llm",
    "llms",
    "api",
    "pdf",
    "board",
    "ehr",
    "ict",
    "rl",
    "cst",
    "lbr",
    "main",
    "orals",
    "schedule",
    "workshop",
    "trust",
    "observability",
    "attendees",
    "content board",
    "linear",
    "next",
    "kit",
    "discovery",
    "global head",
    "content curation",
    "aiops",
}
ORG_NAMES = [
    "NVIDIA",
    "Microsoft",
    "Google",
    "Alphabet",
    "Amazon",
    "Amazon Web Services",
    "AWS",
    "AMD",
    "Advanced Micro Devices",
    "Intel",
    "IBM",
    "Apple",
    "OpenAI",
    "Anthropic",
    "Meta",
    "Samsung",
    "Samsung Electronics",
    "NASA",
    "SEC",
    "Securities and Exchange Commission",
    "Federal Reserve",
    "Federal Reserve Board",
    "UC Berkeley",
    "BAIR",
    "Hugging Face",
]


def entity_key(name: str) -> str:
    value = normalize_text(name).replace("\u2019", "'")
    value = re.sub(r"'s$", "", value)
    value = re.sub(r"[^\w\s+.-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return ALIASES.get(value, value)


def cleanliness(text: str) -> list[str]:
    flags = []
    checks = {
        "html": r"</?[a-z][^>]*>",
        "javascript": r"function\s*\(|document\.|window\.|var\s+\w+\s*=",
        "navigation_cookie": r"accept all cookies|cookie preferences|skip to (?:main )?content|subscribe to our newsletter",
        "mojibake": r"\ufffd|\u00c3[\u0080-\u00bf]|\u00e2\u20ac|\u00c2\u00a0",
        "table_or_code": r"(?:\|[^\n]+){6}|(?:\b(?:const|def|import|SELECT)\b[^\n;]*[;:{]){3}",
    }
    for key, pattern in checks.items():
        if re.search(pattern, text, re.IGNORECASE):
            flags.append(key)
    if len(text.split()) > 10000:
        flags.append("very_long")
    opening = " ".join(text.split()[:12])
    if len(opening) > 40 and text.count(opening) > 1:
        flags.append("repeated_intro")
    return flags


def length_stats(values: list[int]) -> dict:
    if not values:
        return {"min": 0, "median": 0, "p90": 0, "max": 0}
    return {
        "min": min(values),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
        "max": max(values),
    }


def overlap(rows: list[dict], entities: dict[str, list[str]]) -> dict:
    index = defaultdict(lambda: defaultdict(set))
    for row in rows:
        for entity in set(entities.get(row["id"], [])):
            index[entity][row["bubble_hint"]].add(row["id"])
    shared = {e: b for e, b in index.items() if len(b) >= 2}
    pairs = set()
    for bubbles in shared.values():
        for left, right in itertools.combinations(bubbles.values(), 2):
            pairs.update(tuple(sorted((a, b))) for a in left for b in right)
    top = sorted(
        shared,
        key=lambda e: (-len(shared[e]), -sum(len(s) for s in shared[e].values()), e),
    )
    return {
        "entities_in_2_or_more_bubbles": len(shared),
        "entities_in_exactly_2_bubbles": sum(len(b) == 2 for b in shared.values()),
        "entities_in_all_3_bubbles": sum(len(b) == 3 for b in shared.values()),
        "cross_bubble_item_pairs": len(pairs),
        "top_40": [
            {"entity": e, "counts": {b: len(v) for b, v in shared[e].items()}}
            for e in top[:40]
        ],
    }


def connected_clusters(edges: list[dict]) -> list[list[str]]:
    adjacency = defaultdict(set)
    for edge in edges:
        a, b = edge["left"], edge["right"]
        adjacency[a].add(b)
        adjacency[b].add(a)
    visited, result = set(), []
    for node in sorted(adjacency):
        if node in visited:
            continue
        pending, group = [node], []
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            group.append(current)
            pending.extend(adjacency[current] - visited)
        result.append(sorted(group))
    return result


def ner_entities(rows, texts, folder):
    import spacy

    nlp = spacy.load(
        "en_core_web_sm", disable=["parser", "tagger", "lemmatizer", "attribute_ruler"]
    )
    ruler = nlp.add_pipe("entity_ruler", before="ner")
    ruler.add_patterns(
        [
            {"label": "ORG", "pattern": [{"LOWER": t.lower()} for t in name.split()]}
            for name in ORG_NAMES
        ]
    )
    entities, extracted = {}, []
    for row, doc in zip(rows, nlp.pipe(texts, batch_size=16), strict=True):
        found = sorted(
            {
                entity_key(e.text)
                for e in doc.ents
                if e.label_ in {"ORG", "PERSON", "PRODUCT"}
                and 1 < len(e.text) < 100
                and len(e.text.split()) <= 8
                and entity_key(e.text) not in GENERIC_ENTITIES
            }
        )
        entities[row["id"]] = found
        extracted.append({"id": row["id"], "entities": found})
    write_jsonl(folder / "entities.jsonl", extracted)
    return entities, {
        "method": "spaCy en_core_web_sm 3.8.0; ORG/PERSON/PRODUCT; fixed common-organisation EntityRuler, technical-acronym exclusion list, deterministic alias map; no LLM. QA only, not used by the RAG system.",
        "spacy_version": spacy.__version__,
        "model_version": nlp.meta["version"],
        "limitations": "Small general-domain NER misses products and acronyms, may label generic phrases as organisations. Counts are estimates, not graph entity-linking ground truth.",
    }


def near_duplicates(rows, texts, folder):
    from omnistream.embeddings import EmbeddingService

    settings = Settings(_env_file=None)
    embedder = EmbeddingService(settings=settings)
    fingerprint = hashlib.sha256(
        ("bge-chunk-1200-mean-v1\n" + "\n".join(r["sha256"] for r in rows)).encode()
    ).hexdigest()
    cache = folder / f"embeddings-{fingerprint}.npy"
    if cache.exists():
        vectors = np.load(cache, allow_pickle=False)
    elif rows:
        segments, owners = [], []
        for i, text in enumerate(texts):
            for offset in range(0, len(text), 1200):
                segments.append(text[offset : offset + 1200])
                owners.append(i)
        embedded = embedder.embed_documents(segments)
        vectors = np.zeros((len(rows), settings.embedding_dim), dtype=np.float32)
        for vector, owner in zip(embedded, owners, strict=True):
            vectors[owner] += vector
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors /= np.maximum(norms, 1e-12)
        np.save(cache, vectors)
    else:
        vectors = np.empty((0, settings.embedding_dim))
    similarities = vectors @ vectors.T
    edges = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            score = float(similarities[i, j])
            if score >= 0.92:
                edges.append(
                    {
                        "left": rows[i]["id"],
                        "right": rows[j]["id"],
                        "cosine": round(score, 5),
                        "cross_source": rows[i]["source"] != rows[j]["source"],
                    }
                )
    return {
        "model": embedder.index_signature,
        "method": "1200-character nonoverlapping chunks, mean pooled and L2 normalized; cosine >=0.92; candidate similarity, not proof of syndication",
        "threshold": 0.92,
        "pairs": edges,
        "clusters": connected_clusters(edges),
    }


def changed_candidates(rows, texts, entities):
    by_entity = defaultdict(list)
    for row, text in zip(rows, texts, strict=True):
        signals = sorted({s.casefold() for s in CHANGE.findall(text)})
        if not signals:
            continue
        for e in entities[row["id"]]:
            # Require an entity mention and change verb in the SAME sentence.
            sentences = re.split(r"(?<=[.!?])\s+", text)
            if any(CHANGE.search(s) and e in entity_key(s) for s in sentences):
                by_entity[e].append(
                    {
                        "id": row["id"],
                        "date": row["published_at"],
                        "source": row["source"],
                        "url": row["url"],
                        "signals": signals,
                    }
                )
    return [
        {"entity": e, "items": sorted(v, key=lambda r: r["date"])}
        for e, v in sorted(by_entity.items())
        if len({r["date"][:10] for r in v}) > 1
    ]


def assess_requirements(rows, sources, entity_result, integrity):
    counts = Counter(r["bubble_hint"] for r in rows)
    shortfalls = []
    if not 250 <= len(rows) <= 400:
        shortfalls.append(f"Size {len(rows)} outside target 250-400.")
    for bubble in ("news", "finance", "research"):
        selected = [r for r in rows if r["bubble_hint"] == bubble]
        if counts[bubble] < 0.2 * len(rows) or not selected:
            shortfalls.append(f"{bubble}: below 20% of corpus.")
        per_source = Counter(r["source"] for r in selected)
        if len(per_source) < 4:
            shortfalls.append(
                f"{bubble}: only {len(per_source)} contributing sources (target >=4)."
            )
        if per_source and max(per_source.values()) > 0.30 * len(selected):
            shortfalls.append(
                f"{bubble}: a source exceeds the approximate 25% cap (30% tolerance)."
            )
        full = sum(r["content_kind"].startswith("full_text") for r in selected)
        if selected and full / len(selected) < 0.5:
            shortfalls.append(
                f"{bubble}: fewer than half of items are likely/full article texts ({full}/{len(selected)})."
            )
    if not entity_result["entities_in_all_3_bubbles"]:
        shortfalls.append("No extracted entity spans all three bubbles.")
    if integrity:
        shortfalls.append(f"{len(integrity)} integrity errors.")
    # Approval needs audited facts and bubble labels, not merely proxy metrics.
    shortfalls.append(
        "Changed-fact candidates require manual confirmation of actual old/new facts; freshness injection and no-context LLM check remain later tasks."
    )
    return shortfalls


def verify(name: str, *, root: Path = Path("."), entity_fn=None, near_fn=None) -> dict:
    if name == "real-v2":
        from omnistream.eval.real.verify_v2 import verify_v2

        return verify_v2(name, root=root, near_fn=near_fn)
    folder, manifest_path, docs = corpus_paths(name, root)
    rows = read_jsonl(manifest_path)
    config = json.loads((PACKAGE / f"sources-{name}.json").read_text(encoding="utf8"))
    collection = json.loads((folder / "collection.json").read_text(encoding="utf8"))
    outcomes = read_jsonl(folder / "outcomes.jsonl")
    texts, integrity = [], []
    for r in rows:
        text = (root / r["text_path"]).read_text(encoding="utf8")
        texts.append(text)
        if hashlib.sha256(text.encode()).hexdigest() != r["sha256"]:
            integrity.append({"id": r["id"], "error": "clean_text_sha256_mismatch"})
        if content_hash(r["url"], text) != r["id"]:
            integrity.append({"id": r["id"], "error": "dedup_id_mismatch"})
        if len(text) != r["char_count"] or len(text.split()) != r["word_count"]:
            integrity.append({"id": r["id"], "error": "length_mismatch"})
    print(f"QA: {len(rows)} originals read; computing local NER", flush=True)
    entities, ner_info = (entity_fn or ner_entities)(rows, texts, folder)
    print("QA: computing local BGE similarities", flush=True)
    near = (near_fn or near_duplicates)(rows, texts, folder)
    entity_result = overlap(rows, entities)
    changes = changed_candidates(rows, texts, entities)
    flags = {r["id"]: cleanliness(t) for r, t in zip(rows, texts, strict=True)}
    exact_groups, url_groups = defaultdict(list), defaultdict(list)
    for r, t in zip(rows, texts, strict=True):
        exact_groups[hashlib.sha256(normalize_text(t).encode()).hexdigest()].append(
            r["id"]
        )
        url_groups[normalize_url(r["url"])].append(r["id"])
    exact_clusters = [v for v in exact_groups.values() if len(v) > 1]
    url_clusters = [v for v in url_groups.values() if len(v) > 1]
    source_results = []
    for cfg in config["sources"]:
        subset = [r for r in rows if r["source"] == cfg["id"]]
        rejected = Counter(
            o["reason"]
            for o in outcomes
            if o["source"] == cfg["id"] and o["reason"] != "accepted"
        )
        kinds = Counter(r["content_kind"] for r in subset)
        status = next(s for s in collection["sources"] if s["source"] == cfg["id"])
        full = sum(v for k, v in kinds.items() if k.startswith("full_text"))
        verdict = (
            "drop"
            if not subset
            else (
                "keep"
                if full == len(subset) and not any(flags[r["id"]] for r in subset)
                else "keep with caveat"
            )
        )
        source_results.append(
            {
                "source": cfg["id"],
                "bubble": cfg["bubble_hint"],
                "accepted": len(subset),
                "rejected": dict(rejected),
                "word_lengths": length_stats([r["word_count"] for r in subset]),
                "content_kinds": dict(kinds),
                "full_text_likely_share": full / len(subset) if subset else 0,
                "cleanliness_flags": dict(
                    Counter(f for r in subset for f in flags[r["id"]])
                ),
                "verdict": verdict,
                "licence_note": cfg["licence_note"],
                "terms_url": cfg["terms_url"],
                "full_text_policy": cfg["full_text_policy"],
                "errors": status["errors"],
            }
        )
    days = Counter(r["published_at"][:10] for r in rows)
    lower, upper = collection["since"], collection["until"]
    older_body_dates = []
    for row, text in zip(rows, texts, strict=True):
        match = re.search(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})\b",
            text[:200],
        )
        if match:
            try:
                hinted = (
                    datetime.strptime(match.group(), "%B %d, %Y").date().isoformat()
                )
            except ValueError:
                continue
            if hinted < lower:
                older_body_dates.append(
                    {
                        "id": row["id"],
                        "source": row["source"],
                        "body_date_hint": hinted,
                        "feed_date": row["published_at"],
                    }
                )
    cursor = datetime.fromisoformat(lower)
    while cursor.date().isoformat() <= upper:
        days.setdefault(cursor.date().isoformat(), 0)
        cursor += timedelta(days=1)
    invalid = [
        r["id"]
        for r in rows
        if not r["published_at"]
        or not lower <= r["published_at"][:10] <= upper
        or datetime.fromisoformat(r["published_at"]) > datetime.now(UTC)
    ]
    audit_path = PACKAGE / f"{name}-ner-audit.json"
    audit = (
        json.loads(audit_path.read_text(encoding="utf8"))
        if audit_path.exists()
        else {"status": "pending manual review"}
    )
    if (
        audit.get("manifest_sha256")
        != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ):
        audit = {"status": "pending manual review of current manifest"}
    shortfalls = assess_requirements(rows, config["sources"], entity_result, integrity)
    review_path = PACKAGE / f"{name}-review-notes.json"
    review_notes = (
        json.loads(review_path.read_text(encoding="utf8"))
        if review_path.exists()
        else {}
    )
    result = {
        "name": name,
        "verified_at": datetime.now(UTC).isoformat(),
        "window": [lower, upper],
        "accepted": len(rows),
        "per_bubble": dict(Counter(r["bubble_hint"] for r in rows)),
        "words": length_stats([r["word_count"] for r in rows]),
        "full_text_likely_share": sum(
            r["content_kind"].startswith("full_text") for r in rows
        )
        / len(rows)
        if rows
        else 0,
        "outcomes": dict(Counter(o["reason"] for o in outcomes)),
        "sources": source_results,
        "exact_duplicate_clusters": exact_clusters,
        "same_canonical_url_clusters": url_clusters,
        "near_duplicates": near,
        "date_histogram": dict(sorted(days.items())),
        "date_invalid_accepted": invalid,
        "date_invalid_accepted_share": len(invalid) / len(rows) if rows else 0,
        "older_date_in_body_prefix": older_body_dates,
        "timezone": "RSS feedparser parsed offsets into UTC; API naive ISO dates default UTC (C1). UTC inclusive calendar date window; no inferred publication dates.",
        "languages": dict(Counter(r["language"] for r in rows)),
        "cleanliness": dict(Counter(f for v in flags.values() for f in v)),
        "flagged_items": {k: v for k, v in flags.items() if v},
        "entity_extraction": ner_info,
        "entity_audit": audit,
        "manual_review_notes": review_notes,
        "entity_overlap": entity_result,
        "changed_fact_candidates": changes,
        "integrity_errors": integrity,
        "shortfalls": shortfalls,
        "verdict": "HOLD - not approved for benchmark construction",
        "llm_calls": 0,
        "llm_cost_usd": 0,
        "c1_changes": [
            "RSS empty markup content now falls back to a nonempty summary (regression tested).",
            "Official API HTML body fields now become readable clean text while original JSON is preserved (Europe PMC regression).",
            "Shared RSS/API HTML cleaner removes navigation, hidden blocks and script/style nodes (regression tested).",
            "Opt-in include_empty permits auditing empty-body feed records; default C1 behaviour remains to skip them.",
        ],
    }
    docs.mkdir(parents=True, exist_ok=True)
    write_json(docs / f"{name}-quality.json", result)
    write_jsonl(
        PACKAGE / f"{name}-entities.jsonl",
        [{"id": r["id"], "entities": entities[r["id"]]} for r in rows],
    )
    render_report(result, config, rows, texts, docs)
    render_sample(rows, flags, docs / f"{name}-sample.md", audit=audit)
    return result


def render_sample(rows, flags, path, *, audit=None):
    chosen = random.Random(SEED).sample(
        sorted(rows, key=lambda r: r["id"]), min(30, len(rows))
    )
    lines = [
        "# Real-v1 fixed-seed sample",
        "",
        f"Seed {SEED}; simple random sample of {len(chosen)} accepted items. Notes use manual prefix review where recorded, otherwise automated QA observations. Content classes are automated. No article text.",
        "",
    ]
    reviewed = {
        entry["id"]: entry.get("quality_note")
        for entry in (audit or {}).get("items", [])
    }
    for i, r in enumerate(chosen, 1):
        note = (
            reviewed.get(r["id"])
            or ", ".join(flags[r["id"]])
            or "No heuristic cleanliness flags"
        )
        lines += [
            f"## {i}. {r['title']}",
            "",
            f"- Source: {r['source']}; bubble hint: {r['bubble_hint']}",
            f"- Published: {r['published_at']}; words: {r['word_count']}",
            f"- URL: {r['url']}",
            f"- Quality note: {note}; {r['content_kind']}.",
            "",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf8")


def render_report(result, config, rows, texts, docs):
    r = result
    lines = [
        f"# {r['name']} corpus quality report",
        "",
        f"**{r['verdict']}**",
        "",
        f"Window: {r['window'][0]} through {r['window'][1]} inclusive UTC. Verified {r['verified_at']}.",
        "",
        "## Headline results",
        "",
        f"- Accepted: {r['accepted']}; per bubble: {r['per_bubble']}.",
        f"- Words: {r['words']}; likely/full-text share: {r['full_text_likely_share']:.1%}. Abstracts are NOT counted as full papers.",
        f"- Candidate outcomes: {r['outcomes']}.",
        f"- Exact duplicate clusters after dedup: {len(r['exact_duplicate_clusters'])}; canonical URL revision clusters: {len(r['same_canonical_url_clusters'])}; BGE candidate pairs: {len(r['near_duplicates']['pairs'])} in {len(r['near_duplicates']['clusters'])} clusters.",
        f"- Entities in >=2 bubbles: {r['entity_overlap']['entities_in_2_or_more_bubbles']}; all 3: {r['entity_overlap']['entities_in_all_3_bubbles']}; distinct cross-bubble item pairs: {r['entity_overlap']['cross_bubble_item_pairs']}.",
        f"- Entities with candidate changed facts on multiple dates: {len(r['changed_fact_candidates'])}. These are signals, not verified fact revisions.",
        "- LLM calls: 0; LLM cost: $0.00. Local NER/BGE only.",
        "",
        "## Requirements and limitations",
        "",
    ]
    lines.extend("- " + s for s in r["shortfalls"])
    audit = r["entity_audit"]
    if audit.get("items_reviewed"):
        lines += [
            "",
            f"Manual NER spot-check: {audit['valid_prediction_names']}/{audit['predicted_names_reviewed']} candidate names valid ({audit['name_precision']:.1%}); {audit['items_with_missed_name_examples']}/30 items have documented missed-name examples. This is prefix-level name precision, not full-document recall or RAG entity accuracy. Raw overlap counts below contain false positives and must not be used as gold labels.",
        ]
    review = r.get("manual_review_notes", {})
    lines += ["", "### Manual suitability findings", ""]
    for note in review.get("source_label_findings", []):
        lines.append("- " + note)
    for anchor in review.get("confirmed_three_bubble_organisations", []):
        lines.append(
            f"- Confirmed organisation anchor **{anchor['entity']}**: {anchor['counts']}."
        )
    collision = review.get("rejected_three_bubble_identity", {})
    if collision:
        lines.append("- " + collision["reason"])
    timeline = review.get("checked_changed_fact_candidate", {})
    if timeline:
        lines += ["", timeline["description"]]
        lines.extend(
            f"- [{v['title']}]({v['url']}) ({v['published_at']})"
            for v in timeline["items"]
        )
    lines += [
        "",
        "Older dates near the start of clean bodies (review signals, not automatically inferred publication dates):",
    ]
    for warning in r["older_date_in_body_prefix"]:
        row = next(v for v in rows if v["id"] == warning["id"])
        lines.append(
            f"- [{row['title']}]({row['url']}): body hint {warning['body_date_hint']}, feed date {warning['feed_date']}."
        )
    lines += [
        "",
        "8-K completeness means the retrieved primary filing body, not its complete exhibit/earnings packet. Linked exhibits were not fetched. Filing date is recorded at UTC midnight when the API gives a date without a time; it is not assumed to be the effective event date.",
        "",
        "Source balance counts individual issuer/channel sources. Several sources share one publisher or distribution platform (NVIDIA blog/technical/releases; SEC filings from eight issuers). This does not constitute independent publisher diversity. The 50% full-text check is a conservative operational QA gate, not a numeric requirement from the specification.",
        "",
        "Duplicate rejection counts include repeated feed entries from archive parameters that returned the same current issue, particularly NVIDIA releases; they are not counts of unique syndicated stories. Near-duplicate clusters also include repeated cover-page/legal boilerplate in filings and full-post/summary pairs. Review before selecting evidence.",
    ]
    lines += [
        "",
        "The theme is AI, cloud computing and semiconductors. Overlap is measured below rather than assumed. Financial agency items broaden Finance beyond that theme; company press-release hints can include product news. Bubble hints are provisional source labels and have not been run through C3. No retrieval/answering code, production graph, or old evaluation snapshots were changed. No questions were written.",
        "",
        "The recent window reduces prior-knowledge risk but does not prove absence from training data. A later no-context evaluation is required. Relevance/changed-fact verification must precede question writing. No near-duplicate candidate is silently deleted.",
        "",
        "## Per-source accounting and text depth",
        "",
        "| Source | Bubble | Accepted | Words min / median / p90 / max | Likely full share | Verdict |",
        "|---|---|---:|---|---:|---|",
    ]
    for s in r["sources"]:
        v = s["word_lengths"]
        lines.append(
            f"| {s['source']} | {s['bubble']} | {s['accepted']} | {v['min']} / {v['median']:g} / {v['p90']:g} / {v['max']} | {s['full_text_likely_share']:.0%} | {s['verdict']} |"
        )
    lines += [
        "",
        "Full text is a conservative proxy: >=400 words and >=3 HTML paragraphs, without explicit truncation markers; explicit successful public-domain body retrieval is counted separately as fetched full text. This cannot certify completeness; summaries/unknown and abstracts are separate classes in JSON. A literal ellipsis inside an article is not automatically treated as truncation; end ellipsis and Read more/Continue reading markers are.",
        "",
    ]
    rng = random.Random(SEED)
    text_by_id = {row["id"]: t for row, t in zip(rows, texts, strict=True)}
    for s, cfg in zip(r["sources"], config["sources"], strict=True):
        lines += [
            f"### {s['source']}",
            "",
            f"- Source: {cfg['url']}",
            f"- Licence/terms: {s['licence_note']} Terms: {s['terms_url']}",
            f"- Full-text policy: {s['full_text_policy']}; verdict: **{s['verdict']}**.",
            f"- Rejections: {s['rejected']}; content classes: {s['content_kinds']}; cleanliness: {s['cleanliness_flags']}.",
        ]
        for error in s["errors"]:
            lines.append(f"- Source failure/exclusion: {error}")
        candidates = [row for row in rows if row["source"] == s["source"]]
        if cfg["quote_excerpts"]:
            for row in rng.sample(candidates, min(2, len(candidates))):
                # Source excerpts are permitted only here, never in metadata manifests.
                excerpt = text_by_id[row["id"]][:300].replace("\n", " ")
                lines += [
                    "",
                    f"Short excerpt ([{row['title']}]({row['url']})): {excerpt}",
                ]
        elif candidates:
            lines += [
                "",
                "Excerpts withheld: no blanket republication licence established. Inspect the local clean originals referenced by manifest; sample lists titles, dates and URLs only.",
            ]
        lines.append("")
    lines += [
        "## Dates, language and cleanliness",
        "",
        f"Accepted invalid date share: {r['date_invalid_accepted_share']:.1%}; timezone policy: {r['timezone']}",
        "",
        f"Languages: {r['languages']}; langdetect 1.0.9 deterministic seed, heuristic confidence (not calibrated). Short text is filtered before language classification.",
        "",
        f"Cleanliness flags: {r['cleanliness']}; integrity errors: {r['integrity_errors']}. Flags are heuristic candidates; tables and code can be legitimate research content. Counts and item IDs are in JSON.",
        "",
        "| UTC publication day | Items |",
        "|---|---:|",
    ]
    lines.extend(f"| {day} | {count} |" for day, count in r["date_histogram"].items())
    lines += [
        "",
        "## Duplicate audit",
        "",
        r["near_duplicates"]["method"],
        "",
        "BGE is local BAAI/bge-small-en-v1.5 through the project EmbeddingService. Normalized-text SHA-256 is also checked independently of canonical URL. Cosine similarity is a review signal, not a calibrated syndication classifier. The JSON includes all candidate pairs, scores and connected clusters.",
        "",
    ]
    by_id = {row["id"]: row for row in rows}
    for cluster in r["near_duplicates"]["clusters"]:
        lines.append(
            "- Cluster: "
            + "; ".join(
                f"[{by_id[k]['title']}]({by_id[k]['url']}) ({by_id[k]['source']})"
                for k in cluster
            )
        )
    lines += [
        "",
        "## Cross-bubble entity suitability",
        "",
        r["entity_extraction"]["method"],
        "",
        r["entity_extraction"]["limitations"],
        "",
        "Aliases are conservative and explicit: e.g. Microsoft Corporation -> Microsoft, Amazon Web Services -> AWS. Alphabet is not merged into Google; subsidiaries are not merged into parents. Distinct item pairs are counted once even if they share several entities. Full per-item extracted entities are in the metadata-only entities JSONL.",
        "",
        "| Entity | News items | Finance items | Research items |",
        "|---|---:|---:|---:|",
    ]
    for entry in r["entity_overlap"]["top_40"]:
        c = entry["counts"]
        lines.append(
            f"| {entry['entity']} | {c.get('news', 0)} | {c.get('finance', 0)} | {c.get('research', 0)} |"
        )
    lines += [
        "",
        "### Manual extraction spot-check",
        "",
        "See real-v1-ner-audit.json for item IDs, audit scope, manually recorded judgements and errors.",
        "",
        json.dumps(r["entity_audit"], ensure_ascii=False, indent=2),
        "",
        "## Candidate changed facts",
        "",
        "At least two publication days per entity and a change verb in the same sentence as an entity mention. Publication dates are not effective fact dates. These lists are raw material; they do not demonstrate a contradiction, closure, or revised value. Full candidate item IDs, dates, URLs and signal verbs are in JSON.",
        "",
    ]
    for candidate in r["changed_fact_candidates"]:
        lines.append(
            f"- **{candidate['entity']}**: "
            + "; ".join(
                f"{v['date'][:10]} [{by_id[v['id']]['title']}]({v['url']})"
                for v in candidate["items"][:8]
            )
        )
    lines += [
        "",
        "## Reproduction and storage",
        "",
        "```powershell",
        ".venv/Scripts/python.exe -m pip install -e .",
        ".venv/Scripts/python.exe -m pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
        f"omni realdata collect --name {r['name']} --since {r['window'][0]} --until {r['window'][1]}",
        f"omni realdata verify --name {r['name']}",
        "```",
        "",
        "Collector reuses fetch_rss/fetch_api, isolated Intake and store_original, normalized SHA-256 + canonical URL, and SnapshotRecorder. Data, cached HTTP responses, all polled RawItems, and accepted replay JSONL remain under data/. Accepted snapshot is data/snapshots/real-v1.jsonl; all polled is real-v1-polled.jsonl. Intake queues only in data/real/real-v1/intake.db; no workers run. Production database is never opened. Later replay requires registering sources from the committed source list before using omni replay; no registration/ingestion is done here.",
        "",
        "Cached requests make a rerun deterministic. Use a new corpus name/source file to collect a different window or refresh upstream content; the recorded window is immutable. Client: omnistream-research/0.1 (local academic project). At least 3 s between network requests per host, larger robots crawl-delay respected, and redirect destinations checked independently. Robots failures other than 404/410 deny access. Cache hits make no network requests. No login/paywall handling. All settings are constructed with _env_file=None; .env is never read.",
        "",
        "## C1 findings and fixes",
        "",
    ]
    if review.get("provenance_caveat"):
        lines += ["", review["provenance_caveat"], ""]
    lines.extend("- " + s for s in r["c1_changes"])
    lines += [
        "",
        "## Next options before corpus approval",
        "",
        "- Prefer additional feeds/APIs that explicitly publish complete licensed text, particularly earnings/filings. Obtain permission for restricted publishers rather than scraping their articles.",
        "- For SEC, use an approved organisational client identity/access route if the generic research client is blocked; do not evade the block.",
        "- Expand archive/API access under permitted source policies to improve source balance and date coverage; keep a separate corpus version.",
        "- Manually validate Finance bubble labels, source-body completeness and actual changed facts; then freeze the approved corpus before any evaluation questions are authored.",
        "",
    ]
    (docs / f"{r['name']}-quality.md").write_text(
        "\n".join(lines) + "\n", encoding="utf8"
    )
