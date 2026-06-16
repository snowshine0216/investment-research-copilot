"""PURE M3 baselines: buy_hold (always-long), momentum (sign of the 20-obs return
over the <= as_of_date slice — the signal's own feature cutoff), and the
within-run_date permutation null. Paired deltas vs the signal hit-rate.

Momentum-undefined detection is load-bearing: window_returns (returns.py) ONLY
None-guards a falsy denominator (`if not denom`) — it does NOT catch a negative
denom or a non-finite endpoint (a NaN/inf propagates as a NaN/inf return, NOT
None). So definedness needs `is None` OR `not math.isfinite(...)`."""
from __future__ import annotations
import math
import random as _random
from typing import Any, Callable, Sequence

from irc.monitor.eval.constants import BOOTSTRAP_B, FORWARD_H, MIN_PERM_DATES
from irc.monitor.eval.stats import sign
from irc.monitor.returns import window_returns


def buy_hold_dir() -> int:
    """Always-long. hit-rate = base rate of positive forward return."""
    return 1


def _momentum_value(acc_slice: tuple[tuple[str, float], ...]) -> float | None:
    """20-obs return over the provided slice (caller passes the <= as_of_date
    slice). Uses the LAST observation in the slice as the endpoint — never a
    post-publication NAV the signal didn't see."""
    return window_returns(acc_slice, windows=(FORWARD_H,))[FORWARD_H]


def momentum_defined(acc_slice: tuple[tuple[str, float], ...]) -> bool:
    """True iff the 20-obs momentum is a finite number. Catches: < 21 obs / falsy
    denom (window_returns → None) AND non-finite endpoint (window_returns → NaN/inf)."""
    v = _momentum_value(acc_slice)
    return v is not None and math.isfinite(v)


def momentum_dir(acc_slice: tuple[tuple[str, float], ...]) -> int:
    """sign of the 20-obs return over the <= as_of_date slice. Caller must check
    momentum_defined first; on undefined this returns 0 (treated as no-direction)."""
    v = _momentum_value(acc_slice)
    if v is None or not math.isfinite(v):
        return 0
    return sign(v)


def permutable_groups(
    rows: Sequence[dict], *, label_key: str,
) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Group rows by run_date (the publication cohort — NOT entry_nav_date). A
    group is permutable only with >= 2 rows AND non-identical labels. Excluded
    groups are counted separately: too_few_rows vs identical_labels."""
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["run_date"], []).append(r)
    groups: dict[str, list[dict]] = {}
    excl: dict[str, int] = {"too_few_rows": 0, "identical_labels": 0}
    for rd, grp in by_date.items():
        if len(grp) < 2:
            excl["too_few_rows"] += 1
            continue
        if len({r[label_key] for r in grp}) == 1:
            excl["identical_labels"] += 1
            continue
        groups[rd] = grp
    return groups, excl


def permutation_excluded(rows: Sequence[dict], *, label_key: str) -> dict[str, int]:
    """Just the exclusion-reason counts for diagnostics."""
    return permutable_groups(rows, label_key=label_key)[1]


def random_null_delta(
    rows: Sequence[dict], *, metric: Callable[[Sequence[dict]], float],
    label_key: str, signal_value: float, seed: int, b: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """signal_metric - permuted-metric. Permutes labels WITHIN each run_date group
    (preserves each publication cohort's return cross-section). The permuted
    statistic IS the metric under test. < MIN_PERM_DATES permutable groups →
    {state: 'insufficient_data'} (no delta/CI). Returns
    {delta, ci_low, ci_high} otherwise."""
    groups, _ = permutable_groups(rows, label_key=label_key)
    if len(groups) < MIN_PERM_DATES:
        return {"state": "insufficient_data"}
    rng = _random.Random(seed)
    permuted_metric: list[float] = []
    for _ in range(b):
        shuffled: list[dict] = []
        for grp in groups.values():
            labels = [r[label_key] for r in grp]
            rng.shuffle(labels)
            shuffled.extend({**r, label_key: lab} for r, lab in zip(grp, labels))
        permuted_metric.append(metric(shuffled))
    permuted_metric.sort()
    mean_perm = sum(permuted_metric) / len(permuted_metric)
    lo = permuted_metric[int(0.025 * (b - 1))]
    hi = permuted_metric[int(0.975 * (b - 1))]
    return {
        "delta": signal_value - mean_perm,
        "ci_low": signal_value - hi,
        "ci_high": signal_value - lo,
    }
