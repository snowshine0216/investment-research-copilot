"""PURE look-through valuation math for `irc monitor` (no I/O).

Maps a monitor `ActiveFundSnapshot`'s holdings + a per-code PE/PB series map to a
unified-vocab valuation state, reusing the opportunity layer's pure
`fund_valuation_percentile`. The coverage gate lives INSIDE that function (None
percentile when covered NAV ratio < floor or PE history immature) → None state.

ADR 0017: the snapshot is the monitor's OWN cache and the series map comes from
the cached `stock_valuation_history`; both are monitor-consumed cached artifacts,
not opportunity output files. This module performs NO I/O — callers pass the
already-loaded snapshot + series.
"""
from __future__ import annotations

from irc.fundamentals.types import ActiveFundSnapshot
from irc.monitor.valuation import percentile_to_valuation_state
from irc.opportunity.lookthrough_valuation import (
    HoldingWeight,
    MetricSeries,
    fund_valuation_percentile,
)

# Mirror ActiveFundLookthroughConfig defaults (schemas/valuation.py) so monitor
# and opportunity gate identically. The look-through factor keys on PE.
_COVERAGE_FLOOR = 0.50
_PB_USES_PE_GATE = False


def _holdings_from_snapshot(snapshot: ActiveFundSnapshot) -> tuple[HoldingWeight, ...]:
    """Map the snapshot's constituents to HoldingWeight (code=6-digit symbol,
    weight_pct in 0..100 — identical units). Non-A-share symbols pass through
    unchanged; they simply won't match the A-share-keyed series map."""
    return tuple(
        HoldingWeight(code=c.symbol, weight_pct=c.weight_pct)
        for c in snapshot.constituent_analyses
    )


def lookthrough_valuation_state(
    snapshot: ActiveFundSnapshot,
    series_by_code: dict[str, MetricSeries],
) -> str | None:
    """Pure: snapshot holdings + per-code PE/PB series → valuation state or None.
    None when holdings empty, coverage below floor, or PE history immature."""
    holdings = _holdings_from_snapshot(snapshot)
    if not holdings:
        return None
    result = fund_valuation_percentile(
        holdings, series_by_code,
        coverage_floor=_COVERAGE_FLOOR, pb_uses_pe_gate=_PB_USES_PE_GATE,
    )
    return percentile_to_valuation_state(result.pe.percentile)
