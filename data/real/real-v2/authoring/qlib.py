"""Helper used by the batch_*.py authoring files (working files, not deliverables)."""
import json
import os

N, F, R = "News", "Finance", "Research"


def q(id, question, ans, facts, ev, bubbles, alias=None, distractors=(), notes="", time_scope=None,
      type="multi_hop", split=None):
    if split is None:
        split = "test" if id.startswith("rq-t-") else "dev"
    gold = []
    for e in ev:
        if e[0] not in gold:
            gold.append(e[0])
    d = dict(id=id, split=split, type=type, question=question, reference_answer=ans, key_facts=facts, gold=gold,
             evidence=[dict(item_id=e[0], quote=e[1], establishes=e[2]) for e in ev], expected_bubbles=bubbles,
             time_scope=time_scope, alias_bridge=bool(alias), distractors=list(distractors), notes=notes)
    if alias:
        d["surface_forms"] = alias
    return d


def save(name, qs):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    json.dump(qs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved", name, len(qs))
