from __future__ import annotations

import dataclasses

import pytest

from irc.notify.types import NotificationDecision, RunOutcome


def _outcome(**overrides) -> RunOutcome:
    base = dict(
        run_kind="daily",
        last_exit_code=0,
        today_dir_exists=True,
        pipeline_halted=False,
        stale_ingest=False,
        actionable_buy_count=0,
        trim_count=0,
        exit_count=0,
        review_count=0,
    )
    base.update(overrides)
    return RunOutcome(**base)


def test_run_outcome_is_frozen():
    outcome = _outcome()
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.last_exit_code = 1  # type: ignore[misc]


def test_run_outcome_allows_null_sell_counts():
    outcome = _outcome(trim_count=None, exit_count=None, review_count=None)
    assert outcome.trim_count is None
    assert outcome.exit_count is None
    assert outcome.review_count is None


def test_notification_decision_is_frozen():
    decision = NotificationDecision(
        should_notify=True, severity="action", title="t", body="b"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.title = "x"  # type: ignore[misc]
