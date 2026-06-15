import math
from irc.monitor.returns import window_returns


def _series(vals):
    return tuple((f"2026-01-{i % 28 + 1:02d}", float(v)) for i, v in enumerate(vals))


def test_all_windows_present_as_keys():
    rt = window_returns(_series([1.0 + 0.001 * i for i in range(300)]))
    assert set(rt) == {5, 20, 60, 120, 250}


def test_window_return_is_acc_ratio_minus_one():
    vals = [1.0 + 0.001 * i for i in range(300)]
    rt = window_returns(_series(vals))
    assert math.isclose(rt[60], round(vals[-1] / vals[-61] - 1.0, 6), rel_tol=0, abs_tol=0)


def test_short_window_is_none_when_too_few_points():
    rt = window_returns(_series([1.0, 1.01, 1.02]))  # 3 points
    assert rt[5] is None and rt[20] is None
    assert rt[60] is None and rt[120] is None and rt[250] is None


def test_exactly_w_plus_one_points_yields_a_value():
    rt = window_returns(_series([1.0] * 5 + [1.1]))  # 6 points → 5d valid
    assert rt[5] == round(1.1 / 1.0 - 1.0, 6)


def test_zero_denominator_is_none_not_zero_division():
    # acc[-6] == 0.0 → None, no ZeroDivisionError
    rt = window_returns(_series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]))
    assert rt[5] is None


def test_values_rounded_to_six_dp_for_byte_stability():
    vals = [1.0] * 5 + [1.0 + 1.0 / 3.0]
    rt = window_returns(_series(vals))
    assert rt[5] == round((1.0 + 1.0 / 3.0) / 1.0 - 1.0, 6)


def test_empty_series_all_none():
    rt = window_returns(())
    assert all(v is None for v in rt.values()) and set(rt) == {5, 20, 60, 120, 250}
