from __future__ import annotations

from typing import Any

from irc.decision.completeness import MIN_BUY_COMPLETENESS, missing_required_fields
from irc.decision.models import DecisionRow, DecisionStatus, VenueStatus


_BUY_ACTIONS = {"buy_candidate", "strong_buy_candidate"}
_AVOID_ACTIONS = {"avoid", "strong_avoid"}


def target_weights_are_valid(allocation: dict[str, Any], tolerance: float = 1e-3) -> bool:
    """Allocation is valid when invested weight + cash residual ≈ 1.0.

    The allocation pipeline reports the explicitly invested portion as
    ``diagnostics.total_weight``. Classes without a scored candidate
    (always ``cash``; sometimes ``hk_etf``) leave an unfilled hole reported
    as ``diagnostics.cash_residual_weight``. The gate accepts the allocation
    when invested + residual cover the whole portfolio.
    """
    diagnostics = allocation.get("diagnostics", {})
    total = diagnostics.get("total_weight")
    if total is None:
        selected = allocation.get("selected_instruments", [])
        total = sum(
            float(row.get("target_weight") or 0.0) if row.get("target_weight") is not None else 0.0
            for row in selected
        )
    cash_residual = diagnostics.get("cash_residual_weight") or 0.0
    try:
        return abs(float(total) + float(cash_residual) - 1.0) <= tolerance
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
    completeness_threshold: float = MIN_BUY_COMPLETENESS,
) -> dict[str, Any]:
    score_action = str(score.get("action", "unknown"))
    _raw_completeness = score.get("data_completeness", 0.0)
    try:
        completeness = float(_raw_completeness) if _raw_completeness is not None else 0.0
    except (TypeError, ValueError):
        completeness = 0.0
    raw_missing = score.get("missing_data")
    # Fallback for old/serialized scores that pre-date the asset-class-aware
    # missing_data wiring in scoring/pipeline.py: derive the required set from
    # the score's asset_class so gold/bond don't get flagged with metrics that
    # don't apply to them. Passing row=None returns the required set as the
    # all-missing tuple.
    missing_data = (
        tuple(raw_missing) if raw_missing is not None
        else missing_required_fields(None, asset_class=score.get("asset_class"))
    )
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
    missing_data: tuple[str, ...],
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
        blocking_reasons=tuple(blocking_reasons),
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


def _decision_status(score_action: str, blocking_reasons: list[str], allocation_selected: bool) -> DecisionStatus:
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
