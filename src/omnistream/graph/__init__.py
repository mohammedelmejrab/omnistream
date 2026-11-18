"""Graph package: C4 writer pieces and C5 read adapters (spec sections 4.3, C4, C5).

The writer side (``GraphWriter``, ``GraphOps``, linking, grounding, chunking)
runs the ingestion path; the read adapters (``InMemoryGraphStore``,
``Neo4jGraphStore``) serve the C5 ``own``/``graphiti`` retrieval modes and the
subagent graph tools. Graphiti imports stay inside ``graphiti_client``/
``graphiti_mode`` so callers that only need the stores never pull in
``graphiti_core`` eagerly.
"""

from omnistream.graph.aliases import (
    acronym_consistent,
    extract_alias_pairs,
    names_differ_by_number,
    types_compatible,
)
from omnistream.graph.chunks import ChunkStore
from omnistream.graph.graphiti_client import ENTITY_TYPES, build_graphiti
from omnistream.graph.grounding import ground_extraction, is_grounded
from omnistream.graph.linker import GlobalCandidate, GlobalEntityLinker
from omnistream.graph.memory_store import InMemoryGlobalEntityStore, InMemoryGraphStore
from omnistream.graph.neo4j_store import Neo4jGraphStore
from omnistream.graph.ops import EdgeState, GraphOps, Neo4jGraphOps
from omnistream.graph.writer import GraphWriter, build_graph_writer

__all__ = [
    "ENTITY_TYPES",
    "ChunkStore",
    "EdgeState",
    "GlobalCandidate",
    "GlobalEntityLinker",
    "GraphOps",
    "GraphWriter",
    "InMemoryGlobalEntityStore",
    "InMemoryGraphStore",
    "Neo4jGraphOps",
    "Neo4jGraphStore",
    "acronym_consistent",
    "build_graph_writer",
    "build_graphiti",
    "extract_alias_pairs",
    "ground_extraction",
    "is_grounded",
    "names_differ_by_number",
    "types_compatible",
]
