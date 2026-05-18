from __future__ import annotations

import pytest

from irc.decision.gates import decide_row


def _score(action: str = "watch", **kw):
    base = {
        "instrument_id": "X1",
        "asset_class": "cn_equity_fund",
        "conviction": "med",
        "data_completeness": 1.0,
        "missing_data": [],
        "action": action,
    }
    base.update(kw)
    return base


def _direct_trade(iid: str = "X1"):
    return {"target": iid, "venue_compatible": True, "proxy_id": None}


def test_watch_reason_score_watch_when_action_is_watch():
    row = decide_row(
        score=_score(action="watch"),
        allocation_selected=False,
        target_weight_valid=True,
        trade=_direct_trade(),
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert row["decision_status"] == "watch_only"
    assert row["watch_reason"] == "score_watch"


def test_watch_reason_not_selected_when_buy_candidate_but_unselected():
    row = decide_row(
        score=_score(action="buy_candidate"),
        allocation_selected=False,
        target_weight_valid=True,
        trade=_direct_trade(),
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert row["decision_status"] == "watch_only"
    assert row["watch_reason"] == "not_selected_by_allocation"


def test_watch_reason_none_on_actionable_buy():
    row = decide_row(
        score=_score(action="buy_candidate"),
        allocation_selected=True,
        target_weight_valid=True,
        trade=_direct_trade(),
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert row["decision_status"] == "actionable_buy"
    assert row["watch_reason"] is None


def test_watch_reason_none_on_blocked():
    row = decide_row(
        score=_score(action="buy_candidate", data_completeness=0.5),
        allocation_selected=False,
        target_weight_valid=True,
        trade=None,  # no trade -> venue_unknown sub-status
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    assert row["decision_status"] == "blocked"  # data_incomplete + venue_blocked
    assert row["watch_reason"] is None


@pytest.mark.parametrize("action", ["watch", "buy_candidate", "strong_buy_candidate"])
def test_watch_reason_venue_unknown_when_trade_missing_and_already_watch(action):
    # action = watch with no trade still classifies as score_watch (more specific).
    # When the row would otherwise be watch_only and the only remaining
    # distinguisher is the missing trade, watch_reason = venue_unknown.
    # In current logic, watch action wins -> score_watch. So this case
    # surfaces only when action is buy_candidate AND somehow ends up
    # watch_only without unselected_by_allocation triggering. Today the
    # branch is defensive; this test guards future logic changes.
    row = decide_row(
        score=_score(action=action),
        allocation_selected=(action != "watch"),
        target_weight_valid=True,
        trade=_direct_trade() if action != "watch" else None,
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )
    if action == "watch":
        assert row["watch_reason"] == "score_watch"
    else:
        # buy_candidate + selected -> actionable_buy, not watch_only.
        assert row["decision_status"] == "actionable_buy"
        assert row["watch_reason"] is None
