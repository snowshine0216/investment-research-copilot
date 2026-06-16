# tests/monitor/eval/test_review.py
from __future__ import annotations
from irc.monitor.eval.review import review_trigger


def test_fires_when_k_consecutive_weeks_below_random():
    # default K=4: 4 negative deltas → fire
    assert review_trigger([-0.1, -0.2, -0.05, -0.3]) is True


def test_does_not_fire_with_a_positive_week():
    assert review_trigger([-0.1, 0.05, -0.2, -0.3]) is False


def test_none_week_breaks_the_streak():
    # 3 negative + 1 None + 1 negative ⇒ no fire (None = missing/weak week)
    assert review_trigger([-0.1, -0.2, None, -0.3, -0.4][-4:]) is False


def test_too_few_weeks_does_not_fire():
    assert review_trigger([-0.1, -0.2]) is False


def test_uses_most_recent_k_only():
    # 5 entries; only the last K=4 matter; oldest positive is ignored
    assert review_trigger([0.5, -0.1, -0.2, -0.05, -0.3]) is True
