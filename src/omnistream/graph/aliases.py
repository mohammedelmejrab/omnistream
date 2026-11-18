"""Source-evidenced alias and abbreviation extraction (ingestion item 2a).

``extract_alias_pairs`` finds explicit ``(full, short)`` alias pairs in a piece of
source text.  Everything here is lexical and deterministic; no embeddings, no
LLM.  The rules are deliberately conservative:

* parenthetical acronyms (``Full Name (ABBR)`` and ``ABBR (Full Name)``) are only
  accepted when the acronym is consistent with the full name's initials;
* ticker symbols (``(NYSE: X)``) are **not** treated as aliases — a ticker is an
  exchange identifier, not a name, and treating it as a name alias risks merging
  distinct issuers that share a symbol across markets;
* explicit markers (``the listed abbreviation used by``, ``known as``,
  ``also known as``, ``a.k.a.``, ``formerly``) are accepted as stated, because
  the source itself asserts the identity.

A pure acronym-initials match *without* source evidence is intentionally not a
merge signal anywhere in this package.
"""

from __future__ import annotations

import re

# Words that never contribute initials.
_INITIAL_STOPWORDS = frozenset(
    {"of", "the", "and", "for", "or", "a", "an", "&", "at", "in", "on", "to", "with", "by"}
)

# Legal-form suffixes, dropped from an organization's full name before initials.
_LEGAL_SUFFIX_WORDS = frozenset(
    {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "ltd",
        "limited",
        "llc",
        "plc",
        "ag",
        "gmbh",
        "sa",
        "nv",
        "lp",
        "llp",
        "group",
        "holdings",
    }
)

_NUMBER_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")

# A capitalized proper name of 1..7 words, allowing a lowercase stopword between
# capitalized words ("United States of America", "Cobalt Reach Laboratory") and a
# trailing number token ("Dovetail Quay 9").
_STOP = r"(?:of|the|and|for|or|in|on|to|a|an|&|at|with|by)"
_WORD = r"[A-Z][A-Za-z&]*"
_NUM = r"\d+(?:[.,]\d+)?"
_TERM = rf"{_WORD}(?:\s+{_NUM})?"
_FULL_NAME = rf"{_TERM}(?:\s+(?:{_STOP}\s+)?{_TERM}){{0,6}}"
# A short alias: an acronym ("HVM", "DQ9") or a short capitalized name.
_ACRONYM = r"[A-Z][A-Z0-9]{1,7}"
_ALIAS = rf"{_TERM}(?:\s+(?:{_STOP}\s+)?{_TERM}){{0,3}}"

# "Cobalt Reach Laboratory (CRL)" — parenthetical acronym (initials-checked).
_PAREN_ACRO = re.compile(rf"\b({_FULL_NAME})\s+\(([A-Z][A-Za-z]{{1,7}})\)")
# "CRL (Cobalt Reach Laboratory)" — reversed parenthetical (initials-checked).
_PAREN_FULL = re.compile(rf"\b({_ACRONYM})\s+\(({_FULL_NAME})\)")

# "AVT, the listed abbreviation used by Aldervane Transit" — explicit statement.
_ABBR_USED_BY = re.compile(
    rf"\b({_ACRONYM}),\s+the\s+(?:listed\s+)?abbreviation\s+(?:used\s+by|for|of)\s+({_FULL_NAME})"
)
_ABBR_IS = re.compile(
    rf"\b({_ACRONYM})\s+(?:is|stands\s+for)\s+(?:the\s+|an\s+)?"
    rf"(?:abbreviation|acronym)\s+(?:used\s+by|for|of)\s+({_FULL_NAME})"
)

# "Full Name, known as X" / "Full Name, also known as X".
_KNOWN_AS = re.compile(rf"\b({_FULL_NAME})\s*,\s*(?:also\s+)?known\s+as\s+({_ALIAS})")
# "Full Name a.k.a. X" / "Full Name, aka X".
_AKA = re.compile(rf"\b({_FULL_NAME})\s*(?:,)?\s+(?:a\.k\.a\.|aka)\s+({_ALIAS})")
# "Full Name, formerly X" / "Full Name, formerly known as X".
_FORMERLY = re.compile(
    rf"\b({_FULL_NAME})\s*,\s*(?:formerly|previously)\s+(?:known\s+as\s+)?({_ALIAS})"
)


