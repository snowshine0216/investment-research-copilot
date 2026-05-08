from __future__ import annotations

from irc.discovery.universe import UniverseRow
from irc.discovery.role_bucket import (
    ROLE_RULES,
    RoleBucketResult,
    bucket_by_role,
)


def _row(iid: str, asset_class: str, tracked: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class=asset_class, currency="cny",
        tracked_index=tracked, venue_required=(),
    )


def test_bucket_assigns_us_etf_to_core_us_equity() -> None:
    rows = (_row("VTI", "us_etf", "S&P 500"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert "core_us_equity" in out.buckets
    assert out.buckets["core_us_equity"][0].instrument_id == "VTI"


def test_bucket_assigns_gold_role() -> None:
    rows = (_row("518880", "gold", None),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert "core_gold_hedge" in out.buckets


def test_bucket_relaxed_flag_when_short() -> None:
    rows = (_row("VTI", "us_etf", "S&P 500"),)
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert out.relaxed_roles == ("core_us_equity",)


def test_bucket_fail_below_threshold_marks_failed() -> None:
    rows = ()
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert "core_us_equity" in out.failed_roles


def _row_named(iid: str, asset_class: str, tracked: str | None = None, name_cn: str = "") -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=name_cn or iid, asset_class=asset_class, currency="cny",
        tracked_index=tracked, venue_required=(),
    )


def test_bucket_assigns_cn_etf_to_core_cn_equity() -> None:
    rows = (_row_named("510300", "cn_etf", "沪深300"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_cn_equity"][0].instrument_id == "510300"


def test_bucket_assigns_cn_equity_fund_to_core_cn_equity() -> None:
    rows = (_row_named("110020", "cn_equity_fund", "中证500"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_cn_equity"][0].instrument_id == "110020"


def test_bucket_assigns_nasdaq_etf_to_satellite_us_tech() -> None:
    rows = (_row_named("QQQ", "us_etf", "Nasdaq-100"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["satellite_us_tech"][0].instrument_id == "QQQ"


def test_bucket_assigns_cn_equity_fund_to_satellite_cn_growth() -> None:
    # cn_equity_fund without 沪深/中证 index → satellite_cn_growth (core_cn_equity predicate fails)
    rows = (_row_named("320007", "cn_equity_fund", "中小成长"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    # First match wins: core_cn_equity checks tracked_index.startswith(("沪深","中证"))
    # "中小成长" does NOT start with those prefixes, so predicate is False → falls to satellite_cn_growth
    assert out.buckets["satellite_cn_growth"][0].instrument_id == "320007"


def test_bucket_assigns_cn_bond_fund_to_defensive_cn_bond() -> None:
    rows = (_row_named("519083", "cn_bond_fund"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["defensive_cn_bond"][0].instrument_id == "519083"


def test_bucket_assigns_us_bond_etf_to_defensive_us_bond() -> None:
    # tracked_index must contain 'bond' (case-insensitive) — name_cn is typically Chinese
    rows = (_row_named("BND", "us_etf", "US Bond Index", name_cn="标普综合傀券ETF"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["defensive_us_bond"][0].instrument_id == "BND"


def test_bucket_assigns_hk_dividend_etf_to_hedge_low_correlation() -> None:
    rows = (_row_named("3188.HK", "hk_etf", "Hang Seng Dividend Index"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["hedge_low_correlation"][0].instrument_id == "3188.HK"
