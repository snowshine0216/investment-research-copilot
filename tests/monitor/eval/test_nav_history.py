from __future__ import annotations
import json
import logging
from pathlib import Path
from irc.monitor.eval.nav_history import (
    NavHistoryRow, parse_nav_history_lines, latest_per_nav_date,
    nav_history_append_rows, append_nav_history,
)


def _row(fund_id, nav_date, nav_acc, written_at, source_run_date):
    return {"fund_id": fund_id, "nav_date": nav_date, "nav_acc": nav_acc,
            "written_at": written_at, "source_run_date": source_run_date}


def test_parse_skips_truncated_final_line(caplog):
    text = (
        json.dumps(_row("a", "2026-01-01", 1.0, "2026-01-01T09:00:00", "2026-01-01")) + "\n"
        + '{"fund_id": "a", "nav_date": "2026-01-02", "nav_acc": 1.1,'  # truncated, no newline
    )
    with caplog.at_level(logging.WARNING):
        rows = parse_nav_history_lines(text)
    assert len(rows) == 1
    assert rows[0].nav_date == "2026-01-01"


def test_dedup_keeps_max_written_at_and_sorts_ascending():
    rows = [
        NavHistoryRow("a", "2026-01-02", 1.2, "2026-01-02T09:00:00", "2026-01-02"),
        NavHistoryRow("a", "2026-01-01", 1.0, "2026-01-01T09:00:00", "2026-01-01"),
        NavHistoryRow("a", "2026-01-01", 1.05, "2026-01-03T09:00:00", "2026-01-03"),  # newer written_at
    ]
    out = latest_per_nav_date(rows)
    assert [r.nav_date for r in out] == ["2026-01-01", "2026-01-02"]
    assert out[0].nav_acc == 1.05  # max written_at wins


def test_written_at_tie_breaks_by_source_run_date_descending():
    rows = [
        NavHistoryRow("a", "2026-01-01", 1.0, "2026-01-01T09:00:00", "2026-01-01"),
        NavHistoryRow("a", "2026-01-01", 1.5, "2026-01-01T09:00:00", "2026-01-05"),  # later source_run_date
    ]
    out = latest_per_nav_date(rows)
    assert len(out) == 1 and out[0].nav_acc == 1.5


def test_fully_degenerate_tie_last_line_wins():
    # identical fund_id/nav_date/written_at/source_run_date, differing nav_acc → later line wins
    rows = [
        NavHistoryRow("a", "2026-01-01", 1.0, "t", "2026-01-01"),
        NavHistoryRow("a", "2026-01-01", 2.0, "t", "2026-01-01"),  # later in file
    ]
    out = latest_per_nav_date(rows)
    assert len(out) == 1 and out[0].nav_acc == 2.0


def test_reader_resorts_regardless_of_writer_order():
    rows = [
        NavHistoryRow("a", "2026-01-03", 1.3, "w", "r"),
        NavHistoryRow("a", "2026-01-01", 1.1, "w", "r"),
        NavHistoryRow("a", "2026-01-02", 1.2, "w", "r"),
    ]
    out = latest_per_nav_date(rows)
    assert [r.nav_date for r in out] == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_nav_history_append_rows_bounds_to_window():
    series = (
        ("2026-03-01", 1.0), ("2026-03-20", 1.1),
        ("2026-04-30", 1.2), ("2026-05-10", 1.3),
    )
    # run_date 2026-05-10, NAV_APPEND_DAYS=60 → cutoff 2026-03-11; keep >= cutoff
    rows = nav_history_append_rows(
        fund_id="a", acc_series=series, run_date="2026-05-10",
        written_at="2026-05-10T09:00:00", nav_append_days=60,
    )
    kept = [r.nav_date for r in rows]
    assert kept == ["2026-03-20", "2026-04-30", "2026-05-10"]
    assert all(r.source_run_date == "2026-05-10" for r in rows)
    assert all(r.written_at == "2026-05-10T09:00:00" for r in rows)


def test_nav_history_append_rows_empty_series():
    assert nav_history_append_rows(
        fund_id="a", acc_series=(), run_date="2026-05-10",
        written_at="w", nav_append_days=60,
    ) == []


def test_append_nav_history_is_real_append(tmp_path: Path):
    p = tmp_path / "data" / "monitor" / "nav_history.jsonl"
    append_nav_history(p, [NavHistoryRow("a", "2026-01-01", 1.0, "w1", "2026-01-01")])
    append_nav_history(p, [NavHistoryRow("b", "2026-01-02", 1.1, "w2", "2026-01-02")])
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["fund_id"] == "a"
    assert json.loads(lines[1])["fund_id"] == "b"


def test_append_nav_history_swallows_write_failure(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad = blocker / "monitor" / "nav_history.jsonl"
    append_nav_history(bad, [NavHistoryRow("a", "2026-01-01", 1.0, "w", "r")])  # no exception
