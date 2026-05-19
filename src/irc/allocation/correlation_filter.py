from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd


@dataclass(frozen=True)
class FilteredCandidates:
    kept: pd.DataFrame
    dropped: list[dict[str, Any]]


def _tracked_index_key(row: dict[str, Any]) -> str:
    return str(row.get("tracked_index") or "").strip().lower()


def drop_duplicate_index_trackers(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Within each asset_class, dedupe rows that share a tracked_index.

    Two S&P500 share classes (e.g. 017641 + 050025) carry the same
    ``tracked_index``; they are 99%+ correlated and represent the same
    factor exposure. Keep the row with the higher ``target_weight``
    (tie-broken by ``composite_score`` then ``instrument_id``) and drop
    the rest. Rows with an empty / missing ``tracked_index`` are passed
    through unchanged — we never silently dedupe an active fund whose
    holdings happen to overlap.

    Returns (kept, dropped). Each dropped entry carries a
    ``reason: duplicate_tracked_index`` and a ``kept_against`` field so
    diagnostics can surface the decision.
    """
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    pass_through: list[dict[str, Any]] = []
    for row in rows:
        idx = _tracked_index_key(row)
        if not idx:
            pass_through.append(dict(row))
            continue
        cls = str(row.get("asset_class") or "")
        by_group.setdefault((cls, idx), []).append(row)
    kept: list[dict[str, Any]] = list(pass_through)
    dropped: list[dict[str, Any]] = []
    for group_rows in by_group.values():
        sorted_rows = sorted(
            group_rows,
            key=lambda r: (
                -float(r.get("target_weight", 0.0)),
                -float(r.get("composite_score", 0.0)),
                str(r.get("instrument_id", "")),
            ),
        )
        winner = sorted_rows[0]
        kept.append(dict(winner))
        for loser in sorted_rows[1:]:
            dropped.append({
                "instrument_id": loser["instrument_id"],
                "asset_class": loser.get("asset_class"),
                "tracked_index": loser.get("tracked_index"),
                "kept_against": winner["instrument_id"],
                "reason": "duplicate_tracked_index",
            })
    return kept, dropped


def drop_correlated_and_renormalize(
    selected: list[dict],
    corr_matrix: dict[tuple[str, str], float],
    threshold: float,
) -> list[dict]:
    """Drop high-correlation pairs within each asset class (keeping the higher-weighted),
    then renormalize the kept items' target_weight so the within-class sum is
    preserved at its pre-drop value.

    Preserving the pre-drop class total (rather than rescaling to 1.0) keeps the
    portfolio's per-class weighting intact: the global ``sum(target_weight)``
    matches ``sum(class_weights)`` regardless of how many duplicates were
    dropped. Rescaling to 1.0 silently turns target_weight into an intra-class
    share, which makes the diagnostics' total_weight equal the number of
    represented classes instead of 1.0.
    """
    by_class: dict[str, list[dict]] = {}
    for r in selected:
        by_class.setdefault(r["asset_class"], []).append(r)
    kept: list[dict] = []
    for cls, rows in by_class.items():
        class_total = sum(r["target_weight"] for r in rows)
        rows_sorted = sorted(rows, key=lambda r: -r["target_weight"])
        keep_ids: list[str] = []
        for r in rows_sorted:
            iid = r["instrument_id"]
            collides = any(
                corr_matrix.get((iid, k), corr_matrix.get((k, iid), 0.0)) >= threshold
                for k in keep_ids
            )
            if not collides:
                keep_ids.append(iid)
        kept_rows = [r for r in rows if r["instrument_id"] in keep_ids]
        kept_total = sum(r["target_weight"] for r in kept_rows)
        scale = (class_total / kept_total) if kept_total > 0 else 0.0
        kept.extend(
            {**r, "target_weight": r["target_weight"] * scale} for r in kept_rows
        )
    return kept


def drop_high_correlation_pairs(
    candidates: pd.DataFrame, corr_matrix: pd.DataFrame, threshold: float,
) -> FilteredCandidates:
    """For any pair with correlation > threshold, keep the higher-scored instrument."""
    sorted_c = candidates.sort_values("score", ascending=False).reset_index(drop=True)
    kept_ids: list[str] = []
    dropped: list[dict[str, Any]] = []
    for _, row in sorted_c.iterrows():
        iid = row["instrument_id"]
        skip = False
        for kept in kept_ids:
            if iid in corr_matrix.index and kept in corr_matrix.columns:
                rho = corr_matrix.loc[iid, kept]
                if rho > threshold:
                    dropped.append({"instrument_id": iid, "dropped_due_to": kept, "rho": float(rho)})
                    skip = True
                    break
        if not skip:
            kept_ids.append(iid)
    kept_df = sorted_c[sorted_c["instrument_id"].isin(kept_ids)].reset_index(drop=True)
    return FilteredCandidates(kept=kept_df, dropped=dropped)
