from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


Scenario = Literal["strong_bull", "base", "pullback"]


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    triggers_met: tuple[str, ...]


def classify_scenario(
    real_yield: float,
    dxy: float,
    cb_purchases_yearly_tons: float,
    geopolitical_stress: float,  # 0-1 normalized
) -> ScenarioResult:
    """Driver-based 3-scenario classifier."""
    bull_triggers = []
    if real_yield < 0.5: bull_triggers.append("real_yield<0.5")
    if dxy < 100:        bull_triggers.append("dxy<100")
    if cb_purchases_yearly_tons > 1000: bull_triggers.append("cb_buy>1000t")
    if geopolitical_stress > 0.7: bull_triggers.append("geo>0.7")

    bear_triggers = []
    if real_yield > 2.5: bear_triggers.append("real_yield>2.5")
    if dxy > 110:        bear_triggers.append("dxy>110")

    if len(bull_triggers) >= 3:
        return ScenarioResult(scenario="strong_bull", triggers_met=tuple(bull_triggers))
    if len(bear_triggers) >= 2:
        return ScenarioResult(scenario="pullback", triggers_met=tuple(bear_triggers))
    return ScenarioResult(scenario="base", triggers_met=())
