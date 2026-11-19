"""Read-only passage-to-entity joins for the own retriever."""

from omnistream.graph.neo4j_store import _entity
from omnistream.retrieval.own_algorithm.seeding import Seed, is_named_entity

# Five classic chunks; one vote per episode (best chunk rank). No generic nodes.
PASSAGE_K = 5

_MENTIONS = """
UNWIND $passages AS p
MATCH (ep:Episodic {group_id:p.bubble, item_id:p.item})-[:MENTIONS]->(n:Entity)
WHERE n.group_id = p.bubble
WITH n, ep, min(p.rank) AS rank
WITH n, sum(1.0 / rank) AS votes
MATCH (other:Episodic)-[:MENTIONS]->(n)
WITH n, votes, count(DISTINCT other) AS frequency
RETURN n{.uuid, .group_id, .name, .aliases, .type, .entity_type, labels:labels(n),
 global_id:head([(n)-[:SAME_AS]->(g:GlobalEntity) | g.uuid])} AS entity,
 votes / frequency AS score
"""

_FREQUENCIES = """
UNWIND $ids AS id
MATCH (n:Entity {uuid:id})<-[:MENTIONS]-(ep:Episodic)
RETURN id, count(DISTINCT ep) AS frequency
"""


class PassageSource:
    def __init__(self, classic, graph):
        self.classic = classic
        self.graph = graph

    def dense(self, question, bubbles, time_scope, top_k):
        return self.classic.retrieve(
            question, bubbles=bubbles, time_scope=time_scope, top_k=top_k
        ).chunks

    def seeds(self, question, bubbles, time_scope, chunks=None):
        if chunks is None:
            chunks = self.dense(question, bubbles, time_scope, PASSAGE_K)
        chunks = list(chunks)[:PASSAGE_K]
        passages = [
            {"bubble": c.bubble, "item": c.item_id, "rank": i}
            for i, c in enumerate(chunks, 1)
        ]
        found = []
        if passages:
            for row in self.graph._run(_MENTIONS, passages=passages):
                entity = _entity(row["entity"])
                if is_named_entity(entity):
                    found.append(Seed(entity, row["score"], "passage"))
        return found

    def restart_weights(self, seeds):
        counts = {
            row["id"]: row["frequency"]
            for row in self.graph._run(_FREQUENCIES, ids=[s.entity.id for s in seeds])
        }
        # Missing mentions carry neutral weight; apply after seed selection.
        return {s.entity.id: s.score / counts.get(s.entity.id, 1) for s in seeds}
