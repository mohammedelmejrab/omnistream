from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Spec §13.2 variables are read unprefixed; app tunables use OMNI_."""

    model_config = SettingsConfigDict(
        env_prefix="OMNI_", env_file=".env", populate_by_name=True, extra="ignore"
    )

    # Spec §13.2 (no prefix). The API key lives in the environment only.
    llm_base_url: str = Field(
        "https://api.deepseek.com/v1", validation_alias="LLM_BASE_URL"
    )
    llm_api_key: str = Field("", validation_alias="LLM_API_KEY")
    llm_model: str = Field("", validation_alias="LLM_MODEL")
    judge_model: str = Field("", validation_alias="JUDGE_MODEL")
    neo4j_uri: str = Field("bolt://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field("neo4j", validation_alias="NEO4J_USER")
    neo4j_password: str = Field("", validation_alias="NEO4J_PASSWORD")

    # LLM client
    llm_max_concurrency: int = 4
    llm_max_retries: int = 5
    llm_tokens_per_minute: int = 60  # token bucket: requests per minute
    llm_reasks: int = 2

    # Embeddings (always local)
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384

    # Spec defaults
    data_dir: str = "data"
    default_credibility: float = 0.5
    poll_interval_minutes: int = 15
    max_items_per_hour: int = 30
    store_full_text: bool = True
    prefilter_min_chars: int = 200
    queue_workers: int = 2
    router_threshold: float = 0.5
    router_top_k: int = 3
    grounding_threshold: int = 85
    embed_match_threshold: float = 0.88
    fuzzy_match_threshold: int = 90
    document_episode_tokens: int = 1500
    chunk_tokens: int = 300
    summary_refresh_episodes: int = 200
    half_life_news_days: int = 3
    half_life_finance_days: int = 30
    half_life_research_days: int = 365

    # Existing app settings
    chunk_size: int = 2000
    chunk_overlap: int = 200
    max_upload_bytes: int = 20_000_000
