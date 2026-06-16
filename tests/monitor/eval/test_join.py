# tests/monitor/eval/test_join.py
from __future__ import annotations
import math
from irc.monitor.eval.join import series_entry_outcome


def _series(n, start="2026-01-01", base=1.0, step=0.001):
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    return tuple(((d0 + timedelta(days=i)).isoformat(), base + step * i) for i in range(n))


def test_entry_strictly_after_anchor_excludes_same_day():
    series = _series(30)
    # anchor == an existing nav_date → entry must be the NEXT date (strict >)
    anchor = series[5][0]
    out = series_entry_outcome(series, anchor=anchor, h=20, today="2026-12-31")
    assert out.reason == "ok"
    assert out.entry_nav_date == series[6][0]   # strictly AFTER anchor
    assert out.entry_idx == 6


def test_outcome_idx_is_entry_plus_h():
    series = _series(40)
    out = series_entry_outcome(series, anchor=series[2][0], h=20, today="2026-12-31")
    assert out.outcome_idx == out.entry_idx + 20
    expected = series[out.outcome_idx][1] / series[out.entry_idx][1] - 1
    assert math.isclose(out.fwd_ret, expected)


def test_no_entry_obs_when_anchor_is_last_date():
    series = _series(10)
    out = series_entry_outcome(series, anchor=series[-1][0], h=20, today="2026-12-31")
    assert out.reason == "no_entry_obs"


def test_not_matured_when_outcome_beyond_series():
    series = _series(15)  # entry@idx1, outcome needs idx21 > len → not matured
    out = series_entry_outcome(series, anchor=series[0][0], h=20, today="2026-12-31")
    assert out.reason == "not_matured"


def test_not_matured_when_outcome_date_after_today():
    series = _series(40)
    out = series_entry_outcome(series, anchor=series[0][0], h=20, today=series[10][0])
    assert out.reason == "not_matured"


def test_bad_nav_excluded_when_endpoint_non_finite_or_nonpositive():
    series = list(_series(40))
    series[1] = (series[1][0], 0.0)   # entry endpoint <= 0
    out = series_entry_outcome(tuple(series), anchor=series[0][0], h=20, today="2026-12-31")
    assert out.reason == "bad_nav"


def test_scorer_invariant_outcome_before_entry_raises():
    import pytest
    series = _series(40)
    with pytest.raises(ValueError):
        series_entry_outcome(series, anchor=series[0][0], h=-5, today="2026-12-31")
