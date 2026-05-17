from __future__ import annotations

import json
from pathlib import Path

import yaml

from irc.commands.opportunity_cmd import run_opportunity


def _seed(tmp_path: Path) -> None:
    """Seed inputs/, config/, and outputs/scoring.json with realistic data."""
    from datetime import datetime, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo_src = Path(__file__).resolve().parents[2]
    tpl = repo_src / "src" / "irc" / "templates"

    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    (tmp_path / "config" / "opportunity").mkdir(parents=True)
    (tmp_path / "outputs" / "2026-05-14").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    # Write a fresh akshare manifest so the freshness gate passes by default.
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=datetime.now(timezone.utc).isoformat(),
        schema_version="v1", record_counts={"prices": 100},
    ))

    # Copy required config templates
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
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: [cmb_fund, cn_brokerage]\n"
        "    holdings:\n"
        "      - asset_class: cn_etf\n"
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
    (tmp_path / "config" / "opportunity" / "theme_thesis.yaml").write_text(
        "themes:\n"
        "  broad: intact\n"
        "  semiconductor: intact\n"
        "  real_estate: falsified\n",
        encoding="utf-8",
    )
    (tmp_path / "outputs" / "2026-05-14" / "scoring.json").write_text(
        json.dumps({"scores": [
            {"instrument_id": "510300", "asset_class": "cn_etf", "role": "core",
             "composite_score": 80, "action": "buy_candidate", "data_completeness": 0.9,
             "factor_breakdown": {}},
            {"instrument_id": "512760", "asset_class": "cn_etf", "role": "satellite",
             "composite_score": 60, "action": "watch", "data_completeness": 0.7,
             "factor_breakdown": {}},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_opportunity_pipeline_produces_three_outputs(tmp_path: Path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    out = tmp_path / "outputs" / "2026-05-14"
    report = json.loads((out / "opportunity_report.json").read_text())
    assert report["date"] == "2026-05-14"
    assert any(r["instrument_id"] == "510300" for r in report["rows"])
    cards = yaml.safe_load((out / "thesis_cards.yaml").read_text())
    assert isinstance(cards.get("cards"), list)
    md = (out / "discipline_report.md").read_text()
    assert "## 关于回撤的说明" in md


def test_opportunity_pipeline_preserves_holdings_even_when_dropped(tmp_path: Path, monkeypatch):
    """A holding must always appear in the output, even if same-theme
    reduction would have dropped it."""
    _seed(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    rows = json.loads(
        (tmp_path / "outputs" / "2026-05-14" / "opportunity_report.json").read_text()
    )["rows"]
    assert any(r["instrument_id"] == "510300" for r in rows)
