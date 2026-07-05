import json
from pathlib import Path

from irc.rotation.board_fetch import _f, parse_board_spot, parse_board_hist

_FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def test_parse_board_spot_extracts_rows():
    rows = parse_board_spot(_load("board_spot_sample.json"), today="2026-07-06")
    assert rows  # at least one board
    r = rows[0]
    assert r.board_code.startswith("BK")
    assert r.source == "snapshot" and r.date == "2026-07-06"
    assert isinstance(r.chg_pct, float)


def test_parse_board_spot_extracts_board_pe_and_none():
    rows = parse_board_spot(_load("board_spot_sample.json"), today="2026-07-06")
    pes = {r.board_code: r.board_pe for r in rows}
    # at least one board has a numeric PE and at least one has None (missing/"-")
    assert any(isinstance(v, float) for v in pes.values())
    assert any(v is None for v in pes.values())


def test_parse_board_spot_tolerates_empty():
    assert parse_board_spot({"data": None}, today="2026-07-06") == ()
    assert parse_board_spot({}, today="2026-07-06") == ()


def test_parse_board_hist_daily_rows():
    rows = parse_board_hist(_load("board_hist_sample.json"),
                            board_code="BK0475", board_name="半导体")
    assert len(rows) >= 3
    assert all(r.source == "backfill" for r in rows)
    assert rows[0].date < rows[-1].date  # ascending
    assert all(r.board_code == "BK0475" for r in rows)


def test_parse_board_hist_8col_turnover_none():
    """Back-compat: an 8-col kline row (fields2 f51-f58, no f61) carries no turnover
    field, so turnover_pct stays None (never a stray parts[8] index read). Old cached
    backfill rows + any short/legacy payload degrade honestly."""
    rows = parse_board_hist(_load("board_hist_sample.json"),
                            board_code="BK0475", board_name="半导体")
    assert rows
    assert all(r.turnover_pct is None for r in rows)


def test_parse_board_hist_11col_turnover_from_f61():
    """F7: with fields2 extended to f51-f61, the kline row is 11-col and
    turnover_pct is sourced from position 10 (f61=换手率) via tolerant _f. Fixture
    is the real captured BK0475 (银行Ⅱ) rows from 001-probe-notes.md; turnover
    0.29 / 0.25 at position 10. chg_pct stays DERIVED from close (f59 at pos 8 is a
    cross-check only, not consumed); flow + PE stay None on backfill."""
    rows = parse_board_hist(_load("board_hist_f61_sample.json"),
                            board_code="BK0475", board_name="银行Ⅱ")
    assert tuple(r.turnover_pct for r in rows) == (0.29, 0.25)
    assert rows[0].chg_pct == 0.0  # no prev close → derived 0.0
    assert rows[1].chg_pct == round((3880.94 / 3880.50 - 1) * 100, 4)  # derived, not f59
    assert all(r.source == "backfill" for r in rows)
    assert all(r.main_inflow_ratio is None and r.board_pe is None for r in rows)


def test_parse_board_hist_tolerates_short_row_in_11col_payload():
    """Defensive: a row with <11 cols inside an otherwise-extended payload yields
    turnover_pct=None for that row (len guard), never an IndexError."""
    payload = {"data": {"klines": [
        "2026-07-02,3843.00,3880.50,3918.97,3828.06,39091339,29054997866.00,2.37,1.20,46.11,0.29",
        "2026-07-03,3878.87,3880.94,3921.46,3847.28,33636435,24419122450.00",  # 8-col, no f61
    ]}}
    rows = parse_board_hist(payload, "BK0475", "银行Ⅱ")
    assert (rows[0].turnover_pct, rows[1].turnover_pct) == (0.29, None)


def test_parse_board_hist_tolerates_empty():
    assert parse_board_hist({"data": {"klines": []}}, "BK0475", "半导体") == ()
    assert parse_board_hist({}, "BK0475", "半导体") == ()


def test_f_rejects_non_finite_strings():
    assert _f("nan") is None
    assert _f("inf") is None
    assert _f("-inf") is None
    assert _f("NaN") is None
    assert _f("Infinity") is None


def test_f_rejects_non_finite_floats():
    assert _f(float("nan")) is None
    assert _f(float("inf")) is None
    assert _f(float("-inf")) is None


def test_f_accepts_finite_values():
    assert _f("1.5") == 1.5
    assert _f(2) == 2.0
