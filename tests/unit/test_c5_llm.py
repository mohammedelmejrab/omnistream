import httpx
import pytest

from omnistream.config import Settings
from omnistream.llm import LLMClient, LLMError, judge_client
from omnistream.retrieval import HybridRetriever
from tests.conftest import chat_completion, load_llm_fixture


def test_chat_sends_openai_compatible_request(settings, mock_openai):
    client, transport = mock_openai(lambda body: "hello")
    llm = LLMClient(settings, client=client)
    assert llm.chat([{"role": "user", "content": "hi"}]) == "hello"
    req = transport.requests[0]
    assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer test-key"
    body = transport.bodies[0]
    assert body["model"] == "deepseek/deepseek-chat"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["temperature"] == 0.0
    assert "max_tokens" not in body


def test_chat_overrides(settings, mock_openai):
    client, transport = mock_openai(lambda body: "ok")
    LLMClient(settings, client=client).chat(
        [{"role": "user", "content": "x"}],
        model="other/model",
        temperature=0.7,
        max_tokens=5,
    )
    body = transport.bodies[0]
    assert (body["model"], body["temperature"], body["max_tokens"]) == (
        "other/model",
        0.7,
        5,
    )


def test_judge_client_uses_judge_model(mock_openai):
    s = Settings(
        _env_file=None,
        llm_api_key="k",
        llm_model="main/model",
        judge_model="judge/model",
    )
    client, transport = mock_openai(lambda body: "ok")
    judge_client(s, client=client).chat([{"role": "user", "content": "x"}])
    assert transport.bodies[0]["model"] == "judge/model"


@pytest.mark.parametrize(
    "reply, expected",
    [
        (
            '{"bubbles": ["news"], "strategy": "simple"}',
            {"bubbles": ["news"], "strategy": "simple"},
        ),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ("```\n[1, 2]\n```", [1, 2]),
    ],
)
def test_chat_json_parses(settings, mock_openai, reply, expected):
    client, _ = mock_openai(lambda body: reply)
    assert (
        LLMClient(settings, client=client).chat_json([{"role": "user", "content": "x"}])
        == expected
    )


def test_chat_json_invalid_raises(settings, mock_openai):
    client, _ = mock_openai(lambda body: "not json")
    with pytest.raises(LLMError, match="not valid JSON"):
        LLMClient(settings, client=client).chat_json([{"role": "user", "content": "x"}])


def test_empty_content_raises(settings, mock_openai):
    client, _ = mock_openai(
        lambda body: httpx.Response(200, json=chat_completion(None))
    )
    with pytest.raises(LLMError, match="empty"):
        LLMClient(settings, client=client).chat([{"role": "user", "content": "x"}])


def test_no_choices_raises(settings, mock_openai):
    payload = chat_completion("x")
    payload["choices"] = []
    client, _ = mock_openai(lambda body: httpx.Response(200, json=payload))
    with pytest.raises(LLMError, match="no choices"):
        LLMClient(settings, client=client).chat([{"role": "user", "content": "x"}])


def test_http_error_propagates(settings, mock_openai):
    import openai

    client, _ = mock_openai(
        lambda body: httpx.Response(
            401, json={"error": {"message": "No auth credentials found", "code": 401}}
        )
    )
    with pytest.raises(openai.AuthenticationError):
        LLMClient(settings, client=client).chat([{"role": "user", "content": "x"}])


