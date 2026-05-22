"""Deterministic citation selector — single source of truth for picks-table
(D0e) and memo evidence-pool (D1a).

Pure function. Two input tuples with the same set of entries (different order)
produce the same output tuple. Guarantees ≥1 data-leg AND ≥1 information-leg
when both are present in the input. Locked by `tests/memo/test_citation_selector.py`.

See `docs/adr/0001-citation-data-model.md` §3 for the invariant.
"""
from __future__ import annotations

from irc.opportunity.types import ThesisEvidence


def _scope_rank(scope: str) -> int:
    """instrument/constituent → 2; asset_class_macro/policy → 1."""
    if scope in ("instrument", "constituent"):
        return 2
    return 1


def _slot_key(e: ThesisEvidence) -> tuple[int, float, str, str]:
    """Cross-slot ranking ignores citation_kind. Used for `max(..., key=_slot_key)`.

    `holding_weight_pct` is sourced from `e.holding_weight_pct` if present
    (item 003 adds it to constituent-scoped evidence); otherwise 0.0.
    """
    weight = getattr(e, "holding_weight_pct", 0.0) or 0.0
    return (_scope_rank(e.scope), float(weight), e.date, e.citation_id)


def select_citations(
    entries: tuple[ThesisEvidence, ...],
    cap: int = 3,
) -> tuple[ThesisEvidence, ...]:
    """Pick at most `cap` citations from `entries`.

    Algorithm:
      1. Pick the highest-ranked entry with `citation_kind == "data"` AND
         `scope in {"instrument", "constituent"}` (data slot).
      2. Pick the highest-ranked entry with `citation_kind == "information"`
         (info slot), if distinct from the data pick.
      3. Fill remaining slots up to `cap` from un-picked entries by sort key.
      4. Re-sort the result for stable rendering:
         `(scope_rank desc, date desc, citation_id asc)`.
    """
    if not entries or cap <= 0:
        return ()

    data_candidates = [
        e for e in entries
        if e.citation_kind == "data"
        and e.scope in ("instrument", "constituent")
    ]
    data_pick = max(data_candidates, key=_slot_key) if data_candidates else None

    info_candidates = [e for e in entries if e.citation_kind == "information"]
    info_pick = max(info_candidates, key=_slot_key) if info_candidates else None

    selected: list[ThesisEvidence] = []
    if data_pick is not None:
        selected.append(data_pick)
    if info_pick is not None and info_pick is not data_pick:
        selected.append(info_pick)

    # Fill remaining slot(s) up to cap.
    remaining = [e for e in entries if e not in selected]
    remaining.sort(key=_slot_key, reverse=True)
    for e in remaining:
        if len(selected) >= cap:
            break
        selected.append(e)

    # Stable rendering order. Two-pass: stable-sort by citation_id ascending,
    # then stable-sort by (scope_rank desc, date desc). Python's sort is
    # stable, so equal keys preserve the prior pass's order.
    selected.sort(key=lambda e: e.citation_id)
    selected.sort(key=lambda e: (_scope_rank(e.scope), e.date), reverse=True)
    return tuple(selected)
