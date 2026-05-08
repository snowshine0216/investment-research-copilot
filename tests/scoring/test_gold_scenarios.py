from __future__ import annotations
from irc.scoring.gold_scenarios import classify_scenario, ScenarioResult


def test_strong_bull_trips_when_drivers_align():
    out = classify_scenario(
        real_yield=0.30, dxy=98.0, cb_purchases_yearly_tons=1100,
        geopolitical_stress=0.8,
    )
    assert isinstance(out, ScenarioResult)
    assert out.scenario == "strong_bull"


def test_pullback_when_real_yield_high():
    out = classify_scenario(
        real_yield=2.7, dxy=112.0, cb_purchases_yearly_tons=400,
        geopolitical_stress=0.2,
    )
    assert out.scenario == "pullback"


def test_base_when_mixed():
    out = classify_scenario(
        real_yield=2.0, dxy=104.0, cb_purchases_yearly_tons=800,
        geopolitical_stress=0.4,
    )
    assert out.scenario == "base"
