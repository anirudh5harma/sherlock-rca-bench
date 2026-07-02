"""LLM layer: real OpenAI when OPENAI_API_KEY is set, deterministic mock otherwise.

Agents do real heuristic signal analysis at the core; the LLM is used to *polish*
(natural-language summaries, next steps) and to judge. Everything works offline in mock mode.
See CONTRACT.md.
"""
from __future__ import annotations

import json
import os
from typing import Any

try:  # load a standard .env (repo root) so OPENAI_API_KEY etc. are picked up automatically
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # repo-root .env, cwd-independent
except ModuleNotFoundError:  # dotenv optional; env vars still work if exported
    pass


def llm_mode() -> str:
    return "openai" if os.getenv("OPENAI_API_KEY") else "mock"


def agent_model() -> str:
    return os.getenv("RCA_AGENT_MODEL", "gpt-4o-mini")


def judge_model() -> str:
    return os.getenv("RCA_JUDGE_MODEL", "gpt-4o")


_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI  # imported lazily so mock mode needs no network stack

        _client = OpenAI()
    return _client


def complete_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    schema_hint: str = "",
    mock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a dict from the model. In mock mode returns `mock` (or {}).

    Never raises: on any OpenAI error it retries once then falls back to `mock`.
    """
    if llm_mode() == "mock":
        return dict(mock or {})

    sys = system if not schema_hint else f"{system}\n\nReturn JSON only, matching: {schema_hint}"
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
    mdl = model or agent_model()

    last_err: Exception | None = None
    for _ in range(2):
        try:
            resp = _get_client().chat.completions.create(
                model=mdl,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            content = resp.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as e:  # noqa: BLE001 - degrade gracefully, demo must not crash
            last_err = e
    # give up, fall back to deterministic mock so the pipeline still returns something valid
    result = dict(mock or {})
    result.setdefault("_llm_error", str(last_err))
    return result
