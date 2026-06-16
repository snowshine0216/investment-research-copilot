from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
from evals.monitor_forward.runner import run
from evals._shared.missing_input import EVAL_RC_FAIL, EVAL_RC_WARN


def _nav_lines(fund, n, start="2026-01-01", base=1.0, step=0.001):
    d0 = date.fromisoformat(start)
    return [json.dumps({
        "fund_id": fund, "nav_date": (d0 + timedelta(days=i)).isoformat(),
        "nav_acc": base + step * i, "written_at": "w", "source_run_date": "r",
    }) for i in range(n)]


def _ledger_line(run_date, fund, as_of, status="ok", comp=0.2, bias="ADD_BIAS"):
    return json.dumps({
        "run_date": run_date, "fund_id": fund, "written_at": f"{run_date}T09:00:00",
        "raw_status": status, "raw_bias": bias, "raw_composite": comp,
        "nav_acc": 1.0, "as_of_date": as_of,
    })


def test_missing_ledger_is_fail(tmp_path: Path):
    (tmp_path / "data" / "monitor").mkdir(parents=True)
    (tmp_path / "data" / "monitor" / "nav_history.jsonl").write_text("\n", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == EVAL_RC_FAIL


def test_missing_nav_history_is_fail(tmp_path: Path):
    (tmp_path / "data" / "monitor").mkdir(parents=True)
    (tmp_path / "data" / "monitor" / "forward_ledger.jsonl").write_text("\n", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == EVAL_RC_FAIL


def test_thin_ledger_warns_and_writes_report_and_details(tmp_path: Path):
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                          encoding="utf-8")
    run_date = json.loads(_nav_lines("a", 40)[2]).__getitem__("nav_date") \
        if False else (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    (md / "forward_ledger.jsonl").write_text(
        _ledger_line(run_date, "a", run_date) + "\n", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == EVAL_RC_WARN     # thin -> WARN, not FAIL
    # report + details written under outputs/<today>/evals/monitor_forward/
    out_dirs = list((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    assert out_dirs, "report dir not created"
    assert (out_dirs[0] / "report.json").is_file()
    assert (out_dirs[0] / "details.json").is_file()


def test_details_ref_is_repo_relative_no_leading_slash(tmp_path: Path):
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                          encoding="utf-8")
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    (md / "forward_ledger.jsonl").write_text(
        _ledger_line(run_date, "a", run_date) + "\n", encoding="utf-8")
    run(tmp_path)
    out_dir = next((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    report = json.loads((out_dir / "report.json").read_text())
    refs = [m["details_ref"] for m in report["metrics"] if m["details_ref"]]
    assert refs, "no details_ref set"
    for ref in refs:
        assert ref.startswith("outputs/") and not ref.startswith("/")
        assert ref.endswith("evals/monitor_forward/details.json")
