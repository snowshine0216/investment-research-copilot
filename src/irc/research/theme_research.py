from __future__ import annotations
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

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


def build_holdings_query(keywords: Iterable[str]) -> str:
    """Build a concrete holdings_sector query from user holdings.

    Adversarial review §A1: the generic ``用户组合涉及行业的最新新闻`` query
    tokenizes to ``用户/研究/组合`` and matches unrelated industry reports.
    Inject the user's actual sector codes / fund-house names so the
    query has a concrete hook.
    """
    items = [k for k in (str(t).strip() for t in keywords) if k]
    if not items:
        return _THEME_QUERIES["holdings_sector"]
    # Keep the sequence stable so the same holdings produce the same query.
    return (
        "近期 " + "、".join(items) + " 等行业/资产的政策、基本面与研报要点，附原始出处。"
    )

FRESHNESS_DAYS_BY_THEME: Mapping[str, int] = MappingProxyType({
    "us_monetary": 7,
    "us_fiscal_politics": 7,
    "cn_monetary": 7,
    "cn_equity_property_policy": 14,
    "geopolitics": 7,
    "gold_drivers": 30,
    "holdings_sector": 14,
})
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
) -> tuple[ThemeReport, Any]:
    try:
        matched = providers_for_locale(locale, providers)
    except ValueError as exc:
        return ThemeReport(
            theme=theme, query=query, locale=locale.value,
            report_md="", citations=[], failure_reason=str(exc),
            provider_failures=(),
        ), None
    raw_results = provider_results(query, locale, matched, max_results=max_hits, freshness_days=freshness_days)
    failures = tuple(
        f"{r.provider}: {r.failure_reason}"
        for r in raw_results
        if r.failure_reason
    )
    hits = hits_from_results(raw_results, max_hits)
    pages = extract_top_pages(hits, extractor, top_k=top_pages)
    result, resp = synthesize_report(
        query=query, hits=hits, pages=pages, route=route,
    )
    return ThemeReport(
        theme=theme, query=query, locale=locale.value,
        report_md=result.report_md, citations=result.citations,
        failure_reason=result.failure_reason,
        provider_failures=failures,
    ), resp


def _query_for_with_context(theme: str, holdings_keywords: tuple[str, ...]) -> str:
    if theme == "holdings_sector":
        return build_holdings_query(holdings_keywords)
    return _query_for(theme)


def _apply_relevance_filter(
    report: ThemeReport,
    keywords: frozenset[str],
) -> ThemeReport:
    """Drop citations that don't mention any keyword. If the filter
    leaves zero citations on a successful report, mark the whole report
    as failed so the quality gate (item 003) sees the degradation.
    """
    if not keywords or not report.citations:
        return report
    # Local import keeps the module import graph shallow.
    from irc.research.relevance import filter_relevant_citations

    kept = filter_relevant_citations(tuple(report.citations), keywords)
    if len(kept) == len(report.citations):
        return report
    if not kept:
        return ThemeReport(
            theme=report.theme,
            query=report.query,
            locale=report.locale,
            report_md=report.report_md,
            citations=[],
            failure_reason="no relevant sources after relevance filter",
            provider_failures=report.provider_failures,
        )
    return ThemeReport(
        theme=report.theme,
        query=report.query,
        locale=report.locale,
        report_md=report.report_md,
        citations=list(kept),
        failure_reason=report.failure_reason,
        provider_failures=report.provider_failures,
    )


def build_theme_reports(
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
    max_hits: int = 8,
    top_pages: int = 5,
    holdings_keywords: tuple[str, ...] = (),
) -> tuple[list[ThemeReport], list[Any]]:
    """For each theme: pick locale → fan-out search → extract top pages → LLM synth.

    Per-theme failures (no provider, no hits, LLM error) are recorded in the report's
    failure_reason; other themes still run. Wall-clock target ≤30 s per theme.

    Returns ``(reports, llm_responses)`` where ``llm_responses`` collects the
    ChatResponse from each successful LLM call (Shape B — usage rides up as data).

    ``holdings_keywords`` (item 001) drives two behaviors:

    1. For the ``holdings_sector`` theme, a concrete query is built from
       the user's actual sector/asset-class hooks instead of the broken
       generic placeholder.
    2. For any theme, after fetching, citations whose title or URL
       doesn't mention at least one keyword are dropped. A theme whose
       filter leaves zero citations is marked failed so the quality
       gate sees the degradation.
    """
    from irc.observability import progress_iter
    from irc.research.relevance import normalize_keywords

    norm_keywords = normalize_keywords(holdings_keywords)
    out: list[ThemeReport] = []
    llm_responses: list[Any] = []
    for theme in progress_iter(themes, "research", total=len(themes)):
        report, resp = _build_one(
            theme=theme,
            query=_query_for_with_context(theme, holdings_keywords),
            locale=theme_locale(theme),
            providers=providers,
            extractor=extractor,
            route=route,
            max_hits=max_hits,
            top_pages=top_pages,
            freshness_days=FRESHNESS_DAYS_BY_THEME.get(theme, _DEFAULT_FRESHNESS_DAYS),
        )
        # Only the holdings_sector theme is gated on the user's
        # holdings keywords — the broader macro themes (us_monetary,
        # gold_drivers, geopolitics, etc.) carry general-market signal
        # that we want even when no keyword matches.
        if theme == "holdings_sector":
            report = _apply_relevance_filter(report, norm_keywords)
        out.append(report)
        if resp is not None:
            llm_responses.append(resp)
    return out, llm_responses
