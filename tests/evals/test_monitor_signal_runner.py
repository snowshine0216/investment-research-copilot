from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from evals.monitor_signal.runner import run


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _good_fund(composite=0.3):
    return {
        "resolved": {"analysis_profile": "gold_etf", "weights": {"trend": 1.0},
                     "bands": {"buy": 0.1, "sell": -0.1}, "minimum_confidence": 0.5},
        "nav": {"obs_count": 2},
        "evidence_pool": [{"citation_id": "aaaa000000000000"}],
        "factor_scores": [{"name": "trend", "value": 0.3, "eligible": True,
                           "reason": "", "confidence": 1.0}],
        "signal": {"status": "insufficient_evidence", "bias": None, "composite": composite,
                   "signal_confidence": 1.0, "available_weight": 1.0,
                   "present_families": ["price-momentum"],
                   "contributions": [{"name": "trend", "renorm_weight": 1.0, "value": 0.3,
                                      "contribution": 0.3, "confidence": 1.0}],
                   "divergence_codes": []},
        "impacts": {"macro": [], "constituent": []},
        "narrative": {"status": "ok",
                      "price_action": [{"claim": "x", "citation_ids": ["aaaa000000000000"]}],
                      "signal_rationale": [], "risk": []},
    }


def _write_trace(root: Path, funds: dict, date_str: str | None = None) -> None:
    date_str = date_str or _today()
    d = root / "outputs" / date_str / "monitor"
    d.mkdir(parents=True)
    trace = {"schema_version": "1", "engine_version": "1", "run_date": date_str, "funds": funds}
    (d / "eval_trace.json").write_text(json.dumps(trace), encoding="utf-8")


def test_runner_pass_on_good_trace(tmp_path: Path):
    _write_trace(tmp_path, {"a": _good_fund()})
    rc = run(tmp_path)
    report = json.loads(
        (tmp_path / "outputs" / _today() / "evals" / "monitor_signal" / "report.json")
        .read_text(encoding="utf-8"))
    names = {m["name"] for m in report["metrics"]}
    assert {"oracle_signal_match", "citation_resolution", "nav_completeness"} <= names
    assert rc == 0 and report["overall"] == "PASS"


def test_runner_fail_on_tampered_composite(tmp_path: Path):
    # compute_signal would reproduce a value != 0.99 → oracle_signal_match < 1.0 → FAIL
    _write_trace(tmp_path, {"a": _good_fund(composite=0.99)})
    rc = run(tmp_path)
    assert rc == 2
    report = json.loads(
        (tmp_path / "outputs" / _today() / "evals" / "monitor_signal" / "report.json")
        .read_text(encoding="utf-8"))
    oracle = next(m for m in report["metrics"] if m["name"] == "oracle_signal_match")
    assert oracle["status"] == "FAIL"


def test_runner_fail_when_input_missing(tmp_path: Path):
    (tmp_path / "outputs").mkdir(parents=True)
    rc = run(tmp_path)
    assert rc == 2
    candidates = list(tmp_path.rglob("evals/monitor_signal/report.json"))
    assert candidates
    assert json.loads(candidates[0].read_text(encoding="utf-8"))["overall"] == "FAIL"
