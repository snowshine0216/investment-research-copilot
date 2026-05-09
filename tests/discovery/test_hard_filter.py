from __future__ import annotations

import pandas as pd

from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.overrides import OverridesConfig
from irc.discovery.universe import UniverseRow
from irc.discovery.hard_filter import apply_hard_filter, HardFilterResult


def _row(
    iid: str,
    asset_class: str = "us_etf",
    market: str = "cn_off_exchange",
    theme: str | None = None,
) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market=market,
        name_cn=iid, asset_class=asset_class, currency="cny",
        tracked_index=None, theme=theme, venue_required=(),
    )


def _cfg() -> DiscoveryConfig:
    return DiscoveryConfig.model_validate({
        "hard_filters": {
            "inception_years_min": 3, "cn_fund_aum_cny_min": 5e8,
            "us_etf_aum_usd_min": 1e8,
            "cn_active_expense_ratio_max": 0.015,
            "cn_passive_expense_ratio_max": 0.005,
            "us_etf_expense_ratio_max": 0.003,
            "etf_daily_volume_cny_min": 1e7,
        },
        "quality_filters": {"drawdown_3y_buffer": 1.2, "tracking_error_max": 0.015, "manager_tenure_years_min": 2},
        "role_bucket": {"min_candidates_per_role": 8, "fail_below": 5},
    })


def test_hard_filter_passes_compliant_instrument() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.002, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "us_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert isinstance(out, HardFilterResult)
    assert "X" in {r.instrument_id for r in out.passed}
    assert out.rejected == ()


def test_hard_filter_rejects_low_aum() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 1e8,  # below 5e8
        "expense_ratio": 0.005, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "cn_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert out.rejected[0].instrument_id == "X"
    assert "aum" in out.rejected[0].reasons[0].lower()


def test_hard_filter_rejects_missing_metadata() -> None:
    metadata = pd.DataFrame(columns=["instrument_id", "inception_years", "aum_cny", "expense_ratio", "daily_volume_cny"])
    out = apply_hard_filter(rows=(_row("X", "cn_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert "no metadata" in out.rejected[0].reasons[0].lower()


def test_hard_filter_rejects_short_inception() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 1, "aum_cny": 6e8,  # <3y min
        "expense_ratio": 0.001, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "cn_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert any("inception" in r for r in out.rejected[0].reasons)


def test_hard_filter_rejects_high_expense_ratio_etf() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.010,  # > cn_passive_expense_ratio_max (0.005) for ETF
        "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "cn_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert any("expense_ratio" in r for r in out.rejected[0].reasons)


def test_hard_filter_uses_us_expense_cap_for_us_etf() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.004, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "us_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert any("expense_ratio" in r for r in out.rejected[0].reasons)


def test_hard_filter_uses_us_expense_cap_for_hk_etf() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.004, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "hk_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert any("expense_ratio" in r for r in out.rejected[0].reasons)


def test_hard_filter_uses_active_expense_cap_for_non_etf() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.012,  # below active max (0.015) but above passive max (0.005) → should pass
        "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "cn_equity_fund"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert "X" in {r.instrument_id for r in out.passed}


def test_hard_filter_rejects_low_etf_daily_volume() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.001, "daily_volume_cny": 5e6,  # < 1e7 min
    }])
    out = apply_hard_filter(
        rows=(_row("X", "cn_etf", market="cn_on_exchange"),),
        metadata=metadata, cfg=_cfg(), overrides=OverridesConfig(),
    )
    assert out.passed == ()
    assert any("daily_volume" in r for r in out.rejected[0].reasons)


def test_hard_filter_skips_volume_check_for_off_exchange_feeder() -> None:
    """Off-exchange feeder funds (e.g. 006075) trade at NAV, not on an exchange.
    They have no daily_volume_cny — the filter must not reject them on this."""
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.001, "daily_volume_cny": float("nan"),
    }])
    out = apply_hard_filter(
        rows=(_row("X", "us_etf", market="cn_off_exchange"),),
        metadata=metadata, cfg=_cfg(), overrides=OverridesConfig(),
    )
    assert "X" in {r.instrument_id for r in out.passed}


def test_hard_filter_rejects_us_etf_below_usd_aum_min() -> None:
    # US ETFs are checked against us_etf_aum_usd_min (1e8), not cn_fund_aum_cny_min (5e8)
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 5e7,  # < 1e8 USD min
        "expense_ratio": 0.002, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "us_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert any("aum" in r for r in out.rejected[0].reasons)


def test_hard_filter_uses_cny_aum_min_for_cny_us_etf_proxy() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 1.5e8,
        "expense_ratio": 0.002, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "us_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert out.passed == ()
    assert any("aum" in r for r in out.rejected[0].reasons)


def test_hard_filter_passes_zero_expense_ratio() -> None:
    # expense_ratio=0.0 is falsy — ensure it is NOT treated as missing and rejected
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.0, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(rows=(_row("X", "us_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=OverridesConfig())
    assert "X" in {r.instrument_id for r in out.passed}


def test_hard_filter_rejects_nan_numeric_metadata() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": float("nan"),
        "aum_cny": float("nan"), "expense_ratio": float("nan"),
        "daily_volume_cny": float("nan"),
    }])
    out = apply_hard_filter(
        rows=(_row("X", "cn_etf", market="cn_on_exchange"),),
        metadata=metadata, cfg=_cfg(), overrides=OverridesConfig(),
    )
    reasons = " ".join(out.rejected[0].reasons)
    assert out.passed == ()
    assert "missing inception_years" in reasons
    assert "missing aum_cny" in reasons
    assert "missing expense_ratio" in reasons
    assert "missing daily_volume_cny" in reasons


def test_hard_filter_respects_ban_list() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "X", "inception_years": 5, "aum_cny": 1e9,
        "expense_ratio": 0.001, "daily_volume_cny": 5e8,
    }])
    overrides = OverridesConfig.model_validate({
        "boost_list": [],
        "ban_list": [{"instrument_id": "X", "reason": "user banned"}],
    })
    out = apply_hard_filter(rows=(_row("X", "us_etf"),), metadata=metadata,
                            cfg=_cfg(), overrides=overrides)
    assert out.passed == ()
    assert "ban" in out.rejected[0].reasons[0].lower()
