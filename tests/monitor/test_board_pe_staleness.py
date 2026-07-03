from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from irc.monitor.board_pe_staleness import (
    BoardPeFreshness, freshness_dict, newest_nonempty, read_day_table,
    stale_fallback, trading_day_age, write_day_table,
)

# Mon 06-29 … Fri 07-03, all trading days
_TDS = frozenset({date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1),
                  date(2026, 7, 2), date(2026, 7, 3)})


def _day(cache_dir: Path, day: str, table: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{day}.json").write_text(
        json.dumps(table, ensure_ascii=False), encoding="utf-8")


# ---- trading_day_age (AC-10) ----


def test_age_counts_trading_days_after_as_of_up_to_today():
    assert trading_day_age("2026-07-01", "2026-07-03", _TDS) == 2


def test_age_weekend_holiday_gap_counts_zero():
    # as_of Friday, today Sunday: no trading day in (07-03, 07-05] → N = 0
    assert trading_day_age("2026-07-03", "2026-07-05", _TDS) == 0


def test_age_unparseable_dates_is_none():
    assert trading_day_age("garbage", "2026-07-03", _TDS) is None


# ---- day-file I/O (moved from industry_valuation in Task 4) ----


def test_day_table_write_read_roundtrip_byte_stable(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    write_day_table(cache, "2026-07-03", {"银行": 6.5, "白酒": 30.2})
    assert read_day_table(cache, "2026-07-03") == {"银行": 6.5, "白酒": 30.2}
    a = (cache / "2026-07-03.json").read_bytes()
    write_day_table(cache, "2026-07-03", {"白酒": 30.2, "银行": 6.5})   # same content
    assert (cache / "2026-07-03.json").read_bytes() == a                # sorted keys


def test_day_table_missing_or_unreadable_is_none(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    assert read_day_table(cache, "2026-07-03") is None
    cache.mkdir(parents=True)
    (cache / "2026-07-02.json").write_text("{corrupt", encoding="utf-8")
    assert read_day_table(cache, "2026-07-02") is None


# ---- newest_nonempty scan (RD-2) ----


def test_scan_skips_empty_and_unreadable_continues_older(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-06-30", {"银行": 6.5})
    _day(cache, "2026-07-01", {})                              # pre-light-up {} landmine
    (cache / "2026-07-02.json").write_text("{corrupt", encoding="utf-8")
    assert newest_nonempty(cache, "2026-07-03") == ("2026-06-30", {"银行": 6.5})


def test_scan_ignores_today_and_future_files(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-03", {"银行": 6.5})                    # today: FRESH's business
    _day(cache, "2026-07-04", {"白酒": 30.0})                   # future: never
    assert newest_nonempty(cache, "2026-07-03") is None


def test_scan_missing_dir_is_none(tmp_path: Path):
    assert newest_nonempty(tmp_path / "nope", "2026-07-03") is None


# ---- stale_fallback (AC-9 stale branch + RD-3 calendar scoping) ----


def test_stale_within_3td_serves_table_and_names_date(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-01", {"银行": 6.5})
    table, f = stale_fallback(cache, "2026-07-03", _TDS)
    assert table == {"银行": 6.5}
    assert f == BoardPeFreshness("STALE", "2026-07-01", 2)


def test_stale_boundary_n3_serves_n4_darkens(tmp_path: Path):
    cache3 = tmp_path / "ip3"
    _day(cache3, "2026-06-30", {"银行": 6.5})                   # N=3 (07-01, 02, 03)
    table, f = stale_fallback(cache3, "2026-07-03", _TDS)
    assert table == {"银行": 6.5}
    assert (f.state, f.age_td) == ("STALE", 3)

    cache4 = tmp_path / "ip4"
    _day(cache4, "2026-06-29", {"银行": 6.5})                   # N=4 (06-30 … 07-03)
    table, f = stale_fallback(cache4, "2026-07-03", _TDS)
    assert table == {}
    assert f == BoardPeFreshness("DARK", "2026-06-29", 4)


def test_empty_1td_file_skipped_nonempty_3td_serves(tmp_path: Path):
    """RD-2 boundary test verbatim: an empty {} day file 1 td old + a non-empty
    file 3 td old → the 3-td table serves as STALE-3, never the empty one."""
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-02", {})
    _day(cache, "2026-06-30", {"银行": 6.5})
    table, f = stale_fallback(cache, "2026-07-03", _TDS)
    assert table == {"银行": 6.5}
    assert (f.state, f.as_of, f.age_td) == ("STALE", "2026-06-30", 3)


def test_calendar_unavailable_darkens_stale_branch_only(tmp_path: Path):
    """Q5/RD-3: no calendar → an honest N is uncomputable → DARK; as_of still
    names the newest non-empty cached day. (FRESH is calendar-independent —
    covered in test_industry_valuation.py.)"""
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-02", {"银行": 6.5})
    for dead in (None, frozenset()):
        table, f = stale_fallback(cache, "2026-07-03", dead)
        assert table == {}
        assert f == BoardPeFreshness("DARK", "2026-07-02", None)


def test_nothing_cached_is_dark_none(tmp_path: Path):
    table, f = stale_fallback(tmp_path / "industry_pe", "2026-07-03", _TDS)
    assert table == {}
    assert f == BoardPeFreshness("DARK", None, None)


def test_nontrading_day_rerun_yields_stale_0(tmp_path: Path):
    # Q6: a Sunday rerun serving Friday's table → STALE with N = 0 (date named).
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-03", {"银行": 6.5})
    table, f = stale_fallback(cache, "2026-07-05", _TDS)
    assert table == {"银行": 6.5}
    assert (f.state, f.age_td, f.as_of) == ("STALE", 0, "2026-07-03")


def test_freshness_dict_projection():
    assert freshness_dict(None) is None
    assert freshness_dict(BoardPeFreshness("STALE", "2026-07-01", 2)) == {
        "state": "STALE", "as_of": "2026-07-01", "age_td": 2}
