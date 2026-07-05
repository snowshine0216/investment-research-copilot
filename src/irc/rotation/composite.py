"""PURE: per-day cross-sectional percentiles → rotation composite (spec §6, D4).

Composite = 0.5·pct(mom20) + 0.3·pct(flow5) + 0.2·pct(turnΔ). mom20 = 20-td
cumulative chg minus the cross-board median. flow5 = mean main_inflow_ratio over
last 5 td. turnΔ = (5-td mean turnover / 20-td mean turnover) - 1. Percentiles
cross-sectional over boards with ≥20 td of history. Each of the flow and turn
legs independently goes dark (dropped for ALL boards, weights renormalized over
the remaining usable legs) when any board can't compute that leg — never
per-board mixing, never carry-forward (D6). pe_percentiles ranks board PE
cross-sectionally (chase_risk input, §6) over boards that HAVE a PE. No I/O.
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
        # None (not 0.0): backfill kline rows carry turnover_pct=None (kline
        # fields2 have no turnover — see board_fetch.py F7), so a board present in
        # the series but absent from today's snapshot (stale/renamed board, or
        # partial snapshot) can have an all-None recent turnover window. Fabricating
        # 0.0 here would be the same per-board-mixing dark-factor bug D6 forbids for
        # the flow leg — honest "uncomputable" instead; see turn_leg_dark below.
        turn_delta = (m5 / m20 - 1) if (m20 not in (None, 0) and m5 is not None) else None
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


def turn_leg_dark(signals: Mapping[str, dict]) -> bool:
    """Pure: is the turn leg unusable for this cross-section? True iff there are no
    boards or ANY board lacks a computable turn_delta. Mirrors flow_leg_dark and
    enforces the same D6 "never per-board mixing" rule: the turn leg is used only
    when EVERY board has a real turn_delta — else it is dropped for ALL boards.
    Catches a board present in the series but absent from today's snapshot
    (stale/renamed board, or partial snapshot) whose recent turnover window is
    all-None (backfill rows carry turnover_pct=None) — the fabricated-0
    dark-factor bug class, symmetric to the flow leg."""
    return (not signals) or any(s["turn_delta"] is None for s in signals.values())


def cross_sectional(signals: Mapping[str, dict], *, flow_dark: bool,
                    turn_dark: bool = False) -> dict[str, float]:
    """Pure: signals → composite percentile per board, via a generalized renorm
    over usable legs. mom is always usable (backfill rows always carry chg_pct).
    The flow leg is dropped for ALL boards when the caller forces `flow_dark` OR
    `flow_leg_dark(signals)` holds; the turn leg is dropped for ALL boards when
    the caller forces `turn_dark` OR `turn_leg_dark(signals)` holds — so a board's
    None flow5/turn_delta is NEVER fabricated to 0.0 while another board scores a
    real value (D6). Weights renormalize over whichever legs remain (both, either,
    or mom-only). When a leg is kept, every value in it is guaranteed non-None
    (screened by the matching *_leg_dark check)."""
    mom = _percentile_ranks({c: s["mom20"] for c, s in signals.items()})
    legs: list[tuple[float, dict[str, float]]] = [(W_MOM, mom)]
    if not (flow_dark or flow_leg_dark(signals)):
        legs.append((W_FLOW, _percentile_ranks({c: s["flow5"] for c, s in signals.items()})))
    if not (turn_dark or turn_leg_dark(signals)):
        legs.append((W_TURN, _percentile_ranks({c: s["turn_delta"] for c, s in signals.items()})))
    total = sum(w for w, _ in legs)
    return {c: sum(w * leg[c] for w, leg in legs) / total for c in signals}


def pe_percentiles(pe_by_board: Mapping[str, float | None]) -> dict[str, float]:
    """Pure (§6 chase_risk input): cross-sectional PE percentile over boards that
    HAVE a PE. PE-less boards (None) are EXCLUDED from the result → their pe_pctl
    is None downstream (the real §6 'missing PE → no flag, noted in diagnostics'
    path). Reuses the composite percentile helper — one ranking definition."""
    present = {c: v for c, v in pe_by_board.items() if v is not None}
    return _percentile_ranks(present)
