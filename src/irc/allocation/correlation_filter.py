from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd


@dataclass(frozen=True)
class FilteredCandidates:
    kept: pd.DataFrame
    dropped: list[dict[str, Any]]


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
