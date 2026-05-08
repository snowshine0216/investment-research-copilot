from __future__ import annotations
from typing import Literal


Mode = Literal["build", "hybrid", "steady_state"]


def select_mode(current_total_cny: float, monthly_new_capital_cny: float) -> Mode:
    """Mode selector per design spec §4.C:
      Build:   current < 5万  OR monthly < 5000
      Hybrid:  5万 ≤ current < 10万 (and monthly ≥ 5000)
      Steady:  current ≥ 10万 (and monthly ≥ 5000)
    """
    if current_total_cny < 50_000 or monthly_new_capital_cny < 5_000:
        return "build"
    if current_total_cny < 100_000:
        return "hybrid"
    return "steady_state"
