from __future__ import annotations
from datetime import datetime, timezone

from irc.research.search.types import (
    ContentExtractor,
    ExtractedPage,
    Locale,
    SearchHit,
    SearchProvider,
    SearchResult,
)


def providers_for_locale(
    locale: Locale,
    providers: tuple[SearchProvider, ...],
) -> tuple[SearchProvider, ...]:
    """Return only the providers whose locale matches. Raise ValueError if none."""
    matched = tuple(p for p in providers if p.locale == locale)
    if not matched:
        raise ValueError(f"no {locale.value} search provider configured")
    return matched


def multi_provider_search(
    query: str,
    locale: Locale,
    providers: tuple[SearchProvider, ...],
    *,
    max_results: int = 10,
    freshness_days: int | None = None,
    include_domains: tuple[str, ...] = (),
) -> tuple[SearchHit, ...]:
    """Fan out to every provider matching the locale, dedupe by URL preserving the
    first provider's hit, and return up to max_results hits.

    Per-provider failures are ignored (their hits are simply absent); the call as a
    whole never raises. Returns an empty tuple when every matching provider fails
    or returns no hits.
    """
    seen: set[str] = set()
    out: list[SearchHit] = []
    for provider in providers:
        if provider.locale != locale:
            continue
        result = provider.search(
            query,
            max_results=max_results,
            freshness_days=freshness_days,
            include_domains=include_domains,
        )
        if result.failure_reason:
            continue
        for hit in result.hits:
            if not hit.url or hit.url in seen:
                continue
            seen.add(hit.url)
            out.append(hit)
            if len(out) >= max_results:
                return tuple(out)
    return tuple(out)


def provider_results(
    query: str,
    locale: Locale,
    providers: tuple[SearchProvider, ...],
    *,
    max_results: int = 10,
    freshness_days: int | None = None,
    include_domains: tuple[str, ...] = (),
) -> tuple[SearchResult, ...]:
    """Fan out to all locale-matching providers; return one SearchResult per provider.

    Unlike multi_provider_search, this preserves failure_reason for each provider
    instead of silently dropping failed providers. Exceptions from a provider's
    search() method are caught and converted to a failed SearchResult.
    """
    out: list[SearchResult] = []
    for provider in providers:
        if provider.locale != locale:
            continue
        try:
            out.append(provider.search(
                query,
                max_results=max_results,
                freshness_days=freshness_days,
                include_domains=include_domains,
            ))
        except Exception as exc:
            out.append(SearchResult(
                query=query,
                locale=locale,
                provider=provider.name,
                failure_reason=f"provider raised: {exc}",
            ))
    return tuple(out)


def extract_top_pages(
    hits: tuple[SearchHit, ...],
    extractor: ContentExtractor,
    *,
    top_k: int = 5,
    timeout_s: int = 20,
) -> tuple[ExtractedPage, ...]:
    """Convert the first top_k hits to markdown pages. Per-URL failures are kept as
    ExtractedPage with failure_reason set, never dropped. Extractor exceptions are
    caught and converted to failed pages so dispatch never raises."""
    out: list[ExtractedPage] = []
    for hit in hits[:top_k]:
        try:
            page = extractor.extract(hit.url, timeout_s=timeout_s)
        except Exception as exc:
            page = ExtractedPage(
                url=hit.url, title=hit.title, markdown="",
                fetched_at_iso=datetime.now(tz=timezone.utc).isoformat(),
                failure_reason=f"extractor raised: {exc}",
            )
        out.append(page)
    return tuple(out)
