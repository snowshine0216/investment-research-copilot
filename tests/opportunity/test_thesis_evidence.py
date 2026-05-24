"""Tests for the deterministic thesis-state derivation from ConstituentSnapshot
+ ThemeReport. Replaces the prior table-based path with concrete fundamentals."""
from __future__ import annotations

# ── Item 003: NON_INDEXABLE_ASSET_CLASSES ───────────────────────────────────

# ── Item 003: derive_thesis_from_evidence 5-tuple + flatten ordering ──────────

def _make_evidence(type_, weight, citation_seed, *, owner="005827", symbol="600519"):
    """Helper — produce a constituent-scoped evidence with controlled weight + id."""
    from irc.opportunity.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=symbol, url=f"https://x/{citation_seed}",
        date="2024-04-15", summary=f"{symbol}-{citation_seed}",
        scope="constituent", citation_kind="data" if type_ == "filing" else "information",
        owner_instrument_id=owner, parent_fund_id=owner, constituent_key=symbol,
        holding_weight_pct=weight,
    )


def test_derive_thesis_returns_5_tuple_for_active_fund() -> None:
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    from irc.opportunity.types import ConstituentAnalysis
    from irc.fundamentals.types import ActiveFundSnapshot
    ev = _make_evidence("filing", 6.2, "a")
    analysis = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=6.2,
        evidence=(ev,), failure_reasons=(), one_line_view="x",
    )
    snap = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="",
        constituent_analyses=(analysis,),
        failure_reasons_by_symbol={},
    )
    state, reason, evidence, gaps, analyses = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    assert analyses == (analysis,)
    assert evidence == (ev,)


def test_derive_thesis_5_tuple_non_active_returns_empty_analyses_slot() -> None:
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    result = derive_thesis_from_evidence(
        None, None, asset_class="us_etf", owner_instrument_id="x",
    )
    assert len(result) == 5
    assert result[4] == ()


def test_active_fund_thesis_evidence_flatten_ordering() -> None:
    """Q-J: order by (weight_pct desc, type_rank asc, citation_id asc).

    type_rank: filing=0, broker=1, news=2.
    """
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    from irc.opportunity.types import ConstituentAnalysis
    from irc.fundamentals.types import ActiveFundSnapshot
    # Holding A: weight=9.0 — broker + filing + news (broker added before filing
    # to assert sorter pushes filing first by type_rank).
    a_broker = _make_evidence("broker", 9.0, "ab", symbol="600519")
    a_filing = _make_evidence("filing", 9.0, "af", symbol="600519")
    a_news = _make_evidence("news", 9.0, "an", symbol="600519")
    # Holding B: weight=3.0 — single filing.
    b_filing = _make_evidence("filing", 3.0, "bf", symbol="000333")
    analyses = (
        ConstituentAnalysis("600519", "茅台", 9.0,
                            (a_broker, a_filing, a_news), (), ""),
        ConstituentAnalysis("000333", "美的", 3.0, (b_filing,), (), ""),
    )
    snap = ActiveFundSnapshot(
        fund_id="005827", source_report_date="", source_report_quarter="2024Q1",
        cache_probed_at="", constituent_analyses=analyses,
        failure_reasons_by_symbol={},
    )
    _, _, evidence, _, _ = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    # Holding A (weight 9.0) first; within A: filing → broker → news; then B.
    assert [e.type for e in evidence] == ["filing", "broker", "news", "filing"]
    assert [e.summary for e in evidence] == [
        "600519-af", "600519-ab", "600519-an", "000333-bf",
    ]


def test_non_indexable_asset_classes_excludes_cn_equity_fund() -> None:
    from irc.opportunity.thesis_evidence import NON_INDEXABLE_ASSET_CLASSES
    assert "cn_equity_fund" not in NON_INDEXABLE_ASSET_CLASSES
    # Other non-indexable classes preserved.
    assert "gold" in NON_INDEXABLE_ASSET_CLASSES
    assert "cn_bond_fund" in NON_INDEXABLE_ASSET_CLASSES
    assert "qdii_global" in NON_INDEXABLE_ASSET_CLASSES

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
    state, _reason, evidence, gaps, _ = derive_thesis_from_evidence(None, None, owner_instrument_id="510300")
    assert state == "evidence_insufficient"
    assert evidence == ()
    assert "missing_constituent_snapshot" in gaps
    assert "news_stage_skipped" in gaps
    assert "missing_recent_news" not in gaps


def test_evidence_insufficient_when_snapshot_has_no_filings():
    snap = _snapshot(filings=())
    state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(snap, None, owner_instrument_id="510300")
    assert state == "evidence_insufficient"
    assert "missing_constituent_snapshot" in gaps


def test_evidence_insufficient_when_all_filings_lack_yoy():
    snap = _snapshot(filings=tuple(_filing(f"S{i}", None) for i in range(5)))
    state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(snap, None, owner_instrument_id="510300")
    assert state == "evidence_insufficient"
    assert "missing_constituent_snapshot" in gaps


