"""TDD tests for fundamentals types — frozen dataclasses with explicit defaults."""
from __future__ import annotations

import dataclasses

import pytest

from irc.fundamentals.types import (
    BrokerReport,
    Constituent,
    ConstituentSnapshot,
    FilingDigest,
    FundAnnouncement,
    FundLevelSnapshot,
    FundNavReport,
    ThesisEvidence,
)


# ── Item 003 new dataclass tests ──────────────────────────────────────────────

def test_news_item_construction() -> None:
    from irc.fundamentals.types import NewsItem
    n = NewsItem(
        symbol="600519",
        title="贵州茅台 24Q1 营收高于预期",
        url="https://example.com/news/1",
        published_iso="2024-04-15",
        summary="",
        source="stock_news_em",
    )
    assert n.symbol == "600519"
    assert n.source == "stock_news_em"


def test_fund_holding_percent_units() -> None:
    from irc.fundamentals.types import FundHolding
    h = FundHolding(
        symbol="600519",
        name_cn="贵州茅台",
        weight_pct=3.46,
        exchange="SH",
        provider_symbol="600519",
    )
    assert h.weight_pct == 3.46
    assert h.exchange == "SH"


def test_holdings_result_carries_quarter_metadata() -> None:
    from irc.fundamentals.types import HoldingsResult
    res = HoldingsResult(
        constituents=(),
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
    )
    assert res.source_report_quarter == "2024Q1"


def test_active_fund_snapshot_defaults() -> None:
    from irc.fundamentals.types import ActiveFundSnapshot
    snap = ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
    )
    assert snap.fund_level_failure_reasons == ()


def test_constituent_construction_and_immutability() -> None:
    c = Constituent(symbol="600519.SH", name="贵州茅台", weight=0.07, market="cn")
    assert c.symbol == "600519.SH"
    assert c.weight == pytest.approx(0.07)
    assert c.market == "cn"
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.weight = 0.10  # type: ignore[misc]


def test_filing_digest_defaults_and_optional_numerics() -> None:
    f = FilingDigest(
        symbol="AAPL",
        fiscal_period="2026Q1",
        filed_at_iso="2026-04-30",
        revenue_yoy=0.07,
        net_income_yoy=0.04,
        gross_margin=0.46,
    )
    assert f.guidance_text == ""
    assert f.source_url == ""
    nulled = FilingDigest(
        symbol="600519.SH",
        fiscal_period="2025FY",
        filed_at_iso="2026-04-20",
        revenue_yoy=None,
        net_income_yoy=None,
        gross_margin=None,
    )
    assert nulled.revenue_yoy is None
    assert nulled.net_income_yoy is None


def test_filing_digest_roe_defaults_none_and_is_settable() -> None:
    # roe defaults to None (existing call sites/cache files unaffected).
    default = FilingDigest(
        symbol="600519.SH",
        fiscal_period="2026Q1",
        filed_at_iso="2026-04-30",
        revenue_yoy=0.06,
        net_income_yoy=0.04,
        gross_margin=0.69,
    )
    assert default.roe is None
    # roe is the LAST positional field (after source_url) — preserves the one
    # fully-positional construction in test_snapshot_acceptance.py:69.
    positional = FilingDigest(
        "600519.SH", "2026Q1", "2026-04-30", 0.06, 0.04, 0.69, "", "https://x", 0.18,
    )
    assert positional.roe == 0.18


def test_broker_report_target_price_optional() -> None:
    r = BrokerReport(
        symbol="600519.SH",
        broker="中信证券",
        rating="买入",
        target_price=None,
        published_iso="2026-05-08",
        title="维持买入评级",
    )
    assert r.target_price is None
    assert r.source_url == ""


