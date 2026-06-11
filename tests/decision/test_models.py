from __future__ import annotations

from typing import get_args

from irc.decision.models import (
    DecisionRow,
    DecisionStatus,
    PortfolioAction,
)


def test_portfolio_action_members() -> None:
    assert set(get_args(PortfolioAction)) == {
        "no_trade",
        "buy",
        "trim_review",
        "exit_review",
        "review",
    }


def test_decision_status_includes_review_sell_later() -> None:
    assert "review_sell_later" in get_args(DecisionStatus)


def test_decision_row_weight_fields_default_to_zero() -> None:
    row = DecisionRow(
        instrument_id="518880",
        asset_class="gold",
        score_action="watch",
        decision_status="watch_only",
        portfolio_action="no_trade",
        conviction="low",
        data_completeness=1.0,
        missing_data=(),
        target_weight_valid=True,
        venue_status="direct",
        memo_evidence_status="evidence_linked",
    )
    assert row.current_weight == 0.0
    assert row.weight_delta == 0.0
    assert row.target_weight == 0.0


def test_decision_row_weight_fields_serialize() -> None:
    row = DecisionRow(
        instrument_id="518880",
        asset_class="gold",
        score_action="watch",
        decision_status="review_sell_later",
        portfolio_action="exit_review",
        conviction="low",
        data_completeness=1.0,
        missing_data=(),
        target_weight_valid=True,
        venue_status="direct",
        memo_evidence_status="evidence_linked",
        current_weight=0.07,
        weight_delta=0.02,
        target_weight=0.05,
    )
    d = row.to_dict()
    assert d["current_weight"] == 0.07
    assert d["weight_delta"] == 0.02
    assert d["portfolio_action"] == "exit_review"
    assert d["decision_status"] == "review_sell_later"


# P0-1: is_holding field must be on DecisionRow and serialized by to_dict.
def test_decision_row_is_holding_default_false() -> None:
    row = DecisionRow(
        instrument_id="518880",
        asset_class="gold",
        score_action="watch",
        decision_status="watch_only",
        portfolio_action="no_trade",
        conviction="low",
        data_completeness=1.0,
        missing_data=(),
        target_weight_valid=True,
        venue_status="direct",
        memo_evidence_status="evidence_linked",
    )
    assert row.is_holding is False
    assert row.to_dict()["is_holding"] is False


def test_decision_row_is_holding_true_serializes() -> None:
    row = DecisionRow(
        instrument_id="510300",
        asset_class="cn_etf",
        score_action="watch",
        decision_status="review_sell_later",
        portfolio_action="exit_review",
        conviction="med",
        data_completeness=1.0,
        missing_data=(),
        target_weight_valid=True,
        venue_status="direct",
        memo_evidence_status="evidence_linked",
        is_holding=True,
    )
    assert row.is_holding is True
    d = row.to_dict()
    assert d["is_holding"] is True
