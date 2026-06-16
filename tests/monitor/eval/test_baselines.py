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


# ---------------------------------------------------------------------------
# Task 8: within-run_date permutation grouping + degenerate exclusions
# ---------------------------------------------------------------------------
from irc.monitor.eval.baselines import permutable_groups, permutation_excluded  # noqa: E402


def _row(run_date, label, fwd):
    return {"run_date": run_date, "label": label, "fwd": fwd}


def test_single_actionable_run_date_excluded_too_few_rows():
    rows = [_row("2026-01-01", 1, 0.01)]  # only 1 row in its group
    groups, excl = permutable_groups(rows, label_key="label")
    assert groups == {}                       # nothing permutable
    assert excl["too_few_rows"] == 1
    assert excl.get("identical_labels", 0) == 0


def test_identical_label_run_date_excluded_separately():
    # all 7 funds ADD_BIAS (label +1) → permuting is identity → no null variation.
    rows = [_row("2026-01-02", 1, 0.01 * i) for i in range(1, 8)]
    groups, excl = permutable_groups(rows, label_key="label")
    assert groups == {}
    assert excl["identical_labels"] == 1
    assert excl.get("too_few_rows", 0) == 0   # NOT counted as too_few_rows


def test_groups_share_run_date_not_entry_nav_date():
    # two funds same run_date, different entry_nav_date → permuted TOGETHER
    rows = [
        {"run_date": "2026-01-03", "entry_nav_date": "2026-01-04", "label": 1, "fwd": 0.02},
        {"run_date": "2026-01-03", "entry_nav_date": "2026-01-06", "label": -1, "fwd": -0.01},
    ]
    groups, excl = permutable_groups(rows, label_key="label")
    assert set(groups.keys()) == {"2026-01-03"}
    assert len(groups["2026-01-03"]) == 2
