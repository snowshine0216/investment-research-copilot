from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals.scoring.runner import run


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _scoring_payload(scores: list[dict]) -> dict:
    return {"scores": scores}


def _full_factor_breakdown() -> dict:
    return {
        k: {"value": 0.5, "raw_refs": [f"ref_{k}"]}
        for k in ("valuation_cost", "risk", "quality", "macro_fit", "thesis_news")
    }


def test_runner_reads_dated_scoring_json(tmp_path: Path) -> None:
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps(_scoring_payload([
        {
            "instrument_id": "VTI",
            "action": "buy_candidate",
            "composite_score": 80.0,
            "data_completeness": 1.0,
            "factor_breakdown": _full_factor_breakdown(),
        }
    ])), encoding="utf-8")

    rc = run(tmp_path)

    report_path = tmp_path / "outputs" / today / "evals" / "scoring" / "report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    metric_names = {m["name"] for m in report["metrics"]}
    assert "scoring_data_completeness_avg" in metric_names
    assert "buy_candidate_min_completeness" in metric_names
    assert rc == 0


def test_runner_fails_when_buy_candidate_below_threshold(tmp_path: Path) -> None:
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps(_scoring_payload([
        {
            "instrument_id": "VTI",
            "action": "buy_candidate",
            "composite_score": 80.0,
            "data_completeness": 0.0,
            "factor_breakdown": _full_factor_breakdown(),
        }
    ])), encoding="utf-8")

    rc = run(tmp_path)

    assert rc == 2
    report = json.loads((tmp_path / "outputs" / today / "evals" / "scoring" / "report.json").read_text(encoding="utf-8"))
    buy_metric = next(m for m in report["metrics"] if m["name"] == "buy_candidate_min_completeness")
    assert buy_metric["status"] == "FAIL"
