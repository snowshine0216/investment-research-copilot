"""Trade-plan runner tests against current YAML contract.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/008-spec.md
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from evals.trade_plan.runner import run


def _valid_trade() -> dict:
    return {
        "target": "VTI", "asset_class": "equity", "role": "core",
        "target_weight": 0.25, "intra_class_share": 0.5, "composite_score": 70.0,
        "buy_method": "limit", "granularity": "default",
        "venue_compatible": True, "venue_note": "direct", "proxy_id": None,
        "triggers": [{"condition": "price < 150"}],
    }


def _seed(repo_root: Path, date_iso: str, *, trades: list[dict] | None) -> Path:
    out = repo_root / "outputs" / date_iso
    out.mkdir(parents=True, exist_ok=True)
    if trades is not None:
        (out / "trade_plan.yaml").write_text(
            yaml.safe_dump({"mode": "weekly", "trades": trades}, sort_keys=False),
            encoding="utf-8",
        )
    return out


def test_trade_plan_runner_fails_when_input_missing(tmp_path: Path) -> None:
    rc = run(tmp_path)
    assert rc == 2
    candidates = list((tmp_path / "outputs").rglob("evals/trade_plan/report.json"))
    assert candidates
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_trade_plan_runner_passes_against_valid_yaml(tmp_path: Path) -> None:
    date_iso = "2026-05-17"
    _seed(tmp_path, date_iso, trades=[_valid_trade(), _valid_trade()])
    rc = run(tmp_path)
    assert rc == 0
    body = json.loads(
        (tmp_path / "outputs" / date_iso / "evals" / "trade_plan" / "report.json")
        .read_text(encoding="utf-8")
    )
    assert {m["name"] for m in body["metrics"]} == {
        "venue_compatibility_marked",
        "buy_method_class_match",
        "trigger_monitorability",
    }
    assert all(m["status"] == "PASS" for m in body["metrics"])


def test_trade_plan_runner_fails_on_unmonitorable_trigger(tmp_path: Path) -> None:
    bad = _valid_trade()
    bad["triggers"] = []
    _seed(tmp_path, "2026-05-17", trades=[_valid_trade(), bad])
    rc = run(tmp_path)
    assert rc == 2  # 0.5 < fail_below 0.9
    body = json.loads(
        (tmp_path / "outputs" / "2026-05-17" / "evals" / "trade_plan" / "report.json")
        .read_text(encoding="utf-8")
    )
    metric = next(m for m in body["metrics"] if m["name"] == "trigger_monitorability")
    assert metric["status"] == "FAIL"


def test_trade_plan_runner_writes_under_artifact_date(tmp_path: Path) -> None:
    date_iso = "2026-05-14"
    _seed(tmp_path, date_iso, trades=[_valid_trade()])
    run(tmp_path)
    assert (tmp_path / "outputs" / date_iso / "evals" / "trade_plan" / "report.json").exists()
