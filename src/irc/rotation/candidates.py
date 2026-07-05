"""PURE: emerging/hot boards × exposure matrix → ranked rotation candidates (§5).

Per emerging/hot board: top 10 funds by exposure_pct ≥10%. Each row annotates
existing-surface membership + holdings_as_of (staleness stated, never hidden).
new_candidates rollup = candidate funds on NO existing surface. No I/O.
"""
from __future__ import annotations

from collections.abc import Iterable

from irc.rotation.types import BoardState, ExposureRow, RotationCandidate

MIN_EXPOSURE_PCT = 10.0
CAND_TOP_N = 10
_ACTIVE_STATES = frozenset({"emerging", "hot"})


def rank_candidates(
    exposure_rows: Iterable[ExposureRow],
    board_states: Iterable[BoardState],
    *,
    discovered_watchlist: frozenset[str],
    monitor_set: frozenset[str],
    held: frozenset[str],
    min_exposure_pct: float = MIN_EXPOSURE_PCT,
    top_n: int = CAND_TOP_N,
) -> tuple[tuple[RotationCandidate, ...], tuple[str, ...]]:
    active: dict[str, str] = {b.board_code: b.board_name for b in board_states
                             if b.state in _ACTIVE_STATES}
    by_board: dict[str, list[ExposureRow]] = {}
    for r in exposure_rows:
        if r.board_code in active and r.exposure_pct >= min_exposure_pct:
            by_board.setdefault(r.board_code, []).append(r)
    cands: list[RotationCandidate] = []
    for code, rows in sorted(by_board.items()):
        ranked = sorted(rows, key=lambda r: (-r.exposure_pct, r.fund_id))[:top_n]
        for r in ranked:
            cands.append(RotationCandidate(
                fund_id=r.fund_id, name_cn=r.name_cn, board_code=code,
                board_name=active[code], exposure_pct=r.exposure_pct,
                on_discovered_watchlist=r.fund_id in discovered_watchlist,
                in_monitor_set=r.fund_id in monitor_set,
                held=r.fund_id in held, holdings_as_of=r.holdings_as_of))
    on_surface = discovered_watchlist | monitor_set | held
    new = tuple(sorted({c.fund_id for c in cands if c.fund_id not in on_surface}))
    return tuple(cands), new
