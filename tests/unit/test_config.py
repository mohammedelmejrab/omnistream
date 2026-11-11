import pytest

from omnistream.config import Settings


@pytest.fixture
def clean_env(monkeypatch):
    """Strip every spec variable and OMNI_* app variable from the process env."""
    for k in (
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "JUDGE_MODEL",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "OMNI_EMBED_MODEL",
        "OMNI_EMBED_DIM",
        "OMNI_EMBEDDING_MODEL",
        "OMNI_EMBEDDING_DIM",
        "OMNI_QUEUE_WORKERS",
        "OMNI_RRF_K",
    ):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_defaults(clean_env):
    s = Settings(_env_file=None)
    assert s.llm_base_url == "https://api.deepseek.com/v1"
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_user == "neo4j"
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.embed_dim == 384
    assert s.default_credibility == 0.5
    assert s.poll_interval_minutes == 15
    assert s.max_items_per_hour == 30
    assert s.prefilter_min_chars == 200
    assert s.queue_workers == 2
    assert s.router_threshold == 0.5
    assert s.router_top_k == 3
    assert s.grounding_threshold == 85
    assert s.embed_match_threshold == 0.88
    assert s.fuzzy_match_threshold == 90
    assert s.document_episode_tokens == 1500
    assert s.chunk_tokens == 300
    assert s.summary_refresh_episodes == 200
    assert (s.half_life_news_days, s.half_life_finance_days) == (3, 30)
    assert s.half_life_research_days == 365
    assert s.data_dir == "data"
    assert s.llm_tokens_per_minute == 60
    assert s.llm_max_retries == 5
    assert s.rrf_k == 60
    assert s.subagent_max_tool_calls == 6
    assert s.subagent_timeout_seconds == 60.0
    assert s.judge_model == s.llm_model


def test_spec_env_names_unprefixed(monkeypatch, clean_env):
    for k, v in {
        "LLM_BASE_URL": "http://h/v1",
        "LLM_API_KEY": "k",
        "LLM_MODEL": "m",
        "JUDGE_MODEL": "j",
        "NEO4J_URI": "bolt://n:1",
        "NEO4J_USER": "u",
        "NEO4J_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)
    assert (
        s.llm_base_url,
        s.llm_api_key.get_secret_value(),
        s.llm_model,
        s.judge_model,
    ) == (
        "http://h/v1",
        "k",
        "m",
        "j",
    )
    assert (s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value()) == (
        "bolt://n:1",
        "u",
        "p",
    )


def test_omni_prefixed_app_settings(monkeypatch, clean_env):
    monkeypatch.setenv("OMNI_QUEUE_WORKERS", "5")
    assert Settings(_env_file=None).queue_workers == 5


def test_secrets_are_not_leaked(clean_env):
    s = Settings(
        _env_file=None, llm_api_key="sk-or-very-secret", neo4j_password="hunter2"
    )
    assert "sk-or-very-secret" not in repr(s)
    assert "hunter2" not in repr(s)
    assert "sk-or-very-secret" not in str(s.model_dump())


def test_embedding_field_aliases(clean_env):
    s = Settings(_env_file=None, embedding_model="some/model", embedding_dim=7)
    assert s.embed_model == "some/model"
    assert s.embed_dim == 7
