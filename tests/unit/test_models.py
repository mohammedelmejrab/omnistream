import pytest
from pydantic import ValidationError

from omnistream.config import Settings
from omnistream.models import ApiFeedConfig, Source


def make_source(**kw):
    base = dict(id="s1", type="rss", url="http://example.com/feed")
    base.update(kw)
    return Source(**base)


@pytest.mark.parametrize("value", [1.5, -0.1])
def test_source_rejects_credibility_out_of_range(value):
    with pytest.raises(ValidationError):
        make_source(credibility=value)


def test_source_rejects_poll_interval_below_60():
    with pytest.raises(ValidationError):
        make_source(poll_interval=59)


def test_api_source_requires_api_config():
    with pytest.raises(ValidationError):
        make_source(type="api", api_config=None)
    cfg = ApiFeedConfig(items_path="items", text_field="t", url_field="u")
    assert make_source(type="api", api_config=cfg).api_config is cfg


def test_settings_defaults():
    s = Settings()
    assert s.embed_match_threshold == 0.88
