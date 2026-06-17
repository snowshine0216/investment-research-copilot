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
from dataclasses import dataclass
from pathlib import Path

import duckdb

from irc.opportunity.inputs_loader import _index_valuation_metrics
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


@dataclass(frozen=True)
class ValuationResolution:
    """Frozen result of resolving one fund's monitor valuation state.

    state: unified-vocab valuation state (factor_maps._VALUATION_MAP key) or None.
    cached: True iff a real cached percentile produced the state (drives
            FactorInputs.valuation_cached → the _valuation eligibility gate).
    reason: N/A reason code (a KNOWN_NA_REASONS member) when state is None, else None.
    """
    state: str | None
    cached: bool
    reason: str | None


def _tracked_index_for_fund(con: duckdb.DuckDBPyConnection, fund_id: str) -> str | None:
    """EDGE (cached read): the fund's tracked_index from the instruments table —
    the SAME source the opportunity layer uses (inputs_build.py: instr.tracked_index),
    so monitor and opportunity agree. Absent row / null → None (→ look-through)."""
    df = con.execute(
        "SELECT tracked_index FROM instruments WHERE instrument_id = ?",
        [fund_id],
    ).fetchdf()
    if df.empty:
        return None
    value = df.iloc[0]["tracked_index"]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _resolve_index(con: duckdb.DuckDBPyConnection, tracked_index: str) -> ValuationResolution:
    """Index-anchored branch: reuse the opportunity pure derivation on cached data.
    _index_valuation_metrics returns (pe, pb, div, pe_pct, pb_pct); we map pe_pct."""
    _, _, _, pe_pct, _ = _index_valuation_metrics(con, tracked_index)
    state = percentile_to_valuation_state(pe_pct)
    if state is None:
        return ValuationResolution(None, False, _NA_NO_ANCHOR)
    return ValuationResolution(state, True, None)


def _resolve_lookthrough(
    con: duckdb.DuckDBPyConnection, fund_id: str, root: Path
) -> ValuationResolution:
    """Look-through branch (tracked_index is None, pure active funds).

    STUB — item 002 fills this in: assemble the cached look-through inputs from
    the monitor's already-loaded active-fund snapshot holdings + cached stock
    valuations, call opportunity/lookthrough_valuation.fund_valuation_percentile,
    then percentile_to_valuation_state. Until then, honest N/A (never fabricate).
    Contract item 002 must preserve: return ValuationResolution(state, cached,
    reason) where cached is True ONLY on a real percentile, reason is a
    KNOWN_NA_REASONS member (valuation_no_anchor) on a miss, and the (con, fund_id,
    root) inputs are sufficient (no opportunity output-file reads — ADR 0017)."""
    return ValuationResolution(None, False, _NA_NO_ANCHOR)


def resolve_valuation_state(
    fund, *, con: duckdb.DuckDBPyConnection, root: Path
) -> ValuationResolution:
    """PURE-ish dispatch (cached reads only): index path when the fund has a
    tracked_index, else the look-through stub. Never raises on a data miss —
    degrades to an honest N/A so the brief never crashes."""
    tracked_index = _tracked_index_for_fund(con, fund.id)
    if tracked_index is not None:
        return _resolve_index(con, tracked_index)
    return _resolve_lookthrough(con, fund.id, root)
