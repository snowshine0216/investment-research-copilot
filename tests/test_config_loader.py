from __future__ import annotations
from pathlib import Path
import pytest
import yaml
from irc.config_loader import load_yaml, load_repo_configs, ConfigBundle


def write_yaml(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def _minimal_inputs(tmp: Path) -> None:
    write_yaml(tmp / "inputs/account.yaml", {
        "accounts": [
            {"broker": "cmb", "currency": "cny", "available_venues": ["cmb_gold"],
             "holdings": [{"asset_class": "gold", "form": "paper_gold", "cost_basis_cny": 10000}]}
        ]
    })
    write_yaml(tmp / "inputs/preferences.yaml", {
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
        "currency_tolerance": {"cny": [0.40, 0.65], "usd": [0.25, 0.45], "hkd": [0.05, 0.20]},
        "constraints": {"allow_short": False, "allow_leverage": False, "exclude_themes": []},
        "investment_plan": {"monthly_new_capital_cny": 0},
        "report_language": "zh",
    })


def _minimal_configs(tmp: Path) -> None:
    write_yaml(tmp / "config/llm.yaml", {
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
        },
        "tasks": {
            "memo_synthesis": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
            "memo_audit": {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.6"},
        },
    })
    write_yaml(tmp / "config/scoring.yaml", {
        "factor_weights": {"valuation_cost": 0.10, "risk": 0.25, "quality": 0.20, "macro_fit": 0.25, "thesis_news": 0.20},
        "action_thresholds": {"strong_buy_candidate": 80, "buy_candidate": 60, "watch": 40, "avoid": 20},
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "2026-05-07-v1",
    })
    write_yaml(tmp / "config/gold_drivers.yaml", {
        "drivers": {
            "real_yield_10y_tips": {"weight": 0.25, "direction": "inverse"},
            "dxy": {"weight": 0.15, "direction": "inverse"},
            "inflation_5y5y": {"weight": 0.15, "direction": "positive"},
            "cb_purchases_wgc": {"weight": 0.15, "direction": "positive_slow"},
            "etf_holdings_gld": {"weight": 0.15, "direction": "confirmation_short"},
            "geopolitical_proxy": {"weight": 0.15, "direction": "positive_pulse"},
        },
        "regime_detection": {"vol_window_months": 6, "vol_baseline_window_months": 12, "vol_ratio_range_threshold": 1.5, "adx_range_threshold": 25},
        "band": {"rolling_window_months": 6},
    })
    write_yaml(tmp / "config/discovery.yaml", {
        "hard_filters": {
            "inception_years_min": 3, "cn_fund_aum_cny_min": 500_000_000,
            "us_etf_aum_usd_min": 100_000_000,
            "cn_active_expense_ratio_max": 0.015, "cn_passive_expense_ratio_max": 0.005,
            "us_etf_expense_ratio_max": 0.003, "etf_daily_volume_cny_min": 10_000_000,
        },
        "quality_filters": {"drawdown_3y_buffer": 1.2, "tracking_error_max": 0.015, "manager_tenure_years_min": 2},
        "role_bucket": {"min_candidates_per_role": 8, "fail_below": 5},
    })
    write_yaml(tmp / "config/valuation_buckets.yaml", {
        "buckets": [
            {"max_percentile": 0.30, "buy_method": "lump_sum", "granularity": "1-2 tranches"},
            {"max_percentile": 0.60, "buy_method": "dca_weekly", "granularity": "12-16 weeks"},
            {"max_percentile": 0.80, "buy_method": "dca_weekly_slow", "granularity": "24-26 weeks"},
            {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold", "granularity": "36+ weeks"},
            {"max_percentile": 1.00, "buy_method": "suspend", "granularity": "n/a"},
        ]
    })
    write_yaml(tmp / "config/triggers.yaml", {"triggers": {}})
    write_yaml(tmp / "config/overrides.yaml", {"boost_list": [], "ban_list": []})
    write_yaml(tmp / "config/macro_view.yaml", {"views": [], "active": False})
    for name in ("qdii_us", "qdii_hk", "cn_funds", "gold"):
        write_yaml(tmp / f"config/universe/{name}.yaml", {"instruments": []})


def test_load_yaml_dispatches_on_filename(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    cfg = load_yaml(tmp_repo / "inputs/account.yaml")
    assert cfg.accounts[0].broker == "cmb"


def test_load_repo_configs_returns_bundle(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    _minimal_configs(tmp_repo)
    bundle = load_repo_configs(tmp_repo)
    assert isinstance(bundle, ConfigBundle)
    assert bundle.preferences.asset_class_targets["gold"].center == 0.20
    assert bundle.scoring.weights_version == "2026-05-07-v1"


def test_load_repo_configs_bad_yaml_raises(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    _minimal_configs(tmp_repo)
    # Break preferences (invalid centers sum)
    bad = yaml.safe_load((tmp_repo / "inputs/preferences.yaml").read_text())
    bad["asset_class_targets"]["gold"]["center"] = 0.99
    bad["asset_class_targets"]["gold"]["band"] = [0.95, 1.00]
    (tmp_repo / "inputs/preferences.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="sum"):
        load_repo_configs(tmp_repo)
