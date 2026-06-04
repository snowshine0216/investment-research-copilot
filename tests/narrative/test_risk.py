from __future__ import annotations

from irc.narrative.risk import derive_position_risk_level
from irc.narrative.schemas import OverlapResult, RiskEvalView


def _view(**over: object) -> RiskEvalView:
    base = dict(
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        evidence_gaps=(),
        top_holdings=(("601899", "紫金矿业", 8.0), ("600362", "江西铜业", 6.0)),
    )
    base.update(over)
    return RiskEvalView(**base)  # type: ignore[arg-type]


def _overlap(count: int = 3, weight: float = 30.0) -> OverlapResult:
    return OverlapResult(
        basket_weight_pct=weight, overlap_count=count,
        matched_symbols=(), industry_credit_symbols=(),
    )


def test_clean_row_is_low() -> None:
    level, rationale, drivers = derive_position_risk_level(_view(), _overlap(), {})
    assert level == "low"
    assert drivers == ()


def test_evidence_gaps_force_insufficient() -> None:
    level, _r, drivers = derive_position_risk_level(
        _view(evidence_gaps=("holdings_fetch_failed",)), _overlap(), {}
    )
    assert level == "insufficient"
    assert "evidence_gaps" in drivers


def test_valuation_very_expensive_raises() -> None:
    level, rationale, drivers = derive_position_risk_level(
        _view(valuation_state="very_expensive"), _overlap(), {}
    )
    assert level in ("elevated", "high")
    assert "valuation_state" in drivers
    assert "very_expensive" in rationale


def test_heat_overheated_raises() -> None:
    _l, _r, drivers = derive_position_risk_level(
        _view(heat_state="overheated"), _overlap(), {}
    )
    assert "heat_state" in drivers


def test_thesis_falsified_raises_high() -> None:
    level, _r, drivers = derive_position_risk_level(
        _view(thesis_state="falsified"), _overlap(), {}
    )
    assert level == "high"
    assert "thesis_state" in drivers


def test_product_poor_raises() -> None:
    _l, _r, drivers = derive_position_risk_level(
        _view(product_quality_state="poor"), _overlap(), {}
    )
    assert "product_quality_state" in drivers


def test_holdings_concentration_top1_raises() -> None:
    _l, rationale, drivers = derive_position_risk_level(
        _view(top_holdings=(("601899", "紫金矿业", 38.0),)), _overlap(), {}
    )
    assert "holdings_concentration" in drivers
    assert "38" in rationale


def test_narrative_concentration_thin_slice_raises() -> None:
    _l, _r, drivers = derive_position_risk_level(
        _view(), _overlap(count=1, weight=20.0), {}
    )
    assert "narrative_concentration" in drivers


def test_drawdown_metric_raises_when_available() -> None:
    _l, _r, drivers = derive_position_risk_level(
        _view(), _overlap(), {"drawdown_3y": 0.45}
    )
    assert "drawdown_3y" in drivers


def test_multiple_drivers_escalate_to_high() -> None:
    level, _r, drivers = derive_position_risk_level(
        _view(valuation_state="very_expensive", heat_state="overheated"),
        _overlap(), {},
    )
    assert level == "high"
    assert {"valuation_state", "heat_state"}.issubset(set(drivers))


def test_evidence_insufficient_valuation_surfaces_driver_non_blocking():
    # A withheld valuation (no fundamental anchor) on a publishable row surfaces a
    # mild driver — NOT silently dropped, NOT forced to 'insufficient'.
    level, rationale, drivers = derive_position_risk_level(
        _view(valuation_state="evidence_insufficient"), _overlap(), {}
    )
    assert "valuation_state" in drivers
    assert "valuation withheld" in rationale
    # weight 1 alone → 'moderate' (not insufficient, not high).
    assert level == "moderate"


def test_evidence_insufficient_valuation_does_not_force_insufficient_level():
    # evidence_gaps drives 'insufficient'; a withheld VALUATION state must not.
    level, _r, _d = derive_position_risk_level(
        _view(valuation_state="evidence_insufficient"), _overlap(), {}
    )
    assert level != "insufficient"
