from __future__ import annotations

from datetime import date

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.types import OpportunityInput
from irc.schemas.valuation import ActiveFundLookthroughConfig


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "lt.duckdb"))
    ensure_schema(con)
    return con


def _seed_active_fund(con):
    # One active fund "AF1" holding 600519 (60%) — clears a 0.50 floor.
    con.execute(
        "INSERT INTO fund_holdings VALUES "
        "('AF1', DATE '2026-03-31', '600519', '贵州茅台', 60.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    # 600519: 200 PE/PB points over ~398 days → clears the 120/180 gate.
    base = date(2025, 1, 1)
    rows = []
    for i in range(200):
        d = date.fromordinal(base.toordinal() + 2 * i)
        rows.append(("600519", d, 18.0 + i * 0.01, 2.0, None,
                     "2026-05-15 00:00:00", "eastmoney", "r"))
    con.executemany(
        "INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows
    )


def _skeleton():
    return OpportunityInput(
        instrument_id="AF1",
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        theme=None,
        tracked_index=None,
        name_cn="主动基金",
        role="",
        is_holding=False,
        portfolio_weight=None,
        target_band_low=None,
        target_band_high=None,
        venue_compatible=True,
    )


def test_flag_off_leaves_fundamental_percentile_none(tmp_path) -> None:
    con = _con(tmp_path)
    _seed_active_fund(con)
    out = populate_inputs(
        con, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    assert out.valuation_percentile_fundamental is None
    assert out.valuation_percentile_fundamental_pb is None
    con.close()


def test_flag_on_populates_fundamental_percentile(tmp_path) -> None:
    con = _con(tmp_path)
    _seed_active_fund(con)
    out = populate_inputs(
        con, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=True, coverage_floor=0.50),
    )
    assert out.valuation_percentile_fundamental is not None
    assert 0.0 <= out.valuation_percentile_fundamental <= 1.0
    # PB clears the <30 floor (200 points) → populated too.
    assert out.valuation_percentile_fundamental_pb is not None
    con.close()


def test_flag_on_below_floor_leaves_none(tmp_path) -> None:
    con = _con(tmp_path)
    # AF1 holds only 30% of 600519 → coverage 0.30 < 0.50 floor → None.
    con.execute(
        "INSERT INTO fund_holdings VALUES "
        "('AF1', DATE '2026-03-31', '600519', '贵州茅台', 30.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    base = date(2025, 1, 1)
    rows = [("600519", date.fromordinal(base.toordinal() + 2 * i), 18.0, 2.0, None,
             "2026-05-15 00:00:00", "eastmoney", "r") for i in range(200)]
    con.executemany("INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows)
    out = populate_inputs(
        con, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=True, coverage_floor=0.50),
    )
    assert out.valuation_percentile_fundamental is None
    con.close()


def test_index_fund_path_unchanged_by_lookthrough_branch(tmp_path) -> None:
    # An index-tracking ETF must keep using the index path regardless of the
    # active-fund branch / flag. With no index_valuation_history rows it stays
    # None (the index path's all-None dormancy) — proving the branch did not
    # intercept a non-cn_equity_fund row.
    con = _con(tmp_path)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        theme=None, tracked_index="csi300", name_cn="沪深300ETF", role="",
        is_holding=False, portfolio_weight=None, target_band_low=None,
        target_band_high=None, venue_compatible=True,
    )
    out = populate_inputs(
        con, skeleton, holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=True),
    )
    assert out.valuation_percentile_fundamental is None  # no index rows cached
    con.close()
