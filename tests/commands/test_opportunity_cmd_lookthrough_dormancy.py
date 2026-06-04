from __future__ import annotations

import dataclasses
from datetime import date

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.types import OpportunityInput
from irc.schemas.valuation import ActiveFundLookthroughConfig


def _skeleton():
    return OpportunityInput(
        instrument_id="AF1", asset_class="cn_equity_fund", market="cn_off_exchange",
        theme=None, tracked_index=None, name_cn="主动基金", role="",
        is_holding=False, portfolio_weight=None, target_band_low=None,
        target_band_high=None, venue_compatible=True,
    )


def _con_with_lookthrough_data(tmp_path):
    con = duckdb.connect(str(tmp_path / "dorm.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO fund_holdings VALUES "
        "('AF1', DATE '2026-03-31', '600519', '贵州茅台', 60.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    base = date(2025, 1, 1)
    rows = [("600519", date.fromordinal(base.toordinal() + 2 * i), 18.0, 2.0, None,
             "2026-05-15 00:00:00", "eastmoney", "r") for i in range(200)]
    con.executemany("INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows)
    return con


def test_flag_off_output_byte_identical_to_no_lookthrough_data(tmp_path) -> None:
    """Dormancy lock: with the flag OFF, the OpportunityInput is identical whether
    or not stock_valuation_history is populated — i.e. the look-through machinery
    is truly inert in shadow mode."""
    con_with = _con_with_lookthrough_data(tmp_path)
    out_with_data = populate_inputs(
        con_with, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    con_with.close()

    con_empty = duckdb.connect(str(tmp_path / "empty.duckdb"))
    ensure_schema(con_empty)
    out_no_data = populate_inputs(
        con_empty, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    con_empty.close()

    assert dataclasses.asdict(out_with_data) == dataclasses.asdict(out_no_data)
    assert out_with_data.valuation_percentile_fundamental is None


def test_flag_off_matches_default_disabled_config(tmp_path) -> None:
    """Calling populate_inputs WITHOUT lookthrough_cfg (default-disabled) yields
    the same result as the explicit enabled=False config — back-compat lock."""
    con = _con_with_lookthrough_data(tmp_path)
    explicit_off = populate_inputs(
        con, _skeleton(), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    default_arg = populate_inputs(con, _skeleton(), holding_entry_date=None)
    con.close()
    assert dataclasses.asdict(explicit_off) == dataclasses.asdict(default_arg)
