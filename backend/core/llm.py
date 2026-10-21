"""Asking the LLM for structured answers: cloud Qwen on Groq first, the Mac's
Ollama as backup (context/architecture.md).

Every call asks for JSON and checks it against a Pydantic model, so a bad
answer fails the job (which is retried) instead of saving nonsense.
"""

import json
import re
from dataclasses import dataclass

import httpx2
from pydantic import BaseModel, ValidationError

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LlmError(Exception):
    """No LLM gave a usable answer."""


@dataclass(frozen=True)
class LlmConfig:
    groq_api_key: str | None
    groq_model: str
    ollama_url: str | None
    ollama_model: str


@dataclass
class LlmAnswer[T: BaseModel]:
    value: T
    # e.g. "groq:qwen/qwen3.8-27b" or "ollama:qwen3:8b", saved with what it wrote.
    model: str


def _parse[T: BaseModel](text: str, schema: type[T]) -> T:
    # Qwen may "think" first; keep only the answer.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON in the answer")
    return schema.model_validate(json.loads(match.group()))


async def _groq(
    http: httpx2.AsyncClient, config: LlmConfig, system: str, prompt: str, max_tokens: int | None
) -> str:
    response = await http.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {config.groq_api_key}"},
        json={
            "model": config.groq_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "reasoning_format": "hidden",
            # Groq's free tier also limits output tokens per minute (1,000 for Qwen):
            # asking for at most this many keeps a request from being refused outright.
            **({"max_tokens": max_tokens} if max_tokens else {}),
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


async def _ollama(
    http: httpx2.AsyncClient, config: LlmConfig, system: str, prompt: str, max_tokens: int | None
) -> str:
    response = await http.post(
        f"{(config.ollama_url or '').rstrip('/')}/api/chat",
        json={
            "model": config.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "format": "json",
            "stream": False,
            "think": False,
            "options": {"temperature": 0.3},
        },
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


async def ask_json[T: BaseModel](
    http: httpx2.AsyncClient,
    config: LlmConfig,
    system: str,
    prompt: str,
    schema: type[T],
    max_tokens: int | None = None,
) -> LlmAnswer[T]:
    """Ask Groq, then Ollama; return the first answer that fits `schema`."""
    attempts = []
    if config.groq_api_key:
        attempts.append((f"groq:{config.groq_model}", _groq))
    if config.ollama_url:
        attempts.append((f"ollama:{config.ollama_model}", _ollama))
    if not attempts:
        raise LlmError("No LLM set up (GROQ_API_KEY or Ollama)")
    problems = []
    for name, call in attempts:
        try:
            text = await call(http, config, system, prompt, max_tokens)
            return LlmAnswer(value=_parse(text, schema), model=name)
        except (httpx2.HTTPError, KeyError, ValueError, ValidationError) as error:
            problems.append(f"{name}: {type(error).__name__}")
    raise LlmError("No usable answer (" + "; ".join(problems) + ")")
