from omnistream.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_base_url == "https://api.deepseek.com/v1"
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_user == "neo4j"
    assert s.embed_model == "BAAI/bge-small-en-v1.5"
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


def test_spec_env_names_unprefixed(monkeypatch):
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
    assert (s.llm_base_url, s.llm_api_key, s.llm_model, s.judge_model) == (
        "http://h/v1",
        "k",
        "m",
        "j",
    )
    assert (s.neo4j_uri, s.neo4j_user, s.neo4j_password) == ("bolt://n:1", "u", "p")


def test_omni_prefixed_app_settings(monkeypatch):
    monkeypatch.setenv("OMNI_QUEUE_WORKERS", "5")
    assert Settings(_env_file=None).queue_workers == 5
