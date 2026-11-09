from datetime import UTC, datetime

import pytest

from omnistream.ingest.extract import Extractor
from omnistream.llm import LLMError
from omnistream.models import ExtractedTriple, Extraction, RawItem
from tests.conftest import FakeLLM


def triple(**kw) -> ExtractedTriple:
    base = {
        "subject": "Tim Cook",
        "subject_type": "PERSON",
        "relation": "CEO_OF",
        "object": "Apple",
        "object_type": "ORG",
    }
    return ExtractedTriple(**{**base, **kw})


def item(**kw) -> RawItem:
    base = {"source_id": "s1", "url": "https://x.test/a", "title": "T", "text": "body"}
    return RawItem(**{**base, **kw})


def extractor(*triples: ExtractedTriple) -> tuple[Extractor, FakeLLM]:
    fake = FakeLLM({Extraction: Extraction(triples=list(triples))})
    return Extractor(fake, "m"), fake


async def test_extract_normalizes_relations():
    ex, _ = extractor(triple(relation="is CEO of"))
    result = await ex.extract(item())
    assert result.triples[0].relation == "IS_CEO_OF"


async def test_extract_drops_self_loops_and_empty_fields():
    ex, _ = extractor(
        triple(),
        triple(subject="Apple", object=" apple "),
        triple(subject="  "),
        triple(object=""),
        triple(relation="!!!"),
        triple(subject_type=" "),
        triple(object_type=""),
    )
    result = await ex.extract(item())
    assert len(result.triples) == 1
    assert result.triples[0].subject == "Tim Cook"


async def test_extract_unknown_type_becomes_other():
    ex, _ = extractor(triple(subject_type="gizmo", object_type=" org "))
    t = (await ex.extract(item())).triples[0]
    assert t.subject_type == "OTHER"
    assert t.object_type == "ORG"


async def test_extract_preserves_surface_forms_and_fields():
    vf = datetime(2024, 1, 1, tzinfo=UTC)
    ex, _ = extractor(triple(subject=" Tim Cook ", exclusive=True, valid_from=vf))
    t = (await ex.extract(item())).triples[0]
    assert t.subject == "Tim Cook"
    assert t.exclusive is True
    assert t.valid_from == vf


async def test_extract_prompt_contains_title_published_text():
    ex, fake = extractor()
    pub = datetime(2024, 5, 1, tzinfo=UTC)
    await ex.extract(item(title="Headline", text="Some body", published_at=pub))
    user = fake.calls[0][1]
    assert "Title: Headline" in user
    assert f"Published: {pub.isoformat()}" in user
    assert "Text: Some body" in user
    await ex.extract(item())
    assert "Published: unknown" in fake.calls[1][1]


async def test_extract_uses_configured_model():
    ex, fake = extractor()
    await ex.extract(item())
    assert fake.calls[0][0] == "m"


async def test_extract_propagates_llm_error():
    def boom(_user):
        raise LLMError("refused")

    ex = Extractor(FakeLLM({Extraction: boom}), "m")
    with pytest.raises(LLMError):
        await ex.extract(item())
