"""PURE M3 statistics: directional hit-rate, Spearman IC, clustered block
bootstrap CI, effective_n. No I/O, no RNG-from-clock (seeds are explicit args)."""
from __future__ import annotations
import math
import random
from typing import Callable, Sequence

from irc.monitor.eval.constants import FORWARD_H

_BIAS_SIGN = {"ADD_BIAS": 1, "REDUCE_BIAS": -1, "NEUTRAL": 0}


def sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def bias_to_sign(bias: str) -> int:
    """raw_bias string enum → predicted sign. ADD_BIAS→+1, REDUCE_BIAS→-1,
    NEUTRAL→0 (excluded downstream, same as a zero fwd_ret)."""
    return _BIAS_SIGN[bias]


def hit_rate(pred_dir: Sequence[int], fwd_ret: Sequence[float]) -> float:
    """Directional accuracy = fraction of rows where sign(pred)==sign(fwd_ret),
    over rows with fwd_ret != 0. Zero-return rows are excluded (sign(0)=0 is
    non-informative). Empty population → 0.0."""
    pairs = [(p, f) for p, f in zip(pred_dir, fwd_ret) if sign(f) != 0]
    if not pairs:
        return 0.0
    hits = sum(1 for p, f in pairs if sign(p) == sign(f))
    return hits / len(pairs)


def _avg_ranks(xs: Sequence[float]) -> list[float]:
    """Average-rank (standard Spearman tie convention)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_ic(signal: Sequence[float], fwd_ret: Sequence[float]) -> float | None:
    """Spearman rank correlation with average-rank tie handling. Returns None
    ONLY when all signal values are identical OR all return values are identical
    (zero variance on either side). Partial ties → valid avg-rank correlation."""
    n = len(signal)
    if n < 2 or len(fwd_ret) != n:
        return None
    if len(set(signal)) == 1 or len(set(fwd_ret)) == 1:
        return None
    rs, rf = _avg_ranks(signal), _avg_ranks(fwd_ret)
    ms, mf = sum(rs) / n, sum(rf) / n
    cov = sum((a - ms) * (b - mf) for a, b in zip(rs, rf))
    vs = sum((a - ms) ** 2 for a in rs)
    vf = sum((b - mf) ** 2 for b in rf)
    if vs <= 0 or vf <= 0:
        return None
    return cov / math.sqrt(vs * vf)


def _bucket_of(run_date: str, rank: dict[str, int]) -> int:
    # H run-date block: bucket = floor(rank(run_date) / FORWARD_H). FORWARD_H here
    # is a RUN-DATE count (an "H run-date block"), NOT NAV observations.
    return rank[run_date] // FORWARD_H


def _run_date_rank(rows: Sequence[dict]) -> dict[str, int]:
    distinct = sorted({r["run_date"] for r in rows})
    return {d: i for i, d in enumerate(distinct)}


def effective_n(rows: Sequence[dict]) -> int:
    """Count of shared-timeline H run-date blocks spanned by the rows."""
    if not rows:
        return 0
    rank = _run_date_rank(rows)
    return len({_bucket_of(r["run_date"], rank) for r in rows})


def block_bootstrap_ci(
    rows: Sequence[dict], stat: Callable[[Sequence[dict]], float],
    *, seed: int, b: int = 2000,
) -> tuple[float, float]:
    """95% percentile CI by resampling shared-timeline H run-date blocks with
    replacement. All funds' rows in a bucket move together (preserves
    contemporaneous cross-fund correlation; the 7-fund cross-section is not
    independent). Mitigates — does NOT eliminate — within-bucket window overlap.
    Fixed seed → byte-stable CI."""
    if not rows:
        return (0.0, 0.0)
    rank = _run_date_rank(rows)
    buckets: dict[int, list[dict]] = {}
    for r in rows:
        buckets.setdefault(_bucket_of(r["run_date"], rank), []).append(r)
    keys = sorted(buckets)
    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(b):
        sample: list[dict] = []
        for _ in range(len(keys)):
            sample.extend(buckets[rng.choice(keys)])
        stats.append(stat(sample))
    stats.sort()
    lo = stats[int(0.025 * (b - 1))]
    hi = stats[int(0.975 * (b - 1))]
    return (lo, hi)
