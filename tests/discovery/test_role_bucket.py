from __future__ import annotations

from irc.discovery.universe import UniverseRow
from irc.discovery.role_bucket import bucket_by_role


def _row(iid: str, asset_class: str, tracked: str | None = None, theme: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class=asset_class, currency="cny",
        tracked_index=tracked, theme=theme, venue_required=(),
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
    rows = tuple(_row(f"VTI{i}", "us_etf", "S&P 500") for i in range(5))
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert out.relaxed_roles == ("core_us_equity",)


def test_bucket_fail_below_marks_sparse_non_empty_role_failed() -> None:
    rows = (_row("VTI", "us_etf", "S&P 500"),)
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert "core_us_equity" in out.failed_roles
    assert "core_us_equity" not in out.relaxed_roles


def test_bucket_fail_below_threshold_marks_failed() -> None:
    rows = ()
    out = bucket_by_role(rows, min_per_role=8, fail_below=5)
    assert "core_us_equity" in out.failed_roles


def _row_named(iid: str, asset_class: str, tracked: str | None = None, name_cn: str = "", theme: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=name_cn or iid, asset_class=asset_class, currency="cny",
        tracked_index=tracked, theme=theme, venue_required=(),
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


# === theme-based bucketing (sector ETFs + sector active funds bucket together) ===


def test_bucket_sector_etf_routes_to_themed_bucket_not_core_cn() -> None:
    """中证军工 ETF starts with 中证 but is sector — must NOT bucket as
    core_cn_equity. Goes to satellite_cn_defense via theme tag."""
    rows = (_row_named("512660", "cn_etf", "中证军工", theme="defense"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["satellite_cn_defense"][0].instrument_id == "512660"
    assert out.buckets["core_cn_equity"] == ()


def test_bucket_sector_active_fund_routes_to_themed_bucket() -> None:
    """中欧医疗健康 (active healthcare fund) buckets with healthcare ETFs."""
    rows = (_row_named("003095", "cn_equity_fund", None, theme="healthcare"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["satellite_cn_healthcare"][0].instrument_id == "003095"
    assert out.buckets["satellite_cn_growth"] == ()


def test_bucket_groups_themed_etf_and_active_fund_in_same_bucket() -> None:
    """Whole point of theme-based bucketing: passive 半导体ETF and active
    诺安成长 (semiconductor-heavy) compete head-to-head in the same role."""
    rows = (
        _row_named("512760", "cn_etf", "中证全指半导体", theme="semiconductor"),
        _row_named("320007", "cn_equity_fund", None, theme="semiconductor"),
    )
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    ids = {r.instrument_id for r in out.buckets["satellite_cn_semiconductor"]}
    assert ids == {"512760", "320007"}


def test_bucket_broad_theme_overrides_unknown_index() -> None:
    """An ETF with theme=broad always counts as core, even if its
    tracked_index isn't in the broad whitelist (e.g. custom indices)."""
    rows = (_row_named("999999", "cn_etf", "中证某个新宽基", theme="broad"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_cn_equity"][0].instrument_id == "999999"


def test_bucket_dividend_factor_routes_to_dividend_satellite() -> None:
    rows = (_row_named("512890", "cn_etf", "中证红利低波", theme="dividend"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["satellite_cn_dividend"][0].instrument_id == "512890"


def test_bucket_themeless_active_fund_falls_to_satellite_cn_growth() -> None:
    """Broad active managers (张坤/谢治宇) without a theme go to growth bucket."""
    rows = (_row_named("005827", "cn_equity_fund", None),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["satellite_cn_growth"][0].instrument_id == "005827"


def test_bucket_csi_prefix_sector_etf_does_not_pollute_core() -> None:
    """Regression: pre-theme refactor, _is_core_cn matched anything starting
    with 中证, so 中证半导体/中证军工/中证医药 polluted core_cn_equity. With
    theme=None and tracked_index NOT in broad whitelist, they should bucket
    nowhere (not as core, not as sector — sector requires explicit theme)."""
    rows = (_row_named("512170", "cn_etf", "中证医疗"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_cn_equity"] == ()
    assert out.buckets["satellite_cn_healthcare"] == ()


def test_bucket_broad_index_in_whitelist_still_buckets_as_core_without_theme() -> None:
    """Backward compat: 沪深300 ETF with no theme still routes to core_cn_equity
    via tracked_index whitelist (existing 28 yaml entries don't have theme yet)."""
    rows = (_row_named("510300", "cn_etf", "沪深300"),)
    out = bucket_by_role(rows, min_per_role=1, fail_below=0)
    assert out.buckets["core_cn_equity"][0].instrument_id == "510300"
