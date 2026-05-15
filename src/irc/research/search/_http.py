"""Shared HTTP helpers for search providers.

`post_json` and `get_json` handle the common pattern of: make request →
handle timeout → check status → parse JSON. On error they return a failure
SearchResult directly so callers can return it immediately.
"""
from __future__ import annotations

import httpx

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
        resp = httpx.post(url, json=payload, headers=headers, timeout=timeout_s)
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
        resp = httpx.get(url, params=params, headers=headers, timeout=timeout_s)
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