def _significant_words(name: str) -> list[str]:
    """Drop stopwords and legal suffixes; keep each remaining capitalized word."""
    words = re.findall(r"[A-Za-z&][A-Za-z&]*", name)
    out: list[str] = []
    for word in words:
        key = word.casefold().rstrip(".")
        if key in _INITIAL_STOPWORDS or key in _LEGAL_SUFFIX_WORDS:
            continue
        out.append(word)
    return out


def _word_initials(word: str) -> str:
    """First character uppercased plus any further capital letters.

    ``Aldervane`` -> ``A``; ``BioNTech`` -> ``BNT``; ``iPhone`` -> ``IP``.
    """
    if not word:
        return ""
    return word[0].upper() + "".join(c for c in word[1:] if c.isupper())


def initials(name: str) -> str:
    """The initial-letter string for a full name (stopwords and suffixes dropped)."""
    return "".join(_word_initials(w) for w in _significant_words(name)).upper()


def acronym_consistent(full: str, short: str) -> bool:
    """True when ``short`` is consistent with ``full``'s initials.

    The acronym must be an anchored subsequence of the initials string: it starts
    with the first significant word's initial and ends with the last word's
    initial, and its letters appear in order.  This accepts ``CRL`` for ``Cobalt
    Reach Laboratory`` and rejects ``USD`` for ``revenue`` and ``AAPL`` for
    ``Apple``.
    """
    acro = "".join(c for c in short if c.isalpha()).upper()
    if len(acro) < 2:
        return False
    initial = initials(full)
    if not initial:
        return False
    if acro[0] != initial[0] or acro[-1] != initial[-1]:
        return False
    it = iter(initial)
    return all(c in it for c in acro)


def number_tokens(name: str) -> tuple[str, ...]:
    """Digit runs in a name, e.g. ``Dovetail Quay 10`` -> ``('10',)``."""
    return tuple(_NUMBER_TOKEN.findall(name))


def names_differ_by_number(a: str, b: str) -> bool:
    """True when the two names carry a different set of number tokens.

    Guards the documented wrong merge: ``Dovetail Quay 9`` vs ``Dovetail Quay 10``
    (and a numbered name vs an unnumbered one) must never be joined.
    """
    return sorted(number_tokens(a)) != sorted(number_tokens(b))


_UNKNOWN = ("", "entity", "unknown")


def types_compatible(a: str, b: str) -> bool:
    """Two entity types are compatible when equal or either side is unknown.

    "Unknown" covers the untyped fallback label ``Entity`` plus empty strings, so
    a typed side may still resolve against an untyped GlobalEntity (and vice
    versa) during alias linking.
    """
    return a == b or (a or "").strip().casefold() in _UNKNOWN or (b or "").strip().casefold() in _UNKNOWN


def name_key(name: str) -> str:
    """Casefolded, punctuation-free key for exact name comparison."""
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _dedupe(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for full, short in pairs:
        full, short = full.strip(), short.strip()
        if not full or not short or name_key(full) == name_key(short):
            continue
        key = (name_key(full), name_key(short))
        if key in seen:
            continue
        seen.add(key)
        out.append((full, short))
    return out


def extract_alias_pairs(text: str) -> list[tuple[str, str]]:
    """Return source-stated ``(full, short)`` alias pairs from ``text``.

    Recognised patterns (conservative, see module docstring):

    * ``Full Name (ABBR)`` and ``ABBR (Full Name)`` — initials-checked;
    * ``ABBR, the listed abbreviation used by Full Name`` — explicit;
    * ``Full Name, known as X`` / ``also known as X`` / ``a.k.a. X``;
    * ``Full Name, formerly X`` (a former name is an alias of the same entity).

    ``(2024)``, ``(see above)``, ``revenue (USD)`` and ``(NYSE: X)`` yield nothing.
    """
    if not text:
        return []
    pairs: list[tuple[str, str]] = []

    for match in _ABBR_USED_BY.finditer(text):
        pairs.append((match.group(2), match.group(1)))
    for match in _ABBR_IS.finditer(text):
        pairs.append((match.group(2), match.group(1)))

    for match in _PAREN_ACRO.finditer(text):
        full, short = match.group(1), match.group(2)
        if acronym_consistent(full, short):
            pairs.append((full, short))
    for match in _PAREN_FULL.finditer(text):
        short, full = match.group(1), match.group(2)
        if acronym_consistent(full, short):
            pairs.append((full, short))

    for match in _KNOWN_AS.finditer(text):
        pairs.append((match.group(1), match.group(2)))
    for match in _AKA.finditer(text):
        pairs.append((match.group(1), match.group(2)))
    for match in _FORMERLY.finditer(text):
        pairs.append((match.group(1), match.group(2)))

    return _dedupe(pairs)
