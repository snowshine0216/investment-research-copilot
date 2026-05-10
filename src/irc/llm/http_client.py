from __future__ import annotations
import ipaddress
import os
import socket
import time
from typing import Any
from urllib.parse import urlparse
import httpx
from irc.llm._types import ResolvedRoute, ChatResponse


class SSRFError(RuntimeError):
    pass


_BLOCKED_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def _verify_host_resolves_publicly(host: str) -> None:
    resolved = socket.gethostbyname(host)
    addr = ipaddress.ip_address(resolved)
    if any(addr in net for net in _BLOCKED_NETS):
        raise SSRFError(f"host {host} resolves to blocked address {resolved}")


def _resolve_key(env_name: str) -> str:
    val = os.environ.get(env_name, "").strip()
    if not val:
        raise RuntimeError(f"missing required env var: {env_name}")
    return val


def _resolve_proxy(provider: str) -> str | None:
    """Optional per-provider HTTPS proxy from `{PROVIDER}_HTTPS_PROXY` env var.

    Returns None when unset/empty so httpx falls back to a direct connection.
    Used to route geo-restricted providers (e.g., openrouter for Anthropic
    models) through a corporate proxy without affecting other traffic.
    """
    return os.environ.get(f"{provider.upper()}_HTTPS_PROXY", "").strip() or None


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
    timeout_s: float = 30.0,
    client: httpx.Client | None = None,
    proxy: str | None = None,
) -> tuple[httpx.Response, int]:
    parsed = urlparse(url)
    if parsed.hostname:
        _verify_host_resolves_publicly(parsed.hostname)
    started = time.perf_counter()
    if client is not None:
        resp = client.post(url, headers=headers, json=payload, timeout=timeout_s)
    else:
        with httpx.Client(timeout=timeout_s, proxy=proxy) as _client:
            resp = _client.post(url, headers=headers, json=payload)
    return resp, int((time.perf_counter() - started) * 1000)


def _parse_response(body: dict[str, Any], provider: str, model: str, latency_ms: int) -> ChatResponse:
    choices = body.get("choices") or []
    if not choices:
        raise ValueError(f"empty choices in response from {provider}/{model}: {body!r}")
    content = choices[0].get("message", {}).get("content")
    if content is None:
        raise ValueError(
            f"null content in response from {provider}/{model} "
            "(tool-call or unsupported finish_reason?): {body!r}"
        )
    return ChatResponse(
        text=content,
        prompt_tokens=int(body.get("usage", {}).get("prompt_tokens", 0)),
        completion_tokens=int(body.get("usage", {}).get("completion_tokens", 0)),
        latency_ms=latency_ms,
        raw=body if os.environ.get("IRC_PERSIST_LLM_RAW") == "1" else None,
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
    proxy = _resolve_proxy(route.provider)
    payload = _build_payload(route.model, messages, temperature, max_tokens)
    url = f"{route.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp, latency_ms = _post_request(url, headers, payload, timeout_s, client, proxy=proxy)
    resp.raise_for_status()
    return _parse_response(resp.json(), route.provider, route.model, latency_ms)
