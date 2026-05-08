from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from scipy.stats import spearmanr


@dataclass(frozen=True)
class SanityResult:
    rho: float
    p_value: float
    status: str  # "PASS" | "WARN" | "HARD_FAIL"
    n_instruments: int


def historical_sanity_correlation(
    scores: pd.DataFrame,
    realized: pd.DataFrame,
    weak_threshold: float = 0.10,
) -> SanityResult:
    """Spearman ρ between composite_score and realized_risk_adj_return.
    Status: ρ ≤ 0 → HARD_FAIL; ρ ≤ weak_threshold → WARN; else → PASS.
    """
    merged = scores.merge(realized, on="instrument_id", how="inner")
    if merged.empty or len(merged) < 4:
        return SanityResult(
            rho=0.0, p_value=1.0, status="HARD_FAIL", n_instruments=len(merged)
        )
    rho, pval = spearmanr(merged["composite_score"], merged["realized_risk_adj_return"])
    if rho <= 0:
        status = "HARD_FAIL"
    elif rho <= weak_threshold:
        status = "WARN"
    else:
        status = "PASS"
    return SanityResult(
        rho=float(rho),
        p_value=float(pval),
        status=status,
        n_instruments=len(merged),
    )
