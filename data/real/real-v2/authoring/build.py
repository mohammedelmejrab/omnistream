"""Merge authoring batches into the questions file. Ids in batches are 8-char prefixes."""
import json, os, re, sys, glob, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
A = os.path.dirname(__file__)
M = [json.loads(l) for l in open(os.path.join(R, "src/omnistream/eval/real/real-v2-manifest.jsonl"), encoding="utf-8")]
def full(p):
    r = [m for m in M if m["id"].startswith(p)]
    assert len(r) == 1, (p, len(r))
    return r[0]["id"]
TXT = {}
def text(i):
    if i not in TXT:
        m = next(m for m in M if m["id"] == i)
        TXT[i] = open(os.path.join(R, m["text_path"]), encoding="utf-8", errors="replace").read()
    return TXT[i]
qs, errs = [], []
for f in sorted(glob.glob(os.path.join(A, "batch_*.json"))):
    for q in json.load(open(f, encoding="utf-8")):
        q["gold"] = [full(x) for x in q["gold"]]
        q["distractors"] = [full(x) for x in q.get("distractors", [])]
        for e in q["evidence"]:
            e["item_id"] = full(e["item_id"])
            if e["quote"] not in text(e["item_id"]):
                errs.append((q["id"], e["item_id"][:8], "QUOTE NOT FOUND", e["quote"]))
            if len(e["quote"].split()) > 15:
                errs.append((q["id"], e["item_id"][:8], "QUOTE TOO LONG", e["quote"]))
            if e["item_id"] not in q["gold"]:
                errs.append((q["id"], e["item_id"][:8], "EVIDENCE NOT IN GOLD", ""))
        q.setdefault("alias_bridge", False); q.setdefault("time_scope", None); q.setdefault("notes", "")
        qs.append(q)
meta = json.load(open(os.path.join(A, "meta.json"), encoding="utf-8")) if os.path.exists(os.path.join(A, "meta.json")) else {}
fresh = {"test": [], "dev": []}
for q in qs:
    if q["type"] == "freshness":
        fresh[q["split"]] += q["gold"]
rl = json.load(open(os.path.join(A, "routing.json"), encoding="utf-8")) if os.path.exists(os.path.join(A, "routing.json")) else []
for r in rl:
    r["item_id"] = full(r["item_id"])
out = {"version": "real-v2-q1", "corpus": "real-v2", "split_assignment": meta.get("split_assignment", {}),
       "freshness_item_ids": fresh, "questions": sorted(qs, key=lambda q: q["id"]), "routing_labels": rl}
dst = os.path.join(R, "src/omnistream/eval/corpus/real-v2-questions.json")
tmp = dst + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
json.load(open(tmp, encoding="utf-8"))
os.replace(tmp, dst)
from collections import Counter
print(len(qs), "questions", dict(Counter((q["split"], q["type"]) for q in qs)))
for e in errs: print("ERR", e)
