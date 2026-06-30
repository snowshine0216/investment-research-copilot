"""Tests for _build_bias_timeline robustness (review findings A, B, C)."""
from __future__ import annotations
import json
import logging
from irc.commands.monitor_cmd import _build_bias_timeline, _read_ledger_rows
from irc.monitor.render_timeline import BiasTimeline


# ---------------------------------------------------------------------------
# Finding A: malformed ledger row (missing fund_id) must NOT crash
# ---------------------------------------------------------------------------

def _write_ledger(tmp_path, rows):
    led = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    return led


def test_build_bias_timeline_malformed_row_no_crash(tmp_path):
    """A ledger with one valid row + one row missing fund_id must not raise
    KeyError; the valid fund must appear in the returned BiasTimeline."""
    rows = [
        # well-formed
        {"run_date": "2026-06-29", "fund_id": "519069", "raw_bias": "ADD_BIAS",
         "written_at": "2026-06-29T09:00:00+08:00", "manifest_versions": {"engine": "3"}},
        # malformed: missing fund_id
        {"run_date": "2026-06-29", "raw_bias": "NEUTRAL",
         "written_at": "2026-06-29T08:00:00+08:00", "manifest_versions": {"engine": "3"}},
    ]
    _write_ledger(tmp_path, rows)
    # must not raise
    tl = _build_bias_timeline(tmp_path)
    assert isinstance(tl, BiasTimeline)
    fund_ids = {fid for fid, _ in tl.rows}
    assert "519069" in fund_ids


def test_build_bias_timeline_missing_run_date_no_crash(tmp_path):
    """A ledger row missing run_date must not crash; other rows still returned."""
    rows = [
        {"run_date": "2026-06-29", "fund_id": "519069", "raw_bias": "ADD_BIAS",
         "written_at": "2026-06-29T09:00:00+08:00"},
        # missing run_date
        {"fund_id": "270023", "raw_bias": "NEUTRAL",
         "written_at": "2026-06-29T09:00:00+08:00"},
    ]
    _write_ledger(tmp_path, rows)
    tl = _build_bias_timeline(tmp_path)
    assert isinstance(tl, BiasTimeline)
    fund_ids = {fid for fid, _ in tl.rows}
    assert "519069" in fund_ids


# ---------------------------------------------------------------------------
# Finding B: absent (fund, date) cells must carry a sentinel, NOT "NEUTRAL"
# ---------------------------------------------------------------------------

def test_build_bias_timeline_absent_cell_sentinel(tmp_path):
    """Fund 270023 only has an entry on 2026-06-30; on 2026-06-29 its cell must
    NOT be the string "NEUTRAL" (it must be a no-data sentinel)."""
    rows = [
        {"run_date": "2026-06-29", "fund_id": "519069", "raw_bias": "ADD_BIAS",
         "written_at": "2026-06-29T09:00:00+08:00", "manifest_versions": {"engine": "3"}},
        {"run_date": "2026-06-30", "fund_id": "519069", "raw_bias": "NEUTRAL",
         "written_at": "2026-06-30T09:00:00+08:00", "manifest_versions": {"engine": "3"}},
        # 270023 only appears on 06-30, not 06-29
        {"run_date": "2026-06-30", "fund_id": "270023", "raw_bias": "ADD_BIAS",
         "written_at": "2026-06-30T09:00:00+08:00", "manifest_versions": {"engine": "3"}},
    ]
    _write_ledger(tmp_path, rows)
    tl = _build_bias_timeline(tmp_path)
    assert "2026-06-29" in tl.run_dates and "2026-06-30" in tl.run_dates
    date_idx = {d: i for i, d in enumerate(tl.run_dates)}
    by_fund = dict(tl.rows)
    # 270023's cell on 06-29 must NOT be "NEUTRAL"
    absent_cell_bias = by_fund["270023"][date_idx["2026-06-29"]][0]
    assert absent_cell_bias != "NEUTRAL", (
        "absent cell must carry a no-data sentinel, not 'NEUTRAL'"
    )


# ---------------------------------------------------------------------------
# Finding C: silent drop of malformed JSON lines must log a warning with count
# ---------------------------------------------------------------------------

def test_read_ledger_rows_logs_warning_on_malformed(tmp_path, caplog):
    """A ledger file with some malformed lines must log a warning containing
    the dropped count and still return the valid rows."""
    led = tmp_path / "forward_ledger.jsonl"
    led.write_text(
        '{"run_date": "2026-06-29", "fund_id": "519069"}\n'
        'NOT VALID JSON\n'
        '{"run_date": "2026-06-30", "fund_id": "519069"}\n'
        '{{broken}}\n',
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="irc.commands.monitor_cmd"):
        rows = _read_ledger_rows(led)
    assert len(rows) == 2
    assert any("2" in m and "malformed" in m.lower() for m in caplog.messages), (
        f"expected warning about 2 malformed lines; got: {caplog.messages}"
    )
