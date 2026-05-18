"""Allocation metric functions.

`in_band_per_class`, `currency_in_tolerance`, and `max_pair_correlation_1y`
read fields the current producer (src/irc/commands/allocate_cmd.py) does
not write. The runner no longer calls them — they are kept here so existing
tests still exercise their logic, and they are candidates for a Phase-2
redesign that decides what the allocation eval should measure against the
current artifact set.
"""
from __future__ import annotations


def weight_sum(allocation: dict) -> float:
    return sum(allocation["target_weights_per_class"].values())


def in_band_per_class(
    allocation: dict,
    bands: dict[str, tuple[float, float]],
) -> float:
    """Fraction of asset classes whose weight is within the specified band."""
    weights = allocation.get("target_weights_per_class", {})
    if not bands:
        return 1.0
    in_band = sum(
        1 for cls, (lo, hi) in bands.items()
        if lo <= weights.get(cls, 0.0) <= hi
    )
    return in_band / len(bands)


def effective_n(allocation: dict) -> float:
    weights = [r["target_weight"] for r in allocation.get("selected_instruments", [])]
    s = sum(w * w for w in weights)
    return 1.0 / s if s > 0 else 0.0


def currency_in_tolerance(
    allocation: dict,
    target_fx: dict[str, float],
    tolerance: float = 0.05,
) -> float:
    """Fraction of currency exposures within tolerance of target."""
    actual = allocation.get("currency_exposure", {})
    if not target_fx:
        return 1.0
    in_tol = sum(
        1 for ccy, tgt in target_fx.items()
        if abs(actual.get(ccy, 0.0) - tgt) <= tolerance
    )
    return in_tol / len(target_fx)


def max_pair_correlation_1y(correlation_matrix: dict[str, dict[str, float]]) -> float:
    """Maximum off-diagonal pairwise correlation from the 1-year matrix."""
    keys = list(correlation_matrix.keys())
    max_corr = 0.0
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            corr = abs(correlation_matrix[k1].get(k2, 0.0))
            if corr > max_corr:
                max_corr = corr
    return max_corr
