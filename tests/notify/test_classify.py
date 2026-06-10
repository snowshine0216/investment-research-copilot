from __future__ import annotations

import pytest

from irc.notify.classify import classify_run_outcome
from irc.notify.types import RunOutcome


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


def test_missing_today_dir_is_failed_even_at_exit_zero():
    decision = classify_run_outcome(_outcome(today_dir_exists=False, last_exit_code=0))
    assert decision.severity == "failed"
    assert decision.should_notify is True
    assert "never produced output" in decision.body


@pytest.mark.parametrize(
    "code,label",
    [(1, "runtime"), (2, "config"), (3, "fetch-budget"), (4, "lock"), (5, "spend-gate")],
)
def test_nonzero_exit_codes_are_failed_and_named(code, label):
    decision = classify_run_outcome(_outcome(last_exit_code=code))
    assert decision.severity == "failed"
    assert decision.should_notify is True
    assert label in decision.title.lower()


def test_pipeline_halted_is_halted():
    decision = classify_run_outcome(_outcome(pipeline_halted=True))
    assert decision.severity == "halted"
    assert decision.should_notify is True


def test_stale_ingest_is_stale():
    decision = classify_run_outcome(_outcome(stale_ingest=True))
    assert decision.severity == "stale"
    assert decision.should_notify is True


def test_null_sell_counts_are_action_unknown():
    decision = classify_run_outcome(
        _outcome(trim_count=None, exit_count=None, review_count=None)
    )
    assert decision.severity == "action"
    assert decision.should_notify is True
    assert "unknown" in decision.body.lower()
    assert "irc opportunity" in decision.body
    # never rendered as 0 or "healthy"
    assert "0" not in decision.body.replace("irc opportunity", "")
    assert "healthy" not in decision.body.lower()


def test_single_null_among_sell_counts_is_action_unknown():
    decision = classify_run_outcome(_outcome(trim_count=None, exit_count=0, review_count=0))
    assert decision.severity == "action"
    assert "unknown" in decision.body.lower()


def test_buys_only_is_action():
    decision = classify_run_outcome(_outcome(actionable_buy_count=2))
    assert decision.severity == "action"
    assert "2" in decision.body


def test_sell_signals_only_is_action():
    decision = classify_run_outcome(_outcome(trim_count=1, exit_count=0, review_count=0))
    assert decision.severity == "action"
    assert "trim" in decision.body.lower()


def test_buys_and_sell_signals_rollup():
    decision = classify_run_outcome(
        _outcome(actionable_buy_count=2, trim_count=1, exit_count=1, review_count=0)
    )
    assert decision.severity == "action"
    body = decision.body.lower()
    assert "2" in body and "buy" in body
    assert "trim" in body and "exit" in body


def test_all_zero_is_clean():
    decision = classify_run_outcome(_outcome())
    assert decision.severity == "clean"


def test_clean_notify_on_clean_true_notifies():
    decision = classify_run_outcome(_outcome(), notify_on_clean=True)
    assert decision.severity == "clean"
    assert decision.should_notify is True


def test_clean_notify_on_clean_false_suppresses():
    decision = classify_run_outcome(_outcome(), notify_on_clean=False)
    assert decision.severity == "clean"
    assert decision.should_notify is False


def test_failed_precedence_beats_halted_and_action():
    # exit 1 AND a positive buy count AND halted: failed wins.
    decision = classify_run_outcome(
        _outcome(last_exit_code=1, pipeline_halted=True, actionable_buy_count=3)
    )
    assert decision.severity == "failed"


def test_halted_precedence_beats_stale_and_action():
    decision = classify_run_outcome(
        _outcome(pipeline_halted=True, stale_ingest=True, actionable_buy_count=3)
    )
    assert decision.severity == "halted"


# ---- P0-3: rc=124 (watchdog timeout) → failed with timeout label ----

def test_exit_124_is_failed_with_timeout_label():
    """P0-3: watchdog kills the pipeline → rc=124 → severity failed, 'timeout' in title."""
    decision = classify_run_outcome(_outcome(last_exit_code=124))
    assert decision.severity == "failed"
    assert decision.should_notify is True
    assert "timeout" in decision.title.lower()
