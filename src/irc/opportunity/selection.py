from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from irc.opportunity.types import OpportunityRow


@dataclass(frozen=True)
class SelectionQuality:
    expense_ratio: float | None
    aum_cny: float | None
    tracking_error: float | None
    premium_discount_abs: float | None
    history_days: int | None
    data_completeness: float


def _rank_key(q: SelectionQuality) -> tuple[float, float, float, float, float, float]:
    """Sort key for instrument quality — lower is better.

    Order: ER asc, -AUM asc (larger AUM first), tracking_error asc,
    premium_discount_abs asc, -history asc, -data_completeness asc.
    """
    return (
        q.expense_ratio if q.expense_ratio is not None else 1.0,
        -(q.aum_cny if q.aum_cny is not None else 0.0),
        q.tracking_error if q.tracking_error is not None else 1.0,
        q.premium_discount_abs if q.premium_discount_abs is not None else 1.0,
        -(q.history_days if q.history_days is not None else 0),
        -q.data_completeness,
    )


def reduce_same_index(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    qualities: dict[str, SelectionQuality],
) -> tuple[OpportunityRow, OpportunityRow | None, tuple[OpportunityRow, ...]]:
    """Pick one primary + at most one backup for instruments sharing
    a lookthrough key. Remaining rows are returned as dropped.

    This function is available for callers that need explicit per-index
    primary+backup selection (e.g. displaying an alternative instrument).
    The ``reduce_same_theme`` Stage 1 keeps only the single best per key
    (no backup) to stay conservative; wiring per-index backups into the
    default pipeline is tracked in TODOS.md.
    """
    if not rows:
        raise ValueError("rows must be non-empty")
    sorted_rows = sorted(
        rows, key=lambda r: _rank_key(qualities[r.instrument_id]),
    )
    primary = sorted_rows[0]
    backup = sorted_rows[1] if len(sorted_rows) >= 2 else None
    dropped = tuple(sorted_rows[2:])
    return primary, backup, dropped


def reduce_same_theme(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    qualities: dict[str, SelectionQuality],
    max_per_theme: int = 2,
) -> tuple[tuple[OpportunityRow, ...], tuple[OpportunityRow, ...]]:
    """Two-stage reduction:
      1. Collapse rows that share a lookthrough key (same index / clone)
         to a single representative — the highest-quality one.
      2. Within a theme, keep at most `max_per_theme` distinct
         lookthrough keys, ranked by best representative quality.

    Returns (kept, dropped).
    """
    if max_per_theme < 1:
        raise ValueError("max_per_theme must be >= 1")
    # Stage 1: group by lookthrough key, keep best.
    by_key: dict[str, list[OpportunityRow]] = {}
    for r in rows:
        by_key.setdefault(r.lookthrough_target.key, []).append(r)
    per_key_best: list[OpportunityRow] = []
    per_key_dropped: list[OpportunityRow] = []
    for key, group in by_key.items():
        ordered = sorted(group, key=lambda r: _rank_key(qualities[r.instrument_id]))
        per_key_best.append(ordered[0])
        per_key_dropped.extend(ordered[1:])
    # Stage 2: cap distinct keys per theme.
    ordered_by_quality = sorted(
        per_key_best, key=lambda r: _rank_key(qualities[r.instrument_id]),
    )
    kept: list[OpportunityRow] = []
    kept_keys: set[str] = set()
    overflow: list[OpportunityRow] = []
    for r in ordered_by_quality:
        if len(kept) < max_per_theme and r.lookthrough_target.key not in kept_keys:
            kept.append(r)
            kept_keys.add(r.lookthrough_target.key)
        else:
            overflow.append(r)
    return tuple(kept), tuple(per_key_dropped + overflow)


def demote_unstable_active(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    qualities: dict[str, SelectionQuality],
) -> tuple[tuple[OpportunityRow, ...], tuple[OpportunityRow, ...]]:
    """Downgrade active fund rows to ``small_watch`` when a passive alternative
    in the same theme exists with equal or better SelectionQuality.

    Active funds are identified by ``lookthrough_target.kind == "active_fund"``.
    A passive alternative is any row in the same theme where the kind is not
    ``"active_fund"``. Demotion is applied only when the opportunity_state is
    not already ``"exclude"`` (exits should not be upgraded to small_watch).

    Returns ``(all_rows_with_demotions, demoted_rows)`` where demoted_rows is
    a tuple of the original (pre-demotion) rows for logging / diagnostics.
    """
    # Build best passive quality per theme for comparison.
    best_passive_key: dict[str | None, tuple] = {}
    for r in rows:
        if r.lookthrough_target.kind == "active_fund":
            continue
        q = qualities.get(r.instrument_id)
        if q is None:
            continue
        key = _rank_key(q)
        if r.theme not in best_passive_key or key < best_passive_key[r.theme]:
            best_passive_key[r.theme] = key

    out: list[OpportunityRow] = []
    demoted: list[OpportunityRow] = []
    for r in rows:
        if (
            r.lookthrough_target.kind == "active_fund"
            and r.opportunity_state != "exclude"
        ):
            passive_best = best_passive_key.get(r.theme)
            active_key = _rank_key(qualities[r.instrument_id]) if r.instrument_id in qualities else None
            if passive_best is not None and active_key is not None and passive_best <= active_key:
                demoted.append(r)
                r = dataclasses.replace(r, opportunity_state="small_watch")
        out.append(r)
    return tuple(out), tuple(demoted)
