from __future__ import annotations
from irc.monitor.eval.stats import (
    sign, bias_to_sign, hit_rate, spearman_ic, effective_n, block_bootstrap_ci,
)


def test_sign():
    assert sign(0.3) == 1 and sign(-0.3) == -1 and sign(0.0) == 0


def test_bias_to_sign_map():
    assert bias_to_sign("ADD_BIAS") == 1
    assert bias_to_sign("REDUCE_BIAS") == -1
    assert bias_to_sign("NEUTRAL") == 0


def test_hit_rate_excludes_zero_fwd_ret():
    # pred dirs and fwd_rets paired; the zero-return row is excluded entirely
    pred = [1, 1, -1, 1]
    fwd = [0.02, -0.01, -0.03, 0.0]   # last row excluded (sign(0)=0)
    # correct: row0 (1 vs +) yes, row1 (1 vs -) no, row2 (-1 vs -) yes → 2/3
    assert hit_rate(pred, fwd) == 2 / 3


def test_hit_rate_empty_population_is_zero():
    assert hit_rate([], []) == 0.0
    assert hit_rate([1, -1], [0.0, 0.0]) == 0.0  # all zero-return → excluded → empty


def test_spearman_perfect_monotone():
    ic = spearman_ic([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0])
    assert ic is not None and abs(ic - 1.0) < 1e-9


def test_spearman_perfect_inverse():
    ic = spearman_ic([1.0, 2.0, 3.0, 4.0], [40.0, 30.0, 20.0, 10.0])
    assert ic is not None and abs(ic + 1.0) < 1e-9


def test_spearman_constant_signal_returns_none():
    assert spearman_ic([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) is None


def test_spearman_constant_return_returns_none():
    assert spearman_ic([1.0, 2.0, 3.0], [7.0, 7.0, 7.0]) is None


def test_spearman_partial_ties_uses_avg_rank_not_none():
    # all-same-but-one fixture: ties present but arrays are NOT constant → valid IC
    ic = spearman_ic([1.0, 1.0, 1.0, 2.0], [3.0, 3.0, 3.0, 9.0])
    assert ic is not None


def _row(run_date, pred, fwd):
    # minimal row shape the bootstrap consumes
    return {"run_date": run_date, "pred": pred, "fwd": fwd}


def test_effective_n_counts_shared_timeline_blocks():
    # H run-date block = FORWARD_H=20 distinct run_dates per bucket.
    # bucket = floor(rank(run_date) / H). 21 distinct run_dates → 2 buckets.
    # All funds on the SAME run_date share a bucket (cross-section moves together).
    run_dates = [f"2026-01-{d:02d}" for d in range(1, 22)]  # 21 distinct dates
    rows = [_row(d, 1, 0.01) for d in run_dates] + [_row(run_dates[0], -1, -0.01)]
    # bucket assignment is by run_date RANK, not row index / NAV obs index
    assert effective_n(rows) == 2


def _stat_hit_rate(rs):
    return hit_rate([r["pred"] for r in rs], [r["fwd"] for r in rs])


def _stat_zero(_rs):
    return 0.0


def test_block_bootstrap_ci_deterministic_with_fixed_seed():
    rows = [_row(f"2026-01-{d:02d}", 1, 0.01) for d in range(1, 11)] + [
        _row(f"2026-01-{d:02d}", -1, -0.02) for d in range(11, 21)
    ]
    ci1 = block_bootstrap_ci(rows, _stat_hit_rate, seed=1234, b=500)
    ci2 = block_bootstrap_ci(rows, _stat_hit_rate, seed=1234, b=500)
    assert ci1 == ci2                      # fixed-seed determinism
    assert ci1[0] <= ci1[1]                # ordered lo<=hi


def test_block_bootstrap_ci_empty_rows():
    assert block_bootstrap_ci([], _stat_zero, seed=1, b=10) == (0.0, 0.0)
