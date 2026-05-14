from __future__ import annotations
import json
from pathlib import Path

import pytest
import yaml


def _seed_minimal_repo(tmp_path: Path) -> None:
    """Create the minimum file layout needed by run_opportunity."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    (tmp_path / "config" / "opportunity").mkdir(parents=True)
    (tmp_path / "outputs" / "2026-05-14").mkdir(parents=True)
    (tmp_path / "data").mkdir()

    # inputs/account.yaml
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

    # inputs/preferences.yaml — minimal viable
    (tmp_path / "inputs" / "preferences.yaml").write_text(
        "risk_band:\n  max_drawdown: [0.05, 0.20]\n  horizon: long_core_medium_rotation\n"
        "universe:\n  cn_funds: true\n  cn_etfs: true\n  hk_etfs: true\n  us_etfs: true\n"
        "asset_class_targets:\n"
        "  cn_etf: {center: 0.5, band: [0.4, 0.6]}\n"
        "  cn_bond_fund: {center: 0.2, band: [0.1, 0.3]}\n"
        "  us_etf: {center: 0.15, band: [0.1, 0.2]}\n"
        "  hk_etf: {center: 0.10, band: [0.05, 0.15]}\n"
        "  gold: {center: 0.05, band: [0.02, 0.1]}\n"
        "currency_tolerance:\n  cny: [0.5, 1.0]\n  usd: [0.0, 0.4]\n  hkd: [0.0, 0.3]\n"
        "constraints:\n  allow_short: false\n  allow_leverage: false\n  exclude_themes: []\n"
        "investment_plan:\n  monthly_new_capital_cny: 5000\n"
        "report_language: zh\n",
        encoding="utf-8",
    )

    # config files — copy from the project's templates directory at runtime; the
    # tested command does not need the full bundle for opportunity-only logic.
    repo = Path(__file__).resolve().parents[2]
    src_tpl = repo / "src" / "irc" / "templates"
    for fname in (
        "config/llm.yaml", "config/scoring.yaml", "config/gold_drivers.yaml",
        "config/discovery.yaml", "config/valuation_buckets.yaml",
        "config/triggers.yaml", "config/overrides.yaml", "config/macro_view.yaml",
        "config/universe/qdii_us.yaml", "config/universe/qdii_hk.yaml",
        "config/universe/cn_funds.yaml", "config/universe/gold.yaml",
    ):
        target = tmp_path / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((src_tpl / fname).read_text(encoding="utf-8"), encoding="utf-8")

    # outputs/2026-05-14/scoring.json — a single instrument
    (tmp_path / "outputs" / "2026-05-14" / "scoring.json").write_text(
        json.dumps({
            "scores": [{
                "instrument_id": "510300",
                "asset_class": "cn_etf",
                "role": "core_cn_equity",
                "composite_score": 75.0,
                "action": "buy_candidate",
                "data_completeness": 0.85,
                "factor_breakdown": {
                    "valuation_cost": {"score": 80, "raw_refs": []},
                    "risk": {"score": 70, "raw_refs": []},
                    "quality": {"score": 75, "raw_refs": []},
                    "macro_fit": {"score": 65, "raw_refs": []},
                    "thesis_news": {"score": 80, "raw_refs": []},
                },
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_opportunity_command_writes_three_outputs(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd._today", lambda: "2026-05-14"
    )
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    out = tmp_path / "outputs" / "2026-05-14"
    assert (out / "opportunity_report.json").exists()
    assert (out / "thesis_cards.yaml").exists()
    assert (out / "discipline_report.md").exists()


def test_opportunity_report_json_has_summary_and_rows(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    payload = json.loads((tmp_path / "outputs" / "2026-05-14" / "opportunity_report.json").read_text())
    assert payload["date"] == "2026-05-14"
    assert "summary" in payload
    assert isinstance(payload["rows"], list)


def test_opportunity_markdown_starts_with_chinese_sections(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    md = (tmp_path / "outputs" / "2026-05-14" / "discipline_report.md").read_text()
    assert "## 今日可定投" in md
    assert "## 关于回撤的说明" in md


def test_opportunity_does_not_read_external_worktree_path(tmp_path: Path, monkeypatch):
    """Acceptance criterion: never read the external worktree generated universe."""
    from irc.commands.opportunity_cmd import run_opportunity
    import irc.commands.opportunity_cmd as opp_mod
    src = Path(opp_mod.__file__).read_text(encoding="utf-8")
    assert "investment-research-copilot.worktrees" not in src


def test_opportunity_works_with_missing_scoring(tmp_path: Path, monkeypatch):
    """Falls back to latest outputs when today's scoring.json missing."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    # Move scoring under an older date
    today_dir = tmp_path / "outputs" / "2026-05-14"
    older_dir = tmp_path / "outputs" / "2026-05-13"
    older_dir.mkdir(parents=True)
    (today_dir / "scoring.json").rename(older_dir / "scoring.json")
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
