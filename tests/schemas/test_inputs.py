from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.inputs import (
    AccountFile,
    PreferencesFile,
    AssetClassTarget,
)


def test_account_file_minimal_valid():
    raw = {
        "accounts": [
            {
                "broker": "cmb",
                "currency": "cny",
                "available_venues": ["cmb_fund", "cmb_gold"],
                "holdings": [
                    {"asset_class": "gold", "form": "paper_gold", "cost_basis_cny": 10000}
                ],
            }
        ]
    }
    cfg = AccountFile.model_validate(raw)
    assert cfg.accounts[0].broker == "cmb"
    assert cfg.accounts[0].holdings[0].cost_basis_cny == 10000


def test_account_file_requires_at_least_one_holding():
    raw = {"accounts": [{"broker": "cmb", "currency": "cny", "available_venues": [], "holdings": []}]}
    with pytest.raises(ValidationError):
        AccountFile.model_validate(raw)


def test_preferences_file_minimal_valid():
    raw = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.20, "band": [0.12, 0.28]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund": {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.25, "band": [0.18, 0.35]},
            "cash": {"center": 0.05, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    }
    cfg = PreferencesFile.model_validate(raw)
    assert cfg.asset_class_targets["gold"].center == 0.20


def test_preferences_exclude_themes_rejects_unknown_theme():
    raw = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.20, "band": [0.12, 0.28]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund": {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.25, "band": [0.18, 0.35]},
            "cash": {"center": 0.05, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {
            "allow_short": False,
            "allow_leverage": False,
            "exclude_themes": ["not_a_theme"],
        },
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    }
    with pytest.raises(ValidationError, match="not_a_theme"):
        PreferencesFile.model_validate(raw)


def test_preferences_centers_must_sum_to_one():
    raw = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.50, "band": [0.40, 0.60]},
            "cn_equity_fund": {"center": 0.50, "band": [0.40, 0.60]},
            "cn_bond_fund": {"center": 0.50, "band": [0.40, 0.60]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "cash": {"center": 0.05, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    }
    with pytest.raises(ValidationError):
        PreferencesFile.model_validate(raw)


def test_asset_class_target_band_must_contain_center():
    with pytest.raises(ValidationError):
        AssetClassTarget(center=0.20, band=[0.30, 0.40])


def test_preferences_fx_hedge_optional_block_parses():
    """E4 (2026-05-20): preferences may carry an optional ``fx_hedge`` block
    declaring the user's FX policy. Absent → policy defaults to None for
    backward compat. Present → must validate the policy literal."""
    raw = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.20, "band": [0.12, 0.28]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund": {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.25, "band": [0.18, 0.35]},
            "cash": {"center": 0.05, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
        "fx_hedge": {"policy": "accept_unhedged", "notes": "starter portfolio"},
    }
    cfg = PreferencesFile.model_validate(raw)
    assert cfg.fx_hedge is not None
    assert cfg.fx_hedge.policy == "accept_unhedged"
    assert cfg.fx_hedge.notes == "starter portfolio"


def test_preferences_fx_hedge_rejects_unknown_policy():
    raw = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.20, "band": [0.12, 0.28]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund": {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.25, "band": [0.18, 0.35]},
            "cash": {"center": 0.05, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
        "fx_hedge": {"policy": "moon_phase"},
    }
    with pytest.raises(ValidationError):
        PreferencesFile.model_validate(raw)


def test_targets_summing_to_1_005_rejected():
    payload = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.605, "band": [0.50, 0.70]},
            "cn_equity_fund": {"center": 0.20, "band": [0.15, 0.30]},
            "cn_bond_fund": {"center": 0.10, "band": [0.05, 0.20]},
            "hk_etf": {"center": 0.05, "band": [0.00, 0.10]},
            "us_etf": {"center": 0.20, "band": [0.10, 0.30]},
            "cash": {"center": 0.0, "band": [0.00, 0.05]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    }  # sum=1.005 — too high
    with pytest.raises(ValidationError):
        PreferencesFile.model_validate(payload)


def test_targets_summing_to_1_00005_accepted():
    payload = {
        "risk_band": {"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"},
        "universe": {"cn_funds": True, "cn_etfs": True, "hk_etfs": True, "us_etfs": True},
        "asset_class_targets": {
            "gold": {"center": 0.20, "band": [0.12, 0.28]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund": {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf": {"center": 0.10, "band": [0.05, 0.15]},
            "us_etf": {"center": 0.25, "band": [0.18, 0.35]},
            "cash": {"center": 0.05005, "band": [0.00, 0.10]},
        },
        "currency_tolerance": {
            "cny": [0.40, 0.65],
            "usd": [0.25, 0.45],
            "hkd": [0.05, 0.20],
        },
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    }  # sum=1.00005 — within 1e-4 tolerance
    PreferencesFile.model_validate(payload)
