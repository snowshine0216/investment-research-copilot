from __future__ import annotations
import ipaddress
import os
import socket
import time
from typing import Any
from urllib.parse import urlparse
import httpx
from irc.http_proxy import resolve_proxy
from irc.llm._types import ResolvedRoute, ChatResponse
from irc.schemas.llm import _validate_base_url


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


def verify_host_resolves_publicly(host: str) -> None:
    resolved = socket.gethostbyname(host)
    addr = ipaddress.ip_address(resolved)
    if any(addr in net for net in _BLOCKED_NETS):
        raise SSRFError(f"host {host} resolves to blocked address {resolved}")


def _resolve_key(env_name: str) -> str:
    val = os.environ.get(env_name, "").strip()
    if not val:
        raise RuntimeError(f"missing required env var: {env_name}")
    return val


def _resolve_base_url(route: ResolvedRoute) -> str:
    """Resolve the base URL at call time. Literal wins; else read base_url_env.
    Re-runs the SSRF guard so an env-injected private/link-local URL is rejected."""
    if route.base_url:
        url = route.base_url
    elif route.base_url_env:
        url = os.environ.get(route.base_url_env, "").strip()
        if not url:
            raise RuntimeError(f"missing required env var: {route.base_url_env}")
    else:
        raise RuntimeError(f"route {route.task} has no base_url source")
    _validate_base_url(url)  # SSRF block-list on env-resolved URL
    parsed = urlparse(url)
    if parsed.hostname:
        verify_host_resolves_publicly(parsed.hostname)
    return url


def _resolve_model(route: ResolvedRoute) -> str:
    """Resolve model name at call time. Literal wins; else read default_model_env."""
    if route.model:
        return route.model
    if route.default_model_env:
        val = os.environ.get(route.default_model_env, "").strip()
        if not val:
            raise RuntimeError(f"missing required env var: {route.default_model_env}")
        return val
    raise RuntimeError(f"route {route.task} has no model source")


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
        verify_host_resolves_publicly(parsed.hostname)
    started = time.perf_counter()
    if client is not None:
        resp = client.post(url, headers=headers, json=payload, timeout=timeout_s)
    else:
        with httpx.Client(timeout=timeout_s, proxy=proxy) as _client:
            resp = _client.post(url, headers=headers, json=payload)
    return resp, int((time.perf_counter() - started) * 1000)


def _parse_response(body: dict[str, Any], provider: str, model: str, latency_ms: int) -> ChatResponse:
    base_resp = body.get("base_resp")
    if isinstance(base_resp, dict) and int(base_resp.get("status_code", 0)) != 0:
        raise ValueError(
            f"{provider}/{model} returned error envelope base_resp="
            f"{base_resp.get('status_code')}: {base_resp.get('status_msg')!r}"
        )
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
    model = _resolve_model(route)
    base_url = _resolve_base_url(route)
    proxy = resolve_proxy()
    payload = _build_payload(model, messages, temperature, max_tokens)
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp, latency_ms = _post_request(url, headers, payload, timeout_s, client, proxy=proxy)
    resp.raise_for_status()
    return _parse_response(resp.json(), route.provider, model, latency_ms)
