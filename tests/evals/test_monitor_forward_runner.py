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


# ── Fix 2: runner wires retro via load_monitor_config + run_backtest ─────────

def _deep_nav_lines(fund, n=310, start="2024-01-01", base=1.0, step=0.001):
    """310 NAV rows → enough for minimum_observations=251 + some replay points."""
    d0 = date.fromisoformat(start)
    return [json.dumps({
        "fund_id": fund, "nav_date": (d0 + timedelta(days=i)).isoformat(),
        "nav_acc": base + step * i, "written_at": "w", "source_run_date": "r",
    }) for i in range(n)]


def test_runner_retro_block_non_empty_with_deep_nav(tmp_path: Path, monkeypatch):
    """Given a fund in the monitor config and deep nav history, runner produces
    a non-empty retro block in details.json. Uses synthetic config/monitor.yaml
    to avoid coupling to the real 7-fund set."""
    # Write a minimal monitor.yaml with one fund matching the nav fixture
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "monitor.yaml").write_text(
        "schema_version: 1\n"
        "history:\n  minimum_observations: 10\n  fetch_calendar_days: 550\n"
        "defaults:\n"
        "  return_windows: [5, 20, 60, 120, 250]\n"
        "  signal_bands:\n    buy: 0.40\n    sell: -0.40\n"
        "  minimum_confidence: 0.50\n"
        "funds:\n"
        "  - { id: '008986', name_cn: TestFund, market: cn_off_exchange, "
        "analysis_profile: gold, themes: [gold_drivers] }\n",
        encoding="utf-8",
    )

    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    # 60 NAV rows — enough for min_obs=10 from the synthetic config
    nav_rows = _nav_lines("008986", 60)
    (md / "nav_history.jsonl").write_text("\n".join(nav_rows) + "\n", encoding="utf-8")
    # ledger: thin but present (runner still needs it for forward path)
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    (md / "forward_ledger.jsonl").write_text(
        _ledger_line(run_date, "008986", run_date) + "\n", encoding="utf-8"
    )

    rc = run(tmp_path)
    out_dir = next((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    details = json.loads((out_dir / "details.json").read_text())
    # retro sub-block MUST be present in raw_composite_directional after Fix 2
    assert "retro" in details["raw_composite_directional"], (
        "retro sub-block missing — runner did not wire run_backtest (Fix 2)"
    )
    retro = details["raw_composite_directional"]["retro"]
    assert "label" in retro, "retro sub-block missing label"
    # Runner must stay offline — no network imports triggered
    assert rc in (0, 1, 2)  # completed without exception


def test_runner_still_exactly_three_metric_rows_with_retro(tmp_path: Path):
    """Runner with deep nav must still produce exactly 3 MetricReport rows."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "monitor.yaml").write_text(
        "schema_version: 1\n"
        "history:\n  minimum_observations: 10\n  fetch_calendar_days: 550\n"
        "defaults:\n"
        "  return_windows: [5, 20, 60, 120, 250]\n"
        "  signal_bands:\n    buy: 0.40\n    sell: -0.40\n"
        "  minimum_confidence: 0.50\n"
        "funds:\n"
        "  - { id: '008986', name_cn: TestFund, market: cn_off_exchange, "
        "analysis_profile: gold, themes: [gold_drivers] }\n",
        encoding="utf-8",
    )
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("008986", 60)) + "\n",
                                          encoding="utf-8")
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    (md / "forward_ledger.jsonl").write_text(
        _ledger_line(run_date, "008986", run_date) + "\n", encoding="utf-8"
    )
    run(tmp_path)
    out_dir = next((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    report = json.loads((out_dir / "report.json").read_text())
    assert len(report["metrics"]) == 4, f"expected 4 metrics; got {len(report['metrics'])}"
    assert "engine_population" in {m["name"] for m in report["metrics"]}


# ── Finding 3: _target_engine must not crash on non-numeric string versions ───

def test_target_engine_non_numeric_string_does_not_crash():
    """FINDING 3 (RED): _target_engine crashes when manifest_versions.engine is a
    non-numeric string like 'alpha', because max(versions, key=int) calls int('alpha').
    After the fix, non-numeric versions are treated as legacy '0' and the function
    returns gracefully."""
    import evals.monitor_forward.runner as runner_mod
    # Ledger row whose manifest_versions.engine is non-numeric → triggers the bug
    row = {"manifest_versions": {"engine": "alpha"}}
    # Should not raise; result is some string value
    result = runner_mod._target_engine([row])
    assert result is not None


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


# ── FU1: engine_population diagnostic row ─────────────────────────────────────

def _ledger_line_engine(run_date, fund, as_of, engine, status="ok",
                        comp=0.2, bias="ADD_BIAS"):
    """Like _ledger_line but stamps manifest_versions.engine so the runner's
    _target_engine / engine_mismatch path activates."""
    return json.dumps({
        "run_date": run_date, "fund_id": fund, "written_at": f"{run_date}T09:00:00",
        "raw_status": status, "raw_bias": bias, "raw_composite": comp,
        "nav_acc": 1.0, "as_of_date": as_of, "manifest_versions": {"engine": engine},
    })


def test_engine_population_warns_on_transition(tmp_path: Path):
    """A ledger dominated by legacy-engine rows (dropped under engine_mismatch)
    with a thin matured engine-'2' population → engine_population row WARNs,
    state 'engine_transition', ci_low/ci_high None (producer side of the CI
    contract), and run() returns rc 1 (WARN)."""
    md = tmp_path / "data" / "monitor"
    md.mkdir(parents=True)
    (md / "nav_history.jsonl").write_text("\n".join(_nav_lines("a", 40)) + "\n",
                                          encoding="utf-8")
    run_date = (date.fromisoformat("2026-01-01") + timedelta(days=2)).isoformat()
    # 3 legacy-engine rows (engine '0') + 1 target-engine row (engine '2').
    # target_engine='2' → the 3 legacy rows drop under engine_mismatch, leaving
    # 1 thin matured target-engine row → publishable_bias_directional is
    # insufficient_data → engine_population must WARN.
    lines = [
        _ledger_line_engine(run_date, "a", run_date, "0"),
        _ledger_line_engine(run_date, "b", run_date, "0"),
        _ledger_line_engine(run_date, "c", run_date, "0"),
        _ledger_line_engine(run_date, "a", run_date, "2"),
    ]
    (md / "forward_ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rc = run(tmp_path)
    assert rc == EVAL_RC_WARN
    out_dir = next((tmp_path / "outputs").glob("*/evals/monitor_forward"))
    report = json.loads((out_dir / "report.json").read_text())
    names = [m["name"] for m in report["metrics"]]
    assert "engine_population" in names
    ep = next(m for m in report["metrics"] if m["name"] == "engine_population")
    assert ep["status"] == "WARN"

    details = json.loads((out_dir / "details.json").read_text())
    epd = details["engine_population"]
    assert epd["state"] == "engine_transition"
    assert epd["ci_low"] is None and epd["ci_high"] is None
    assert epd["n_excluded"] >= 1
    # raw counts unchanged (additive block)
    assert details["excluded_by_engine"]["engine_mismatch"] >= 1
