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


def _theme_report_usable(report: ThemeReport | None) -> bool:
    return report is not None and not report.failure_reason and bool(report.report_md)


_MIN_RESEARCH_CITATIONS = 3


def _thesis_from_theme_report(
    report: ThemeReport,
) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...]]:
    """Conservative rule: usable report with ≥3 citations → intact (research-backed)."""
    if len(report.citations) < _MIN_RESEARCH_CITATIONS:
        return "evidence_insufficient", "", ()
    return (
        "intact",
        f"长期逻辑由主题研究背书（citations={len(report.citations)}），暂未触发证伪。",
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


def derive_thesis_from_evidence(
    snapshot: ConstituentSnapshot | None,
    theme_report: ThemeReport | None,
) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...], tuple[str, ...]]:
    """Derive (state, reason, evidence, gap_labels) from concrete sources.

    Pure: no I/O, no time-of-day dependence. The caller decides what to do
    with `gap_labels` — typically merge into `OpportunityRow.evidence_gaps`.
    """
    gaps: list[str] = []

    snapshot_usable = snapshot is not None and bool(snapshot.filings)
    if not snapshot_usable:
        gaps.append("missing_constituent_snapshot")
    if not _theme_report_usable(theme_report):
        gaps.append("missing_recent_news")

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
        if state != "evidence_insufficient":
            return state, reason, evidence, tuple(gaps)

    return (
        "evidence_insufficient",
        "缺少底层成分股财报数据，且主题研究证据不足，无法判定长期逻辑。",
        (),
        tuple(gaps),
    )
