from __future__ import annotations

from irc.decision.gates import decide_row, target_weights_are_valid


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
