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


# ── F6: filing-evidence summary reframe ──────────────────────────────────────

def test_filing_evidence_summary_uses_disclosure_existence_template_legacy() -> None:
    """F6 AC #1 — legacy `_filing_evidence` producer.

    The summary must (a) NOT contain `revenue_yoy=` substring, (b) NOT
    contain `营收同比` substring (the legacy +.1%-formatted phrasing),
    and (c) contain the locked Chinese phrase `财报已披露（口径未核实）`
    with full-width parentheses, prefixed by `{symbol} {fiscal_period}`.
    """
    from irc.opportunity.thesis_evidence import _filing_evidence

    digest = _filing("600519", -0.0771, period="2026Q1")
    out = _filing_evidence((digest,), owner_instrument_id="fund-x")

    assert len(out) == 1
    summary = out[0].summary
    # AC #1 load-bearing assertion: old scalar substring is gone.
    assert "revenue_yoy=" not in summary
    # AC #1 load-bearing assertion: legacy +.1%-formatted phrasing is gone.
    assert "营收同比" not in summary
    # AC #1 load-bearing assertion: new template phrase present, leading
    # with symbol + fiscal_period for stable `summary[:24]` appendix
    # fragment behaviour.
    assert summary == "600519 2026Q1 财报已披露（口径未核实）"


def test_filing_evidence_preserves_structural_role_legacy() -> None:
    """F6 AC #2 + AC #3 — non-summary fields unchanged.

    `_TYPE_RANK` ordering and the filing row's structural role
    (`scope`, `citation_kind`, `type`) MUST be preserved by the
    summary-only reframe. Confirms Policy B rule 3 and the
    dual-coverage gate keep seeing what they expect.
    """
    from irc.opportunity.thesis_evidence import _filing_evidence, _TYPE_RANK

    digest = _filing("000333", 0.18, period="2026Q1")
    out = _filing_evidence((digest,), owner_instrument_id="fund-y")

    assert len(out) == 1
    ev = out[0]
    assert ev.type == "filing"
    assert ev.citation_kind == "data"
    assert ev.scope == "instrument"   # legacy path; active-fund path uses "constituent"
    assert ev.url == digest.source_url
    assert ev.date == digest.filed_at_iso
    # AC #3: filing still ranks first per holding.
    assert _TYPE_RANK["filing"] == 0
    assert _TYPE_RANK["filing"] < _TYPE_RANK["broker"] < _TYPE_RANK["news"]


def test_evidence_for_constituent_cn_uses_disclosure_existence_template(
    monkeypatch,
) -> None:
    """F6 AC #1 — active-fund CN branch.

    `_evidence_for_constituent` is the only producer of
    `citation_kind="data" AND scope="constituent"` in V1. Its filing
    summary MUST converge to the same locked phrase as the legacy
    producer so Policy B rule 3 + the dual-coverage gate read a
    user-safe summary while the structural role is preserved.
    """
    from irc.fundamentals import snapshot as snap_mod
    from irc.fundamentals.types import FundHolding

    digest = _filing("600519", -0.0771, period="2026Q1")

    class _DigestProvider:
        def fetch_filing_digest(self, sym): return digest
        def fetch_broker_reports(self, sym, **_): return ()
        def fetch_index_valuation(self, k): return None

    monkeypatch.setattr(
        snap_mod, "fetch_cn_stock_news", lambda sym, top_k=3: (),
    )
    holding = FundHolding(
        symbol="600519", name_cn="贵州茅台",
        exchange="SH", weight_pct=8.0,
        provider_symbol="600519",
    )
    evidence, _failures, _digest = snap_mod._evidence_for_constituent(
        holding, fund_id="005827", provider=_DigestProvider(),
    )
    filings = [e for e in evidence if e.type == "filing"]
    assert len(filings) == 1
    ev = filings[0]
    assert ev.scope == "constituent"
    assert ev.citation_kind == "data"
    assert "revenue_yoy=" not in ev.summary
    assert ev.summary == "600519 2026Q1 财报已披露（口径未核实）"


def test_evidence_for_constituent_hk_uses_disclosure_existence_template(
    monkeypatch,
) -> None:
    """F6 AC #1 — active-fund HK branch — same template lock."""
    from irc.fundamentals import snapshot as snap_mod
    from irc.fundamentals.types import FundHolding

    digest = _filing("00700", 0.12, period="2026H1")
    monkeypatch.setattr(
        snap_mod, "fetch_hk_filing_digest", lambda sym: digest,
    )
    monkeypatch.setattr(
        snap_mod, "hk_news_adapter_available", lambda: False,
    )
    holding = FundHolding(
        symbol="00700", name_cn="腾讯控股",
        exchange="HK", weight_pct=6.5,
        provider_symbol="00700",
    )
    from irc.fundamentals.provider import AkShareProvider
    evidence, _failures, _digest = snap_mod._evidence_for_constituent(
        holding, fund_id="005827", provider=AkShareProvider(),
    )
    filings = [e for e in evidence if e.type == "filing"]
    assert len(filings) == 1
    ev = filings[0]
    assert ev.scope == "constituent"
    assert ev.citation_kind == "data"
    assert "revenue_yoy=" not in ev.summary
    assert ev.summary == "00700 2026H1 财报已披露（口径未核实）"


# ── Item 002 (todos-critical-fixes 2026-07-03): ActiveFundSnapshot dual-leg gate ──
# Spec: docs/2026-07-03-todos-critical-fixes/items/002-spec.md
# ADR 0003 §8; CONTEXT.md "Dual-leg thesis heuristic".


