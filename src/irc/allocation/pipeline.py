from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd
from irc.allocation.target_weights import (
    DEFAULT_SATELLITE_QDII_MAX_WEIGHT,
    cap_satellite_qdii,
    compute_target_weights,
    is_satellite_qdii,
    redistribute_shaved_to_class,
    softmax_distribute,
)
from irc.allocation.correlation_filter import (
    drop_duplicate_index_trackers,
    drop_high_correlation_pairs,
)


@dataclass(frozen=True)
class AllocationOutput:
    target_weights_per_class: dict[str, float]
    selected_instruments: list[dict[str, Any]]
    dropped_due_to_correlation: list[dict[str, Any]]
    diagnostics: dict[str, float]


def _select_top_k_per_class(scores: list[dict], k: int) -> dict[str, list[dict]]:
    """Pick up to `k` instruments per asset_class with role-aware diversity.

    Two-phase greedy within each class:
      1. Walk candidates by descending score; take the first one from each
         distinct `role`. Ensures every represented role gets a slot before
         duplicates compete.
      2. If fewer than `k` slots are filled (more slots than distinct roles),
         backfill by raw composite_score from the remaining candidates.

    Without this, 4 high-scored 沪深300 ETFs (all role=core_cn_equity) would
    crowd out the single 中证红利 / 央企创新 candidate even though they're
    near-clones — the discovery's role-based diversity would silently
    collapse at allocate. Rows without a `role` field are treated as a single
    anonymous role, preserving the old pure-score behavior in that case.
    """
    by_class: dict[str, list[dict]] = {}
    for s in scores:
        by_class.setdefault(s["asset_class"], []).append(s)
    if k <= 0:
        return {cls: [] for cls in by_class}
    for cls, rows in by_class.items():
        ranked = sorted(rows, key=lambda r: r["composite_score"], reverse=True)
        seen_roles: set[str] = set()
        picks: list[dict] = []
        for r in ranked:
            role = r.get("role") or ""
            if role in seen_roles:
                continue
            picks.append(r)
            seen_roles.add(role)
            if len(picks) >= k:
                break
        if len(picks) < k:
            for r in ranked:
                if r in picks:
                    continue
                picks.append(r)
                if len(picks) >= k:
                    break
        by_class[cls] = picks
    return by_class


def _effective_n(weights: list[float]) -> float:
    """1 / sum(w_i^2). Higher = more diversified."""
    if not weights:
        return 0.0
    s = sum(w * w for w in weights)
    return 1.0 / s if s > 0 else 0.0


def _class_weight_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        asset_class = row["asset_class"]
        totals[asset_class] = totals.get(asset_class, 0.0) + row["target_weight"]
    return totals


def _keep_and_preserve_class_totals(
    selected: list[dict[str, Any]],
    kept_ids: set[str],
) -> list[dict[str, Any]]:
    kept_rows = [row for row in selected if row["instrument_id"] in kept_ids]
    pre_drop_totals = _class_weight_totals(selected)
    kept_totals = _class_weight_totals(kept_rows)

    return [
        {
            **row,
            "target_weight": row["target_weight"]
            * (pre_drop_totals[row["asset_class"]] / kept_totals[row["asset_class"]]),
        }
        for row in kept_rows
        if kept_totals.get(row["asset_class"], 0.0) > 0
    ]


def _apply_satellite_qdii_cap(
    selected: list[dict[str, Any]],
    cap: float,
) -> tuple[list[dict[str, Any]], float]:
    """Cap satellite-role QDII rows and redistribute the shaved weight.

    Strategy: shaved weight first tries to spill back into the same QDII
    class (giving headroom to a non-capped peer); whatever doesn't fit
    becomes cash residual (returned as the second tuple element).
    """
    if cap <= 0:
        return selected, 0.0
    capped_rows, shaved = cap_satellite_qdii(selected, cap=cap)
    if shaved <= 0:
        return capped_rows, 0.0
    qdii_classes_present = {
        r["asset_class"] for r in capped_rows if is_satellite_qdii(r)
    }
    remaining = shaved
    rows = capped_rows
    for cls in sorted(qdii_classes_present):
        if remaining <= 0:
            break
        rows, remaining = redistribute_shaved_to_class(rows, remaining, cls, cap=cap)
    return rows, remaining


