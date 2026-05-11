from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from irc.commands.decision_cmd import run_decision
from irc.commands.init_cmd import run_init


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def test_decision_returns_2_when_required_outputs_missing(tmp_path: Path) -> None:
    run_init(str(tmp_path), force=False)

    assert run_decision(repo_root=str(tmp_path)) == 2


def test_decision_writes_json_and_markdown(tmp_path: Path) -> None:
    run_init(str(tmp_path), force=False)
    out_dir = tmp_path / "outputs" / _today()
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps({
        "scores": [{
            "instrument_id": "050025",
            "asset_class": "us_etf",
            "action": "buy_candidate",
            "conviction": "med",
            "data_completeness": 1.0,
            "missing_data": [],
        }]
    }), encoding="utf-8")
    (out_dir / "proposed_allocation.yaml").write_text(yaml.safe_dump({
        "selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}],
        "diagnostics": {"total_weight": 1.0},
    }), encoding="utf-8")
    (out_dir / "trade_plan.yaml").write_text(yaml.safe_dump({
        "mode": "build",
        "trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}],
    }), encoding="utf-8")
    (out_dir / "memo_traceability.json").write_text(json.dumps({"coverage_ratio": 1.0}), encoding="utf-8")

    assert run_decision(repo_root=str(tmp_path)) == 0

    report_json = out_dir / "decision_report.json"
    report_md = out_dir / "decision_report.md"
    assert report_json.exists()
    assert report_md.exists()
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["rows"][0]["decision_status"] == "actionable_buy"
    assert report_md.read_text(encoding="utf-8").startswith(f"# Decision Report {_today()}")