def test_evidence_insufficient_when_theme_report_failed():
    snap = _snapshot(filings=())
    tr = ThemeReport(theme="x", query="q", locale="zh", report_md="",
                     citations=[], failure_reason="all providers down")
    state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(snap, tr, owner_instrument_id="510300")
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
    state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
    assert state == "intact"
    assert "missing_constituent_snapshot" not in gaps


def test_intact_when_majority_positive_and_buy_broker_consensus():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(7))
    brokers = tuple(_broker(f"S{i}", rating="买入") for i in range(5))
    snap = _snapshot(filings=filings, brokers=brokers)
    state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
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
    state, _reason, _ev, _gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
    assert state == "under_pressure"


def test_under_pressure_when_broker_consensus_negative():
    """Majority positive YoY but broker ratings collapsed → under_pressure."""
    filings = tuple(_filing(f"S{i}", 0.08) for i in range(7))
    brokers = tuple(_broker(f"S{i}", rating="减持") for i in range(5))
    snap = _snapshot(filings=filings, brokers=brokers)
    state, _reason, _ev, _gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
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
    state, _reason, _ev, _gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
    assert state == "falsified"


# ---------------------------------------------------------------------------
# Evidence assembly
# ---------------------------------------------------------------------------

def test_evidence_includes_filing_entries():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(5))
    snap = _snapshot(filings=filings)
    _state, _reason, evidence, _gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
    assert any(e.type == "filing" for e in evidence)
    filing_e = next(e for e in evidence if e.type == "filing")
    assert filing_e.url.startswith("https://example.com/filing/")
    assert filing_e.date == "2026-04-28"


def test_evidence_includes_broker_entries():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(3))
    brokers = (_broker("S0", rating="买入"),)
    snap = _snapshot(filings=filings, brokers=brokers)
    _state, _reason, evidence, _gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
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
    _state, _reason, evidence, _gaps, _ = derive_thesis_from_evidence(snap, tr, owner_instrument_id="510300")
    assert any(e.type == "news" for e in evidence)


def test_evidence_capped_to_keep_card_readable():
    """Cap each evidence kind at a small N so cards don't bloat."""
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(20))
    brokers = tuple(_broker(f"S{i}", rating="买入") for i in range(10))
    snap = _snapshot(filings=filings, brokers=brokers)
    _state, _reason, evidence, _gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
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
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(snap, _theme_report(), owner_instrument_id="510300")
    assert "missing_broker_coverage" in gaps


# ---------------------------------------------------------------------------
# Theme-report-only thesis derivation (Path B)
# ---------------------------------------------------------------------------

def _research_theme_report(n_citations: int, *, failure: str = "") -> ThemeReport:
    # Use trusted-tier URLs (wire service) so adversarial-fix item 002's
    # tier gate (intact requires ≥1 trusted-tier citation) doesn't downgrade
    # the legacy "≥3 citations → intact" path being tested here.
    return ThemeReport(
        theme="gold_drivers",
        query="gold drivers",
        locale="en",
        report_md="# gold drivers\n\nContent body.\n",
        citations=[
            Citation(index=i, title=f"t{i}",
                     url=f"https://www.reuters.com/article/{i}",
                     published_iso="2026-05-01")
            for i in range(n_citations)
        ],
        failure_reason=failure,
    )


def test_theme_report_with_3plus_citations_yields_intact_when_no_snapshot():
    state, reason, evidence, gaps, _ = derive_thesis_from_evidence(None, _research_theme_report(3), owner_instrument_id="510300")
    assert state == "intact"
    assert "研究" in reason or "research" in reason or "citations" in reason
    assert any(e.type == "news" for e in evidence)
    assert "missing_constituent_snapshot" in gaps


def test_theme_report_with_failure_falls_back_to_insufficient():
    state, _, _, gaps, _ = derive_thesis_from_evidence(None, _research_theme_report(5, failure="provider 429"), owner_instrument_id="510300")
    assert state == "evidence_insufficient"


def test_theme_report_with_too_few_citations_falls_back_to_insufficient():
    state, _, _, _, _ = derive_thesis_from_evidence(None, _research_theme_report(1), owner_instrument_id="510300")
    assert state == "evidence_insufficient"


def test_theme_report_with_zero_citations_insufficient():
    state, _, _, _, _ = derive_thesis_from_evidence(None, _research_theme_report(0), owner_instrument_id="510300")
    assert state == "evidence_insufficient"


def test_empty_report_md_with_no_failure_reason_adds_news_search_empty_gap():
    """ThemeReport with empty body but no failure_reason should yield a gap, not be treated as failed."""
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(5))
    snap = _snapshot(filings=filings)
    tr = _theme_report(report_md="")  # empty report, no failure_reason
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(snap, tr, owner_instrument_id="510300")
    assert "news_search_empty" in gaps
    assert "missing_recent_news" not in gaps


# ---------------------------------------------------------------------------
# Refined constituent-gap labels (in addition to legacy missing_constituent_snapshot)
# ---------------------------------------------------------------------------


