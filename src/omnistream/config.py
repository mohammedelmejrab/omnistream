"""Application settings loaded from environment variables and the project ``.env`` file.

Conventions (spec §13.2, this repo): the spec's variables are read *unprefixed*
(``LLM_BASE_URL``, ``LLM_API_KEY``, ...); every other tunable uses the ``OMNI_``
prefix. Secrets (``llm_api_key``, ``neo4j_password``) are ``SecretStr`` so they
never appear in ``repr`` or ``model_dump`` output.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime configuration.

    Values come from (highest priority first) process environment variables,
    then the ``.env`` file at the project root, then the defaults below.
    """

    model_config = SettingsConfigDict(
        env_prefix="OMNI_", env_file=".env", populate_by_name=True, extra="ignore"
    )

    # Spec §13.2 (no prefix). The API key lives in the environment only.
    llm_base_url: str = Field(
        "https://api.deepseek.com/v1", validation_alias="LLM_BASE_URL"
    )
    llm_api_key: SecretStr = Field(SecretStr(""), validation_alias="LLM_API_KEY")
    llm_model: str = Field("", validation_alias="LLM_MODEL")
    # Blank/unset -> same as llm_model (spec D4: one model, optional judge).
    judge_model: str = Field("", validation_alias="JUDGE_MODEL")
    neo4j_uri: str = Field("bolt://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field("neo4j", validation_alias="NEO4J_USER")
    neo4j_password: SecretStr = Field(SecretStr(""), validation_alias="NEO4J_PASSWORD")

    # LLM client (C4 structured client + C5 chat clients share these).
    llm_reasoning: Literal["off", "low", "medium", "high", "provider_default"] = "off"
    judge_reasoning: Literal["off", "low", "medium", "high", "provider_default"] = "off"
    llm_send_reasoning_param: Literal["auto", "always", "never"] = "auto"
    llm_max_concurrency: int = 4
    llm_max_retries: int = Field(default=5, ge=0)
    llm_tokens_per_minute: int = 60  # token bucket: requests per minute
    llm_reasks: int = 2
    llm_timeout_seconds: float = 60.0

    # Optional OpenRouter attribution headers (C5).
    llm_app_url: str | None = None
    llm_app_title: str | None = "OmniStream RAG"

    # Embeddings (always local, spec section 5).
    embedding_model: str = Field(
        "BAAI/bge-small-en-v1.5",
        validation_alias=AliasChoices("OMNI_EMBEDDING_MODEL", "OMNI_EMBED_MODEL"),
    )
    embedding_dim: int = Field(
        384, validation_alias=AliasChoices("OMNI_EMBEDDING_DIM", "OMNI_EMBED_DIM")
    )
    embedding_batch_size: int = 32
    embedding_device: str | None = None

    entity_index_name: str = Field(default="entity_name_embedding", min_length=1)
    fact_index_name: str = Field(default="fact_embedding", min_length=1)

    # Retrieval defaults (C5).
    rrf_k: int = Field(default=60, ge=1)
    subagent_max_tool_calls: int = Field(default=6, ge=1)
    subagent_timeout_seconds: float = Field(default=60.0, gt=0)

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
    record_snapshot: str | None = (
        None  # when set, polled items go to snapshots/<name>.jsonl
    )
    max_upload_bytes: int = 20_000_000

    @field_validator("llm_model", "judge_model", "llm_base_url", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _judge_defaults_to_main_model(self) -> Settings:
        if not self.judge_model:
            self.judge_model = self.llm_model
        return self

    @property
    def has_llm_credentials(self) -> bool:
        return bool(self.llm_api_key.get_secret_value().strip())

    # Backwards-compatible names used by the C1-C4 modules.
    @property
    def embed_model(self) -> str:
        return self.embedding_model

    @property
    def embed_dim(self) -> int:
        return self.embedding_dim


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide settings instance."""
    return Settings()
