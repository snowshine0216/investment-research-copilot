from __future__ import annotations
from dataclasses import dataclass
import os
import time
from typing import Any
import httpx
from irc.llm._types import ResolvedRoute


@dataclass(frozen=True)
class ChatResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw: dict[str, Any]


def _resolve_key(env_name: str) -> str:
    val = os.environ.get(env_name, "").strip()
    if not val:
        raise RuntimeError(f"missing required env var: {env_name}")
    return val


def _build_payload(
    model: str,
    messages: list[dict[str, str]],
    temperature: float | None,
    max_tokens: int | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    return payload


def _post_request(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_s: float,
    client: httpx.Client | None,
) -> tuple[httpx.Response, int]:
    started = time.perf_counter()
    if client is not None:
        resp = client.post(url, headers=headers, json=payload, timeout=timeout_s)
    else:
        with httpx.Client(timeout=timeout_s) as _client:
            resp = _client.post(url, headers=headers, json=payload)
    return resp, int((time.perf_counter() - started) * 1000)


def _parse_response(body: dict[str, Any], provider: str, model: str, latency_ms: int) -> ChatResponse:
    choices = body.get("choices") or []
    if not choices:
        raise ValueError(f"empty choices in response from {provider}/{model}: {body!r}")
    content = choices[0].get("message", {}).get("content") or ""
    return ChatResponse(
        text=content,
        prompt_tokens=int(body.get("usage", {}).get("prompt_tokens", 0)),
        completion_tokens=int(body.get("usage", {}).get("completion_tokens", 0)),
        latency_ms=latency_ms,
        raw=body,
    )


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
    payload = _build_payload(route.model, messages, temperature, max_tokens)
    url = f"{route.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp, latency_ms = _post_request(url, headers, payload, timeout_s, client)
    resp.raise_for_status()
    return _parse_response(resp.json(), route.provider, route.model, latency_ms)
