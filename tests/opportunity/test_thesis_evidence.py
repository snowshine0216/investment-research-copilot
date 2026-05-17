"""Tests for the deterministic thesis-state derivation from ConstituentSnapshot
+ ThemeReport. Replaces the prior table-based path with concrete fundamentals."""
from __future__ import annotations

from irc.fundamentals.types import (
    BrokerReport,
    Constituent,
    ConstituentSnapshot,
    FilingDigest,
)
from irc.opportunity.thesis_evidence import _classify_theme_report, derive_thesis_from_evidence
from irc.research.synthesize import Citation
from irc.research.theme_research import ThemeReport


# ---------------------------------------------------------------------------
# _classify_theme_report — unit tests (Task 1, Step 1.1)
# ---------------------------------------------------------------------------

def _r(failure_reason: str = "", report_md: str = "body") -> ThemeReport:
    return ThemeReport(theme="t", query="q", locale="en",
                       report_md=report_md, citations=[],
                       failure_reason=failure_reason)


def test_classify_usable_report():
    assert _classify_theme_report(_r()) == "usable"


def test_classify_search_empty():
    assert _classify_theme_report(_r(failure_reason="no sources to synthesize from")) == "search_empty"


def test_classify_search_empty_via_provider_no_results():
    # bocha/tavily/brave emit "no results", dispatch may forward this verbatim
    assert _classify_theme_report(_r(failure_reason="bocha: no results")) == "search_empty"


def test_classify_llm_failed_on_arbitrary_exception_text():
    assert _classify_theme_report(_r(failure_reason="ChatCompletionError: 429 rate limit")) == "llm_failed"


def test_classify_llm_failed_on_unrecognized_failure():
    # Any failure_reason that doesn't match the search-empty pattern is treated as LLM/synth-side
    assert _classify_theme_report(_r(failure_reason="something else")) == "llm_failed"


def test_classify_treats_empty_body_with_no_failure_as_search_empty():
    # ThemeReport with empty report_md but no failure_reason — only happens when
    # the synthesizer returned an empty string for an unknown reason; treat as
    # search-empty (closer to user-actionable than llm_failed).
    assert _classify_theme_report(_r(report_md="")) == "search_empty"


def _filing(symbol: str, yoy: float | None, *, period: str = "Q1") -> FilingDigest:
    return FilingDigest(
        symbol=symbol,
        fiscal_period=period,
        filed_at_iso="2026-04-28",
        revenue_yoy=yoy,
        net_income_yoy=None,
        gross_margin=None,
        guidance_text="",
        source_url=f"https://example.com/filing/{symbol}",
    )


def _broker(symbol: str, rating: str, days_ago: int = 5) -> BrokerReport:
    from datetime import date, timedelta
    pub = (date(2026, 5, 15) - timedelta(days=days_ago)).isoformat()
    return BrokerReport(
        symbol=symbol,
        broker="中信证券",
        rating=rating,
        target_price=None,
        published_iso=pub,
        title=f"{symbol} 研报",
        source_url=f"https://example.com/broker/{symbol}",
    )


def _snapshot(filings: tuple[FilingDigest, ...], brokers: tuple[BrokerReport, ...] = ()) -> ConstituentSnapshot:
    cons = tuple(
        Constituent(symbol=f.symbol, name=f.symbol, weight=0.05, market="cn")
        for f in filings
    )
    return ConstituentSnapshot(
        lookthrough_target="半导体",
        as_of_iso="2026-05-15",
        constituents=cons,
        filings=filings,
        broker_reports=brokers,
    )


def _theme_report(report_md: str = "Recent industry news.", *, citations: list[Citation] | None = None) -> ThemeReport:
    return ThemeReport(
        theme="semiconductor",
        query="q",
        locale="zh",
        report_md=report_md,
        citations=citations or [],
        failure_reason="",
    )


# ---------------------------------------------------------------------------
# Evidence-insufficient paths
# ---------------------------------------------------------------------------

def test_evidence_insufficient_when_snapshot_and_theme_report_both_none():
    state, _reason, evidence, gaps = derive_thesis_from_evidence(None, None)
    assert state == "evidence_insufficient"
    assert evidence == ()
    assert "missing_constituent_snapshot" in gaps
    assert "news_stage_skipped" in gaps
    assert "missing_recent_news" not in gaps


def test_evidence_insufficient_when_snapshot_has_no_filings():
    snap = _snapshot(filings=())
    state, _reason, _ev, gaps = derive_thesis_from_evidence(snap, None)
    assert state == "evidence_insufficient"
    assert "missing_constituent_snapshot" in gaps


def test_evidence_insufficient_when_all_filings_lack_yoy():
    snap = _snapshot(filings=tuple(_filing(f"S{i}", None) for i in range(5)))
    state, _reason, _ev, gaps = derive_thesis_from_evidence(snap, None)
    assert state == "evidence_insufficient"
    assert "missing_constituent_snapshot" in gaps


