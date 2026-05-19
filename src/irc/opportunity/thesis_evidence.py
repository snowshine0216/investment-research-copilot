"""Derive `thesis_state` from concrete `ConstituentSnapshot` + `ThemeReport`
evidence rather than free-text LLM prose.

Pure function. The rules implement the May-14 spec's deterministic table:

- intact: ≥60% of constituents with a reported revenue YoY are positive AND
  broker consensus is not negative.
- under_pressure: ≥30% of constituents with a reported revenue YoY are
  negative OR broker consensus leans negative.
- falsified: ≥60% of constituents are in YoY decline (proxy for the spec's
  "≥2 consecutive negative quarters across the top constituents").
- evidence_insufficient: snapshot missing, has no constituents, has no
  filings with usable revenue_yoy, or the theme report failed and the
  snapshot is also empty.
"""
from __future__ import annotations

from irc.fundamentals.types import (
    BrokerReport,
    ConstituentSnapshot,
    FilingDigest,
)
from irc.opportunity.types import ThesisEvidence, ThesisState
from irc.research.theme_research import ThemeReport


_POSITIVE_RATING_TOKENS: frozenset[str] = frozenset({
    "买入", "增持", "推荐", "强烈推荐", "Buy", "Overweight", "Outperform",
})
_NEGATIVE_RATING_TOKENS: frozenset[str] = frozenset({
    "卖出", "减持", "回避", "Sell", "Underweight", "Underperform",
})

_MAX_FILING_EVIDENCE = 3
_MAX_BROKER_EVIDENCE = 2
_MAX_NEWS_EVIDENCE = 2

_INTACT_POSITIVE_PCT = 0.60
_UNDER_PRESSURE_NEGATIVE_PCT = 0.30
_FALSIFIED_NEGATIVE_PCT = 0.60


def _rating_sentiment(rating: str) -> int:
    """+1 / 0 / -1 for positive / neutral / negative broker ratings."""
    r = (rating or "").strip()
    if any(tok in r for tok in _POSITIVE_RATING_TOKENS):
        return 1
    if any(tok in r for tok in _NEGATIVE_RATING_TOKENS):
        return -1
    return 0


def _broker_consensus(reports: tuple[BrokerReport, ...]) -> int:
    """Sum of rating sentiments. >0 → buy-leaning, <0 → sell-leaning, 0 → mixed."""
    return sum(_rating_sentiment(r.rating) for r in reports)


def _yoy_split(filings: tuple[FilingDigest, ...]) -> tuple[int, int, int]:
    """Return (positive, negative, total_with_yoy)."""
    pos = neg = total = 0
    for f in filings:
        if f.revenue_yoy is None:
            continue
        total += 1
        if f.revenue_yoy > 0:
            pos += 1
        elif f.revenue_yoy < 0:
            neg += 1
    return pos, neg, total


def _filing_evidence(filings: tuple[FilingDigest, ...]) -> tuple[ThesisEvidence, ...]:
    """Up to N filings with the most extreme YoY moves (largest magnitude first)."""
    scored = [
        (abs(f.revenue_yoy), f) for f in filings if f.revenue_yoy is not None
    ]
    scored.sort(key=lambda t: t[0], reverse=True)
    out: list[ThesisEvidence] = []
    for _, f in scored[:_MAX_FILING_EVIDENCE]:
        out.append(ThesisEvidence(
            type="filing",
            source=f.symbol,
            url=f.source_url,
            date=f.filed_at_iso,
            summary=f"{f.symbol} {f.fiscal_period} 营收同比 {f.revenue_yoy:+.1%}。",
        ))
    return tuple(out)


def _broker_evidence(reports: tuple[BrokerReport, ...]) -> tuple[ThesisEvidence, ...]:
    """Up to N most recent broker reports."""
    recent = sorted(reports, key=lambda r: r.published_iso, reverse=True)
    out: list[ThesisEvidence] = []
    for r in recent[:_MAX_BROKER_EVIDENCE]:
        out.append(ThesisEvidence(
            type="broker",
            source=r.broker,
            url=r.source_url,
            date=r.published_iso,
            summary=f"{r.broker} {r.rating}: {r.title}".strip(),
        ))
    return tuple(out)


