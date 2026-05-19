"""Shared HTTP helpers for search providers.

`post_json` and `get_json` handle the common pattern of: make request →
handle timeout → check status → parse JSON. On error they return a failure
SearchResult directly so callers can return it immediately.

If ``IRC_HTTPS_PROXY`` is set, all calls route through that proxy.
"""
from __future__ import annotations

import httpx

from irc.http_proxy import resolve_proxy
from irc.research.search.types import Locale, SearchResult


def post_json(
    url: str,
    *,
    payload: dict,
    headers: dict,
    timeout_s: int,
    query: str,
    locale: Locale,
    provider: str,
) -> tuple[dict, None] | tuple[None, SearchResult]:
    """POST JSON and parse response. Returns (body, None) on success or (None, failure)."""
    try:
        with httpx.Client(timeout=timeout_s, proxy=resolve_proxy()) as client:
            resp = client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        return None, SearchResult(query=query, locale=locale, provider=provider,
                                  failure_reason=f"timeout: {exc}")
    except httpx.HTTPError as exc:
        return None, SearchResult(query=query, locale=locale, provider=provider,
                                  failure_reason=f"http error: {exc}")
    if resp.status_code != 200:
        return None, SearchResult(query=query, locale=locale, provider=provider,
                                  failure_reason=f"http {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json(), None
    except ValueError as exc:
        return None, SearchResult(query=query, locale=locale, provider=provider,
                                  failure_reason=f"invalid JSON: {exc}")


def get_json(
    url: str,
    *,
    params: dict,
    headers: dict,
    timeout_s: int,
    query: str,
    locale: Locale,
    provider: str,
) -> tuple[dict, None] | tuple[None, SearchResult]:
    """GET with params and parse response. Returns (body, None) on success or (None, failure)."""
    try:
        with httpx.Client(timeout=timeout_s, proxy=resolve_proxy()) as client:
            resp = client.get(url, params=params, headers=headers)
    except httpx.TimeoutException as exc:
        return None, SearchResult(query=query, locale=locale, provider=provider,
                                  failure_reason=f"timeout: {exc}")
    except httpx.HTTPError as exc:
        return None, SearchResult(query=query, locale=locale, provider=provider,
                                  failure_reason=f"http error: {exc}")
    if resp.status_code != 200:
        return None, SearchResult(query=query, locale=locale, provider=provider,
                                  failure_reason=f"http {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json(), None
    except ValueError as exc:
        return None, SearchResult(query=query, locale=locale, provider=provider,
                                  failure_reason=f"invalid JSON: {exc}")
