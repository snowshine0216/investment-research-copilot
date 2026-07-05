"""PURE: per-day cross-sectional percentiles → rotation composite (spec §6, D4).

Composite = 0.5·pct(mom20) + 0.3·pct(flow5) + 0.2·pct(turnΔ). mom20 = 20-td
cumulative chg minus the cross-board median. flow5 = mean main_inflow_ratio over
last 5 td. turnΔ = (5-td mean turnover / 20-td mean turnover) - 1. Percentiles
cross-sectional over boards with ≥20 td of history. flow_dark → drop the flow
leg for ALL boards, renormalize to 0.71·mom/0.29·turn (never per-board mixing,
never carry-forward). pe_percentiles ranks board PE cross-sectionally (chase_risk
input, §6) over boards that HAVE a PE. No I/O.
"""
from __future__ import annotations

from collections.abc import Mapping
from statistics import median

from irc.rotation.types import BoardDay

W_MOM, W_FLOW, W_TURN = 0.5, 0.3, 0.2
MIN_TD = 20


def _tail_mean(values: list[float], n: int) -> float | None:
    tail = [v for v in values[-n:] if v is not None]
    return sum(tail) / len(tail) if tail else None


def board_signals(series: Mapping[str, tuple[BoardDay, ...]]) -> dict[str, dict]:
    """Pure: per eligible board (≥20 td) → {mom20, flow5, turn_delta}. Boards
    below MIN_TD are excluded (states/diagnostics handle them; no silent cap)."""
    eligible = {c: rows for c, rows in series.items() if len(rows) >= MIN_TD}
    cum = {c: sum(r.chg_pct for r in rows[-MIN_TD:]) for c, rows in eligible.items()}
    med = median(cum.values()) if cum else 0.0
    out: dict[str, dict] = {}
    for c, rows in eligible.items():
        flows = [r.main_inflow_ratio for r in rows]
        turns = [r.turnover_pct for r in rows]
        m20 = _tail_mean(turns, MIN_TD)
        m5 = _tail_mean(turns, 5)
        turn_delta = (m5 / m20 - 1) if (m20 not in (None, 0) and m5 is not None) else 0.0
        out[c] = {"mom20": cum[c] - med,
                  "flow5": _tail_mean(flows, 5),
                  "turn_delta": turn_delta}
    return out


def _percentile_ranks(values: Mapping[str, float]) -> dict[str, float]:
    """Pure: fractional rank in [0,1] (ties share the mean rank). Single board → 0.5."""
    if not values:
        return {}
    if len(values) == 1:
        return {k: 0.5 for k in values}
    ordered = sorted(values.values())
    n = len(ordered)
    out = {}
    for k, v in values.items():
        below = sum(1 for x in ordered if x < v)
        equal = sum(1 for x in ordered if x == v)
        out[k] = (below + (equal - 1) / 2) / (n - 1)
    return out


def flow_leg_dark(signals: Mapping[str, dict]) -> bool:
    """Pure: is the flow leg unusable for this cross-section? True iff there are no
    boards or ANY board lacks a computable flow5. Enforces D6 "never per-board
    mixing": the flow leg is used only when EVERY board has a real flow5 — else it
    is dropped for ALL boards. This catches the post-seed window (backfill rows
    carry main_inflow_ratio=None → flow5 None for every board until ~5 snapshot
    days accumulate) that a today's-snapshot-only gate misses — the fabricated-0
    dark-factor bug class."""
    return (not signals) or any(s["flow5"] is None for s in signals.values())


def cross_sectional(signals: Mapping[str, dict], *, flow_dark: bool
                    ) -> dict[str, float]:
    """Pure: signals → composite percentile per board. The flow leg is dropped for
    ALL boards (renorm 0.71·mom/0.29·turn) when the caller forces `flow_dark` OR
    when `flow_leg_dark(signals)` holds — so a board's None flow5 is NEVER
    fabricated to 0.0 while another scores real flow (D6). When the flow leg is
    kept, every flow5 is guaranteed non-None (flow_leg_dark screened it)."""
    mom = _percentile_ranks({c: s["mom20"] for c, s in signals.items()})
    turn = _percentile_ranks({c: s["turn_delta"] for c, s in signals.items()})
    if flow_dark or flow_leg_dark(signals):
        denom = W_MOM + W_TURN
        return {c: (W_MOM * mom[c] + W_TURN * turn[c]) / denom for c in signals}
    flow = _percentile_ranks({c: s["flow5"] for c, s in signals.items()})
    return {c: W_MOM * mom[c] + W_FLOW * flow[c] + W_TURN * turn[c] for c in signals}


def pe_percentiles(pe_by_board: Mapping[str, float | None]) -> dict[str, float]:
    """Pure (§6 chase_risk input): cross-sectional PE percentile over boards that
    HAVE a PE. PE-less boards (None) are EXCLUDED from the result → their pe_pctl
    is None downstream (the real §6 'missing PE → no flag, noted in diagnostics'
    path). Reuses the composite percentile helper — one ranking definition."""
    present = {c: v for c, v in pe_by_board.items() if v is not None}
    return _percentile_ranks(present)