def _news_evidence(report: ThemeReport | None) -> tuple[ThesisEvidence, ...]:
    if report is None or not report.citations:
        return ()
    out: list[ThesisEvidence] = []
    for c in report.citations[:_MAX_NEWS_EVIDENCE]:
        out.append(ThesisEvidence(
            type="news",
            source=c.title or c.url,
            url=c.url,
            date=c.published_iso,
            summary=c.title,
        ))
    return tuple(out)


# Substring patterns that indicate a search-side failure (zero hits, provider
# unavailable). Anything else with a failure_reason is treated as LLM/synth side.
# Pattern-match is intentionally permissive — failure_reasons are free-text
# concatenations from providers, dispatch, and synthesize.py.
_SEARCH_EMPTY_PATTERNS: tuple[str, ...] = (
    "no sources to synthesize from",
    "no results",
    "missing 'results'",
    "missing 'webPages",
)


def _classify_theme_report(report: ThemeReport | None) -> str:
    """Classify a ThemeReport into one of:
      - "usable": has body and no failure_reason.
      - "search_empty": search returned zero/empty results.
      - "llm_failed": LLM synthesis raised, or any other non-search failure.

    Returns "search_empty" if the report has an empty body with no failure_reason
    (treat as user-actionable rather than internal error).
    Does NOT cover the report-is-None case — that's "stage_skipped" and the
    caller checks for it before classifying.
    """
    if report is None:
        # Defensive — callers should check is-None first. Treat as stage_skipped.
        return "stage_skipped"
    reason = (report.failure_reason or "").lower()
    if reason:
        for pat in _SEARCH_EMPTY_PATTERNS:
            if pat in reason:
                return "search_empty"
        return "llm_failed"
    if not report.report_md or not report.report_md.strip():
        return "search_empty"
    return "usable"


def _theme_report_usable(report: ThemeReport | None) -> bool:
    """Back-compat shim: True iff classifier says 'usable'."""
    return _classify_theme_report(report) == "usable"


_MIN_RESEARCH_CITATIONS = 3


def _count_trusted_citations(report: ThemeReport) -> int:
    """Citations whose host tier is PAPER-or-better.

    Adversarial review §A2: ``len(citations) >= 3`` is not enough to
    call a thesis ``intact`` when every citation is a republisher (e.g.
    我的钢铁网 reposting a PBOC press release). At least one citation
    must come from a tier-1 wire / paper / primary source.
    """
    from irc.research.source_tier import classify, is_trusted

    return sum(1 for c in report.citations if is_trusted(classify(c.url)))


def _thesis_from_theme_report(
    report: ThemeReport,
) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...]]:
    """Rule: report with ≥3 citations AND ≥1 trusted-tier citation
    → intact (research-backed). Otherwise evidence_insufficient."""
    if len(report.citations) < _MIN_RESEARCH_CITATIONS:
        return "evidence_insufficient", "", ()
    trusted = _count_trusted_citations(report)
    if trusted < 1:
        return (
            "evidence_insufficient",
            f"主题研究 {len(report.citations)} 条引用全部来自次级转载源，"
            f"未达到一级新闻/研究层级，长期逻辑暂不可背书。",
            _news_evidence(report),
        )
    return (
        "intact",
        f"长期逻辑由主题研究背书（citations={len(report.citations)}，"
        f"其中一级来源 {trusted} 条），暂未触发证伪。",
        _news_evidence(report),
    )


def _classify_state(
    pct_pos: float,
    pct_neg: float,
    consensus: int,
) -> tuple[ThesisState, str]:
    """Map YoY percentages + broker consensus to (state, reason). Pure."""
    if pct_neg >= _FALSIFIED_NEGATIVE_PCT:
        return (
            "falsified",
            f"成分股 {pct_neg:.0%} 营收同比为负，长期逻辑实质受损。",
        )
    if pct_pos >= _INTACT_POSITIVE_PCT and pct_neg < _UNDER_PRESSURE_NEGATIVE_PCT and consensus >= 0:
        return (
            "intact",
            f"成分股 {pct_pos:.0%} 营收同比为正，长期逻辑完好。",
        )
    if pct_neg >= _UNDER_PRESSURE_NEGATIVE_PCT or consensus < 0:
        reason = (
            f"成分股营收同比正向比例 {pct_pos:.0%}，但券商一致评级偏空。"
            if consensus < 0
            else f"成分股 {pct_neg:.0%} 营收同比为负，行业景气承压。"
        )
        return ("under_pressure", reason)
    return (
        "evidence_insufficient",
        f"成分股营收同比方向不明确（正 {pct_pos:.0%}/负 {pct_neg:.0%}）。",
    )


