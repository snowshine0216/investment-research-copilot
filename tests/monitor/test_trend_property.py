"""D1 properties for trend_score (spec §3.1: properties only).

clamp ∈ [-1,1]; monotone non-decreasing in r60 with structure/drawdown fixed;
tanh saturation at extremes.
"""
from __future__ import annotations
import math
from hypothesis import given, strategies as st
from irc.monitor.trend import trend_score


def _flat_then_ramp(base: float, ramp: float, n: int = 300):
    """A series whose r60 grows with `ramp` while ma_struct/drawdown stay fixed:
    constant `base` for the first n-61 points (flat MA + no drawdown anchor below
    the recent window), then a single jump to base*(1+ramp) at the end."""
    head = [base] * (n - 1)
    return tuple((f"d{i:04d}", v) for i, v in enumerate(head + [base * (1.0 + ramp)]))


@given(
    base=st.floats(0.5, 5.0, allow_nan=False),
    ramp=st.floats(-0.9, 5.0, allow_nan=False),
)
def test_output_always_in_unit_interval(base, ramp):
    s = _flat_then_ramp(base, ramp)
    assert -1.0 <= trend_score(s) <= 1.0


@given(
    base=st.floats(1.0, 3.0, allow_nan=False),
    r_lo=st.floats(-0.5, 0.5, allow_nan=False),
    bump=st.floats(0.0, 2.0, allow_nan=False),
)
def test_monotone_nondecreasing_in_r60(base, r_lo, bump):
    # Raising the terminal value (→ higher r60) with the rest of the series fixed
    # never lowers the score (structure + drawdown are functions of the head only
    # here, held fixed across the two series).
    lo = _flat_then_ramp(base, r_lo)
    hi = _flat_then_ramp(base, r_lo + bump)
    assert trend_score(hi) >= trend_score(lo) - 1e-9


def test_tanh_saturation_at_extreme_positive():
    # A huge positive r60 drives tanh(8·r60) → 1; with positive structure the blend
    # saturates near the upper clamp.
    s = _flat_then_ramp(1.0, 100.0)
    assert trend_score(s) >= 0.5


def test_tanh_saturation_at_extreme_negative():
    s = _flat_then_ramp(1.0, -0.99)
    assert trend_score(s) <= 0.0


@given(base=st.integers(1, 100).map(float))
def test_flat_series_is_near_zero_momentum(base):
    # base must be exactly representable (integer float) so that repeated summation of
    # equal values yields identical means across all windows — no MA float drift.
    s = tuple((f"d{i:04d}", base) for i in range(300))
    # flat → r60=0 → tanh(0)=0; structure 0; drawdown 0 → score 0
    assert math.isclose(trend_score(s), 0.0, abs_tol=1e-9)
