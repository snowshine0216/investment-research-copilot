from __future__ import annotations
import json
from pathlib import Path
from datetime import date, timedelta
from irc.commands.monitor_cmd import _predictive_panel_model
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict


def _write_report(root: Path, artifact_date: str, *, bias_value=0.6, random_delta=0.05,
                  bias_state="ok"):
    d = root / "outputs" / artifact_date / "evals" / "monitor_forward"
    d.mkdir(parents=True)
    rel = f"outputs/{artifact_date}/evals/monitor_forward/details.json"
    metrics = [
        MetricReport("raw_composite_directional", 0.55, "WARN", 5, {}, rel),
        MetricReport("publishable_bias_directional", bias_value, "PASS", 9, {}, rel),
        MetricReport("rank_ic", 0.1, "WARN", 3, {}, rel),
    ]
    rep = StageReport("monitor_forward", f"{artifact_date}T09:00:00+08:00",
                      [], metrics, "WARN")
    (d / "report.json").write_text(json.dumps(report_to_dict(rep)), encoding="utf-8")
    details = {
        "publishable_bias_directional": {
            "value": bias_value, "state": bias_state,
            "baseline_deltas": {"random": {"delta": random_delta}},
        },
        "raw_composite_directional": {"value": 0.55, "state": "ok",
                                      "baseline_deltas": {"random": {"delta": 0.0}}},
        "rank_ic": {"value": 0.1, "state": "insufficient_data",
                    "baseline_deltas": {"random": {"state": "insufficient_data"}}},
    }
    (d / "details.json").write_text(json.dumps(details), encoding="utf-8")


def test_no_report_yields_absent_model(tmp_path: Path):
    model = _predictive_panel_model(tmp_path, today="2026-06-16")
    assert model.present is False


def test_fresh_report_populates_metrics(tmp_path: Path):
    _write_report(tmp_path, "2026-06-15")
    model = _predictive_panel_model(tmp_path, today="2026-06-16")
    assert model.present is True and model.stale is False
    assert {m.name for m in model.metrics} == {
        "raw_composite_directional", "publishable_bias_directional", "rank_ic"}


def test_stale_when_artifact_date_old(tmp_path: Path):
    _write_report(tmp_path, "2026-05-01")  # > 10 days before today
    model = _predictive_panel_model(tmp_path, today="2026-06-16")
    assert model.stale is True and model.artifact_date == "2026-05-01"


def test_review_flag_fires_on_four_negative_weeks(tmp_path: Path):
    # four distinct ISO weeks, each headline random delta < 0
    for wk, d in enumerate(["2026-05-28", "2026-06-04", "2026-06-11", "2026-06-18"]):
        _write_report(tmp_path, d, random_delta=-0.05)
    model = _predictive_panel_model(tmp_path, today="2026-06-19")
    assert model.review_flag is True


def test_review_flag_not_fired_when_a_week_is_none(tmp_path: Path):
    _write_report(tmp_path, "2026-05-28", random_delta=-0.05)
    _write_report(tmp_path, "2026-06-04", random_delta=-0.05)
    _write_report(tmp_path, "2026-06-11", bias_state="insufficient_data")  # None week
    _write_report(tmp_path, "2026-06-18", random_delta=-0.05)
    model = _predictive_panel_model(tmp_path, today="2026-06-19")
    assert model.review_flag is False
