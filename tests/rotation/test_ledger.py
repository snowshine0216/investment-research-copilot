import json

from irc.rotation.ledger import build_ledger_rows, append_rows
from irc.rotation.types import BoardState


def _bs(code, state, pctl=0.85):
    return BoardState(code, code, state, 1, pctl, 1.0, 1.0, 0.1, None, False)


def test_build_skips_quiet():
    rows = build_ledger_rows("2026-07-06",
                             (_bs("BK1", "emerging"), _bs("BK2", "quiet")), 1)
    assert [r["board_code"] for r in rows] == ["BK1"]
    assert rows[0]["radar_version"] == 1 and rows[0]["date"] == "2026-07-06"


def test_append_is_append_only(tmp_path):
    p = tmp_path / "forward_ledger.jsonl"
    append_rows(p, build_ledger_rows("2026-07-06", (_bs("BK1", "emerging"),), 1))
    append_rows(p, build_ledger_rows("2026-07-07", (_bs("BK2", "hot"),), 1))
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["date"] == "2026-07-06"
    assert json.loads(lines[1])["date"] == "2026-07-07"


def test_same_day_rerun_no_duplicate(tmp_path):
    p = tmp_path / "forward_ledger.jsonl"
    rows = build_ledger_rows("2026-07-06", (_bs("BK1", "emerging"),), 1)
    append_rows(p, rows)
    append_rows(p, rows)  # rerun same day
    assert len(p.read_text().strip().splitlines()) == 1  # no dup (AC9)
