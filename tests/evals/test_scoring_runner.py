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


def _stable_corpus(action: str, completeness: float, composite: float = 80.0) -> list[dict]:
    """Four near-identical scores so the runner's 2-vs-2 split makes
    score_distribution_stability measurable (>=2 obs/half) — avoids the
    too-small-corpus WARN so PASS-path tests assert what they intend."""
    return [
        {
            "instrument_id": f"INST{i}",
            "action": action,
            "composite_score": composite,
            "data_completeness": completeness,
            "factor_breakdown": _full_factor_breakdown(),
        }
        for i in range(4)
    ]


def test_runner_reads_dated_scoring_json(tmp_path: Path) -> None:
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(
        json.dumps(_scoring_payload(_stable_corpus("buy_candidate", 1.0))), encoding="utf-8")

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


def test_runner_warns_when_data_completeness_avg_in_warn_band(tmp_path: Path) -> None:
    """rc=1 when any metric is WARN and none are FAIL."""
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    # data_completeness_avg = 0.85 is below warn_below=0.90 but above fail_below=0.75 → WARN
    (out_dir / "scoring.json").write_text(json.dumps(_scoring_payload([
        {
            "instrument_id": "VTI",
            "action": "watch",
            "composite_score": 60.0,
            "data_completeness": 0.85,
            "factor_breakdown": _full_factor_breakdown(),
        }
    ])), encoding="utf-8")

    rc = run(tmp_path)

    assert rc == 1
    report = json.loads((tmp_path / "outputs" / today / "evals" / "scoring" / "report.json").read_text(encoding="utf-8"))
    data_metric = next(m for m in report["metrics"] if m["name"] == "scoring_data_completeness_avg")
    assert data_metric["status"] == "WARN"


def test_runner_warns_on_too_small_corpus_for_stability(tmp_path: Path) -> None:
    """A 1-item corpus splits into ([], [x]); distribution stability can't be
    assessed with <2 observations per half, so the metric must WARN (not report
    a false 0.0 PASS) and the run must surface rc=1."""
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps(_scoring_payload([
        {
            "instrument_id": "VTI",
            "action": "watch",
            "composite_score": 80.0,
            "data_completeness": 1.0,
            "factor_breakdown": _full_factor_breakdown(),
        }
    ])), encoding="utf-8")

    rc = run(tmp_path)

    report = json.loads((tmp_path / "outputs" / today / "evals" / "scoring" / "report.json").read_text(encoding="utf-8"))
    stability = next(m for m in report["metrics"] if m["name"] == "score_distribution_stability")
    assert stability["status"] == "WARN"
    assert rc == 1


def test_runner_returns_pass_when_no_scoring_json(tmp_path: Path) -> None:
    """If no scoring.json file exists anywhere in outputs/, runner returns rc=2 (FAIL)."""
    (tmp_path / "outputs").mkdir(parents=True)
    rc = run(tmp_path)
    assert rc == 2  # missing input is now FAIL, not PASS


def test_runner_falls_back_to_latest_scoring_json_when_today_absent(tmp_path: Path) -> None:
    """When today's file is absent, runner picks the latest available file."""
    past_dir = tmp_path / "outputs" / "2026-05-01"
    past_dir.mkdir(parents=True)
    (past_dir / "scoring.json").write_text(
        json.dumps(_scoring_payload(_stable_corpus("buy_candidate", 1.0, composite=75.0))),
        encoding="utf-8")

    rc = run(tmp_path)
    assert rc == 0


def test_runner_parses_raw_list_scoring_json(tmp_path: Path) -> None:
    """_parse_scores handles a scoring.json that is a bare list (not wrapped in dict)."""
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    raw_list = _stable_corpus("buy_candidate", 1.0, composite=70.0)
    (out_dir / "scoring.json").write_text(json.dumps(raw_list), encoding="utf-8")

    rc = run(tmp_path)
    assert rc == 0


def test_scoring_runner_fails_when_input_missing(tmp_path: Path) -> None:
    rc = run(tmp_path)
    assert rc == 2
    candidates = list(tmp_path.rglob("evals/scoring/report.json"))
    assert candidates, "runner must write a FAIL report"
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
