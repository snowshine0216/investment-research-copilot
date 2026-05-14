from __future__ import annotations

from irc.decision.gates import decide_row, target_weights_are_valid, venue_status_for_trade


def _score(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "instrument_id": "518850",
        "asset_class": "gold",
        "action": "buy_candidate",
        "conviction": "med",
        "data_completeness": 1.0,
        "missing_data": [],
    }
    return {**row, **overrides}


def test_target_weights_are_valid_requires_total_near_one() -> None:
    assert target_weights_are_valid({"diagnostics": {"total_weight": 1.0}})
    assert not target_weights_are_valid({"diagnostics": {"total_weight": 3.0}})


def test_pipeline_halt_blocks_everything() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=True,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert decision["portfolio_action"] == "no_trade"
    assert "pipeline_halted" in decision["blocking_reasons"]


def test_low_data_completeness_blocks_buy() -> None:
    decision = decide_row(
        score=_score(data_completeness=0.0, missing_data=["expense_ratio"]),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert "data_incomplete" in decision["blocking_reasons"]


def test_avoid_action_stays_avoid_even_when_selected() -> None:
    decision = decide_row(
        score=_score(action="avoid"),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "avoid"
    assert decision["portfolio_action"] == "no_trade"


def test_incompatible_venue_without_proxy_blocks_execution() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": False, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert decision["venue_status"] == "blocked_no_proxy"


def test_complete_healthy_buy_candidate_can_be_actionable() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "actionable_buy"
    assert decision["portfolio_action"] == "no_trade"


def test_zero_memo_traceability_marks_evidence_narrative_only() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=0.0,
    )

    assert decision["memo_evidence_status"] == "narrative_only"
    assert "memo_narrative_only" in decision["blocking_reasons"]
    assert decision["decision_status"] == "blocked"


def test_target_weights_valid_falls_back_to_sum_selected_when_total_absent() -> None:
    allocation = {
        "selected_instruments": [
            {"instrument_id": "A", "target_weight": 0.6},
            {"instrument_id": "B", "target_weight": 0.4},
        ]
    }
    assert target_weights_are_valid(allocation)


def test_venue_status_none_trade_returns_unknown() -> None:
    assert venue_status_for_trade(None) == "unknown"


def test_venue_status_proxy_available_when_proxy_id_present() -> None:
    assert venue_status_for_trade({"venue_compatible": False, "proxy_id": "PROXY"}) == "proxy_available"


def test_target_weights_invalid_blocks_via_decide_row() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=False,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert "target_weights_invalid" in decision["blocking_reasons"]
    assert decision["decision_status"] == "blocked"


def test_score_avoid_appears_in_blocking_reasons() -> None:
    decision = decide_row(
        score=_score(action="avoid"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert "score_avoid" in decision["blocking_reasons"]


def test_watch_only_when_buy_candidate_not_selected() -> None:
    decision = decide_row(
        score=_score(action="buy_candidate"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "watch_only"


def test_watch_only_when_action_is_watch() -> None:
    decision = decide_row(
        score=_score(action="watch"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "watch_only"


def test_strong_buy_candidate_action_results_in_actionable_buy() -> None:
    decision = decide_row(
        score=_score(action="strong_buy_candidate"),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "actionable_buy"


def test_next_step_for_target_weights_invalid() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=False,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert "Fix allocation normalization" in decision["next_step"]


def test_next_step_watch_only_fallback() -> None:
    decision = decide_row(
        score=_score(action="watch"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert "watchlist" in decision["next_step"]


def test_avoid_with_pipeline_halted_reports_both_reasons_and_status_is_avoid() -> None:
    # design: score_action wins → "avoid"; blocking_reasons still records both gates
    decision = decide_row(
        score=_score(action="avoid"),
        allocation_selected=False,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=True,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "avoid"
    assert "pipeline_halted" in decision["blocking_reasons"]
    assert "score_avoid" in decision["blocking_reasons"]


# ---------------------------------------------------------------------------
# _next_step: remaining text branches not yet asserted
# ---------------------------------------------------------------------------

def test_next_step_actionable_buy_text() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert decision["decision_status"] == "actionable_buy"
    assert "Review manually" in decision["next_step"]


def test_next_step_pipeline_halted_text() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=True,
        memo_traceability_coverage=1.0,
    )
    assert "Fix the halted stage" in decision["next_step"]


def test_next_step_data_incomplete_text() -> None:
    decision = decide_row(
        score=_score(data_completeness=0.0),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert "Repair required financial metrics" in decision["next_step"]


def test_next_step_venue_blocked_text() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": False, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert "Add a compatible account venue" in decision["next_step"]


def test_next_step_memo_narrative_only_text() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=0.0,
    )
    assert "memo traceability" in decision["next_step"]
