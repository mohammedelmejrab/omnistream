from omnistream.graph.grounding import ground_extraction, is_grounded
from omnistream.models import ExtractedTriple, Extraction

THRESHOLD = 85
APPLE_TEXT = (
    "Apple Inc. said on Tuesday it would open a new store in Berlin, "
    "its CEO Tim Cook announced."
)


def _triple(subject: str, obj: str) -> ExtractedTriple:
    return ExtractedTriple(
        subject=subject,
        subject_type="Company",
        relation="OPENS",
        object=obj,
        object_type="Place",
    )


def test_exact_mention_grounded():
    assert is_grounded("Tim Cook", APPLE_TEXT, THRESHOLD)


def test_minor_variation_grounded():
    assert is_grounded("Apple Inc", APPLE_TEXT, THRESHOLD)
    assert is_grounded(
        "Federal Reserve", "The federal  reserve raised rates.", THRESHOLD
    )


def test_hallucinated_entity_dropped():
    extraction = Extraction(
        triples=[_triple("Apple Inc", "Berlin"), _triple("Microsoft", "Berlin")]
    )
    kept, dropped = ground_extraction(extraction, APPLE_TEXT, THRESHOLD)
    assert dropped == 1
    assert [t.subject for t in kept.triples] == ["Apple Inc"]
    assert len(extraction.triples) == 2  # input not mutated


def test_short_mention_requires_word_boundary():
    assert not is_grounded("US", "the status quo", THRESHOLD)
    assert is_grounded("US", "the US economy", THRESHOLD)


def test_empty_mention_not_grounded():
    assert not is_grounded("   ", APPLE_TEXT, THRESHOLD)


def test_triple_dropped_if_object_ungrounded():
    extraction = Extraction(triples=[_triple("Apple Inc", "Zanzibar Holdings")])
    kept, dropped = ground_extraction(extraction, APPLE_TEXT, THRESHOLD)
    assert kept.triples == []
    assert dropped == 1


def test_empty_extraction_returns_zero_dropped():
    kept, dropped = ground_extraction(Extraction(triples=[]), APPLE_TEXT, THRESHOLD)
    assert kept.triples == []
    assert dropped == 0
