from __future__ import annotations
from urllib.parse import urlparse

import httpx

from irc.research.search.types import Locale, SearchHit, SearchResult


_ENDPOINT = "https://api.search.brave.com/res/v1/news/search"


def _freshness_bucket(days: int) -> str:
    """Map a day-count to Brave's freshness enum (pd, pw, pm, py)."""
    if days <= 1:
        return "pd"
    if days <= 7:
        return "pw"
    if days <= 31:
        return "pm"
    return "py"


class BraveNewsProvider:
    """English news via Brave Search News API.

    Pure adapter — failures degrade into SearchResult(failure_reason=...).
    """

    name: str = "brave_news"
    locale: Locale = Locale.EN

    def __init__(self, api_key: str, *, timeout_s: int = 10) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        freshness_days: int | None = None,
        include_domains: tuple[str, ...] = (),
        exclude_domains: tuple[str, ...] = (),
    ) -> SearchResult:
        params: dict[str, str | int] = {"q": query, "count": max_results}
        if freshness_days is not None:
            params["freshness"] = _freshness_bucket(freshness_days)
        headers = {
            "X-Subscription-Token": self._api_key,
            "Accept": "application/json",
        }
        try:
            resp = httpx.get(
                _ENDPOINT,
                params=params,
                headers=headers,
                timeout=self._timeout_s,
            )
        except httpx.TimeoutException as exc:
            return SearchResult(
                query=query, locale=self.locale, provider=self.name,
                failure_reason=f"timeout: {exc}",
            )
        except httpx.HTTPError as exc:
            return SearchResult(
                query=query, locale=self.locale, provider=self.name,
                failure_reason=f"http error: {exc}",
            )
        if resp.status_code != 200:
            return SearchResult(
                query=query, locale=self.locale, provider=self.name,
                failure_reason=f"http {resp.status_code}: {resp.text[:200]}",
            )
        try:
            body = resp.json()
        except ValueError as exc:
            return SearchResult(
                query=query, locale=self.locale, provider=self.name,
                failure_reason=f"invalid JSON: {exc}",
            )
        results = body.get("results")
        if not isinstance(results, list):
            return SearchResult(
                query=query, locale=self.locale, provider=self.name,
                failure_reason="missing 'results' array in response",
            )
        hits = tuple(_to_hit(r) for r in results if isinstance(r, dict))
        if include_domains:
            allowed = {d.lower() for d in include_domains}
            hits = tuple(h for h in hits if h.source_domain.lower() in allowed)
        if exclude_domains:
            blocked = {d.lower() for d in exclude_domains}
            hits = tuple(h for h in hits if h.source_domain.lower() not in blocked)
        return SearchResult(
            query=query, locale=self.locale, hits=hits, provider=self.name,
        )


def _to_hit(raw: dict) -> SearchHit:
    url = raw.get("url", "") or ""
    meta_host = ""
    meta = raw.get("meta_url")
    if isinstance(meta, dict):
        meta_host = meta.get("hostname", "") or ""
    return SearchHit(
        title=raw.get("title", "") or "",
        url=url,
        snippet=raw.get("description", "") or "",
        published_iso=raw.get("page_age", "") or "",
        source_domain=meta_host or (urlparse(url).hostname or "" if url else ""),
    )
