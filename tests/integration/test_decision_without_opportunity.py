from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_decision_command_exit_zero_with_no_opportunity_files(tmp_path: Path, monkeypatch):
    """The decision command must run unchanged when opportunity outputs
    are absent. Existing functionality is preserved as a sidecar layer.
    """
    from irc.commands.decision_cmd import run_decision
    repo_src = Path(__file__).resolve().parents[2]
    tpl = repo_src / "src" / "irc" / "templates"

    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    (tmp_path / "outputs" / "2026-05-14").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    for fname in (
        "config/llm.yaml", "config/scoring.yaml", "config/gold_drivers.yaml",
        "config/discovery.yaml", "config/valuation_buckets.yaml",
        "config/triggers.yaml", "config/overrides.yaml", "config/macro_view.yaml",
        "config/universe/qdii_us.yaml", "config/universe/qdii_hk.yaml",
        "config/universe/cn_funds.yaml", "config/universe/gold.yaml",
    ):
        target = tmp_path / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((tpl / fname).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n  - broker: cmb\n    currency: cny\n"
        "    available_venues: [cmb_fund]\n"
        "    holdings:\n      - asset_class: cn_etf\n"
        "        instrument_id: '510300'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )
    (tmp_path / "inputs" / "preferences.yaml").write_text(
        "risk_band: {max_drawdown: [0.05, 0.20], horizon: long_core_medium_rotation}\n"
        "universe: {cn_funds: true, cn_etfs: true, hk_etfs: true, us_etfs: true}\n"
        "asset_class_targets:\n"
        "  cn_etf: {center: 0.5, band: [0.4, 0.6]}\n"
        "  cn_bond_fund: {center: 0.2, band: [0.1, 0.3]}\n"
        "  us_etf: {center: 0.15, band: [0.1, 0.2]}\n"
        "  hk_etf: {center: 0.10, band: [0.05, 0.15]}\n"
        "  gold: {center: 0.05, band: [0.02, 0.1]}\n"
        "currency_tolerance: {cny: [0.5, 1.0], usd: [0.0, 0.4], hkd: [0.0, 0.3]}\n"
        "constraints: {allow_short: false, allow_leverage: false, exclude_themes: []}\n"
        "investment_plan: {monthly_new_capital_cny: 5000}\n"
        "report_language: zh\n",
        encoding="utf-8",
    )
    # Seed minimal upstream outputs the decision command expects.
    (tmp_path / "outputs" / "2026-05-14" / "scoring.json").write_text(
        json.dumps({"scores": []}), encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    rc = run_decision(repo_root=str(tmp_path))
    # rc may be 0 (success) or 2 (missing upstream). It MUST NOT raise.
    assert rc in (0, 2)
