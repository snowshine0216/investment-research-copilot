from __future__ import annotations

from dataclasses import dataclass

from irc.opportunity.types import DcaAction, OpportunityRow, RiskAction


_DRAWDOWN_REVIEW_THRESHOLD: float = 0.20


@dataclass(frozen=True)
class PositionContext:
    portfolio_weight: float | None
    target_band_low: float | None
    target_band_high: float | None
    drawdown_since_entry: float | None
    is_holding: bool


def derive_dca_action(row: OpportunityRow) -> DcaAction:
    """Map opportunity_state + sub-states to DCA rhythm.

    Rules (from spec, conservative side):
      - exclude => do_not_buy
      - thesis under_pressure or falsified => pause_dca
      - pause_wait => pause_dca
      - cheap + cold + intact + strong => accelerate_dca
      - core_dca otherwise => normal_dca
      - small_watch => slow_dca
    """
    if row.opportunity_state == "exclude":
        return "do_not_buy"
    if row.thesis_state in ("under_pressure", "falsified"):
        return "pause_dca"
    if row.opportunity_state == "pause_wait":
        return "pause_dca"
    if row.opportunity_state == "small_watch":
        return "slow_dca"
    if (
        row.valuation_state == "cheap"
        and row.heat_state == "cold"
        and row.thesis_state == "intact"
        and row.product_quality_state == "strong"
    ):
        return "accelerate_dca"
    return "normal_dca"


def _is_overweight(pos: PositionContext) -> bool:
    if pos.portfolio_weight is None or pos.target_band_high is None:
        return False
    return pos.portfolio_weight > pos.target_band_high


def derive_risk_action(row: OpportunityRow, pos: PositionContext) -> RiskAction:
    """Derive risk action with strict separation between trim and exit.

    - Falsified thesis OR poor product quality => exit_review
    - Trim conditions => trim_review:
      * expensive/very_expensive valuation AND overweight
      * crowded/overheated heat AND overweight
    - Drawdown >= 20% alone => review_required (NEVER auto-sell)
    - Otherwise => none
    """
    if row.thesis_state == "falsified" or row.product_quality_state == "poor":
        return "exit_review"
    overweight = _is_overweight(pos)
    expensive = row.valuation_state in ("expensive", "very_expensive")
    hot = row.heat_state in ("crowded", "overheated")
    if overweight and (expensive or hot):
        return "trim_review"
    drawdown = pos.drawdown_since_entry
    if drawdown is not None and drawdown >= _DRAWDOWN_REVIEW_THRESHOLD:
        return "review_required"
    if row.thesis_state == "under_pressure":
        return "review_required"
    return "none"