def test_refined_label_constituent_not_applicable_for_gold():
    """Gold has no equity-style constituents; emit constituent_not_applicable
    alongside the legacy label."""
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="gold",
        owner_instrument_id="510300",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_not_applicable" in gaps


def test_refined_label_constituent_not_applicable_for_bond():
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_bond_fund",
        owner_instrument_id="510300",
    )
    assert "constituent_not_applicable" in gaps


def test_refined_label_constituent_not_applicable_for_active_fund():
    # Item 003: cn_equity_fund is no longer NON_INDEXABLE; it now routes through
    # the active-fund snapshot path. With None snapshot, it gets constituent_missing.
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_equity_fund",
        owner_instrument_id="510300",
    )
    # constituent_not_applicable is gone; constituent_missing is the correct gap
    assert "constituent_missing" in gaps
    assert "constituent_not_applicable" not in gaps


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
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(
        snap, _theme_report(), asset_class="us_etf",
        owner_instrument_id="510300",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_fetch_failed" in gaps


def test_refined_label_constituent_missing_when_snapshot_none_for_indexable_class():
    """ETF whose lookthrough target is not yet registered → constituent_missing."""
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_etf",
        owner_instrument_id="510300",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_missing" in gaps


def test_no_refined_label_when_snapshot_usable():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(5))
    snap = _snapshot(filings=filings)
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(
        snap, _theme_report(), asset_class="cn_etf",
        owner_instrument_id="510300",
    )
    assert "missing_constituent_snapshot" not in gaps
    assert "constituent_not_applicable" not in gaps
    assert "constituent_fetch_failed" not in gaps
    assert "constituent_missing" not in gaps


def test_no_refined_label_when_asset_class_omitted():
    """Backward-compatible: without asset_class, only legacy label appears."""
    _state, _reason, _ev, gaps, _ = derive_thesis_from_evidence(None, _theme_report(), owner_instrument_id="510300")
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_not_applicable" not in gaps
    assert "constituent_fetch_failed" not in gaps
    assert "constituent_missing" not in gaps


# ---------------------------------------------------------------------------
# Typed news-cause codes at emission sites (Task 2, Step 2.1)
# ---------------------------------------------------------------------------

def test_news_stage_skipped_when_theme_report_is_none():
    _, _, _, gaps, _ = derive_thesis_from_evidence(None, None, asset_class="cn_etf", owner_instrument_id="510300")
    assert "news_stage_skipped" in gaps
    assert "missing_recent_news" not in gaps


def test_news_search_empty_when_no_sources():
    r = ThemeReport(theme="t", query="q", locale="en", report_md="", citations=[],
                    failure_reason="no sources to synthesize from")
    _, _, _, gaps, _ = derive_thesis_from_evidence(None, r, asset_class="cn_etf", owner_instrument_id="510300")
    assert "news_search_empty" in gaps
    assert "missing_recent_news" not in gaps


def test_news_llm_failed_on_synth_exception():
    r = ThemeReport(theme="t", query="q", locale="en", report_md="", citations=[],
                    failure_reason="429 rate limit")
    _, _, _, gaps, _ = derive_thesis_from_evidence(None, r, asset_class="cn_etf", owner_instrument_id="510300")
    assert "news_llm_failed" in gaps
    assert "missing_recent_news" not in gaps


# ── F-FIX-4: FundLevelSnapshot QDII sentinel branch — reason must be non-empty ──


def _qdii_sentinel_snapshot(fund_id: str = "513100") -> "FundLevelSnapshot":
    from irc.fundamentals.types import FundLevelSnapshot
    return FundLevelSnapshot(
        fund_id=fund_id,
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        fund_level_failure_reasons=(),
        evidence_gaps=("qdii_information_unavailable",),
    )


def test_qdii_sentinel_fund_level_snapshot_reason_is_non_empty() -> None:
    """When evidence=() and gaps=('qdii_information_unavailable',), the reason
    must be non-empty. The inverted conditional produced '' when gaps was truthy,
    which caused a double-separator in OpportunityRow.opportunity_reason."""
    state, reason, evidence, gaps, _ = derive_thesis_from_evidence(
        _qdii_sentinel_snapshot(), None, owner_instrument_id="513100",
    )
    assert state == "evidence_insufficient"
    assert reason, f"reason must be non-empty for QDII sentinel; got {reason!r}"
    assert evidence == ()
    assert "qdii_information_unavailable" in gaps


def test_no_gaps_fund_level_snapshot_reason_is_fallback() -> None:
    """When evidence=() and gaps=() (no explanation available), the reason
    should be the fallback '基金层级证据未能加载。' (not empty string)."""
    from irc.fundamentals.types import FundLevelSnapshot
    snap = FundLevelSnapshot(
        fund_id="518880",
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        fund_level_failure_reasons=(),
        evidence_gaps=(),  # no specific gap label — plain fallback
    )
    state, reason, evidence, gaps, _ = derive_thesis_from_evidence(
        snap, None, owner_instrument_id="518880",
    )
    assert state == "evidence_insufficient"
    assert reason == "基金层级证据未能加载。"
    assert evidence == ()
    assert gaps == ()

