"""At most ten tiny live requests; never load dotenv or run ingestion."""

import argparse
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai_like import OpenAILike
from openai.resources.chat.completions import AsyncCompletions, Completions
from pydantic import BaseModel

from omnistream.config import Settings
from omnistream.eval.resources import UsageMeter, stage
from omnistream.llm import (
    AsyncLLMClient,
    LLMClient,
    build_llm_client,
    judge_client,
    reasoning_kwargs,
)
from omnistream.retrieval.graphiti_clients import GraphitiLLMClient


class Result(BaseModel):
    ok: bool


async def main(secret_file):
    settings = Settings(
        _env_file=None,
        llm_api_key=Path(secret_file).read_text().strip(),
        llm_base_url="https://openrouter.ai/api/v1",
        llm_model="deepseek/deepseek-v4.1-flash-1017",
        llm_max_retries=0,
        judge_model="deepseek/deepseek-v4.1-flash-1017",
        llm_reasoning="off",
        judge_reasoning="off",
        llm_send_reasoning_param="auto",
    )
    meter = UsageMeter()
    sync, async_ = Completions.create, AsyncCompletions.create
    rows = []
    count = 0

    def prepare(kwargs):
        nonlocal count
        if count >= 10:
            raise RuntimeError("Ten-call hard cap reached")
        count += 1
        kwargs["max_tokens"] = 128
        assert kwargs.get("extra_body", {}).get("reasoning") == {"enabled": False}

    def record(response):
        meter.record(response)
        usage = response.usage
        row = dict(  # noqa: C408 - compact measurement row
            path=stage.get(),
            completion_tokens=usage.completion_tokens,
            reasoning_tokens=getattr(
                usage.completion_tokens_details, "reasoning_tokens", None
            ),
            finish_reason=response.choices[0].finish_reason,
        )
        rows.append(row)
        print(json.dumps(row), flush=True)

    def call(client, *args, **kwargs):
        prepare(kwargs)
        result = sync(client, *args, **kwargs)
        record(result)
        return result

    async def acall(client, *args, **kwargs):
        prepare(kwargs)
        result = await async_(client, *args, **kwargs)
        record(result)
        return result

    messages = [{"role": "user", "content": 'Return JSON {"ok":true} only.'}]
    client = LLMClient(settings)
    structured = build_llm_client(settings)
    tools = AsyncLLMClient(settings)
    judge = judge_client(settings)
    graph = GraphitiLLMClient(
        settings=settings,
        config=LLMConfig(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        ),
        structured_output_mode="json_object",
    )
    graph.client._client.max_retries = 0
    external = OpenAILike(
        model=settings.llm_model,
        api_base=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        is_chat_model=True,
        additional_kwargs=reasoning_kwargs(settings),
        max_retries=0,
    )
    with (
        patch.object(Completions, "create", call),
        patch.object(AsyncCompletions, "create", acall),
    ):
        for name, operation in [
            (
                "parse",
                lambda: structured.parse(
                    settings.llm_model,
                    "Return JSON.",
                    "ok=true",
                    Result,
                    max_tokens=128,
                ),
            ),
            ("chat", lambda: client.chat(messages)),
            (
                "chat_json",
                lambda: client.chat_json(
                    messages, response_format={"type": "json_object"}
                ),
            ),
            ("answer", lambda: client.answer("What is the code?", ["The code is OK."])),
            (
                "chat_with_tools",
                lambda: tools.chat_with_tools(
                    messages,
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": "ping",
                                "parameters": {"type": "object", "properties": {}},
                            },
                        }
                    ],
                    tool_choice="auto",
                ),
            ),
            (
                "judge",
                lambda: judge.chat_json(
                    messages, response_format={"type": "json_object"}
                ),
            ),
            (
                "graphiti",
                lambda: graph._generate_response(
                    [Message(role="user", content=messages[0]["content"])],
                    Result,
                    max_tokens=128,
                ),
            ),
            (
                "llamaindex",
                lambda: external.chat([ChatMessage(role="user", content="Say OK.")]),
            ),
        ]:
            stage.set(name)
            try:
                result = operation()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:  # noqa: BLE001 - retain per-path verification failures
                print(
                    json.dumps({"path": name, "error_type": type(exc).__name__}),
                    flush=True,
                )
    summary = {"calls": count, "rows": rows, "usage": meter.summary()}
    Path("docs/reasoning-live-verification.json").write_text(
        json.dumps(summary, indent=2)
    )
    print(
        json.dumps(
            {"cost_usd": sum(v["cost_usd"] or 0 for v in meter.summary().values())}
        )
    )
    await structured._client.close()
    if tools._client:
        await tools._client.close()
    await graph.client.close()
    for c in (client, judge):
        if c._client:
            c._client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-file", required=True)
    asyncio.run(main(parser.parse_args().secret_file))