def test_empty_200_response_is_retried_with_backoff(settings, mock_openai, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("omnistream.llm._sleep", sleeps.append)
    empty = chat_completion("x")
    empty["choices"] = []
    empty["error"] = {"code": 502, "message": "upstream timeout"}
    replies = iter(
        [httpx.Response(200, json=empty), httpx.Response(200, json=empty), "recovered"]
    )
    client, transport = mock_openai(lambda body: next(replies))
    assert (
        LLMClient(settings, client=client).chat([{"role": "user", "content": "x"}])
        == "recovered"
    )
    assert len(transport.requests) == 3
    assert sleeps == [0.5, 1.0]


def test_empty_responses_exhaust_retry_budget(mock_openai, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("omnistream.llm._sleep", sleeps.append)
    s = Settings(_env_file=None, llm_api_key="k", llm_max_retries=6)
    empty = chat_completion("x")
    empty["choices"] = []
    empty["error"] = {"code": 429, "message": "Provider returned error"}
    client, transport = mock_openai(lambda body: httpx.Response(200, json=empty))
    with pytest.raises(
        LLMError, match="no choices after 7 attempt.*429 Provider returned error"
    ):
        LLMClient(s, client=client).chat([{"role": "user", "content": "x"}])
    assert len(transport.requests) == 7
    assert sleeps == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]  # exponential, capped at 8 s


def test_zero_retries_fails_fast(mock_openai):
    s = Settings(_env_file=None, llm_api_key="k", llm_max_retries=0)
    client, transport = mock_openai(
        lambda body: httpx.Response(200, json=chat_completion(None))
    )
    with pytest.raises(LLMError, match="empty message after 1 attempt"):
        LLMClient(s, client=client).chat([{"role": "user", "content": "x"}])
    assert len(transport.requests) == 1


def test_http_429_is_retried_by_sdk_then_succeeds(settings, mock_openai):
    from openai import OpenAI

    replies = iter(
        [
            httpx.Response(
                429,
                headers={"retry-after-ms": "1"},
                json={"error": {"message": "rate"}},
            ),
            "ok",
        ]
    )
    _, transport = mock_openai(lambda body: next(replies))
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="k",
        max_retries=2,
        http_client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    assert (
        LLMClient(settings, client=client).chat([{"role": "user", "content": "x"}])
        == "ok"
    )
    assert len(transport.requests) == 2


def test_missing_api_key_raises():
    llm = LLMClient(Settings(_env_file=None, llm_api_key=""))
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        _ = llm.client


def test_default_client_built_from_settings():
    s = Settings(
        _env_file=None,
        llm_api_key="sk-or-x",
        llm_base_url="https://openrouter.ai/api/v1",
        llm_app_url="https://example.test",
        llm_timeout_seconds=12,
        llm_max_retries=4,
    )
    c = LLMClient(s).client
    assert str(c.base_url).rstrip("/") == "https://openrouter.ai/api/v1"
    assert c.api_key == "sk-or-x"
    assert c.max_retries == 4
    assert c.timeout == 12
    assert c.default_headers["HTTP-Referer"] == "https://example.test"
    assert c.default_headers["X-Title"] == "OmniStream RAG"


def test_retrieval_to_answer_pipeline(settings, embedder, mock_openai):
    """Integration: hybrid retrieval feeds numbered passages to the LLM."""
    retriever = HybridRetriever(embedder, settings=settings)
    retriever.add(
        {
            "c1": "Neo4j is a graph database.",
            "c2": "Bananas are yellow.",
            "c3": "Graph databases store nodes and relationships.",
        }
    )
    hits = retriever.search("graph database", top_k=2)
    assert {h.id for h in hits} == {"c1", "c3"}

    client, transport = mock_openai(lambda body: "Neo4j is a graph database [1].")
    answer = LLMClient(settings, client=client).answer(
        "What is Neo4j?", [h.text for h in hits]
    )
    assert answer.endswith("[1].")

    messages = transport.bodies[0]["messages"]
    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "[1] " in user and "[2] " in user and "[3]" not in user
    assert "Bananas" not in user
    assert user.rstrip().endswith("Question: What is Neo4j?")


def test_answer_with_no_passages(settings, mock_openai):
    client, transport = mock_openai(lambda body: "I don't know.")
    LLMClient(settings, client=client).answer("q", [])
    assert "(no context)" in transport.bodies[0]["messages"][1]["content"]


# ------------------------------------------------- recorded fixtures
def replay(name, mock_openai):
    """Serve a recorded OpenRouter response and check our request matches the recorded one."""
    fx = load_llm_fixture(name)
    client, transport = mock_openai(
        lambda body: httpx.Response(200, json=fx["response"])
    )
    return fx, client, transport


def test_recorded_fixtures_contain_no_secrets():
    from tests.conftest import FIXTURES

    for path in (FIXTURES / "llm").glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert (
            "sk-or" not in text
            and "authorization" not in text
            and "api_key" not in text
        ), path.name


def test_replay_chat_pong(settings, mock_openai):
    fx, client, transport = replay("chat_pong", mock_openai)
    reply = LLMClient(settings, client=client).chat(
        fx["request"]["messages"], max_tokens=10
    )
    assert reply.strip().lower() == "pong"
    assert transport.bodies[0] == {**fx["request"], "reasoning": {"enabled": False}}


def test_replay_cited_answer(settings, mock_openai):
    fx, client, transport = replay("answer_codename", mock_openai)
    answer = LLMClient(settings, client=client).answer(
        "What is the OmniStream project codename?",
        ["The OmniStream project codename is BLUEHERON."],
        max_tokens=50,
    )
    assert "BLUEHERON" in answer and "[1]" in answer
    assert transport.bodies[0] == {
        **fx["request"],
        "reasoning": {"enabled": False},
    }  # our prompt matches what was recorded


def test_replay_router_json_with_real_code_fence(settings, mock_openai):
    """DeepSeek wrapped its JSON in a ```json fence in the real recording."""
    fx, client, _ = replay("router_json", mock_openai)
    assert fx["response"]["choices"][0]["message"]["content"].startswith("```json")
    routed = LLMClient(settings, client=client).chat_json(
        fx["request"]["messages"], max_tokens=120
    )
    assert set(routed) == {"bubbles", "strategy", "time_scope", "names_specific_item"}
    assert routed["strategy"] in {"simple", "multi_hop"}
    assert set(routed["bubbles"]) <= {"news", "finance", "research"}


# ----------------------------------------------------------------- live
@pytest.mark.live
def test_live_openrouter_chat():
    s = Settings()  # real .env
    if not s.has_llm_credentials:
        pytest.skip("LLM_API_KEY not configured")
    reply = LLMClient(s).chat(
        [{"role": "user", "content": "Reply with exactly the word: pong"}],
        max_tokens=10,
    )
    assert "pong" in reply.lower()


@pytest.mark.live
def test_live_openrouter_retrieval_answer(embedder):
    s = Settings()
    if not s.has_llm_credentials:
        pytest.skip("LLM_API_KEY not configured")
    retriever = HybridRetriever(embedder, settings=s)
    retriever.add(
        {
            "c1": "The OmniStream project codename is BLUEHERON.",
            "c2": "Bananas are yellow.",
        }
    )
    hits = retriever.search("OmniStream codename", top_k=1)
    answer = LLMClient(s).answer(
        "What is the OmniStream project codename?",
        [h.text for h in hits],
        max_tokens=50,
    )
    assert "blueheron" in answer.lower()
