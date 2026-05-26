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


def _seed_cn_10y_yield(con, values: list[float], base_date: date = date(2025, 1, 1)) -> None:
    """Insert a deterministic CN10Y series into `macro_series` for percentile tests."""
    rows = []
    for i, v in enumerate(values):
        d = date.fromordinal(base_date.toordinal() + i)
        rows.append(("cn_10y_yield", d, float(v)))
    con.executemany(
        "INSERT INTO macro_series VALUES (?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:cn_10y_yield')",
        rows,
    )


def test_populate_inputs_computes_bond_yield_percentile_for_bond_fund(tmp_path):
    """A bond fund's `cn_bond_yield_percentile` reflects today's 10Y CGB yield
    against the 3y history — high yield = high percentile = bond cheap.
    """
    con = duckdb.connect(str(tmp_path / "bond.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('014502','014502','cn_off_exchange','泰信汇盈',NULL,'cn_bond_fund','cny',"
        " DATE '2020-01-01', 0.004, 1.0e9, NULL, 5.0,"
        " TIMESTAMP '2026-05-15', 'test', 'test:014502')"
    )
    # Yield series: 100 days rising from 2.0 to 2.99. Today's value 2.99 == max → percentile 1.0.
    yields = [2.0 + i * 0.01 for i in range(100)]
    _seed_cn_10y_yield(con, yields)

    skeleton = OpportunityInput(
        instrument_id="014502",
        asset_class="cn_bond_fund",
        market="cn_off_exchange",
        name_cn="泰信汇盈债券A",
        role="defensive_cn_bond",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.cn_bond_yield_percentile == pytest.approx(1.0)
    con.close()


def test_populate_inputs_bond_yield_percentile_none_for_equity_fund(tmp_path):
    """Non-bond asset classes never populate cn_bond_yield_percentile — keeps the
    field's contract aligned with classify_bond_valuation's dispatch rule."""
    con = duckdb.connect(str(tmp_path / "eq.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('003318','003318','cn_off_exchange','低波A',NULL,'cn_equity_fund','cny',"
        " DATE '2020-01-01', 0.012, 1.0e9, NULL, 5.0,"
        " TIMESTAMP '2026-05-15', 'test', 'test:003318')"
    )
    _seed_cn_10y_yield(con, [2.0, 2.1, 2.2, 2.3, 2.4])
    skeleton = OpportunityInput(
        instrument_id="003318",
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.cn_bond_yield_percentile is None
    con.close()


def test_populate_inputs_bond_yield_percentile_none_when_series_empty(tmp_path):
    """Missing macro series → percentile stays None (evidence_insufficient downstream)."""
    con = duckdb.connect(str(tmp_path / "empty_series.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('014502','014502','cn_off_exchange','泰信汇盈',NULL,'cn_bond_fund','cny',"
        " DATE '2020-01-01', 0.004, 1.0e9, NULL, 5.0,"
        " TIMESTAMP '2026-05-15', 'test', 'test:014502')"
    )
    # No macro_series rows inserted.
    skeleton = OpportunityInput(
        instrument_id="014502",
        asset_class="cn_bond_fund",
        market="cn_off_exchange",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.cn_bond_yield_percentile is None
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
