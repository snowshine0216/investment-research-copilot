from irc.narrative.schemas import Holding
from irc.rotation.exposure import build_exposure


def _h(sym, w):
    return Holding(symbol=sym, name_cn=sym, weight_pct=w, sw_industry="")


def test_three_holdings_one_board_sum_weights():
    funds = [("F1", "基金一", (_h("600001", 5.0), _h("600002", 4.0), _h("600003", 3.0)),
              "2026Q1")]
    s2b = {"600001": "BK1", "600002": "BK1", "600003": "BK1"}
    rows, diag = build_exposure(funds, s2b)
    assert len(rows) == 1
    r = rows[0]
    assert r.board_code == "BK1" and round(r.exposure_pct, 4) == 12.0
    assert set(r.matched_symbols) == {"600001", "600002", "600003"}
    assert r.holdings_as_of == "2026Q1"


def test_unmapped_stocks_reduce_coverage_and_listed():
    funds = [("F1", "基金一", (_h("600001", 5.0), _h("999999", 4.0)), "2026Q1")]
    s2b = {"600001": "BK1"}
    rows, diag = build_exposure(funds, s2b)
    assert "999999" in diag["unmapped_syms"]
    assert diag["mapped_syms"] == 1 and diag["total_holding_syms"] == 2
    assert round(diag["coverage_pct"], 4) == 50.0


def test_multiple_boards_split_rows():
    funds = [("F1", "基金一", (_h("600001", 5.0), _h("000002", 4.0)), "2026Q1")]
    s2b = {"600001": "BK1", "000002": "BK2"}
    rows, _ = build_exposure(funds, s2b)
    by_board = {r.board_code: r.exposure_pct for r in rows}
    assert by_board == {"BK1": 5.0, "BK2": 4.0}