def test_constituent_snapshot_groups_evidence_per_lookthrough_target() -> None:
    constituents = (
        Constituent(symbol="600519.SH", name="贵州茅台", weight=0.07, market="cn"),
        Constituent(symbol="000858.SZ", name="五粮液", weight=0.04, market="cn"),
    )
    filings = (
        FilingDigest(
            symbol="600519.SH",
            fiscal_period="2026Q1",
            filed_at_iso="2026-04-29",
            revenue_yoy=0.18,
            net_income_yoy=0.16,
            gross_margin=0.92,
        ),
    )
    reports = (
        BrokerReport(
            symbol="600519.SH",
            broker="中金公司",
            rating="买入",
            target_price=2000.0,
            published_iso="2026-05-01",
            title="一季报点评",
        ),
    )
    snap = ConstituentSnapshot(
        lookthrough_target="白酒指数",
        as_of_iso="2026-05-15",
        constituents=constituents,
        filings=filings,
        broker_reports=reports,
    )
    assert snap.failure_reasons == ()
    assert snap.constituents[0].name == "贵州茅台"
    assert snap.filings[0].symbol == "600519.SH"
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.as_of_iso = "2026-06-01"  # type: ignore[misc]


def test_constituent_snapshot_records_per_source_failures() -> None:
    snap = ConstituentSnapshot(
        lookthrough_target="半导体指数",
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=("edgar 503", "akshare timeout"),
    )
    assert snap.failure_reasons == ("edgar 503", "akshare timeout")


# ── Task 1: FundNavReport tests ───────────────────────────────────────────────


def test_fund_nav_report_construction_happy() -> None:
    r = FundNavReport(
        fund_id="518880",
        fund_name="华安黄金易ETF",
        latest_nav=4.5678,
        latest_nav_date="2026-03-15",
        nav_history=(("2026-03-14", 4.5500), ("2026-03-15", 4.5678)),
        source_report_quarter="2026Q1",
    )
    assert r.fund_id == "518880"
    assert r.latest_nav == 4.5678
    assert r.source_report_quarter == "2026Q1"


def test_fund_nav_report_rejects_empty_fund_id() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 1.0),),
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_non_positive_nav() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=0.0,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 0.0),),
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_malformed_date() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026/03/15",  # wrong separator
            nav_history=(("2026/03/15", 1.0),),
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_empty_history() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026-03-15",
            nav_history=(),
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_history_mismatch_with_latest() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-14", 0.99),),  # last date != latest_nav_date
            source_report_quarter="2026Q1",
        )


def test_fund_nav_report_rejects_malformed_quarter() -> None:
    with pytest.raises(ValueError):
        FundNavReport(
            fund_id="518880",
            fund_name="X",
            latest_nav=1.0,
            latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 1.0),),
            source_report_quarter="2026-Q1",  # extra hyphen
        )


# ── Task 2: FundAnnouncement tests ────────────────────────────────────────────


def test_fund_announcement_construction_happy() -> None:
    a = FundAnnouncement(
        fund_id="518880",
        title="关于华安易富黄金交易型开放式证券投资基金基金份额折算日的公告",
        topic="dividend",
        date="2013-07-24",
        report_id="AN201307240003689710",
    )
    assert a.fund_id == "518880"
    assert a.topic == "dividend"
    assert a.report_id.startswith("AN")


def test_fund_announcement_rejects_empty_fund_id() -> None:
    with pytest.raises(ValueError):
        FundAnnouncement(
            fund_id="", title="x", topic="dividend",
            date="2024-01-01", report_id="AN1",
        )


def test_fund_announcement_rejects_empty_title() -> None:
    with pytest.raises(ValueError):
        FundAnnouncement(
            fund_id="518880", title="", topic="dividend",
            date="2024-01-01", report_id="AN1",
        )


def test_fund_announcement_rejects_empty_report_id() -> None:
    with pytest.raises(ValueError):
        FundAnnouncement(
            fund_id="518880", title="x", topic="dividend",
            date="2024-01-01", report_id="",
        )


