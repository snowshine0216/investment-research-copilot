from __future__ import annotations

from datetime import date

import duckdb
import pytest

from irc.data.duckdb_helper import ensure_schema
from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.types import BrokerReport
from irc.opportunity import inputs_loader
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.states import classify_valuation
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


def _seed_csi300_instrument_with_prices(con) -> None:
    con.execute(
        "INSERT INTO instruments VALUES "
        "('510300','510300','cn_on_exchange','沪深300ETF',NULL,'cn_etf','cny',"
        " DATE '2020-01-01', 0.005, 5.0e10, NULL, 6.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:510300')"
    )
    base = date(2025, 1, 1)
    rows = [
        ("510300", date.fromordinal(base.toordinal() + i), 100.0, 100.0, 100.0, 100.0, 1.0)
        for i in range(300)
    ]
    con.executemany(
        "INSERT INTO prices VALUES (?,?,?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:510300')",
        rows,
    )


def _stub_index_valuation(index_key, *, fetch=None):  # noqa: ARG001
    return IndexValuation(
        index_key="csi300", pe_ttm=12.1, pb=1.31, dividend_yield=None,
        as_of_iso="2026-05-31",
    )


def test_populate_inputs_fills_pe_pb_for_recognised_broad_index(tmp_path, monkeypatch):
    con = duckdb.connect(str(tmp_path / "csi.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    skeleton = OpportunityInput(
        instrument_id="510300",
        asset_class="cn_etf",
        market="cn_on_exchange",
        tracked_index="csi300",
        name_cn="沪深300ETF",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm == 12.1
    assert inp.pb == 1.31
    assert inp.dividend_yield is None
    con.close()


def test_populate_inputs_leaves_pe_pb_none_for_unrecognised_index(tmp_path, monkeypatch):
    con = duckdb.connect(str(tmp_path / "unk.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('159999','159999','cn_on_exchange','某主题ETF',NULL,'cn_etf','cny',"
        " DATE '2020-01-01', 0.005, 1.0e9, NULL, 3.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:159999')"
    )

    def _boom(index_key, *, fetch=None):  # noqa: ARG001
        raise AssertionError("fetch must NOT be called for an unrecognised index")

    monkeypatch.setattr(inputs_loader, "fetch_cn_index_valuation", _boom)
    skeleton = OpportunityInput(
        instrument_id="159999",
        asset_class="cn_etf",
        market="cn_on_exchange",
        tracked_index="some_sector_theme",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm is None
    assert inp.pb is None
    assert inp.dividend_yield is None
    con.close()


def test_populate_inputs_leaves_pe_pb_none_for_gold_and_bond(tmp_path, monkeypatch):
    con = duckdb.connect(str(tmp_path / "gold.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('518880','518880','cn_on_exchange','黄金ETF',NULL,'gold','cny',"
        " DATE '2020-01-01', 0.005, 5.0e10, NULL, 6.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:518880')"
    )
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fetch for gold")),
    )
    skeleton = OpportunityInput(
        instrument_id="518880",
        asset_class="gold",
        market="cn_on_exchange",
        tracked_index=None,
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm is None and inp.pb is None and inp.dividend_yield is None
    con.close()


def test_populate_inputs_consensus_upside_none_with_no_broker_reports(tmp_path, monkeypatch):
    con = duckdb.connect(str(tmp_path / "noupside.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.consensus_upside_pct is None  # no reports passed → None (ADR 0009)
    con.close()


def test_populate_inputs_consensus_upside_computed_when_reports_carry_targets(
    tmp_path, monkeypatch
):
    con = duckdb.connect(str(tmp_path / "upside.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)  # latest close == 100.0
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    reports = (
        BrokerReport("510300", "中信", "买入", 120.0, "2026-05-08", "t"),
        BrokerReport("510300", "中金", "增持", 100.0, "2026-05-07", "t"),
    )
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    inp = populate_inputs(
        con, skeleton, holding_entry_date=None, broker_reports=reports
    )
    # median([120, 100]) = 110 ; 110/100 - 1 = 0.10
    assert inp.consensus_upside_pct == pytest.approx(0.10)
    con.close()


def test_population_is_inert_classify_valuation_byte_identical(tmp_path, monkeypatch):
    """AC4 inertness lock: classify_valuation output is byte-identical whether
    or not pe/pb/dividend/consensus_upside are populated — proving population
    changes no state until item 002 wires these fields."""
    con = duckdb.connect(str(tmp_path / "inert.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    monkeypatch.setattr(
        inputs_loader, "fetch_cn_index_valuation", _stub_index_valuation
    )
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    reports = (BrokerReport("510300", "中信", "买入", 120.0, "2026-05-08", "t"),)

    populated = populate_inputs(
        con, skeleton, holding_entry_date=None, broker_reports=reports
    )
    # Same row with pe/pb/dividend/consensus_upside forced back to None.
    import dataclasses
    bare = dataclasses.replace(
        populated, pe_ttm=None, pb=None, dividend_yield=None,
        consensus_upside_pct=None,
    )
    assert populated.pe_ttm is not None  # guard: population actually happened
    assert classify_valuation(populated) == classify_valuation(bare)
    con.close()
