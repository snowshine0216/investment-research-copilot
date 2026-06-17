"""PURE valuation resolution for `irc monitor` (reuses the opportunity engine).

Reuse boundary (ADR 0017 monitor evidence isolation): this module calls the
opportunity layer's *pure functions* (`_index_valuation_metrics`, the shared
`_VALUATION_BANDS`/`_band`) on monitor-loaded CACHED DuckDB tables. It does NOT
depend on the opportunity *pipeline* having run, and NEVER reads opportunity
*output files*. The only effect here is cached DuckDB reads, confined to the
thin query wrapper `_tracked_index_for_fund`; the dispatch + mapping is pure.

Slice 1 (item 001) wires the INDEX-anchored branch. The look-through branch is
an honest N/A stub filled in by item 002 (see `_resolve_lookthrough`).
"""
from __future__ import annotations

import math

from irc.opportunity.states import _band

_NA_NO_ANCHOR = "valuation_no_anchor"


def percentile_to_valuation_state(pct: float | None) -> str | None:
    """Map a 0..1 valuation percentile to a unified-vocab state, or None.

    DRY: the band thresholds live in opportunity/states._VALUATION_BANDS and are
    applied by `_band`; we only add the None/NaN guard. None/NaN → None (→ N/A).
    """
    if pct is None or math.isnan(pct):
        return None
    return _band(float(pct))
