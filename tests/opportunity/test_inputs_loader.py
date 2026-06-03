from __future__ import annotations

import dataclasses
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


def dataclasses_replace_upside(inp: OpportunityInput, upside: float) -> OpportunityInput:
    return dataclasses.replace(inp, consensus_upside_pct=upside)


def dataclasses_replace_self_pct(inp: OpportunityInput, pct: float) -> OpportunityInput:
    return dataclasses.replace(inp, valuation_percentile_self=pct)


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


def _seed_index_valuation_history(con, index_key, pe_pb_pairs, base_date=date(2025, 1, 1)):
    rows = []
    for i, (pe, pb) in enumerate(pe_pb_pairs):
        d = date.fromordinal(base_date.toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_populate_inputs_reads_cached_index_valuation_percentile(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    # 30+ rising PE points so self_history_percentile fires; latest is the max.
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(40)]
    _seed_index_valuation_history(con, "csi300", pairs)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300", name_cn="沪深300ETF",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    # latest PE = 10 + 39*0.1 = 13.9; pb = 1 + 39*0.01 = 1.39
    assert inp.pe_ttm == pytest.approx(13.9)
    assert inp.pb == pytest.approx(1.39)
    assert inp.valuation_percentile_fundamental == pytest.approx(1.0)
    assert inp.valuation_percentile_fundamental_pb == pytest.approx(1.0)
    # earnings_yield = 1/13.9
    assert inp.earnings_yield == pytest.approx(1.0 / 13.9)
    con.close()


def test_populate_inputs_fundamental_percentile_none_under_30_points(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv2.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    _seed_index_valuation_history(con, "csi300", [(12.0, 1.3)] * 10)  # < 30 points
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.valuation_percentile_fundamental is None
    assert inp.valuation_percentile_fundamental_pb is None
    # latest pe/pb still populated (for reason text + earnings_yield).
    assert inp.pe_ttm == pytest.approx(12.0)
    assert inp.earnings_yield == pytest.approx(1.0 / 12.0)
    con.close()


def test_populate_inputs_real_yield_in_ratio_units(tmp_path):
    # R1 regression: cn_10y_yield = 2.45 (percent) → real_yield_10y ≈ 0.0245 (ratio).
    con = duckdb.connect(str(tmp_path / "iv3.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    _seed_cn_10y_yield(con, [2.45, 2.45, 2.45])
    _seed_index_valuation_history(con, "csi300", [(14.0, 1.3)] * 30)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.real_yield_10y == pytest.approx(0.0245)
    # earnings_yield = 1/14 ≈ 0.0714 > 0.0245 → anchor reads POSITIVE.
    assert inp.earnings_yield == pytest.approx(1.0 / 14.0)
    from irc.opportunity.states import expected_real_return_positive
    assert expected_real_return_positive(inp) is True
    con.close()


def test_populate_inputs_no_live_index_fetch(tmp_path):
    # R3: a provider whose fetch_index_valuation raises must NOT be invoked.
    con = duckdb.connect(str(tmp_path / "iv4.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    _seed_index_valuation_history(con, "csi300", [(12.0, 1.3)] * 30)
    provider = _StubProvider(raise_on_fetch=True)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300",
    )
    # Must not raise — the index path reads the cached table, never the provider.
    inp = populate_inputs(con, skeleton, holding_entry_date=None, provider=provider)
    assert inp.pe_ttm == pytest.approx(12.0)
    con.close()


def _stub_index_valuation(index_key, *, fetch=None):  # noqa: ARG001
    return IndexValuation(
        index_key="csi300", pe_ttm=12.1, pb=1.31, dividend_yield=None,
        as_of_iso="2026-05-31",
    )


class _StubProvider:
    """In-memory provider for inputs_loader tests. Replaces old fetch_cn_index_valuation patch."""

    def __init__(self, *, index_val=None, raise_on_fetch=False):
        self._index_val = index_val
        self._raise_on_fetch = raise_on_fetch

    def fetch_filing_digest(self, symbol):
        return None

    def fetch_broker_reports(self, symbol, *, days=90, max_reports=20):
        return ()

    def fetch_index_valuation(self, index_key):
        if self._raise_on_fetch:
            raise AssertionError("fetch must NOT be called")
        return self._index_val


def test_populate_inputs_fills_pe_pb_for_recognised_broad_index(tmp_path):
    con = duckdb.connect(str(tmp_path / "csi.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    _seed_index_valuation_history(con, "csi300", [(12.1, 1.31)])
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300", name_cn="沪深300ETF",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm == pytest.approx(12.1)
    assert inp.pb == pytest.approx(1.31)
    assert inp.dividend_yield is None
    con.close()


def test_populate_inputs_leaves_pe_pb_none_for_unrecognised_index(tmp_path):
    con = duckdb.connect(str(tmp_path / "unk.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('159999','159999','cn_on_exchange','某主题ETF',NULL,'cn_etf','cny',"
        " DATE '2020-01-01', 0.005, 1.0e9, NULL, 3.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:159999')"
    )
    skeleton = OpportunityInput(
        instrument_id="159999", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="some_sector_theme",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm is None
    assert inp.pb is None
    assert inp.dividend_yield is None
    con.close()


def test_populate_inputs_leaves_pe_pb_none_for_gold_and_bond(tmp_path):
    con = duckdb.connect(str(tmp_path / "gold.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('518880','518880','cn_on_exchange','黄金ETF',NULL,'gold','cny',"
        " DATE '2020-01-01', 0.005, 5.0e10, NULL, 6.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:518880')"
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


def test_populate_inputs_consensus_upside_none_with_no_broker_reports(tmp_path):
    con = duckdb.connect(str(tmp_path / "noupside.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    # Item 001: index_valuation_history now drives pe/pb (not provider).
    _seed_index_valuation_history(con, "csi300", [(12.1, 1.31)])
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.consensus_upside_pct is None  # no reports passed → None (ADR 0009)
    con.close()


def test_populate_inputs_consensus_upside_computed_when_reports_carry_targets(tmp_path):
    con = duckdb.connect(str(tmp_path / "upside.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)  # latest close == 100.0
    # Item 001: index_valuation_history now drives pe/pb (not provider).
    _seed_index_valuation_history(con, "csi300", [(12.1, 1.31)])
    reports = (
        BrokerReport("510300", "中信", "买入", 120.0, "2026-05-08", "t"),
        BrokerReport("510300", "中金", "增持", 100.0, "2026-05-07", "t"),
    )
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    inp = populate_inputs(
        con, skeleton, holding_entry_date=None, broker_reports=reports,
    )
    # median([120, 100]) = 110 ; 110/100 - 1 = 0.10
    assert inp.consensus_upside_pct == pytest.approx(0.10)
    con.close()


def test_population_consumes_consensus_upside_per_item_002(tmp_path):
    """Item 002 (AC7) — EVOLVED from item 001's AC4 inertness lock.

    The 001 lock asserted classify_valuation(populated) == classify_valuation(bare).
    Item 002 INTENTIONALLY makes a populated `consensus_upside_pct` flow into the
    equity valuation reason, so that equality is now false BY DESIGN. This test is
    updated (not deleted) to assert the new specified behaviour and the all-None
    dormancy, per docs/2026-05-31-funding-analysis/items/002-spec.md (AC2/AC3/AC6/AC7)
    and ADR 0009 (degrade-to-None). Provenance preserved: stays in this file, keeps
    the population guard.

    Row anatomy (grill Q-T4): 510300/csi300 seeds a flat 300x100.0 price series, so
    `self_history_percentile` (inclusive count_le/len) gives percentile 1.0 →
    classify_valuation returns `very_expensive`. target_price=120 / close=100 →
    consensus_upside_pct=0.20 → signal `"cheap"`. AC3's one-notch adjustment fires
    only on a cheap/reasonable_low percentile, so for this very_expensive row the
    notch NEVER fires — the break is ANNOTATION-ONLY (AC2's appended caveat).
    """
    con = duckdb.connect(str(tmp_path / "consume.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    # Item 001: seed the cached index_valuation_history table (single row — no percentile).
    _seed_index_valuation_history(con, "csi300", [(12.1, 1.31)])
    provider = _StubProvider(raise_on_fetch=True)  # must NOT be called (R3)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300",
    )
    reports = (BrokerReport("510300", "中信", "买入", 120.0, "2026-05-08", "t"),)

    populated = populate_inputs(
        con, skeleton, holding_entry_date=None, broker_reports=reports, provider=provider
    )
    bare = dataclasses.replace(
        populated, pe_ttm=None, pb=None, dividend_yield=None,
        consensus_upside_pct=None,
    )
    assert populated.pe_ttm is not None  # guard: population actually happened
    assert populated.consensus_upside_pct == pytest.approx(0.20)

    pop_state, pop_reason = classify_valuation(populated)
    bare_state, bare_reason = classify_valuation(bare)

    # (i) Annotation-only break on THIS row: state unchanged at very_expensive
    # (percentile 1.0 → notch never fires), but the reason now carries the
    # equity fundamental caveat that the bare (all-None) row does not.
    assert pop_state == bare_state == "very_expensive"
    assert pop_reason != bare_reason
    assert "上行空间" in pop_reason
    assert "上行空间" not in bare_reason

    # (ii) All-None dormancy (AC6): the bare row is byte-identical to pre-002.
    assert classify_valuation(bare) == classify_valuation(
        dataclasses.replace(bare, consensus_upside_pct=None)
    )
    con.close()


def test_consensus_upside_notch_fires_on_genuinely_cheap_percentile(tmp_path):
    """Item 002 (AC7) — SECOND row exercising the AC3 one-notch corroboration.

    Unlike the flat-series row above (percentile 1.0 → very_expensive), this seeds
    a deeply cheap percentile and a 'cheap' consensus-upside signal, so the AC3
    one-notch adjustment fires: reasonable_low → cheap / cheap → cheap. Cites
    docs/2026-05-31-funding-analysis/items/002-spec.md (AC3) and ADR 0009.
    """
    con = duckdb.connect(str(tmp_path / "notch.duckdb"))
    ensure_schema(con)
    # reasonable_low percentile: build a synthetic input directly (no DB price
    # path needed — the notch lives in classify_valuation, a pure function).
    base = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        tracked_index="csi300", valuation_percentile_self=0.30,
    )
    without = classify_valuation(base)
    assert without[0] == "reasonable_low"  # baseline percentile band

    with_cheap_signal = classify_valuation(
        dataclasses_replace_upside(base, 0.25)  # 'cheap' signal
    )
    assert with_cheap_signal[0] == "cheap"  # AC3 corroboration notch fired

    # cheap percentile + cheap signal stays cheap (notch no-op)
    deeply_cheap = dataclasses_replace_upside(
        dataclasses_replace_self_pct(base, 0.10), 0.25
    )
    assert classify_valuation(deeply_cheap)[0] == "cheap"
    con.close()
