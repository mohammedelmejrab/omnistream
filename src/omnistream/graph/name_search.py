"""Shared lexical fallback and literal Lucene construction."""

import re

from rapidfuzz.fuzz import WRatio

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "from",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "has",
        "have",
        "had",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "which",
        "what",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "before",
        "after",
        "immediately",
        "than",
        "then",
        "as",
        "any",
        "all",
        "about",
        "into",
        "during",
        "under",
        "over",
        "company",
        "inc",
        "incorporated",
        "corporation",
        "com",
    ]
)


def content_words(question):
    return sorted(set(re.findall(r"\w+", question.casefold())) - STOPWORDS)


def escape_lucene(text):
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)', r"\\\1", text)


def lucene_query(question):
    return " OR ".join(
        'name:"' + escape_lucene(t) + '"' for t in content_words(question)
    )


def rank_names(question, entities):
    words = set(content_words(question))

    def score(e):
        names = (e.name, *e.aliases)
        overlap = max(
            (len(words & set(re.findall(r"\w+", n.casefold()))) for n in names),
            default=0,
        )
        fuzzy = max(
            (WRatio(" ".join(sorted(words)), n.casefold()) for n in names), default=0
        )
        return (-overlap, -fuzzy, e.name.casefold(), e.bubble, tuple(e.aliases))

    return sorted(entities, key=score) if words else []
