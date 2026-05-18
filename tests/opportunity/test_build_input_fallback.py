from __future__ import annotations

from unittest.mock import MagicMock

from irc.commands.opportunity_cmd import _build_input


def test_build_input_unknown_instrument_uses_placeholder_name() -> None:
    """When the instrument isn't in any universe yaml, _build_input should
    fall back to a deterministic placeholder rather than the raw id. The
    discipline report previously rendered "110022 110022" because the fallback
    was the id itself — see docs/2026-05-18-fix-memo-audit/items/003-spec.md.
    """
    score_row = {"instrument_id": "999999", "asset_class": "cn_equity_fund", "role": ""}
    con = MagicMock()
    # Simulate empty DuckDB lookups for everything _build_input may query.
    fake_df = MagicMock()
    fake_df.empty = True
    con.execute.return_value.fetchdf.return_value = fake_df
    inp = _build_input(
        score_row=score_row,
        instr=None,
        holding=None,
        target_band=None,
        portfolio_total_cny=0.0,
        available_venues=set(),
        con=con,
    )
    assert inp.name_cn == "未登记(999999)"
    assert inp.instrument_id == "999999"


def test_build_input_known_instrument_uses_instrument_name() -> None:
    """Smoke test: when instr is provided, the name comes from the instrument."""
    score_row = {"instrument_id": "510300", "asset_class": "cn_etf", "role": "core_cn_equity"}
    con = MagicMock()
    fake_df = MagicMock()
    fake_df.empty = True
    con.execute.return_value.fetchdf.return_value = fake_df

    instr = MagicMock()
    instr.name_cn = "华泰柏瑞沪深300ETF"
    instr.asset_class = "cn_etf"
    instr.market = "cn_on_exchange"
    instr.theme = None
    instr.tracked_index = "沪深300"
    instr.venue_required = ["cn_brokerage"]

    inp = _build_input(
        score_row=score_row,
        instr=instr,
        holding=None,
        target_band=None,
        portfolio_total_cny=0.0,
        available_venues={"cn_brokerage"},
        con=con,
    )
    assert inp.name_cn == "华泰柏瑞沪深300ETF"
