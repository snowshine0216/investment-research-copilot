from __future__ import annotations

from irc.monitor.holding_metrics import flow_band as flow_score  # noqa: F401

# D7 band thresholds (percent-points), documented here for the factor layer.
# Single source of truth is holding_metrics.flow_band; flow_score re-exports it.
_FLOW_BANDS = ((3.0, 1.0), (1.0, 0.5), (-1.0, 0.0), (-3.0, -0.5), (-1e18, -1.0))

_VALUATION_MAP: dict[str, float] = {
    "cheap": 1.0, "reasonable_low": 0.5, "fair": 0.0,
    "expensive": -0.5, "very_expensive": -1.0,
}
_RAPID_INFLOW_PCT = 20.0   # AUM/share QoQ Δ above this counts as a rapid inflow


def valuation_state_score(state: str) -> float | None:
    """Fixed map; None for an unrecognised state (→ N/A upstream)."""
    return _VALUATION_MAP.get(state)


def heat_score(*, restricted: bool | None, aum_delta_pct: float | None) -> float | None:
    """Crowding index → overheated -1 … calm +0.3. None when NO data (§4)."""
    if restricted is None and aum_delta_pct is None:
        return None
    rapid = aum_delta_pct is not None and aum_delta_pct >= _RAPID_INFLOW_PCT
    if restricted and rapid:
        return -1.0
    if restricted or rapid:
        return -0.5
    return 0.3
