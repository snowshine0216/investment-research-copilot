from __future__ import annotations

from irc.narrative.schemas import OverlapResult, RiskEvalView, RiskLevel

_TOP1_CONCENTRATION_PCT = 30.0
_TOP3_CONCENTRATION_PCT = 60.0
_DRAWDOWN_3Y_THRESHOLD = 0.30
_VOLATILITY_THRESHOLD = 0.30
_THIN_OVERLAP_COUNT = 1

# Level severity ladder (index = severity).
_LADDER: tuple[RiskLevel, ...] = ("low", "moderate", "elevated", "high")


def _concentration_drivers(view: RiskEvalView) -> tuple[tuple[str, str, int], ...]:
    out: list[tuple[str, str, int]] = []
    holds = view.top_holdings
    if holds and holds[0][2] >= _TOP1_CONCENTRATION_PCT:
        out.append(("holdings_concentration", f"{holds[0][2]:.0f}% in top holding", 2))
    top3 = sum(w for _s, _n, w in holds[:3])
    if top3 >= _TOP3_CONCENTRATION_PCT:
        out.append(("holdings_concentration", f"top-3 weight {top3:.0f}%", 1))
    return tuple(out)


def _state_drivers(
    view: RiskEvalView,
    overlap: OverlapResult,
    metrics: dict[str, float],
) -> tuple[tuple[str, str, int], ...]:
    out: list[tuple[str, str, int]] = []
    if view.valuation_state in ("expensive", "very_expensive"):
        out.append(("valuation_state", f"{view.valuation_state} valuation", 2))
    if view.heat_state in ("crowded", "overheated"):
        out.append(("heat_state", f"{view.heat_state} heat", 2))
    if view.thesis_state in ("under_pressure", "falsified"):
        sev = 3 if view.thesis_state == "falsified" else 1
        out.append(("thesis_state", f"thesis {view.thesis_state}", sev))
    if view.product_quality_state in ("weak", "poor"):
        out.append(("product_quality_state", f"{view.product_quality_state} product", 1))
    if overlap.overlap_count <= _THIN_OVERLAP_COUNT:
        out.append(("narrative_concentration", "narrative is a thin slice", 1))
    dd = metrics.get("drawdown_3y")
    if dd is not None and dd >= _DRAWDOWN_3Y_THRESHOLD:
        out.append(("drawdown_3y", f"3y drawdown {dd:.0%}", 1))
    vol = metrics.get("volatility")
    if vol is not None and vol >= _VOLATILITY_THRESHOLD:
        out.append(("volatility", f"volatility {vol:.0%}", 1))
    return tuple(out)


def derive_position_risk_level(
    view: RiskEvalView,
    overlap: OverlapResult,
    metrics: dict[str, float],
) -> tuple[RiskLevel, str, tuple[str, ...]]:
    """Pure: prospective-buy risk level + rationale + dominant drivers.

    evidence_gaps non-empty => 'insufficient' (never fabricate)."""
    if view.evidence_gaps:
        return ("insufficient", "evidence_gaps present — risk cannot be assessed",
                ("evidence_gaps",))
    found = _state_drivers(view, overlap, metrics) + _concentration_drivers(view)
    if not found:
        return ("low", "no elevated risk drivers", ())
    severity = min(len(_LADDER) - 1, sum(w for _d, _why, w in found))
    level = _LADDER[severity]
    drivers = tuple(dict.fromkeys(d for d, _why, _w in found))  # dedup, stable order
    rationale = f"{level} — " + "; ".join(why for _d, why, _w in found)
    return (level, rationale, drivers)
