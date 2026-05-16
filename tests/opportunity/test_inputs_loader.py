from __future__ import annotations

from datetime import date

import duckdb
import pytest

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.types import OpportunityInput


def _make_db(tmp_path):
    con = duckdb.connect(str(tmp_path / "test.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('518880','518880','cn_on_exchange','黄金ETF',NULL,'gold','cny',"
        " DATE '2020-01-01', 0.005, 5.0e10, 'SHFE Au99.99', 6.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:518880')"
    )
    # 300 days of prices: flat for 260 at 100, then 40 at 110
    base = date(2025, 1, 1)
    rows = []
    for i in range(260):
        d = date.fromordinal(base.toordinal() + i)
        rows.append(("518880", d, 100.0, 100.0, 100.0, 100.0, 1.0))
    for i in range(40):
        d = date.fromordinal(base.toordinal() + 260 + i)
        rows.append(("518880", d, 110.0, 110.0, 110.0, 110.0, 1.0))
    con.executemany(
        "INSERT INTO prices VALUES (?,?,?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:518880')",
        rows,
    )
    con.execute(
        "INSERT INTO fund_metrics VALUES "
        "('518880', DATE '2026-05-15', 0.12, 0.18, 0.40, 0.003, 0.8, "
        " TIMESTAMP '2026-05-15', 'test', 'test:518880')"
    )
    return con


def test_populate_inputs_fills_evidence_fields(tmp_path):
    con = _make_db(tmp_path)
    skeleton = OpportunityInput(
        instrument_id="518880",
        asset_class="gold",
        market="cn_on_exchange",
        theme=None,
        name_cn="黄金ETF",
        role="core_gold_hedge",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.expense_ratio == pytest.approx(0.005)
    assert inp.aum_cny == pytest.approx(5.0e10)
    assert inp.manager_tenure_years == pytest.approx(6.0)
    assert inp.tracking_error == pytest.approx(0.003)
    # ret_1m=0 (last 21 days flat at 110); ret_3m=10% (63-day window spans the jump)
    assert inp.ret_1m is not None
    assert inp.ret_3m is not None and inp.ret_3m > 0.05
    # self_history_percentile: 300 total points, latest 110 is the max → percentile = 1.0
    assert inp.valuation_percentile_self == pytest.approx(1.0)
    con.close()


def test_populate_inputs_returns_unchanged_when_instrument_missing(tmp_path):
    con = duckdb.connect(str(tmp_path / "empty.duckdb"))
    ensure_schema(con)
    skeleton = OpportunityInput(
        instrument_id="999999",
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.expense_ratio is None
    assert inp.aum_cny is None
    assert inp.ret_1m is None
    assert inp.valuation_percentile_self is None
    con.close()