def _fund_level_leg(kind: str, *, owner: str = "005827"):
    """Fund-level evidence in the exact producer shapes (fundamentals/snapshot.py
    :186-221): NAV data leg (type="snapshot") / announcement information leg
    (type="news"). scope="instrument", owner=fund_id, parent/constituent None."""
    from irc.opportunity.types import ThesisEvidence
    if kind == "data":
        return ThesisEvidence(
            type="snapshot", source=owner, url="",
            date="2026-06-30", summary="NAV=1.2345 @ 2026-06-30",
            scope="instrument", citation_kind="data",
            owner_instrument_id=owner, parent_fund_id=None, constituent_key=None,
        )
    return ThesisEvidence(
        type="news", source="fund_announcement_report_em", url="",
        date="2026-06-30", summary="[RPT1] 2026年第二季度报告",
        scope="instrument", citation_kind="information",
        owner_instrument_id=owner, parent_fund_id=None, constituent_key=None,
    )


def _dual_leg_analysis(evidence, *, failure_reasons=()):
    from irc.opportunity.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=6.2,
        evidence=evidence, failure_reasons=failure_reasons, one_line_view="",
    )


def _dual_leg_snapshot(analyses, fund_level=()):
    from irc.fundamentals.types import ActiveFundSnapshot
    return ActiveFundSnapshot(
        fund_id="005827", source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="",
        constituent_analyses=analyses,
        failure_reasons_by_symbol={},
        fund_level_evidence=fund_level,
    )


def _derive_active(snap):
    return derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )


def test_active_fund_data_only_evidence_is_insufficient() -> None:
    """AC1 + AC6: non-empty flattened, all data-leg, fund_level=() → NOT intact;
    missing-information-leg reason literal."""
    con = _make_evidence("filing", 6.2, "d1")
    snap = _dual_leg_snapshot((_dual_leg_analysis((con,)),))
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "evidence_insufficient"
    assert reason == "主动基金证据缺少信息腿（券商/新闻/公告），长期逻辑暂不背书。"
    assert evidence == (con,)   # AC8: evidence slot byte-identical
    assert gaps == ()           # AC7: gaps slot byte-identical


def test_active_fund_info_only_evidence_is_insufficient() -> None:
    """AC2 + AC6: non-empty flattened, all information-leg → missing data leg."""
    con = _make_evidence("broker", 6.2, "i1")
    snap = _dual_leg_snapshot((_dual_leg_analysis((con,)),))
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "evidence_insufficient"
    assert reason == "主动基金证据缺少数据腿（成分股财报），长期逻辑暂不背书。"
    assert evidence == (con,)
    assert gaps == ()


def test_active_fund_constituent_dual_leg_stays_intact() -> None:
    """AC3 (regression lock, GREEN pre-fix): flattened carries data + information
    → intact with the reason literal byte-identical to today."""
    ev = (_make_evidence("filing", 6.2, "d1"), _make_evidence("broker", 6.2, "i1"))
    snap = _dual_leg_snapshot((_dual_leg_analysis(ev),))
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "intact"
    assert reason == "主动基金 1 个核心持仓的成分股证据已收集。"
    assert gaps == ()


def test_active_fund_fund_level_info_leg_satisfies_gate() -> None:
    """AC4 (kills a constituent-only implementation): data-only constituent
    evidence + fund-level announcement (information) → intact; the returned
    evidence tuple stays flattened-constituent-only (fund_level NOT merged —
    that remains _stamp_fund_level_evidence_from_verdict's job)."""
    con = _make_evidence("filing", 6.2, "d1")
    snap = _dual_leg_snapshot(
        (_dual_leg_analysis((con,)),),
        fund_level=(_fund_level_leg("information"),),
    )
    state, _, evidence, gaps, _ = _derive_active(snap)
    assert state == "intact"
    assert evidence == (con,)
    assert gaps == ()


def test_active_fund_fund_level_data_leg_satisfies_gate() -> None:
    """AC4 mirror: info-only constituent evidence + fund-level NAV (data) → intact."""
    con = _make_evidence("broker", 6.2, "i1")
    snap = _dual_leg_snapshot(
        (_dual_leg_analysis((con,)),),
        fund_level=(_fund_level_leg("data"),),
    )
    state, _, evidence, gaps, _ = _derive_active(snap)
    assert state == "intact"
    assert evidence == (con,)
    assert gaps == ()


def test_active_fund_empty_evidence_stays_insufficient_plain() -> None:
    """AC5(a) (regression lock): empty flattened + fund_level=() → the existing
    empty-reason literal, unchanged."""
    snap = _dual_leg_snapshot(
        (_dual_leg_analysis((), failure_reasons=("filing_fetch_failed:600519",)),),
    )
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "evidence_insufficient"
    assert reason == "主动基金未能收集到任何成分股证据。"
    assert evidence == ()
    assert gaps == ()


def test_active_fund_empty_flattened_with_dual_leg_fund_level_stays_insufficient() -> None:
    """AC5(b) — the naive-implementation killer (grill R1; ADR 0003 §8 property 3).

    Rule-2.5-publishable shape: ALL top-N constituents pure-failure (empty
    evidence, non-empty failure_reasons — reachable per ADR 0003 §7's
    2026-06-04 reconciliation) + fund_level_evidence carrying BOTH legs.
    The empty-flattened guard must short-circuit BEFORE the union leg check;
    a union-first implementation would flip this *published* row
    evidence_insufficient → intact (AC10 invariance would break).
    """
    snap = _dual_leg_snapshot(
        (_dual_leg_analysis((), failure_reasons=("filing_fetch_failed:600519",)),),
        fund_level=(_fund_level_leg("data"), _fund_level_leg("information")),
    )
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "evidence_insufficient"
    assert reason == "主动基金未能收集到任何成分股证据。"
    assert evidence == ()
    assert gaps == ()