def test_fund_announcement_rejects_malformed_date() -> None:
    with pytest.raises(ValueError):
        FundAnnouncement(
            fund_id="518880", title="x", topic="dividend",
            date="20240101", report_id="AN1",  # missing hyphens
        )


# ── Task 3: FundLevelSnapshot tests ──────────────────────────────────────────


def test_fund_level_snapshot_construction_minimal() -> None:
    snap = FundLevelSnapshot(
        fund_id="518880",
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
    )
    assert snap.fund_id == "518880"
    assert snap.fund_level_failure_reasons == ()
    assert snap.evidence_gaps == ()


def test_fund_level_snapshot_qdii_sentinel_shape() -> None:
    snap = FundLevelSnapshot(
        fund_id="qdii_us:sp500",
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        evidence_gaps=("qdii_information_unavailable",),
    )
    assert snap.evidence_gaps == ("qdii_information_unavailable",)
    assert snap.nav_report is None


def test_fund_level_snapshot_carries_evidence_tuple() -> None:
    e = ThesisEvidence(
        type="snapshot", source="518880", url="",
        date="2026-03-15",
        summary="NAV=4.5678 @ 2026-03-15",
        scope="instrument", citation_kind="data",
        owner_instrument_id="518880",
        parent_fund_id=None, constituent_key=None,
    )
    snap = FundLevelSnapshot(
        fund_id="518880",
        nav_report=None,
        announcements=(),
        evidence=(e,),
        source_report_quarter="2026Q1",
        cache_probed_at="2026-05-23",
    )
    assert len(snap.evidence) == 1
    assert snap.evidence[0].citation_kind == "data"


def test_fund_level_snapshot_rejects_empty_fund_id() -> None:
    with pytest.raises(ValueError):
        FundLevelSnapshot(
            fund_id="",
            nav_report=None,
            announcements=(),
            evidence=(),
            source_report_quarter="",
            cache_probed_at="",
        )


def test_fund_level_snapshot_in_all() -> None:
    from irc.fundamentals import types as _t
    assert "FundLevelSnapshot" in _t.__all__
    assert "FundNavReport" in _t.__all__
    assert "FundAnnouncement" in _t.__all__


def test_constituent_analysis_audit_errors_default_empty() -> None:
    from irc.fundamentals.types import ConstituentAnalysis
    c = ConstituentAnalysis(
        symbol="600519",
        name_cn="贵州茅台",
        weight_pct=6.2,
        evidence=(),
        failure_reasons=(),
        one_line_view="证据获取失败",
    )
    assert c.audit_errors == ()


def test_constituent_analysis_audit_errors_explicit() -> None:
    from irc.fundamentals.types import ConstituentAnalysis
    c = ConstituentAnalysis(
        symbol="600519",
        name_cn="贵州茅台",
        weight_pct=6.2,
        evidence=(),
        failure_reasons=(),
        one_line_view="",
        audit_errors=("missing_constituent_record:600519",),
    )
    assert c.audit_errors == ("missing_constituent_record:600519",)


def test_constituent_analysis_audit_errors_field_position_at_end() -> None:
    """Field MUST be at the END of the dataclass — required for positional
    compat with item 003's existing call sites and cache JSON deserialisers."""
    from dataclasses import fields
    from irc.fundamentals.types import ConstituentAnalysis
    field_names = [f.name for f in fields(ConstituentAnalysis)]
    assert field_names[-1] == "audit_errors"


# ── Item 007 OQ1 — ThesisEvidence.from_dict classmethod ─────────────────────


def test_thesis_evidence_from_dict_happy_path() -> None:
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "filing",
        "source": "akshare:filing:600519",
        "url": "https://example.com/600519/2024q1",
        "date": "2024-04-15",
        "summary": "600519 24Q1 财报",
        "scope": "constituent",
        "citation_kind": "data",
        "owner_instrument_id": "005827",
        "parent_fund_id": "005827",
        "constituent_key": "600519",
    }
    ev = ThesisEvidence.from_dict(d)
    assert ev.type == "filing"
    assert ev.owner_instrument_id == "005827"
    assert ev.constituent_key == "600519"
    assert len(ev.citation_id) == 16
    assert all(c in "0123456789abcdef" for c in ev.citation_id)


