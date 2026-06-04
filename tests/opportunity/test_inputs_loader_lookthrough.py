from __future__ import annotations

from datetime import date

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.types import OpportunityInput
from irc.schemas.valuation import ActiveFundLookthroughConfig

# ── helpers ───────────────────────────────────────────────────────────────────

def _seed_index_valuation_history(
    con, index_key: str, pe_pb_pairs: list, base_date: date = date(2025, 1, 1)
) -> None:
    """Mirror of the helper in test_inputs_loader.py for seeding index PE/PB history."""
    rows = []
    for i, (pe, pb) in enumerate(pe_pb_pairs):
        d = date.fromordinal(base_date.toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


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


# ── Finding 1 (P0) regression tests: tracked_index guard ─────────────────────

def _seed_enhanced_index_fund_with_index_history(con) -> None:
    """Seed a cn_equity_fund (enhanced-index) that has a tracked_index=csi300
    with ≥120 points spanning ≥180 days so the index PE percentile is mature."""
    # 200 rising PE/PB pairs → latest is the max → percentile = 1.0
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "csi300", pairs)


def _enhanced_index_skeleton(enabled: bool) -> OpportunityInput:
    """cn_equity_fund WITH tracked_index — an enhanced-index fund."""
    return OpportunityInput(
        instrument_id="EIF1",
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        theme=None,
        tracked_index="csi300",  # has a tracked index — NOT a pure active fund
        name_cn="沪深300增强",
        role="",
        is_holding=False,
        portfolio_weight=None,
        target_band_low=None,
        target_band_high=None,
        venue_compatible=True,
    )


def test_enhanced_index_fund_flag_off_preserves_index_derived_percentile(tmp_path) -> None:
    """Finding 1 (P0) regression: cn_equity_fund WITH tracked_index + flag-off must
    NOT overwrite the index-derived percentile with None.  Before the guard fix the
    active-fund branch ran unconditionally, nuking fund_pct/fund_pct_pb to None."""
    con = _con(tmp_path)
    _seed_enhanced_index_fund_with_index_history(con)
    out = populate_inputs(
        con, _enhanced_index_skeleton(enabled=False), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=False),
    )
    # The index path computed a valid percentile (200 pts, 199-day span → mature).
    # The active-fund branch must NOT have overwritten it with None.
    assert out.valuation_percentile_fundamental is not None, (
        "index-derived percentile was nuked by the active-fund branch "
        "(missing tracked_index is None guard)"
    )
    con.close()


def test_enhanced_index_fund_flag_on_still_uses_index_path(tmp_path) -> None:
    """Enhanced-index funds (cn_equity_fund WITH tracked_index) always use the index
    path, even when the look-through flag is on — the branch must be guarded by
    `tracked_index is None` so it only fires for pure active funds."""
    con = _con(tmp_path)
    _seed_enhanced_index_fund_with_index_history(con)
    out = populate_inputs(
        con, _enhanced_index_skeleton(enabled=True), holding_entry_date=None,
        lookthrough_cfg=ActiveFundLookthroughConfig(enabled=True, coverage_floor=0.50),
    )
    # No fund_holdings rows for EIF1, but the index path has mature data.
    # The percentile must come from the index, not from look-through (which has no data).
    assert out.valuation_percentile_fundamental is not None, (
        "enhanced-index fund's index-derived percentile was lost when flag=on"
    )
    con.close()
