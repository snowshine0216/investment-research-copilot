"""TDD tests for fundamentals types — frozen dataclasses with explicit defaults."""
from __future__ import annotations

import dataclasses

import pytest

from irc.fundamentals.types import (
    BrokerReport,
    Constituent,
    ConstituentSnapshot,
    FilingDigest,
)


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
