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
