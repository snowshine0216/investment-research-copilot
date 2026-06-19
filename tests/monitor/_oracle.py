"""TEST-ONLY independent reference impls for D1 (spec §3.1).

Independent formulations where one genuinely exists; NEVER imported by production.
A second copy of a direct formula transcription would be circular, so trend /
build_factor_scores / news_factor get PROPERTIES (in their *_property modules),
not an oracle here.
"""
from __future__ import annotations

# ── compute_signal: composite via a separate Σw'·s formulation ────────────────
_MIN_FAMILIES = 2
_MIN_AVAILABLE_WEIGHT = 0.60
_FAMILY_OF = {
    "trend": "price-momentum", "valuation": "valuation",
    "heat": "crowding", "macro_tilt": "news", "constituent": "news",
    "flow": "capital-flow",
}


def present_scores(scores):
    """(name, value, confidence) for eligible-and-present factors."""
    return [(s.name, s.value, s.confidence) for s in scores
            if s.eligible and s.value is not None]


def available_weight(weights: dict, scores) -> float:
    return sum(weights.get(n, 0.0) for n, _, _ in present_scores(scores))


def composite_oracle(weights: dict, scores) -> float:
    """Σ (w_i / Σw_present) · s_i — a different grouping than production's
    per-contribution accumulation. Unrounded; caller applies the §3.3 eps."""
    present = present_scores(scores)
    avail = sum(weights.get(n, 0.0) for n, _, _ in present)
    if avail <= 0:
        return 0.0
    return sum((weights.get(n, 0.0) / avail) * v for n, v, _ in present)


def renorm_weight_sum(weights: dict, scores) -> float:
    present = present_scores(scores)
    avail = sum(weights.get(n, 0.0) for n, _, _ in present)
    if avail <= 0:
        return 0.0
    return sum(weights.get(n, 0.0) / avail for n, _, _ in present)


def gate_predicate_ok(weights: dict, scores) -> bool:
    """status == 'ok' is GATED by: trend present AND ≥2 families AND avail ≥ .60.
    (Confidence gate is a separate check.) Independent boolean form."""
    present = present_scores(scores)
    families = {_FAMILY_OF[n] for n, _, _ in present}
    avail = sum(weights.get(n, 0.0) for n, _, _ in present)
    trend_present = any(n == "trend" for n, _, _ in present)
    return trend_present and len(families) >= _MIN_FAMILIES and avail >= _MIN_AVAILABLE_WEIGHT


def band_classifier(composite: float, bands: dict) -> str:
    """ADD_BIAS / REDUCE_BIAS / NEUTRAL via explicit boundaries."""
    if composite >= bands["buy"]:
        return "ADD_BIAS"
    if composite <= bands["sell"]:
        return "REDUCE_BIAS"
    return "NEUTRAL"


# ── valuation / heat: re-expressed decision tables (different shape) ───────────
def valuation_oracle(state: str):
    """Re-expressed as an explicit if-ladder instead of a dict lookup."""
    if state == "cheap":
        return 1.0
    if state == "reasonable_low":
        return 0.5
    if state == "fair":
        return 0.0
    if state == "expensive":
        return -0.5
    if state == "very_expensive":
        return -1.0
    return None


def heat_oracle(*, restricted, aum_delta_pct):
    """Re-expressed decision table (no-data → None; both → -1; either → -0.5; calm → .3)."""
    if restricted is None and aum_delta_pct is None:
        return None
    rapid = aum_delta_pct is not None and aum_delta_pct >= 20.0
    if restricted is True and rapid:
        return -1.0
    if restricted is True or rapid:
        return -0.5
    return 0.3
