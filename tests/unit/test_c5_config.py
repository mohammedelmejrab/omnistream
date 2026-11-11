import os
from pathlib import Path

import pytest

from omnistream.config import DEFAULT_ENV_FILE, PROJECT_ROOT, Settings, get_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    return monkeypatch  # conftest.isolated_env already strips settings variables


def test_env_file_points_at_project_root():
    assert DEFAULT_ENV_FILE == PROJECT_ROOT / ".env"
    assert (PROJECT_ROOT / "pyproject.toml").is_file()


def test_reads_values_from_env_file(tmp_path: Path, clean_env):
    env = tmp_path / ".env"
    env.write_text(
        "LLM_BASE_URL=https://openrouter.ai/api/v1\n"
        "LLM_API_KEY=sk-or-abc\n"
        "LLM_MODEL=deepseek/deepseek-chat\n"
        "JUDGE_MODEL=deepseek/deepseek-chat\n"
        "NEO4J_PASSWORD=secret\n"
        "UNRELATED_KEY=ignored\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=env)
    assert s.llm_base_url == "https://openrouter.ai/api/v1"
    assert s.llm_api_key.get_secret_value() == "sk-or-abc"
    assert s.llm_model == "deepseek/deepseek-chat"
    assert s.judge_model == "deepseek/deepseek-chat"
    assert s.neo4j_password.get_secret_value() == "secret"
    assert s.has_llm_credentials


def test_process_env_overrides_env_file(tmp_path: Path, clean_env):
    env = tmp_path / ".env"
    env.write_text("LLM_MODEL=from-file\n", encoding="utf-8")
    clean_env.setenv("LLM_MODEL", "from-env")
    assert Settings(_env_file=env).llm_model == "from-env"


def test_defaults_without_env_file(clean_env):
    s = Settings(_env_file=None)
    # Spec §13.2: the DeepSeek endpoint, blank model until configured.
    assert s.llm_base_url == "https://api.deepseek.com/v1"
    assert s.llm_model == ""
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.embedding_dim == 384
    assert s.rrf_k == 60
    assert s.judge_model == s.llm_model
    assert s.neo4j_password.get_secret_value() == ""
    assert not s.has_llm_credentials


@pytest.mark.parametrize("judge", [None, "", "   "])
def test_blank_judge_model_follows_main_model(tmp_path: Path, clean_env, judge):
    env = tmp_path / ".env"
    lines = ["LLM_MODEL=main/model"] + (
        [] if judge is None else [f"JUDGE_MODEL={judge}"]
    )
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert Settings(_env_file=env).judge_model == "main/model"


def test_explicit_judge_model_is_kept(clean_env):
    s = Settings(_env_file=None, llm_model="main/model", judge_model=" judge/model ")
    assert s.judge_model == "judge/model"


def test_settings_isolated_from_ambient_environment():
    """conftest strips settings variables and disables the project .env."""
    assert "OMNI_EMBEDDING_DIM" not in os.environ
    assert "LLM_API_KEY" not in os.environ
    assert not get_settings().has_llm_credentials
    assert Settings().embedding_dim == 384


def test_invalid_rrf_k_rejected(clean_env):
    with pytest.raises(ValueError):
        Settings(_env_file=None, rrf_k=0)


def test_api_key_is_not_leaked_in_repr(clean_env):
    s = Settings(_env_file=None, llm_api_key="sk-or-very-secret")
    assert "sk-or-very-secret" not in repr(s)
    assert "sk-or-very-secret" not in str(s.model_dump())


@pytest.mark.live
def test_project_env_file_is_configured():
    """The checked-out .env must configure an LLM endpoint and a model."""
    if not DEFAULT_ENV_FILE.exists():
        pytest.skip("no .env in this checkout")
    get_settings.cache_clear()
    s = Settings()
    assert s.llm_base_url.rstrip("/").endswith("/v1")
    assert s.llm_model
    assert s.judge_model == s.llm_model
    assert s.has_llm_credentials
