from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd
from irc.allocation.target_weights import compute_target_weights, softmax_distribute
from irc.allocation.correlation_filter import drop_high_correlation_pairs, drop_correlated_and_renormalize


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


def run_allocation(
    scores: list[dict],
    class_targets: dict[str, dict[str, object]],
    gold_tilt: str,
    correlation: pd.DataFrame,
    per_class_top_k: int = 2,
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
                "composite_score": row["composite_score"],
                "intra_class_share": w,
                "target_weight": class_weights.get(cls, 0.0) * w,
            })
    if not correlation.empty:
        cand_df = pd.DataFrame([
            {"instrument_id": s["instrument_id"], "score": s["composite_score"], "asset_class": s["asset_class"]}
            for s in selected
        ])
        filt = drop_high_correlation_pairs(cand_df, correlation, threshold=0.85)
        kept_ids = set(filt.kept["instrument_id"])
        selected = [s for s in selected if s["instrument_id"] in kept_ids]
        dropped = filt.dropped
    else:
        dropped = []
    # Renormalize intra-class weights after any drops, using empty corr dict (no further drops)
    selected = drop_correlated_and_renormalize(selected, corr_matrix={}, threshold=0.85)
    eff_n = _effective_n([s["target_weight"] for s in selected])
    invested = sum(s["target_weight"] for s in selected)
    # Honest accounting of the unallocated portion. Classes that lack a scored
    # instrument (e.g., `cash` always, `hk_etf` when discovery returns nothing)
    # leave a hole — surface it as cash_residual so total + cash ≈ 1.0 instead
    # of pretending the allocation covers the whole portfolio.
    cash_residual = max(0.0, 1.0 - invested)
    return AllocationOutput(
        target_weights_per_class=class_weights,
        selected_instruments=selected,
        dropped_due_to_correlation=dropped,
        diagnostics={"effective_n": eff_n,
                     "total_weight": invested,
                     "cash_residual_weight": cash_residual},
    )
