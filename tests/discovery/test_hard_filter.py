from __future__ import annotations

import pandas as pd

from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.overrides import OverridesConfig
from irc.discovery.universe import UniverseRow
from irc.discovery.hard_filter import apply_hard_filter, HardFilterResult


def _row(iid: str, asset_class: str = "us_etf") -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class=asset_class, currency="cny",
        tracked_index=None, venue_required=(),
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
        "expense_ratio": 0.005, "daily_volume_cny": 2e7,
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
