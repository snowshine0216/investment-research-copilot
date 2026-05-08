from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd
from irc.allocation.target_weights import compute_target_weights, softmax_distribute
from irc.allocation.correlation_filter import drop_high_correlation_pairs


@dataclass(frozen=True)
class AllocationOutput:
    target_weights_per_class: dict[str, float]
    selected_instruments: list[dict[str, Any]]
    dropped_due_to_correlation: list[dict[str, Any]]
    diagnostics: dict[str, float]


def _select_top_k_per_class(scores: list[dict], k: int) -> dict[str, list[dict]]:
    by_class: dict[str, list[dict]] = {}
    for s in scores:
        by_class.setdefault(s["asset_class"], []).append(s)
    for cls in by_class:
        by_class[cls] = sorted(by_class[cls], key=lambda r: r["composite_score"], reverse=True)[:k]
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
      2. select top-K per class by score
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
    eff_n = _effective_n([s["target_weight"] for s in selected])
    return AllocationOutput(
        target_weights_per_class=class_weights,
        selected_instruments=selected,
        dropped_due_to_correlation=dropped,
        diagnostics={"effective_n": eff_n,
                     "total_weight": sum(s["target_weight"] for s in selected)},
    )
