from __future__ import annotations
import math
from irc.monitor.eval.baselines import (
    buy_hold_dir, momentum_dir, momentum_defined,
)


def test_buy_hold_is_always_long():
    assert buy_hold_dir() == 1


def test_momentum_dir_sign_from_as_of_slice():
    # 22 ascending obs → 20-day return is positive → +1
    series = tuple((f"2026-01-{i:02d}", 1.0 + 0.01 * i) for i in range(1, 23))
    assert momentum_dir(series) == 1


def test_momentum_uses_as_of_slice_not_entry_idx_plus_1():
    # SIGN-FLIP fixture: the <= as_of_date slice trends UP (momentum +1),
    # but a single post-publication NAV (entry obs) reverses the 20-day sign.
    # The baseline must use the as_of_date slice → +1, NOT the entry+1 slice → -1.
    up = [1.0 + 0.01 * i for i in range(21)]    # 21 obs, rising
    as_of_slice = tuple((f"2026-01-{i:02d}", v) for i, v in enumerate(up, start=1))
    # momentum over the 21-obs as_of slice is positive
    assert momentum_dir(as_of_slice) == 1
    # (The forward_score layer is responsible for passing the as_of slice; this
    #  test pins that momentum_dir reads the LAST obs of whatever slice it's given.)


def test_momentum_defined_false_when_too_few_obs():
    short = tuple((f"2026-01-{i:02d}", 1.0 + 0.01 * i) for i in range(1, 21))  # 20 obs < 21
    assert momentum_defined(short) is False


def test_momentum_defined_false_when_non_finite():
    # window_returns returns the NaN (not None) for a NaN endpoint; an is-None-only
    # filter would let it slip → must be caught by math.isfinite.
    series = tuple((f"2026-01-{i:02d}", 1.0 + 0.01 * i) for i in range(1, 22))
    series = series[:-1] + (("2026-01-22", float("nan")),)
    assert momentum_defined(series) is False


def test_momentum_defined_true_for_clean_series():
    series = tuple((f"2026-01-{i:02d}", 1.0 + 0.01 * i) for i in range(1, 23))
    assert momentum_defined(series) is True
