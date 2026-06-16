# tests/scripts/test_backfill_nav_history.py
from __future__ import annotations
import json
from pathlib import Path
from scripts.backfill_nav_history import backfill_rows_from_trace, run_backfill


def _trace(funds):
    return {"schema_version": "1", "engine_version": "1", "run_date": "2026-06-16",
            "funds": {fid: {"nav": {"as_of_date": series[-1][0],
                                    "acc_series": [list(p) for p in series]}}
                      for fid, series in funds.items()}}


def test_backfill_rows_from_trace_seeds_all_obs():
    trace = _trace({"a": [("2025-01-01", 1.0), ("2025-01-02", 1.1)]})
    rows = backfill_rows_from_trace(trace, source_run_date="2026-06-16", written_at="w")
    assert {r.fund_id for r in rows} == {"a"}
    assert [r.nav_date for r in rows] == ["2025-01-01", "2025-01-02"]
    assert all(r.source_run_date == "2026-06-16" for r in rows)


def test_run_backfill_returns_1_on_corrupt_trace(tmp_path: Path):
    """A corrupt (non-JSON) eval_trace.json should return 1, not raise."""
    out = tmp_path / "outputs" / "2026-06-16" / "monitor"
    out.mkdir(parents=True)
    (out / "eval_trace.json").write_text("THIS IS NOT JSON {{{", encoding="utf-8")
    rc = run_backfill(tmp_path)
    assert rc == 1


def test_run_backfill_writes_and_is_idempotent_under_dedup(tmp_path: Path):
    out = tmp_path / "outputs" / "2026-06-16" / "monitor"
    out.mkdir(parents=True)
    trace = _trace({"a": [("2025-01-01", 1.0), ("2025-01-02", 1.1)]})
    (out / "eval_trace.json").write_text(json.dumps(trace), encoding="utf-8")
    run_backfill(tmp_path)
    run_backfill(tmp_path)   # second run → reader dedups duplicates
    from irc.monitor.eval.nav_history import parse_nav_history_lines, latest_per_nav_date
    text = (tmp_path / "data" / "monitor" / "nav_history.jsonl").read_text()
    deduped = latest_per_nav_date(parse_nav_history_lines(text))
    assert [r.nav_date for r in deduped] == ["2025-01-01", "2025-01-02"]
