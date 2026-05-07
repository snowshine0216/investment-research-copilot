from __future__ import annotations
from dataclasses import dataclass
import os
import time
from typing import Any
import httpx
from irc.llm.gateway import ResolvedRoute


@dataclass(frozen=True)
class ChatResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw: dict[str, Any]


def _resolve_key(env_name: str) -> str:
    val = os.environ.get(env_name, "")
    if not val:
        raise RuntimeError(f"missing required env var: {env_name}")
    return val


def call_chat(
    route: ResolvedRoute,
    messages: list[dict[str, str]],
    timeout_s: float = 30.0,
    temperature: float | None = None,
    max_tokens: int | None = None,
    client: httpx.Client | None = None,
) -> ChatResponse:
    """Make a single chat-completions call. Raises httpx.HTTPStatusError on 4xx/5xx."""
    api_key = _resolve_key(route.api_key_env)
    payload: dict[str, Any] = {
        "model": route.model,
        "messages": messages,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    url = f"{route.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    started = time.perf_counter()
    if client is not None:
        resp = client.post(url, headers=headers, json=payload, timeout=timeout_s)
        latency_ms = int((time.perf_counter() - started) * 1000)
    else:
        with httpx.Client(timeout=timeout_s) as _client:
            resp = _client.post(url, headers=headers, json=payload)
        latency_ms = int((time.perf_counter() - started) * 1000)
    resp.raise_for_status()
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError(
            f"empty choices in response from {route.provider}/{route.model}: {body!r}"
        )
    content = choices[0].get("message", {}).get("content") or ""
    return ChatResponse(
        text=content,
        prompt_tokens=int(body.get("usage", {}).get("prompt_tokens", 0)),
        completion_tokens=int(body.get("usage", {}).get("completion_tokens", 0)),
        latency_ms=latency_ms,
        raw=body,
    )
