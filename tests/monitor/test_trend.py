import math
import pytest
from irc.monitor.trend import trend_score, _r60, _ma_struct, _drawdown_250


def _series(values):
    # acc-NAV as tuple[(date, value)]; dates immaterial to the math here.
    return tuple((f"2026-01-{i % 28 + 1:02d}", float(v)) for i, v in enumerate(values))


def test_flat_series_is_near_zero():
    s = _series([1.0] * 300)
    assert abs(trend_score(s)) < 1e-9


def test_strong_uptrend_is_positive_and_bounded():
    s = _series([1.0 + 0.001 * i for i in range(300)])   # steady rise
    t = trend_score(s)
    assert 0.0 < t <= 1.0


def test_strong_downtrend_is_negative_and_bounded():
    s = _series([2.0 - 0.001 * i for i in range(300)])
    t = trend_score(s)
    assert -1.0 <= t < 0.0


def test_r60_is_total_return_over_60d():
    s = _series([1.0] * 240 + [1.0] + [1.10])  # last 60d ~ +10% near the end
    # exact: nav[-1]/nav[-61] - 1
    vals = [v for _, v in s]
    assert math.isclose(_r60(vals), vals[-1] / vals[-61] - 1.0, rel_tol=1e-12)


def test_ma_struct_uptrend_returns_plus_one():
    vals = [1.0 + 0.002 * i for i in range(120)]
    assert _ma_struct(vals) == 1.0


def test_drawdown_zero_at_new_high():
    vals = [1.0 + 0.001 * i for i in range(300)]
    assert _drawdown_250(vals) == pytest.approx(0.0, abs=1e-12)


def test_output_clamped_to_unit_interval():
    s = _series([1.0] + [5.0])  # explosive jump
    assert -1.0 <= trend_score(s) <= 1.0


def test_r60_zero_denominator_returns_zero():
    """Guard: when vals[-61] is 0.0 → return 0.0, NOT ZeroDivisionError."""
    # 239 normal values, then 0.0, then 60 values → vals[-61] == 0.0
    vals = [1.0] * 239 + [0.0] + [1.0] * 60
    assert len(vals) == 300
    assert vals[-61] == 0.0
    assert _r60(vals) == 0.0          # must not raise


def test_r60_zero_first_element_short_series_returns_zero():
    """Guard: short series where vals[0] == 0.0 → return 0.0, NOT ZeroDivisionError."""
    vals = [0.0, 1.0, 2.0]
    assert _r60(vals) == 0.0


def test_trend_score_zero_nav_degrades_not_crash():
    """trend_score must not raise ZeroDivisionError when _r60 hits a zero denominator."""
    # Build a series where the 61st-from-end element is 0.0
    s = _series([1.0] * 239 + [0.0] + [1.0] * 60)
    score = trend_score(s)            # must not raise
    assert -1.0 <= score <= 1.0
