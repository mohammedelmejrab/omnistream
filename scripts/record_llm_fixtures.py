"""Record real LLM responses as sanitised fixtures for the offline test suite.

Usage: python scripts/record_llm_fixtures.py
Makes live calls with the credentials in .env and writes tests/fixtures/llm/*.json.
Only the request body and response body are stored; no headers or API keys.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from omnistream.config import Settings
from omnistream.llm import ANSWER_SYSTEM_PROMPT, LLMClient

OUT = ROOT / "tests" / "fixtures" / "llm"

CASES = {
    "chat_pong": {
        "messages": [{"role": "user", "content": "Reply with exactly the word: pong"}],
        "max_tokens": 10,
    },
    "answer_codename": {
        "messages": [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Context:\n[1] The OmniStream project codename is BLUEHERON.\n\n"
                "Question: What is the OmniStream project codename?",
            },
        ],
        "max_tokens": 50,
    },
    "router_json": {
        "messages": [
            {
                "role": "system",
                "content": "Select bubbles for the question. Reply with JSON only: "
                '{"bubbles": [...], "strategy": "simple | multi_hop", "time_scope": {}, '
                '"names_specific_item": false}. Bubbles: news, finance, research.',
            },
            {
                "role": "user",
                "content": "How did Apple's share price react to last week's EU ruling?",
            },
        ],
        "max_tokens": 120,
    },
}


def main() -> None:
    settings = Settings()
    llm = LLMClient(settings)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, case in CASES.items():
        request = {"model": settings.llm_model, "temperature": 0.0, **case}
        response = llm.client.chat.completions.create(**request).model_dump(
            mode="json", exclude_none=True
        )
        response["id"] = f"gen-recorded-{name}"
        (OUT / f"{name}.json").write_text(
            json.dumps(
                {"request": request, "response": response}, indent=2, ensure_ascii=False
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"recorded {name}: {response['choices'][0]['message']['content']!r}")


if __name__ == "__main__":
    main()
