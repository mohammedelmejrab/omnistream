"""Offline tests for the single-call OpenIE extraction (graph/openie.py)."""

import json

from omnistream.graph.openie import (
    DEFAULT_TYPE,
    OpenIEEntity,
    OpenIEResult,
    OpenIETriple,
    canonical_type,
    clean_extraction,
    load_extraction_cache,
    name_key,
    relation_name,
)


def test_name_key_is_exact_match_normalisation():
    assert name_key("  Barack   Obama. ") == "barack obama"
    assert name_key("\"MINSK\"") == name_key("minsk")
    assert name_key("ＡＢＣ") == "abc"  # NFKC full-width
    assert name_key("Obama") != name_key("Barack Obama")  # no fuzzy merging


def test_canonical_type_maps_to_ontology_or_concept():
    assert canonical_type("person") == "Person"
    assert canonical_type("Organisation") == "Organization"
    assert canonical_type("Financial Instrument") == "FinancialInstrument"
    assert canonical_type("date") == DEFAULT_TYPE
    assert canonical_type("") == DEFAULT_TYPE


def test_relation_name_is_upper_snake():
    assert relation_name("date of birth") == "DATE_OF_BIRTH"
    assert relation_name("is part-of") == "IS_PART_OF"
    assert relation_name("!!!") == "RELATED_TO"


def test_clean_extraction_dedupes_and_adds_missing_endpoints():
    result = OpenIEResult(
        entities=[
            OpenIEEntity(name="Minsk Region", type="Location"),
            OpenIEEntity(name="minsk region", type="Concept"),  # duplicate key
            OpenIEEntity(name="Belarus", type="location"),
        ],
        triples=[
            OpenIETriple(subject="Minsk Region", predicate="is in", object="Belarus",
                         fact="Minsk Region is in Belarus."),
            OpenIETriple(subject="minsk region", predicate="is in", object="BELARUS"),
            OpenIETriple(subject="Minsk Region", predicate="capital", object="Minsk"),
            OpenIETriple(subject="Belarus", predicate="same", object="belarus"),
            OpenIETriple(subject="", predicate="x", object="Belarus"),
        ],
    )
    clean = clean_extraction(result)
    assert clean.entities["minsk region"] == ("Minsk Region", "Location")
    assert clean.entities["belarus"] == ("Belarus", "Location")
    # Endpoint the model did not list becomes an untyped concept.
    assert clean.entities["minsk"] == ("Minsk", DEFAULT_TYPE)
    assert clean.triples == [
        ("minsk region", "IS_IN", "belarus", "Minsk Region is in Belarus."),
        ("minsk region", "CAPITAL", "minsk", "Minsk Region capital Minsk"),
    ]


def test_extraction_cache_skips_torn_lines(tmp_path):
    path = tmp_path / "openie.jsonl"
    good = {"key": "p1", "result": {"entities": [], "triples": []}, "usage": None}
    path.write_text(json.dumps(good) + "\n" + '{"key": "p2", "res', encoding="utf-8")
    assert list(load_extraction_cache(path)) == ["p1"]
    assert load_extraction_cache(tmp_path / "missing.jsonl") == {}
