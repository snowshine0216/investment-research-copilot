from __future__ import annotations

from datetime import date as date_cls

import duckdb

from irc.fundamentals.provider import CnFundamentalsProvider
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.types import OpportunityInput
from irc.schemas.inputs import Holding
from irc.schemas.universe import Instrument
from irc.schemas.valuation import ActiveFundLookthroughConfig


def _build_input(
    score_row: dict,
    instr: Instrument | None,
    holding: Holding | None,
    target_band: tuple[float, float] | None,
    portfolio_total_cny: float,
    available_venues: set[str],
    con: duckdb.DuckDBPyConnection,
    *,
    provider: CnFundamentalsProvider,
    lookthrough_cfg: ActiveFundLookthroughConfig = ActiveFundLookthroughConfig(),
    activated_sector_slugs: frozenset[str] = frozenset(),
) -> OpportunityInput:
    asset_class = score_row.get("asset_class") or (instr.asset_class if instr else "unknown")
    market = instr.market if instr else "cn_off_exchange"
    theme = instr.theme if instr else None
    tracked_index = instr.tracked_index if instr else None
    # When the instrument isn't in any universe yaml, mark the row with a
    # placeholder rather than the raw id. The discipline report previously
    # rendered "110022 110022" because the fallback was the id itself; the
    # placeholder makes future unknown IDs visually distinct.
    iid = score_row.get("instrument_id", "")
    name_cn = instr.name_cn if instr is not None else f"未登记({iid})"
    weight = None
    if holding is not None and portfolio_total_cny > 0:
        weight = holding.cost_basis_cny / portfolio_total_cny
    # Empty available_venues means no venue restriction configured — treat as compatible.
    if available_venues and instr is not None and instr.venue_required:
        venue_ok = bool(set(instr.venue_required) & available_venues)
    else:
        venue_ok = True
    skeleton = OpportunityInput(
        instrument_id=score_row.get("instrument_id", ""),
        asset_class=asset_class,
        market=market,
        theme=theme,
        tracked_index=tracked_index,
        name_cn=name_cn,
        role=score_row.get("role", ""),
        is_holding=holding is not None,
        portfolio_weight=weight,
        target_band_low=target_band[0] if target_band else None,
        target_band_high=target_band[1] if target_band else None,
        venue_compatible=venue_ok,
    )
    entry_date: date_cls | None = None
    if holding is not None and holding.hold_since:
        try:
            entry_date = date_cls.fromisoformat(holding.hold_since)
        except ValueError:
            pass  # Malformed date string; drawdown_since_entry will remain None
    return populate_inputs(
        con, skeleton,
        holding_entry_date=entry_date,
        provider=provider,
        lookthrough_cfg=lookthrough_cfg,
        activated_sector_slugs=activated_sector_slugs,
    )
