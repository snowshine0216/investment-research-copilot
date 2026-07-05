from irc.rotation.series_store import load_store, append_snapshot
from irc.rotation.types import BoardDay


def _bd(date, code, chg, src="snapshot", pe=45.0):
    return BoardDay(date=date, board_code=code, board_name="半导体",
                    chg_pct=chg, main_inflow_ratio=1.0, turnover_pct=2.0,
                    board_pe=pe, source=src)


def test_missing_store_is_empty(tmp_path):
    assert load_store(tmp_path / "nope.jsonl") == {}


def test_append_then_load_roundtrip(tmp_path):
    p = tmp_path / "board_series.jsonl"
    tds = ("2026-07-06", "2026-07-07")
    append_snapshot(p, [_bd("2026-07-06", "BK0475", 1.0)], keep_td=25, trading_days=tds)
    store = append_snapshot(p, [_bd("2026-07-07", "BK0475", 2.0)], keep_td=25,
                            trading_days=tds)
    assert [r.date for r in store["BK0475"]] == ["2026-07-06", "2026-07-07"]


def test_same_day_rerun_no_double_append(tmp_path):
    p = tmp_path / "board_series.jsonl"
    tds = ("2026-07-06",)
    append_snapshot(p, [_bd("2026-07-06", "BK0475", 1.0)], keep_td=25, trading_days=tds)
    store = append_snapshot(p, [_bd("2026-07-06", "BK0475", 9.9)], keep_td=25,
                            trading_days=tds)
    assert len(store["BK0475"]) == 1
    assert store["BK0475"][0].chg_pct == 9.9  # overwrite, not append


def test_prune_to_keep_td(tmp_path):
    p = tmp_path / "board_series.jsonl"
    tds = ("2026-07-01", "2026-07-02", "2026-07-03")
    append_snapshot(p, [_bd("2026-07-01", "BK0475", 1.0)], keep_td=2, trading_days=tds)
    append_snapshot(p, [_bd("2026-07-02", "BK0475", 2.0)], keep_td=2, trading_days=tds)
    store = append_snapshot(p, [_bd("2026-07-03", "BK0475", 3.0)], keep_td=2,
                            trading_days=tds)
    assert [r.date for r in store["BK0475"]] == ["2026-07-02", "2026-07-03"]


def test_write_is_byte_stable(tmp_path):
    p = tmp_path / "board_series.jsonl"
    tds = ("2026-07-06",)
    append_snapshot(p, [_bd("2026-07-06", "BK0475", 1.0)], keep_td=25, trading_days=tds)
    first = p.read_bytes()
    append_snapshot(p, [_bd("2026-07-06", "BK0475", 1.0)], keep_td=25, trading_days=tds)
    assert p.read_bytes() == first  # deterministic (AC3 foundation)
