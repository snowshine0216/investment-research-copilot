import json
from pathlib import Path

from irc.rotation.board_fetch import parse_board_spot, parse_board_hist

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


def test_parse_board_hist_tolerates_empty():
    assert parse_board_hist({"data": {"klines": []}}, "BK0475", "半导体") == ()
    assert parse_board_hist({}, "BK0475", "半导体") == ()
