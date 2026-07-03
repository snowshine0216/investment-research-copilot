from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ImpactRow:
    key: str            # theme key or holding symbol
    weight: float       # θ_wt (theme weight) or holding_wt
    impact: float       # structured impact ∈ [-1,1]
    confidence: float   # item confidence ∈ [0,1]


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def aggregate_news_factor(rows: tuple[ImpactRow, ...]) -> tuple[float | None, float]:
    """Pure: weight-normalized impact (clamped) + weighted item-confidence.
    Both are divided by Σweight, so the value is scale-invariant (percent-
    scale holding weights and unit theme weights aggregate identically).
    Returns (None, 0.0) when the pool is empty (→ N/A upstream)."""
    if not rows:
        return None, 0.0
    wsum = sum(r.weight for r in rows)
    if wsum <= 0:
        return None, 0.0
    value = _clamp(sum(r.weight * r.impact * r.confidence for r in rows) / wsum)
    conf = sum(r.weight * r.confidence for r in rows) / wsum
    return value, conf
