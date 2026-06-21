"""PURE dual-track scoring helpers for the monitor valuation leg (ADR 0020).

Extracted from holding_metrics.py to keep that file under the 200-line budget.
Public API: industry_band, DualTrack, dual_track_score. All pure/immutable.
"""
from __future__ import annotations

from dataclasses import dataclass

# Dual-track valuation constants (ADR 0020 D3/D5/D9/D10 — priors, never auto-tuned).
_SELF_W = 0.60
_INDUSTRY_W = 0.40
_FALSE_CHEAP_RICHNESS = 1.2  # r >= this → max rich-vs-peers AND clamp trigger

# Per-stock HoldingMetric reasons (NOT factor reasons, NEVER in KNOWN_NA_REASONS).
_REASON_INDUSTRY_NO_DATA = "industry_no_data"
_REASON_FALSE_CHEAP_CLAMP = "false_cheap_clamp"


def industry_band(r: float) -> float:
    """Pure: industry richness r = stock_pe/industry_avg_pe → score in [-1,+1].
    Cheaper-than-peers → positive. ASYMMETRIC bands (slow to call cheap, quick to
    withhold cheap). The -1.0 edge is pinned to _FALSE_CHEAP_RICHNESS so ONE
    threshold governs both 'max rich-vs-peers' and the clamp trigger."""
    if r <= 0.70:
        return 1.0
    if r <= 0.90:
        return 0.5
    if r <= 1.10:
        return 0.0
    if r < _FALSE_CHEAP_RICHNESS:
        return -0.5
    return -1.0


@dataclass(frozen=True)
class DualTrack:
    industry_score: float | None
    val_score: float | None
    false_cheap: bool
    industry_reason: str | None  # None | industry_no_data | false_cheap_clamp
    industry_richness: float | None


def _industry_leg(stock_pe: float | None, industry_avg_pe: float | None):
    """(richness, score) or (None, None) when the industry denominator is unusable."""
    if (stock_pe is None or stock_pe <= 0.0
            or industry_avg_pe is None or industry_avg_pe <= 0.0):
        return None, None
    r = stock_pe / industry_avg_pe
    return r, industry_band(r)


def dual_track_score(
    *, self_score: float | None, stock_pe: float | None, industry_avg_pe: float | None,
) -> DualTrack:
    """Pure: 0.60·self + 0.40·industry, with industry-N/A → self-only and a
    hard-0 False-Cheap clamp (self>0 AND r>=1.2). self-N/A → no val_score."""
    r, industry_score = _industry_leg(stock_pe, industry_avg_pe)
    if self_score is None:                        # self leg N/A → no score
        return DualTrack(industry_score, None, False, None, r)
    if industry_score is None:                    # industry leg N/A → self-only
        return DualTrack(None, self_score, False, _REASON_INDUSTRY_NO_DATA, None)
    if self_score > 0.0 and r >= _FALSE_CHEAP_RICHNESS:  # value-trap quadrant
        return DualTrack(industry_score, 0.0, True, _REASON_FALSE_CHEAP_CLAMP, r)
    blend = _SELF_W * self_score + _INDUSTRY_W * industry_score
    return DualTrack(industry_score, blend, False, None, r)
