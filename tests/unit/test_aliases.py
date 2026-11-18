"""Unit tests for source-evidenced alias extraction (ingestion item 2a)."""

import pytest

from omnistream.graph.aliases import (
    acronym_consistent,
    extract_alias_pairs,
    initials,
    name_key,
    names_differ_by_number,
    number_tokens,
)

# All 20 eval-v2 source-stated pairs (see docs/diagnostics/eval-v2-diagnosis.md).
EVAL_V2_PAIRS = [
    ("Halvex Mobility", "HVM"),
    ("Nacreline Systems", "NLS"),
    ("Brindle Arc", "BDA"),
    ("Oxbriar Robotics", "OBR"),
    ("Vespergate Works", "VGW"),
    ("Quenara Devices", "QND"),
    ("Tesselmere Controls", "TMC"),
    ("Aldervane Transit", "AVT"),
    ("Pellucid Forge", "PCF"),
    ("Ravenspire Instruments", "RSI"),
    ("Cobalt Reach Laboratory", "CRL"),
    ("Juniper Basin Institute", "JBI"),
    ("Sable Meridian Centre", "SMC"),
    ("Ivory Delta Laboratory", "IDL"),
    ("Copper Fen Institute", "CFI"),
    ("Indigo Vale Centre", "IVC"),
    ("Opal Ridge Laboratory", "ORL"),
    ("Ochre Hollow Institute", "OHI"),
    ("Violet Strand Centre", "VSC"),
    ("Silver Marsh Laboratory", "SML"),
]


def test_listed_abbreviation_used_by_finds_all_company_pairs():
    for full, short in EVAL_V2_PAIRS[:10]:
        text = f"ANALYST NOTE. {short}, the listed abbreviation used by {full}, signed."
        pairs = extract_alias_pairs(text)
        assert (full, short) in pairs, (full, short)


def test_parenthetical_acronym_finds_all_lab_pairs():
    for full, short in EVAL_V2_PAIRS[10:]:
        text = f"{full} ({short}) reported a result."
        assert (full, short) in extract_alias_pairs(text)


def test_funding_note_yields_both_pairs():
    text = (
        "ANALYST NOTE. HVM, the listed abbreviation used by Halvex Mobility, signed "
        "a research funding agreement with Cobalt Reach Laboratory (CRL) on February 7."
    )
    pairs = extract_alias_pairs(text)
    assert ("Halvex Mobility", "HVM") in pairs
    assert ("Cobalt Reach Laboratory", "CRL") in pairs


def test_no_duplicates():
    text = "Cobalt Reach Laboratory (CRL) and again Cobalt Reach Laboratory (CRL)."
    assert extract_alias_pairs(text) == [("Cobalt Reach Laboratory", "CRL")]


# --- negatives ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "revenue (USD)",
        "the figure (2024)",
        "(see above)",
        "traded on (NYSE: X)",
        "revenue was 12 (USD)",
    ],
)
def test_negatives_yield_nothing(text):
    assert extract_alias_pairs(text) == []


def test_pure_acronym_initials_without_source_not_extracted():
    # No explicit marker: even a perfect initial match must not be invented.
    assert extract_alias_pairs("Cobalt Reach Laboratory CRL") == []


def test_ticker_not_treated_as_alias():
    # (NYSE: X) is never a name alias; reversed ticker-style also fails initials.
    assert extract_alias_pairs("Apple Inc. (AAPL)") == []


# --- initials / acronym consistency ------------------------------------------


@pytest.mark.parametrize(
    "full,short",
    [
        ("Cobalt Reach Laboratory", "CRL"),
        ("Ivory Delta Laboratory", "IDL"),
        ("Copper Fen Institute", "CFI"),
        ("United States of America", "USA"),
        ("World Health Organization", "WHO"),
        ("BioNTech", "BNT"),
    ],
)
def test_acronym_consistent_true(full, short):
    assert acronym_consistent(full, short)


@pytest.mark.parametrize(
    "full,short",
    [
        ("revenue", "USD"),
        ("Apple", "AAPL"),
        ("Aldervane Transit", "AVT"),  # V is not an initial of Aldervane Transit
        ("Brindle Arc", "BDA"),  # D is not an initial
    ],
)
def test_acronym_consistent_false(full, short):
    assert not acronym_consistent(full, short)


def test_initials_drop_stopwords_and_legal_suffix():
    assert initials("Cobalt Reach Laboratory") == "CRL"
    assert initials("United States of America") == "USA"
    assert initials("Apple Incorporated") == "A"
    assert initials("BioNTech") == "BNT"


# --- number-token guard ------------------------------------------------------


def test_names_differ_by_number():
    assert names_differ_by_number("Dovetail Quay 9", "Dovetail Quay 10")
    assert names_differ_by_number("Dovetail Quay 9", "Dovetail Quay")
    assert not names_differ_by_number("Dovetail Quay 9", "Dovetail Quay 9")
    assert not names_differ_by_number("Acme", "Acme Corp")


def test_number_tokens():
    assert number_tokens("Dovetail Quay 10") == ("10",)
    assert number_tokens("no numbers here") == ()
    assert number_tokens("1,234 and 5.6") == ("1,234", "5.6")


def test_name_key():
    assert name_key("Aldervane Transit") == name_key("alderVANE   transit")
    assert name_key("Inc.") == name_key("inc")