NON_INDEXABLE_ASSET_CLASSES: frozenset[str] = frozenset({
    "gold", "cn_bond_fund", "cn_equity_fund",
})
_NON_INDEXABLE_ASSET_CLASSES = NON_INDEXABLE_ASSET_CLASSES  # backward-compat alias


def _classify_constituent_gap(
    snapshot: ConstituentSnapshot | None,
    asset_class: str | None,
) -> str | None:
    """Refined gap label for the constituent layer.

    Returns one of:
      - 'constituent_not_applicable': asset class has no equity-style top-N
        (gold, bond, active fund).
      - 'constituent_fetch_failed': snapshot exists but every filing fetch
        failed (snapshot.failure_reasons is non-empty, filings is empty).
      - 'constituent_missing': asset class is constituent-bearing but no
        snapshot was loaded (lookthrough target not in _TARGET_REGISTRY).
      - None: snapshot present with usable filings.
    """
    if asset_class is None:
        return None
    if asset_class in _NON_INDEXABLE_ASSET_CLASSES:
        return "constituent_not_applicable"
    if snapshot is None:
        return "constituent_missing"
    if not snapshot.filings:
        return "constituent_fetch_failed" if snapshot.failure_reasons else "constituent_missing"
    return None


def derive_thesis_from_evidence(
    snapshot: ConstituentSnapshot | None,
    theme_report: ThemeReport | None,
    *,
    asset_class: str | None = None,
) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...], tuple[str, ...]]:
    """Derive (state, reason, evidence, gap_labels) from concrete sources.

    Pure: no I/O, no time-of-day dependence. The caller decides what to do
    with `gap_labels` — typically merge into `OpportunityRow.evidence_gaps`.

    When `asset_class` is provided, a refined constituent-gap label is appended
    to the legacy `missing_constituent_snapshot` label so consumers can
    distinguish 'not applicable' from 'fetch failed' from 'missing target'.
    """
    gaps: list[str] = []

    snapshot_usable = snapshot is not None and bool(snapshot.filings)
    if not snapshot_usable:
        gaps.append("missing_constituent_snapshot")
    if theme_report is None:
        gaps.append("news_stage_skipped")
    else:
        news_status = _classify_theme_report(theme_report)
        if news_status == "search_empty":
            gaps.append("news_search_empty")
        elif news_status == "llm_failed":
            gaps.append("news_llm_failed")
        # else 'usable' → no gap added

    refined = _classify_constituent_gap(snapshot, asset_class)
    if refined is not None and refined not in gaps:
        gaps.append(refined)

    # Path A: snapshot present and usable → constituent-driven thesis (authoritative)
    if snapshot_usable:
        pos, neg, total = _yoy_split(snapshot.filings)
        if total == 0:
            # Snapshot exists but no YoY data → fall through to theme_report path
            gaps.append("missing_constituent_snapshot")
        else:
            if not snapshot.broker_reports:
                gaps.append("missing_broker_coverage")
            consensus = _broker_consensus(snapshot.broker_reports)
            evidence = (
                _filing_evidence(snapshot.filings)
                + _broker_evidence(snapshot.broker_reports)
                + _news_evidence(theme_report)
            )
            state, reason = _classify_state(pos / total, neg / total, consensus)
            return (state, reason, evidence, tuple(gaps))

    # Path B: no usable snapshot → try theme_report-only thesis
    if theme_report is not None and _theme_report_usable(theme_report):
        state, reason, evidence = _thesis_from_theme_report(theme_report)
        # A non-empty reason means Path B reached a definite verdict —
        # either intact (research-backed) or a specific
        # evidence_insufficient ruling (e.g. all-republisher tier). The
        # empty-reason case is the legacy "no opinion, fall through".
        if reason:
            return state, reason, evidence, tuple(gaps)

    return (
        "evidence_insufficient",
        "缺少底层成分股财报数据，且主题研究证据不足，无法判定长期逻辑。",
        (),
        tuple(gaps),
    )
