from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd


@dataclass(frozen=True)
class FilteredCandidates:
    kept: pd.DataFrame
    dropped: list[dict[str, Any]]


def drop_correlated_and_renormalize(
    selected: list[dict],
    corr_matrix: dict[tuple[str, str], float],
    threshold: float,
) -> list[dict]:
    """Drop high-correlation pairs within each asset class (keeping the higher-weighted),
    then renormalize weights within each class so they sum to 1.0.
    """
    by_class: dict[str, list[dict]] = {}
    for r in selected:
        by_class.setdefault(r["asset_class"], []).append(r)
    kept: list[dict] = []
    for cls, rows in by_class.items():
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
        total = sum(r["target_weight"] for r in kept_rows) or 1.0
        kept.extend(
            {**r, "target_weight": r["target_weight"] / total} for r in kept_rows
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
