from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evals.opportunity.runner import run


def _seed_outputs(tmp_path: Path) -> Path:
    out = tmp_path / "outputs" / "2026-05-14"
    out.mkdir(parents=True)
    (out / "opportunity_report.json").write_text(
        json.dumps({
            "date": "2026-05-14",
            "summary": {"core_dca_count": 1, "small_watch_count": 0,
                        "pause_wait_count": 0, "exclude_count": 0},
            "rows": [{
                "instrument_id": "510300",
                "name_cn": "X",
                "asset_class": "cn_etf",
                "theme": "broad",
                "lookthrough_target": "沪深300",
                "lookthrough_kind": "broad_index",
                "lookthrough_key": "csi300",
                "valuation_state": "reasonable_low",
                "heat_state": "normal",
                "thesis_state": "intact",
                "product_quality_state": "acceptable",
                "opportunity_state": "core_dca",
                "opportunity_reason": "x",
                "evidence_gaps": [],
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (out / "thesis_cards.yaml").write_text(
        yaml.safe_dump({"cards": [{
            "instrument_id": "510300", "name_cn": "X", "asset_class": "cn_etf",
            "theme": "broad", "role": "core", "lookthrough_target": "沪深300",
            "entry_reason": "core",
            "valuation_state": "reasonable_low", "heat_state": "normal",
            "thesis_state": "intact", "product_quality_state": "acceptable",
            "opportunity_state": "core_dca",
            "dca_action": "normal_dca", "risk_action": "none",
            "falsification_triggers": ["a"], "trim_triggers": ["a"],
            "do_not_sell_just_because": ["drawdown_since_entry >= 0.20"],
            "review_cadence": "weekly_light_monthly_full",
            "evidence_gaps": [],
        }]}, allow_unicode=True),
        encoding="utf-8",
    )
    (out / "discipline_report.md").write_text(
        "# Discipline Report — 2026-05-14\n\n"
        "## 今日可定投\n- foo\n\n"
        "## 暂停加仓\n（无）\n\n"
        "## 风险复核\n（无）\n\n"
        "## 调仓复核\n（无）\n\n"
        "## 退出复核\n（无）\n\n"
        "## 关于回撤的说明\n持仓回撤 20% 不构成卖出。\n",
        encoding="utf-8",
    )
    return out


def test_runner_returns_zero_when_no_inputs(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 0
    candidates = list((tmp_path / "outputs").glob("*/evals/opportunity/report.json"))
    assert candidates, "runner must always write a report"


def test_runner_writes_report_with_metrics(tmp_path: Path):
    out = _seed_outputs(tmp_path)
    rc = run(tmp_path)
    assert rc in (0, 1)  # PASS or WARN
    report_path = out / "evals" / "opportunity" / "report.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text())
    metric_names = {m["name"] for m in payload["metrics"]}
    expected = {
        "thesis_card_required_field_completeness",
        "opportunity_evidence_gap_visibility",
        "same_theme_distinct_index_limit",
        "drawdown_not_auto_sell",
        "hot_chase_prevention",
        "valid_action_enums",
        "no_external_worktree_path",
    }
    assert expected.issubset(metric_names)


def test_runner_fails_when_external_worktree_path_referenced(tmp_path: Path, monkeypatch):
    """If the opportunity_cmd.py source ever references the external
    worktree path, the eval must FAIL."""
    out = _seed_outputs(tmp_path)
    # Force the runner to see a polluted source file
    monkeypatch.setattr(
        "evals.opportunity.runner._read_opportunity_cmd_source",
        lambda: "x = 'investment-research-copilot.worktrees/foo'",
    )
    rc = run(tmp_path)
    assert rc == 2
    report = json.loads((out / "evals" / "opportunity" / "report.json").read_text())
    assert report["overall"] == "FAIL"