def test_evidence_insufficient_when_theme_report_failed():
    snap = _snapshot(filings=())
    tr = ThemeReport(theme="x", query="q", locale="zh", report_md="",
                     citations=[], failure_reason="all providers down")
    state, _reason, _ev, gaps = derive_thesis_from_evidence(snap, tr)
    assert state == "evidence_insufficient"
    assert "news_llm_failed" in gaps
    assert "missing_recent_news" not in gaps


# ---------------------------------------------------------------------------
# Intact path
# ---------------------------------------------------------------------------

def test_intact_when_strong_majority_positive_yoy_and_neutral_brokers():
    """Strong majority positive (≥60% pos AND <30% neg) with no broker signal → intact."""
    filings = tuple(
        [_filing(f"P{i}", 0.15) for i in range(8)]
        + [_filing(f"N{i}", -0.05) for i in range(2)]
    )
    snap = _snapshot(filings=filings)
    state, _reason, _ev, gaps = derive_thesis_from_evidence(snap, _theme_report())
    assert state == "intact"
    assert "missing_constituent_snapshot" not in gaps


def test_intact_when_majority_positive_and_buy_broker_consensus():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(7))
    brokers = tuple(_broker(f"S{i}", rating="买入") for i in range(5))
    snap = _snapshot(filings=filings, brokers=brokers)
    state, _reason, _ev, gaps = derive_thesis_from_evidence(snap, _theme_report())
    assert state == "intact"
    assert "missing_broker_coverage" not in gaps


# ---------------------------------------------------------------------------
# Under-pressure path
# ---------------------------------------------------------------------------

def test_under_pressure_when_30pct_negative_yoy():
    filings = tuple(
        [_filing(f"P{i}", 0.05) for i in range(7)]
        + [_filing(f"N{i}", -0.10) for i in range(3)]
    )
    snap = _snapshot(filings=filings)
    state, _reason, _ev, _gaps = derive_thesis_from_evidence(snap, _theme_report())
    assert state == "under_pressure"


def test_under_pressure_when_broker_consensus_negative():
    """Majority positive YoY but broker ratings collapsed → under_pressure."""
    filings = tuple(_filing(f"S{i}", 0.08) for i in range(7))
    brokers = tuple(_broker(f"S{i}", rating="减持") for i in range(5))
    snap = _snapshot(filings=filings, brokers=brokers)
    state, _reason, _ev, _gaps = derive_thesis_from_evidence(snap, _theme_report())
    assert state == "under_pressure"


# ---------------------------------------------------------------------------
# Falsified path
# ---------------------------------------------------------------------------

def test_falsified_when_majority_negative_yoy():
    filings = tuple(
        [_filing(f"N{i}", -0.15) for i in range(7)]
        + [_filing(f"P{i}", 0.05) for i in range(3)]
    )
    snap = _snapshot(filings=filings)
    state, _reason, _ev, _gaps = derive_thesis_from_evidence(snap, _theme_report())
    assert state == "falsified"


# ---------------------------------------------------------------------------
# Evidence assembly
# ---------------------------------------------------------------------------

def test_evidence_includes_filing_entries():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(5))
    snap = _snapshot(filings=filings)
    _state, _reason, evidence, _gaps = derive_thesis_from_evidence(snap, _theme_report())
    assert any(e.type == "filing" for e in evidence)
    filing_e = next(e for e in evidence if e.type == "filing")
    assert filing_e.url.startswith("https://example.com/filing/")
    assert filing_e.date == "2026-04-28"


def test_evidence_includes_broker_entries():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(3))
    brokers = (_broker("S0", rating="买入"),)
    snap = _snapshot(filings=filings, brokers=brokers)
    _state, _reason, evidence, _gaps = derive_thesis_from_evidence(snap, _theme_report())
    assert any(e.type == "broker" for e in evidence)
    broker_e = next(e for e in evidence if e.type == "broker")
    assert broker_e.source == "中信证券"


def test_evidence_includes_news_from_theme_report_citations():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(3))
    snap = _snapshot(filings=filings)
    tr = _theme_report(citations=[
        Citation(index=1, title="Policy news", url="https://x.example/news",
                 published_iso="2026-05-10"),
    ])
    _state, _reason, evidence, _gaps = derive_thesis_from_evidence(snap, tr)
    assert any(e.type == "news" for e in evidence)


def test_evidence_capped_to_keep_card_readable():
    """Cap each evidence kind at a small N so cards don't bloat."""
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(20))
    brokers = tuple(_broker(f"S{i}", rating="买入") for i in range(10))
    snap = _snapshot(filings=filings, brokers=brokers)
    _state, _reason, evidence, _gaps = derive_thesis_from_evidence(snap, _theme_report())
    n_filing = sum(1 for e in evidence if e.type == "filing")
    n_broker = sum(1 for e in evidence if e.type == "broker")
    assert n_filing <= 3
    assert n_broker <= 2


# ---------------------------------------------------------------------------
# Gap typing
# ---------------------------------------------------------------------------

def test_missing_broker_coverage_gap_when_no_broker_reports():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(5))
    snap = _snapshot(filings=filings, brokers=())
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(snap, _theme_report())
    assert "missing_broker_coverage" in gaps


# ---------------------------------------------------------------------------
# Theme-report-only thesis derivation (Path B)
# ---------------------------------------------------------------------------