def test_thesis_evidence_from_dict_missing_optional_fields() -> None:
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "snapshot",
        "source": "akshare:nav:518880",
        "url": "",
        "date": "2026-03-15",
        "summary": "518880 NAV snapshot",
        "scope": "instrument",
        "citation_kind": "data",
        "owner_instrument_id": "518880",
    }
    ev = ThesisEvidence.from_dict(d)
    assert ev.parent_fund_id is None
    assert ev.constituent_key is None
    assert ev.holding_weight_pct is None
    assert ev.url == ""


def test_thesis_evidence_from_dict_holding_weight_carried() -> None:
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "filing",
        "source": "akshare:filing:600519",
        "url": "https://example.com/600519",
        "date": "2024-04-15",
        "summary": "600519",
        "scope": "constituent",
        "citation_kind": "data",
        "owner_instrument_id": "005827",
        "parent_fund_id": "005827",
        "constituent_key": "600519",
        "holding_weight_pct": 8.2,
    }
    ev = ThesisEvidence.from_dict(d)
    assert ev.holding_weight_pct == 8.2


def test_thesis_evidence_from_dict_citation_id_mismatch_raises() -> None:
    """If the JSON carries a citation_id that doesn't match __post_init__'s
    recomputed value, raise (catches tampering of opportunity_report.json)."""
    import pytest
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "filing",
        "source": "akshare:filing:600519",
        "url": "https://example.com/600519",
        "date": "2024-04-15",
        "summary": "600519",
        "scope": "constituent",
        "citation_kind": "data",
        "owner_instrument_id": "005827",
        "parent_fund_id": "005827",
        "constituent_key": "600519",
        "citation_id": "ffffffffffffffff",  # bogus
    }
    with pytest.raises(ValueError, match="citation_id mismatch"):
        ThesisEvidence.from_dict(d)


def test_thesis_evidence_from_dict_empty_string_citation_id_raises() -> None:
    """Regression — pre-merge silent-failure review surfaced that the
    `if expected_id` guard would silently skip the mismatch check for an
    explicit `citation_id == ""` (truthiness, not `is not None`). An older
    pipeline version that wrote `citation_id=""` would bypass the integrity
    check and silently reconstruct with the recomputed id. Lock the
    `is not None` contract so explicit-empty raises loudly."""
    import pytest
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "filing",
        "source": "akshare:filing:600519",
        "url": "https://example.com/600519",
        "date": "2024-04-15",
        "summary": "600519",
        "scope": "constituent",
        "citation_kind": "data",
        "owner_instrument_id": "005827",
        "parent_fund_id": "005827",
        "constituent_key": "600519",
        "citation_id": "",  # explicit empty — must raise on the mismatch
    }
    with pytest.raises(ValueError, match="citation_id mismatch"):
        ThesisEvidence.from_dict(d)


def test_thesis_evidence_from_dict_no_citation_id_key_does_not_raise() -> None:
    """Complement to the above — when the JSON key is absent entirely,
    `expected_id` is None and the mismatch check is intentionally skipped
    (the dataclass simply rebuilds, recomputes citation_id, and returns)."""
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "filing",
        "source": "akshare:filing:600519",
        "url": "https://example.com/600519",
        "date": "2024-04-15",
        "summary": "600519",
        "scope": "constituent",
        "citation_kind": "data",
        "owner_instrument_id": "005827",
        "parent_fund_id": "005827",
        "constituent_key": "600519",
        # no "citation_id" key
    }
    ev = ThesisEvidence.from_dict(d)
    assert len(ev.citation_id) == 16
