"""Offline validator for src/omnistream/eval/corpus/real-v2-questions.json.

Usage:
    .venv/Scripts/python.exe scripts/realdata/check_questions.py [--table out.md]

Hard checks (FAIL): schema, id format and uniqueness, gold/evidence/distractor ids exist in
the real-v2 manifest, evidence quotes found verbatim in the local clean text, quote length
<= 15 words, evidence items are gold items, dev/test share no gold item, freshness items are
used by exactly one question and appear in no other question's gold, no output text copies
16 or more consecutive words from a gold item, routing labels are well formed.
Soft checks (WARN): counts per split and type against the targets, alias-bridge minimums,
answer-token uniqueness search (other items that contain the reference answer's distinctive
tokens; these are listed so a verifier can check them).
Needs only the standard library and the local corpus under data/real/real-v2/.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QFILE = ROOT / "src/omnistream/eval/corpus/real-v2-questions.json"
MANIFEST = ROOT / "src/omnistream/eval/real/real-v2-manifest.jsonl"
TARGETS = {
    "test": {"single": 15, "multi_hop": 20, "time_sensitive": 15, "freshness": 10},
    "dev": {"single": 8, "multi_hop": 10, "time_sensitive": 7, "freshness": 5},
}
ALIAS_MIN = {"test": 6, "dev": 3}
TSMC_MONTHLY_MAX = {"test": 4, "dev": 2}
BUBBLES = {"News", "Finance", "Research"}
REQUIRED = ["id", "split", "type", "question", "reference_answer", "key_facts", "gold", "evidence",
            "expected_bubbles", "time_scope", "alias_bridge", "distractors", "notes"]
HINT = {"news": "News", "finance": "Finance", "research": "Research"}

fails: list[str] = []
warns: list[str] = []


def fail(msg: str) -> None:
    fails.append(msg)


def warn(msg: str) -> None:
    warns.append(msg)


def words(s: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9$€%.,'’\-]+", s.lower())


def answer_tokens(ans: str) -> list[str]:
    """Distinctive tokens of a reference answer: numbers with decimals or separators, and proper names."""
    toks = re.findall(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+|\b\d{2,}\b", ans)
    toks += re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z]+\b", ans)
    stop = {"2026", "2027", "2028", "2029", "2030", "2031"}
    return [t for t in dict.fromkeys(toks) if t not in stop]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", help="write a per-question self-check table (markdown) to this path")
    args = ap.parse_args()

    manifest = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            m = json.loads(line)
            manifest[m["id"]] = m
    texts: dict[str, str] = {}

    def text(i: str) -> str:
        if i not in texts:
            texts[i] = (ROOT / manifest[i]["text_path"]).read_text(encoding="utf-8", errors="replace")
        return texts[i]

    data = json.loads(QFILE.read_text(encoding="utf-8"))
    for k in ["version", "corpus", "split_assignment", "freshness_item_ids", "questions", "routing_labels"]:
        if k not in data:
            fail(f"top-level key missing: {k}")
    qs = data.get("questions", [])
    rows = []
    ids = Counter(q.get("id") for q in qs)
    for i, n in ids.items():
        if n > 1:
            fail(f"duplicate question id {i}")
    gold_by_split = defaultdict(set)
    gold_owner = defaultdict(list)
    support_by_split = defaultdict(set)
    for q in qs:
        qid = q.get("id", "?")
        for k in REQUIRED:
            if k not in q:
                fail(f"{qid}: missing field {k}")
        if q.get("split") not in TARGETS:
            fail(f"{qid}: bad split {q.get('split')}")
            continue
        pref = "rq-t-" if q["split"] == "test" else "rq-d-"
        if not re.fullmatch(pref + r"\d{3}", qid):
            fail(f"{qid}: id does not match split prefix {pref}")
        if q.get("type") not in TARGETS["test"]:
            fail(f"{qid}: bad type {q.get('type')}")
        if not q.get("key_facts"):
            fail(f"{qid}: empty key_facts")
        if not set(q.get("expected_bubbles", [])) <= BUBBLES or not q.get("expected_bubbles"):
            fail(f"{qid}: bad expected_bubbles {q.get('expected_bubbles')}")
        if q.get("alias_bridge") and len(q.get("surface_forms", [])) < 2:
            fail(f"{qid}: alias_bridge without two surface_forms")
        gold = q.get("gold", [])
        if not gold:
            fail(f"{qid}: no gold items")
        acceptable = q.get("acceptable_evidence", [])
        if not isinstance(acceptable, list) or any(not isinstance(i, str) for i in acceptable):
            fail(f"{qid}: acceptable_evidence must be a list of item IDs")
            acceptable = []
        if len(acceptable) != len(set(acceptable)):
            fail(f"{qid}: duplicate acceptable_evidence")
        if set(acceptable) & set(gold):
            fail(f"{qid}: acceptable_evidence overlaps gold")
        if set(acceptable) & set(q.get("distractors", [])):
            fail(f"{qid}: acceptable_evidence overlaps distractors")
        for field in ("exclude_from_scoring", "date_order_unavailable", "exclude_from_freshness_scoring"):
            if field in q and not isinstance(q[field], bool):
                fail(f"{qid}: {field} must be boolean")
        if q.get("exclude_from_scoring") and (not isinstance(q.get("exclusion_reason"), str) or not q["exclusion_reason"].strip()):
            fail(f"{qid}: excluded question needs exclusion_reason")
        if (q.get("date_order_unavailable") or q.get("exclude_from_freshness_scoring")) and not q.get("exclude_from_scoring"):
            fail(f"{qid}: special scoring exclusion requires exclude_from_scoring")
        if q.get("date_order_unavailable") and q.get("type") != "time_sensitive":
            fail(f"{qid}: date_order_unavailable requires time_sensitive")
        if q.get("exclude_from_freshness_scoring") and q.get("type") != "freshness":
            fail(f"{qid}: freshness exclusion requires freshness type")
        overlaps = q.get("split_overlap", [])
        if not isinstance(overlaps, list):
            fail(f"{qid}: split_overlap must be a list")
            overlaps = []
        for record in overlaps:
            if not isinstance(record, dict) or set(record) != {"item", "other_split_org"}:
                fail(f"{qid}: malformed split_overlap record")
                continue
            i, org = record["item"], record["other_split_org"]
            if i not in gold + acceptable or i not in manifest:
                fail(f"{qid}: split_overlap item must be known gold or acceptable evidence")
            elif not isinstance(org, str) or not org.strip() or org not in text(i):
                fail(f"{qid}: split_overlap organisation not found in source")
        support_by_split[q["split"]].update(gold + acceptable)
        support_by_split[q["split"]].update(e.get("item_id") for e in q.get("evidence", []))
        for g in gold + q.get("distractors", []) + acceptable:
            if g not in manifest:
                fail(f"{qid}: id not in manifest {g}")
        if set(gold) & set(q.get("distractors", [])):
            fail(f"{qid}: an item is both gold and distractor")
        for g in gold:
            gold_by_split[q["split"]].add(g)
            gold_owner[g].append(qid)
        if q["type"] == "multi_hop":
            hints = {HINT[manifest[g]["bubble_hint"]] for g in gold if g in manifest}
            if len(gold) < 2 or len(set(q.get("expected_bubbles", []))) < 2:
                fail(f"{qid}: multi_hop needs >=2 gold items and >=2 expected bubbles")
            if len(hints) < 2:
                warn(f"{qid}: multi_hop gold items share one source bubble hint {hints}")
        if q["type"] == "time_sensitive" and len(gold) < 2:
            fail(f"{qid}: time_sensitive needs old and new items")
        quotes_ok, len_ok = True, True
        ev_items = set()
        for e in q.get("evidence", []):
            i, quote = e.get("item_id"), e.get("quote", "")
            ev_items.add(i)
            if i not in gold:
                fail(f"{qid}: evidence item {str(i)[:8]} not in gold")
            if i not in manifest:
                quotes_ok = False
                continue
            if quote not in text(i):
                quotes_ok = False
                fail(f"{qid}: quote not found verbatim in {i[:8]}: {quote!r}")
            if len(quote.split()) > 15:
                len_ok = False
                fail(f"{qid}: quote longer than 15 words ({len(quote.split())})")
            if not e.get("establishes"):
                fail(f"{qid}: evidence without paraphrase")
        if set(gold) - ev_items:
            fail(f"{qid}: gold items without evidence {[g[:8] for g in set(gold) - ev_items]}")
        # copying check: no 16-word run from any gold text in the authored prose
        prose = " ".join([q.get("question", ""), q.get("reference_answer", ""), q.get("notes", "")]
                         + list(map(str, q.get("key_facts", []))))
        pw = words(prose)
        for g in gold:
            if g not in manifest:
                continue
            gw = words(text(g))
            grams = {tuple(gw[k:k + 16]) for k in range(len(gw) - 15)}
            if any(tuple(pw[k:k + 16]) in grams for k in range(len(pw) - 15)):
                fail(f"{qid}: authored text copies 16+ consecutive words from {g[:8]}")
        # uniqueness search over the whole corpus
        toks = answer_tokens(q.get("reference_answer", ""))
        others = set()
        for t in toks:
            for i in manifest:
                if i not in gold and t in text(i):
                    others.add(i)
        listed = others & set(q.get("distractors", []))
        rows.append((qid, q["split"], q["type"], all(g in manifest for g in gold), quotes_ok, len_ok,
                     ", ".join(toks) if toks else "(no distinctive token; manual search)",
                     len(others), len(listed), sorted(o[:8] for o in others)))

    # split disjointness
    inter = gold_by_split["test"] & gold_by_split["dev"]
    if inter:
        fail(f"dev and test share gold items: {[i[:8] for i in inter]}")
    for split, other in (("dev", "test"), ("test", "dev")):
        leaked = gold_by_split[split] & support_by_split[other]
        if leaked:
            fail(f"{split} gold overlaps {other} gold/evidence: {sorted(leaked)}")
    # freshness
    fr = data.get("freshness_item_ids", {})
    for split in TARGETS:
        fids = fr.get(split, [])
        fq = [q for q in qs if q.get("split") == split and q.get("type") == "freshness"]
        if sorted(fids) != sorted(g for q in fq for g in q["gold"]):
            fail(f"{split}: freshness_item_ids do not match freshness questions' gold")
        if len(set(fids)) != len(fids):
            fail(f"{split}: duplicate freshness item")
        for f_ in fids:
            if len(gold_owner[f_]) != 1:
                fail(f"{split}: freshness item {f_[:8]} used by {gold_owner[f_]}")
        dates = sorted(manifest[f_]["published_at"][:10] for f_ in fids if f_ in manifest)
        if dates:
            print(f"[info] {split} freshness items published {dates[0]} .. {dates[-1]}")
    # counts
    cnt = Counter((q.get("split"), q.get("type")) for q in qs)
    scored = Counter((q["split"], q["type"]) for q in qs if not q.get("exclude_from_scoring", False))
    print("scored questions: " + str(sum(scored.values())) + "  " + "  ".join(f"{s}/{t}={scored[s,t]}" for s in TARGETS for t in TARGETS[s]))
    print("excluded questions: " + ", ".join(q["id"] for q in qs if q.get("exclude_from_scoring")))
    print("acceptable_evidence additions: " + str(sum(len(q.get("acceptable_evidence", [])) for q in qs)))
    print("split_overlap records: " + "  ".join(f"{s}={sum(len(q.get('split_overlap', [])) for q in qs if q['split']==s)}" for s in TARGETS))
    for split, t in TARGETS.items():
        for typ, n in t.items():
            got = cnt[(split, typ)]
            if got != n:
                warn(f"count {split}/{typ}: {got} (target {n}) -> shortfall {n - got}")
        al = sum(1 for q in qs if q.get("split") == split and q.get("alias_bridge"))
        if al < ALIAS_MIN[split]:
            warn(f"{split}: {al} alias-bridge questions (target >= {ALIAS_MIN[split]})")
        tsmc = sum(1 for q in qs if q.get("split") == split and q.get("type") == "time_sensitive"
                   and any(manifest[g]["source"] == "edgar-tsmc" for g in q["gold"] if g in manifest)
                   and "month" in q.get("question", "").lower() + q.get("reference_answer", "").lower())
        if tsmc > TSMC_MONTHLY_MAX[split]:
            fail(f"{split}: {tsmc} TSMC monthly time-sensitive questions (max {TSMC_MONTHLY_MAX[split]})")
    # routing labels
    rl = data.get("routing_labels", [])
    per_hint = Counter()
    for r in rl:
        if r.get("item_id") not in manifest:
            fail(f"routing label for unknown item {r.get('item_id')}")
            continue
        per_hint[manifest[r["item_id"]]["bubble_hint"]] += 1
        if not r.get("routing_labels") or not set(r["routing_labels"]) <= BUBBLES or not r.get("reason"):
            fail(f"routing label malformed for {r['item_id'][:8]}")
    if len(rl) != 80 or len({r.get("item_id") for r in rl}) != 80:
        fail(f"routing_labels: need 80 distinct items, got {len(rl)}")
    if any(per_hint[h] < 20 for h in HINT):
        fail(f"routing_labels: fewer than 20 for some hint {dict(per_hint)}")

    # report
    print(f"questions: {len(qs)}  " + "  ".join(f"{s}/{t}={cnt[(s, t)]}" for s in TARGETS for t in TARGETS[s]))
    print(f"alias bridges: test={sum(1 for q in qs if q['split']=='test' and q.get('alias_bridge'))} "
          f"dev={sum(1 for q in qs if q['split']=='dev' and q.get('alias_bridge'))}")
    print(f"gold items: test={len(gold_by_split['test'])} dev={len(gold_by_split['dev'])} shared={len(inter)}")
    print(f"routing labels: {len(rl)} {dict(per_hint)}; differ from hint: "
          f"{sum(1 for r in rl if r.get('differs_from_hint'))}")
    print(f"uniqueness search: {len(rows)} questions searched; "
          f"{sum(1 for r in rows if r[7])} have answer tokens in non-gold items (see table / notes)")
    for w in warns:
        print("WARN", w)
    for f_ in fails:
        print("FAIL", f_)
    if args.table:
        lines = ["| id | split | type | gold ids exist | quotes verbatim | quotes <= 15 words | answer tokens searched | non-gold items containing them | of which listed as distractors |",
                 "|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            yn = lambda b: "yes" if b else "NO"
            other = f"{r[7]} ({', '.join(r[9][:6])}{', ...' if len(r[9]) > 6 else ''})" if r[7] else "0"
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {yn(r[3])} | {yn(r[4])} | {yn(r[5])} | {r[6]} | {other} | {r[8]} |")
        Path(args.table).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"table written: {args.table}")
    print("RESULT:", "FAIL" if fails else "PASS", f"({len(fails)} failures, {len(warns)} warnings)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
