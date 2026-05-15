from __future__ import annotations
from urllib.parse import urlparse

from irc.research.search._http import post_json
from irc.research.search.types import Locale, SearchHit, SearchResult


_ENDPOINT = "https://api.tavily.com/search"


class TavilyProvider:
    """English-language search via Tavily.

    Pure adapter — no caching at this layer. Failures degrade into
    SearchResult(failure_reason=...) rather than raising.
    """

    name: str = "tavily"
    locale: Locale = Locale.EN

    def __init__(self, api_key: str, *, timeout_s: int = 15) -> None:
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
        payload: dict = {"query": query, "search_depth": "advanced", "max_results": max_results}
        if freshness_days is not None:
            payload["topic"] = "news"
            payload["days"] = freshness_days
        if include_domains:
            payload["include_domains"] = list(include_domains)
        if exclude_domains:
            payload["exclude_domains"] = list(exclude_domains)
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        body, err = post_json(
            _ENDPOINT, payload=payload, headers=headers, timeout_s=self._timeout_s,
            query=query, locale=self.locale, provider=self.name,
        )
        if err is not None:
            return err
        results = body.get("results")
        if not isinstance(results, list):
            return SearchResult(query=query, locale=self.locale, provider=self.name,
                                failure_reason="missing 'results' array in response")
        hits = tuple(_to_hit(r) for r in results if isinstance(r, dict))
        return SearchResult(query=query, locale=self.locale, hits=hits, provider=self.name)


def _to_hit(raw: dict) -> SearchHit:
    url = raw.get("url", "") or ""
    return SearchHit(
        title=raw.get("title", "") or "",
        url=url,
        snippet=raw.get("content", "") or "",
        published_iso=raw.get("published_date", "") or "",
        source_domain=urlparse(url).hostname or "" if url else "",
    )
