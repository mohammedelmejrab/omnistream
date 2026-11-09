from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMNI_")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    anthropic_model_extract: str = "claude-haiku-5-5"
    anthropic_model_route: str = "claude-haiku-5-5"
    llm_max_concurrency: int = 4
    llm_max_retries: int = 5
    embed_model: str = "all-MiniLM-L6-v2"
    embed_dim: int = 384
    embed_match_threshold: float = 0.88
    fuzzy_match_threshold: int = 90
    grounding_threshold: int = 85
    chunk_size: int = 2000
    chunk_overlap: int = 200
    max_upload_bytes: int = 20_000_000
