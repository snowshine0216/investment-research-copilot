# tests/monitor/eval/test_review.py
from __future__ import annotations
from collections import namedtuple
from irc.monitor.eval.review import dedup_iso_weeks, review_trigger

_Rep = namedtuple("_Rep", ["ran_at"])
_Entry = namedtuple("_Entry", ["artifact_date", "report"])


def _e(d, ran="T09:00"):
    return _Entry(d, _Rep(d + ran))


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


def test_four_reruns_same_iso_week_collapse_to_one():
    # 2026-06-15..2026-06-18 are all ISO week 25 of 2026 (Mon-Thu)
    entries = [_e("2026-06-18"), _e("2026-06-17"), _e("2026-06-16"), _e("2026-06-15")]
    out = dedup_iso_weeks(entries, k=4)
    assert len(out) == 1
    assert out[0].artifact_date == "2026-06-18"   # highest in the week


def test_four_distinct_weeks_kept():
    entries = [_e("2026-06-18"), _e("2026-06-11"), _e("2026-06-04"), _e("2026-05-28")]
    out = dedup_iso_weeks(entries, k=4)
    assert [e.artifact_date for e in out] == \
        ["2026-06-18", "2026-06-11", "2026-06-04", "2026-05-28"]


def test_dedup_caps_at_k_weeks():
    entries = [_e(f"2026-{m:02d}-01") for m in (6, 5, 4, 3, 2)]  # 5 distinct weeks
    out = dedup_iso_weeks(entries, k=4)
    assert len(out) == 4
