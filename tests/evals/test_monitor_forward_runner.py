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


# ── Fix 4: malformed ledger / scorer-invariant handling ──────────────────────

def test_malformed_ledger_line_skipped_valid_runs(tmp_path: Path):
    """A ledger with one bad line among valid lines: bad line skipped, run continues."""
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                         encoding="utf-8")
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    good_line = _ledger_line(run_date, "a", run_date)
    bad_line = "NOT_VALID_JSON{{{"
    (md / "forward_ledger.jsonl").write_text(
        bad_line + "\n" + good_line + "\n", encoding="utf-8")
    # should not raise; bad line skipped, valid line processed
    rc = run(tmp_path)
    # rc can be WARN or PASS (thin data) but NOT an exception
    assert rc in (EVAL_RC_WARN, 0), f"unexpected rc={rc}"


def test_all_malformed_ledger_lines_returns_fail(tmp_path: Path):
    """All lines malformed: runner writes FAIL report and returns rc 2."""
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                         encoding="utf-8")
    (md / "forward_ledger.jsonl").write_text(
        "BAD_JSON_LINE_1\nBAD_JSON_LINE_2\n", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == EVAL_RC_FAIL


def test_scorer_invariant_error_returns_fail(tmp_path: Path, monkeypatch):
    """A ValueError from score_forward is caught → rc 2 FAIL, no traceback."""
    import evals.monitor_forward.runner as runner_mod
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                         encoding="utf-8")
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    (md / "forward_ledger.jsonl").write_text(
        _ledger_line(run_date, "a", run_date) + "\n", encoding="utf-8")

    def _raise(*_a, **_kw):
        raise ValueError("scorer invariant violated")
    monkeypatch.setattr(runner_mod, "score_forward", _raise)
    rc = run(tmp_path)
    assert rc == EVAL_RC_FAIL


# ── Fix 6: forward_excluded surfaced in details.json ─────────────────────────

def test_details_json_carries_forward_excluded(tmp_path: Path):
    """A null_signal_nav row (nav_acc=None) should be excluded by prefilter;
    the exclusion count must appear in details.json under forward_excluded."""
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                         encoding="utf-8")
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    # Good line (fund a) + line with nav_acc=null (fund b → null_signal_nav exclusion)
    good_line = _ledger_line(run_date, "a", run_date)
    null_nav_line = json.dumps({
        "run_date": run_date, "fund_id": "b", "written_at": f"{run_date}T09:00:00",
        "raw_status": "ok", "raw_bias": "ADD_BIAS", "raw_composite": 0.2,
        "nav_acc": None, "as_of_date": run_date,
    })
    (md / "forward_ledger.jsonl").write_text(
        good_line + "\n" + null_nav_line + "\n", encoding="utf-8")
    run(tmp_path)
    out_dir = next((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    details = json.loads((out_dir / "details.json").read_text())
    assert "forward_excluded" in details, "forward_excluded key missing from details.json"
    assert details["forward_excluded"].get("null_signal_nav", 0) >= 1


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