def _research_theme_report(n_citations: int, *, failure: str = "") -> ThemeReport:
    return ThemeReport(
        theme="gold_drivers",
        query="gold drivers",
        locale="en",
        report_md="# gold drivers\n\nContent body.\n",
        citations=[
            Citation(index=i, title=f"t{i}", url=f"https://x/{i}", published_iso="2026-05-01")
            for i in range(n_citations)
        ],
        failure_reason=failure,
    )


def test_theme_report_with_3plus_citations_yields_intact_when_no_snapshot():
    state, reason, evidence, gaps = derive_thesis_from_evidence(None, _research_theme_report(3))
    assert state == "intact"
    assert "研究" in reason or "research" in reason or "citations" in reason
    assert any(e.type == "news" for e in evidence)
    assert "missing_constituent_snapshot" in gaps


def test_theme_report_with_failure_falls_back_to_insufficient():
    state, _, _, gaps = derive_thesis_from_evidence(None, _research_theme_report(5, failure="provider 429"))
    assert state == "evidence_insufficient"


def test_theme_report_with_too_few_citations_falls_back_to_insufficient():
    state, _, _, _ = derive_thesis_from_evidence(None, _research_theme_report(1))
    assert state == "evidence_insufficient"


def test_theme_report_with_zero_citations_insufficient():
    state, _, _, _ = derive_thesis_from_evidence(None, _research_theme_report(0))
    assert state == "evidence_insufficient"


def test_empty_report_md_with_no_failure_reason_adds_news_search_empty_gap():
    """ThemeReport with empty body but no failure_reason should yield a gap, not be treated as failed."""
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(5))
    snap = _snapshot(filings=filings)
    tr = _theme_report(report_md="")  # empty report, no failure_reason
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(snap, tr)
    assert "news_search_empty" in gaps
    assert "missing_recent_news" not in gaps


# ---------------------------------------------------------------------------
# Refined constituent-gap labels (in addition to legacy missing_constituent_snapshot)
# ---------------------------------------------------------------------------


def test_refined_label_constituent_not_applicable_for_gold():
    """Gold has no equity-style constituents; emit constituent_not_applicable
    alongside the legacy label."""
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="gold",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_not_applicable" in gaps


def test_refined_label_constituent_not_applicable_for_bond():
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_bond_fund",
    )
    assert "constituent_not_applicable" in gaps


def test_refined_label_constituent_not_applicable_for_active_fund():
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_equity_fund",
    )
    assert "constituent_not_applicable" in gaps


def test_refined_label_constituent_fetch_failed_when_snapshot_empty():
    """Snapshot object exists but filings is empty AND failure_reasons records
    a fetch problem → constituent_fetch_failed."""
    snap = ConstituentSnapshot(
        lookthrough_target="纳斯达克100",
        as_of_iso="2026-05-16",
        constituents=(Constituent(symbol="AAPL", name="AAPL", weight=0.0, market="us"),),
        filings=(),
        broker_reports=(),
        failure_reasons=("missing filing digest: AAPL (missing_email)",),
    )
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        snap, _theme_report(), asset_class="us_etf",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_fetch_failed" in gaps


def test_refined_label_constituent_missing_when_snapshot_none_for_indexable_class():
    """ETF whose lookthrough target is not yet registered → constituent_missing."""
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_etf",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_missing" in gaps


def test_no_refined_label_when_snapshot_usable():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(5))
    snap = _snapshot(filings=filings)
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        snap, _theme_report(), asset_class="cn_etf",
    )
    assert "missing_constituent_snapshot" not in gaps
    assert "constituent_not_applicable" not in gaps
    assert "constituent_fetch_failed" not in gaps
    assert "constituent_missing" not in gaps


def test_no_refined_label_when_asset_class_omitted():
    """Backward-compatible: without asset_class, only legacy label appears."""
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(None, _theme_report())
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_not_applicable" not in gaps
    assert "constituent_fetch_failed" not in gaps
    assert "constituent_missing" not in gaps


# ---------------------------------------------------------------------------
# Typed news-cause codes at emission sites (Task 2, Step 2.1)
# ---------------------------------------------------------------------------

def test_news_stage_skipped_when_theme_report_is_none():
    _, _, _, gaps = derive_thesis_from_evidence(None, None, asset_class="cn_etf")
    assert "news_stage_skipped" in gaps
    assert "missing_recent_news" not in gaps


def test_news_search_empty_when_no_sources():
    r = ThemeReport(theme="t", query="q", locale="en", report_md="", citations=[],
                    failure_reason="no sources to synthesize from")
    _, _, _, gaps = derive_thesis_from_evidence(None, r, asset_class="cn_etf")
    assert "news_search_empty" in gaps
    assert "missing_recent_news" not in gaps


def test_news_llm_failed_on_synth_exception():
    r = ThemeReport(theme="t", query="q", locale="en", report_md="", citations=[],
                    failure_reason="429 rate limit")
    _, _, _, gaps = derive_thesis_from_evidence(None, r, asset_class="cn_etf")
    assert "news_llm_failed" in gaps
    assert "missing_recent_news" not in gaps

