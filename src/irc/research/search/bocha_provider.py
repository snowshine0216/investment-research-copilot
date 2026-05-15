from __future__ import annotations
from urllib.parse import urlparse

from irc.research.search._http import post_json
from irc.research.search.types import Locale, SearchHit, SearchResult


_ENDPOINT = "https://api.bochaai.com/v1/web-search"


def _freshness_bucket(days: int) -> str:
    if days <= 1:
        return "oneDay"
    if days <= 7:
        return "oneWeek"
    if days <= 31:
        return "oneMonth"
    if days <= 366:
        return "oneYear"
    return "noLimit"


class BochaProvider:
    """Mainland-China search via Bocha AI (博查).

    Covers eastmoney, xueqiu, cls.cn, wallstreetcn, sina finance, gov.cn outlets.
    Pure adapter — failures degrade into SearchResult(failure_reason=...).
    """

    name: str = "bocha"
    locale: Locale = Locale.ZH

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
        payload: dict = {"query": query, "count": max_results, "summary": True}
        if freshness_days is not None:
            payload["freshness"] = _freshness_bucket(freshness_days)
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        body, err = post_json(
            _ENDPOINT, payload=payload, headers=headers, timeout_s=self._timeout_s,
            query=query, locale=self.locale, provider=self.name,
        )
        if err is not None:
            return err
        if body.get("code") != 200:
            return SearchResult(query=query, locale=self.locale, provider=self.name,
                                failure_reason=f"bocha error {body.get('code')}: {body.get('msg', '')}")
        data = body.get("data")
        if not isinstance(data, dict):
            return SearchResult(query=query, locale=self.locale, provider=self.name,
                                failure_reason="missing 'data' object in response")
        web_pages = data.get("webPages")
        if not isinstance(web_pages, dict):
            return SearchResult(query=query, locale=self.locale, provider=self.name,
                                failure_reason="missing 'webPages' object in response")
        values = web_pages.get("value")
        if not isinstance(values, list):
            return SearchResult(query=query, locale=self.locale, provider=self.name,
                                failure_reason="missing 'webPages.value' array in response")
        hits = tuple(_to_hit(r) for r in values if isinstance(r, dict))
        if include_domains:
            allowed = {d.lower() for d in include_domains}
            hits = tuple(h for h in hits if h.source_domain.lower() in allowed)
        if exclude_domains:
            blocked = {d.lower() for d in exclude_domains}
            hits = tuple(h for h in hits if h.source_domain.lower() not in blocked)
        return SearchResult(query=query, locale=self.locale, hits=hits, provider=self.name)


def _to_hit(raw: dict) -> SearchHit:
    url = raw.get("url", "") or ""
    return SearchHit(
        title=raw.get("name", "") or "",
        url=url,
        snippet=raw.get("summary", "") or raw.get("snippet", "") or "",
        published_iso=raw.get("datePublished", "") or "",
        source_domain=urlparse(url).hostname or "" if url else "",
    )



