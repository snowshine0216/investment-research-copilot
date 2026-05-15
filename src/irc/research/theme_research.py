from __future__ import annotations
from dataclasses import dataclass

from irc.llm._types import ResolvedRoute
from irc.research.search.dispatch import (
    extract_top_pages,
    hits_from_results,
    provider_results,
    providers_for_locale,
)
from irc.research.search.types import (
    ContentExtractor,
    Locale,
    SearchProvider,
)
from irc.research.synthesize import Citation, synthesize_report


@dataclass(frozen=True)
class ThemeReport:
    theme: str
    query: str
    locale: str
    report_md: str
    citations: list[Citation]
    failure_reason: str
    provider_failures: tuple[str, ...] = ()


_THEME_QUERIES: dict[str, str] = {
    "us_monetary": "What did the Fed say or do this past week? Cite primary sources.",
    "us_fiscal_politics": "Recent US fiscal / political news affecting markets, with citations.",
    "cn_monetary": "央行最近一周的货币政策操作和表态，附原始出处。",
    "cn_equity_property_policy": "中国股市/地产监管和政策最新进展，附原始出处。",
    "geopolitics": (
        "Material geopolitical events (Russia-Ukraine, Middle East, Taiwan) this week "
        "with primary sources."
    ),
    "gold_drivers": (
        "Recent moves in real yields, USD, central bank gold purchases, ETF flows; "
        "cite primary sources."
    ),
    "holdings_sector": "用户组合涉及行业的最新新闻和研报要点，附原始出处。",
}

FRESHNESS_DAYS_BY_THEME: dict[str, int] = {
    "us_monetary": 7,
    "us_fiscal_politics": 7,
    "cn_monetary": 7,
    "cn_equity_property_policy": 14,
    "geopolitics": 7,
    "gold_drivers": 30,
    "holdings_sector": 14,
}
_DEFAULT_FRESHNESS_DAYS = 14

_LOCALE_BY_PREFIX: tuple[tuple[str, Locale], ...] = (
    ("us_", Locale.EN),
    ("gold", Locale.EN),
    ("geopolitics", Locale.EN),
    ("cn_", Locale.ZH),
    ("hk_", Locale.ZH),
    ("holdings", Locale.ZH),
)


def theme_locale(theme: str) -> Locale:
    """Map a theme key to the search locale that fits its source ecosystem."""
    for prefix, locale in _LOCALE_BY_PREFIX:
        if theme.startswith(prefix):
            return locale
    return Locale.EN


def _query_for(theme: str) -> str:
    return _THEME_QUERIES.get(theme, f"Research summary for {theme}")


def _build_one(
    theme: str,
    query: str,
    locale: Locale,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
    max_hits: int,
    top_pages: int,
    freshness_days: int = _DEFAULT_FRESHNESS_DAYS,
) -> ThemeReport:
    try:
        matched = providers_for_locale(locale, providers)
    except ValueError as exc:
        return ThemeReport(
            theme=theme, query=query, locale=locale.value,
            report_md="", citations=[], failure_reason=str(exc),
            provider_failures=(),
        )
    raw_results = provider_results(query, locale, matched, max_results=max_hits, freshness_days=freshness_days)
    failures = tuple(
        f"{r.provider}: {r.failure_reason}"
        for r in raw_results
        if r.failure_reason
    )
    hits = hits_from_results(raw_results, max_hits)
    pages = extract_top_pages(hits, extractor, top_k=top_pages)
    result = synthesize_report(
        query=query, hits=hits, pages=pages, route=route,
    )
    return ThemeReport(
        theme=theme, query=query, locale=locale.value,
        report_md=result.report_md, citations=result.citations,
        failure_reason=result.failure_reason,
        provider_failures=failures,
    )


def build_theme_reports(
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
    max_hits: int = 8,
    top_pages: int = 5,
) -> list[ThemeReport]:
    """For each theme: pick locale → fan-out search → extract top pages → LLM synth.

    Per-theme failures (no provider, no hits, LLM error) are recorded in the report's
    failure_reason; other themes still run. Wall-clock target ≤30 s per theme.
    """
    from irc.observability import progress_iter

    out: list[ThemeReport] = []
    for theme in progress_iter(themes, "research", total=len(themes)):
        out.append(_build_one(
            theme=theme,
            query=_query_for(theme),
            locale=theme_locale(theme),
            providers=providers,
            extractor=extractor,
            route=route,
            max_hits=max_hits,
            top_pages=top_pages,
            freshness_days=FRESHNESS_DAYS_BY_THEME.get(theme, _DEFAULT_FRESHNESS_DAYS),
        ))
    return out
