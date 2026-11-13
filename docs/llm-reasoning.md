# LLM reasoning controls

`OMNI_LLM_REASONING=off` is the default. Allowed values are `off`, `low`,
`medium`, `high`, and `provider_default`. `OMNI_JUDGE_REASONING` has the same
values and independently defaults to `off` for the eval judge and citation
faithfulness judging. Production citation entailment uses the main LLM policy.

- `off`: OpenRouter body `{"reasoning": {"enabled": false}}`.
- `low`, `medium`, `high`: `{"reasoning": {"effort": "<level>"}}`.
- `provider_default`: omit the reasoning field entirely.

`OMNI_LLM_SEND_REASONING_PARAM=auto` sends the field only when the parsed base
URL hostname is exactly `openrouter.ai`. `always` explicitly opts generic
OpenAI-compatible endpoints into this extension; `never` omits it everywhere.
The SDK receives the body extension through `extra_body`, including Graphiti
and the LlamaIndex external baseline. Other request options are retained.

Structured extraction, chat/JSON/answer, tool calls, and Graphiti reject
`finish_reason=length` before consuming content or arguments, log a warning,
and retry within their existing retry budget. Graphiti uses its upstream
resampling loop. Exhausted retries surface a clear failure.

`UsageMeter.summary()` includes `reasoning_tokens` per stage (zero when the
provider omits the details), alongside completion tokens, total tokens and
provider cost. Existing eval and ingestion-probe usage exports inherit it.
Hidden reasoning tokens are a subset of completion tokens, not added to totals.
