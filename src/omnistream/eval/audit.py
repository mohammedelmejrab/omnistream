"""Deterministic 100-node graph audit with semantic duplicate confirmation."""

import asyncio
import json
import random
import re

import numpy as np


def normalized(name):
    return re.sub(r"[^a-z0-9]", "", name.casefold())


async def audit_graph(builder, judge):
    records = await builder.writer.ops._q(
        "MATCH (e:Entity) WHERE e.group_id IN $groups OPTIONAL MATCH (e)-[:SAME_AS]->(g:GlobalEntity) RETURN e.uuid AS id, e.name AS name, e.group_id AS bubble, e.grounded AS grounded, g.uuid AS global_id ORDER BY id",
        groups=list(builder.groups.values()),
    )
    # Keep one row per local entity even if malformed multiple global links exist.
    nodes = list({r["id"]: r for r in records}.values())
    sample = random.Random(731).sample(nodes, min(100, len(nodes)))
    if not nodes:
        return {
            "audit_sample_size": 0,
            "duplicate_entity_rate": None,
            "ungrounded_entity_rate": None,
            "audit_pairs": [],
        }
    embeddings = await asyncio.to_thread(
        builder.embedder.service.embed_documents, [n["name"] for n in nodes]
    )
    positions = {n["id"]: i for i, n in enumerate(nodes)}
    duplicates = set()
    pairs = []
    confirmed = set()
    for node in sample:
        index = positions[node["id"]]
        for other_index, other in enumerate(nodes):
            if node["id"] == other["id"]:
                continue
            if (
                node["bubble"] != other["bubble"]
                and node["global_id"]
                and node["global_id"] == other["global_id"]
            ):
                continue
            cosine = float(np.dot(embeddings[index], embeddings[other_index]))
            if normalized(node["name"]) != normalized(other["name"]) and cosine < 0.88:
                continue
            pair = tuple(sorted((node["id"], other["id"])))
            if pair in confirmed:
                duplicates.add(node["id"])
                continue
            result = await asyncio.to_thread(
                judge.client.chat_json,
                [
                    {
                        "role": "system",
                        "content": 'Determine whether these two fictional entity names refer to the same real identity, including aliases. Generic concepts are the same only if semantically equivalent. Return JSON {"same":true|false,"rationale":"..."}.',
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"left": node["name"], "right": other["name"]}
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=250,
            )
            pairs.append(
                {
                    "left": node["id"],
                    "right": other["id"],
                    "left_name": node["name"],
                    "right_name": other["name"],
                    "cosine": cosine,
                    **result,
                }
            )
            if result.get("same") is True:
                confirmed.add(pair)
                duplicates.add(node["id"])
    return {
        "audit_sample_size": len(sample),
        "audit_entity_count": len(nodes),
        "duplicate_entity_rate": len(duplicates) / len(sample),
        "ungrounded_entity_rate": sum(n["grounded"] is False for n in nodes)
        / len(nodes),
        "grounding_flag_missing": sum(n["grounded"] is None for n in nodes),
        "audit_pairs": pairs,
    }