def run_allocation(
    scores: list[dict],
    class_targets: dict[str, dict[str, object]],
    gold_tilt: str,
    correlation: pd.DataFrame,
    per_class_top_k: int = 2,
    satellite_qdii_cap: float = DEFAULT_SATELLITE_QDII_MAX_WEIGHT,
) -> AllocationOutput:
    """Compose Stage 5 allocation:
    1. apply gold_tilt to class centers
    2. select top-K per class with role-aware diversity, then score backfill
    3. softmax-distribute class weight across selected instruments
    4. correlation_filter drops near-duplicates
    """
    class_weights_obj = compute_target_weights(class_targets, gold_tilt=gold_tilt)
    class_weights: dict[str, float] = {k: v.target_weight for k, v in class_weights_obj.items()}
    by_class = _select_top_k_per_class(scores, per_class_top_k)
    selected: list[dict[str, Any]] = []
    for cls, rows in by_class.items():
        if not rows:
            continue
        scores_arr = tuple(r["composite_score"] for r in rows)
        share = softmax_distribute(scores_arr, temperature=10.0)
        for row, w in zip(rows, share):
            selected.append({
                "instrument_id": row["instrument_id"], "asset_class": cls,
                "role": row.get("role", ""),
                "tracked_index": row.get("tracked_index", ""),
                "composite_score": row["composite_score"],
                "intra_class_share": w,
                "target_weight": class_weights.get(cls, 0.0) * w,
            })
    # Dedupe by tracked_index BEFORE the numeric correlation filter:
    # two S&P500 share classes are deterministically the same factor
    # exposure, so we don't need a correlation matrix to drop the dup.
    pre_dedupe_selected = list(selected)
    selected, index_dupes = drop_duplicate_index_trackers(selected)
    if index_dupes:
        kept_ids = {r["instrument_id"] for r in selected}
        # Renormalize per class so the class total is preserved
        # (the dedupe takes weight away; the remaining row absorbs it).
        selected = _keep_and_preserve_class_totals(pre_dedupe_selected, kept_ids)
    if not correlation.empty:
        cand_df = pd.DataFrame([
            {"instrument_id": s["instrument_id"], "score": s["composite_score"], "asset_class": s["asset_class"]}
            for s in selected
        ])
        filt = drop_high_correlation_pairs(cand_df, correlation, threshold=0.85)
        kept_ids = set(filt.kept["instrument_id"])
        selected = _keep_and_preserve_class_totals(selected, kept_ids)
        dropped = list(filt.dropped)
    else:
        dropped = []
    dropped = list(index_dupes) + dropped
    selected, satellite_qdii_residual = _apply_satellite_qdii_cap(selected, satellite_qdii_cap)
    eff_n = _effective_n([s["target_weight"] for s in selected])
    invested = sum(s["target_weight"] for s in selected)
    # Honest accounting of the unallocated portion. Classes that lack a scored
    # instrument (e.g., `cash` always, `hk_etf` when discovery returns nothing)
    # leave a hole — surface it as cash_residual so total + cash ≈ 1.0 instead
    # of pretending the allocation covers the whole portfolio.
    cash_residual = max(0.0, 1.0 - invested)
    diagnostics: dict[str, float] = {
        "effective_n": eff_n,
        "total_weight": invested,
        "cash_residual_weight": cash_residual,
    }
    if satellite_qdii_residual > 0:
        diagnostics["satellite_qdii_excess_to_cash"] = satellite_qdii_residual
    return AllocationOutput(
        target_weights_per_class=class_weights,
        selected_instruments=selected,
        dropped_due_to_correlation=dropped,
        diagnostics=diagnostics,
    )
