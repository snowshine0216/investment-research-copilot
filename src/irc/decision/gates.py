from __future__ import annotations

from typing import Any

from irc.decision.completeness import REQUIRED_METRIC_FIELDS
from irc.decision.models import DecisionRow, VenueStatus


_BUY_ACTIONS = {"buy_candidate", "strong_buy_candidate"}
_AVOID_ACTIONS = {"avoid", "strong_avoid"}


def target_weights_are_valid(allocation: dict[str, Any], tolerance: float = 1e-3) -> bool:
    total = allocation.get("diagnostics", {}).get("total_weight")
    if total is None:
        selected = allocation.get("selected_instruments", [])
        total = sum(float(row.get("target_weight", 0.0)) for row in selected)
    try:
        return abs(float(total) - 1.0) <= tolerance
    except (TypeError, ValueError):
        return False


def venue_status_for_trade(trade: dict[str, Any] | None) -> VenueStatus:
    if trade is None:
        return "unknown"
    if bool(trade.get("venue_compatible")):
        return "direct"
    if trade.get("proxy_id") is not None:
        return "proxy_available"
    return "blocked_no_proxy"


def memo_evidence_status(coverage: float) -> str:
    return "evidence_linked" if coverage > 0.0 else "narrative_only"


def decide_row(
    score: dict[str, Any],
    allocation_selected: bool,
    target_weight_valid: bool,
    trade: dict[str, Any] | None,
    pipeline_halted: bool,
    memo_traceability_coverage: float,
    completeness_threshold: float = 0.80,
) -> dict[str, Any]:
    score_action = str(score.get("action", "unknown"))
    completeness = float(score.get("data_completeness", 0.0))
    missing_data = list(score.get("missing_data") or REQUIRED_METRIC_FIELDS)
    venue_status = venue_status_for_trade(trade)
    evidence_status = memo_evidence_status(memo_traceability_coverage)
    blocking_reasons = _blocking_reasons(
        pipeline_halted=pipeline_halted,
        completeness=completeness,
        completeness_threshold=completeness_threshold,
        target_weight_valid=target_weight_valid,
        venue_status=venue_status,
        evidence_status=evidence_status,
        score_action=score_action,
    )
    decision_status = _decision_status(score_action, blocking_reasons, allocation_selected)
    return _build_decision_row(
        score=score,
        score_action=score_action,
        completeness=completeness,
        missing_data=missing_data,
        target_weight_valid=target_weight_valid,
        venue_status=venue_status,
        evidence_status=evidence_status,
        blocking_reasons=blocking_reasons,
        decision_status=decision_status,
    ).to_dict()


def _build_decision_row(
    score: dict[str, Any],
    score_action: str,
    completeness: float,
    missing_data: list[str],
    target_weight_valid: bool,
    venue_status: VenueStatus,
    evidence_status: str,
    blocking_reasons: list[str],
    decision_status: str,
) -> DecisionRow:
    return DecisionRow(
        instrument_id=str(score.get("instrument_id", "")),
        asset_class=str(score.get("asset_class", "unknown")),
        score_action=score_action,
        decision_status=decision_status,
        portfolio_action="no_trade",
        conviction=str(score.get("conviction", "low")),
        data_completeness=completeness,
        missing_data=missing_data,
        target_weight_valid=target_weight_valid,
        venue_status=venue_status,
        memo_evidence_status=evidence_status,
        blocking_reasons=blocking_reasons,
        reason=_reason(decision_status, blocking_reasons, score_action),
        next_step=_next_step(blocking_reasons, decision_status),
    )


def _blocking_reasons(
    pipeline_halted: bool,
    completeness: float,
    completeness_threshold: float,
    target_weight_valid: bool,
    venue_status: VenueStatus,
    evidence_status: str,
    score_action: str,
) -> list[str]:
    reasons: list[str] = []
    if pipeline_halted:
        reasons.append("pipeline_halted")
    if completeness < completeness_threshold:
        reasons.append("data_incomplete")
    if not target_weight_valid:
        reasons.append("target_weights_invalid")
    if venue_status == "blocked_no_proxy":
        reasons.append("venue_blocked")
    if evidence_status == "narrative_only":
        reasons.append("memo_narrative_only")
    if score_action in _AVOID_ACTIONS:
        reasons.append("score_avoid")
    return reasons


def _decision_status(score_action: str, blocking_reasons: list[str], allocation_selected: bool) -> str:
    if score_action in _AVOID_ACTIONS:
        return "avoid"
    if blocking_reasons:
        return "blocked"
    if score_action in _BUY_ACTIONS and allocation_selected:
        return "actionable_buy"
    return "watch_only"


def _reason(decision_status: str, blocking_reasons: list[str], score_action: str) -> str:
    if decision_status == "actionable_buy":
        return "Score, data, allocation, venue, pipeline, and traceability gates are all clear."
    if decision_status == "avoid":
        return f"Scoring action is {score_action}; allocation or trade-plan presence cannot upgrade an avoid signal."
    return "Blocked by: " + ", ".join(blocking_reasons)


def _next_step(blocking_reasons: list[str], decision_status: str) -> str:
    if decision_status == "actionable_buy":
        return "Review manually before any order; this plan does not size trades."
    if "pipeline_halted" in blocking_reasons:
        return "Fix the halted stage and rerun the pipeline."
    if "data_incomplete" in blocking_reasons:
        return "Repair required financial metrics and rerun scoring."
    if "target_weights_invalid" in blocking_reasons:
        return "Fix allocation normalization before using target weights."
    if "venue_blocked" in blocking_reasons:
        return "Add a compatible account venue or exact proxy."
    if "memo_narrative_only" in blocking_reasons:
        return "Improve memo traceability before treating narrative claims as evidence."
    return "Keep on watchlist and rerun after new data."
