from __future__ import annotations
import statistics


def factor_breakdown_completeness(scores: list[dict]) -> float:
    if not scores:
        return 1.0
    required = {"valuation_cost", "risk", "quality", "macro_fit", "thesis_news"}
    counts = [
        len(required & set(s.get("factor_breakdown", {}).keys())) / len(required)
        for s in scores
    ]
    return sum(counts) / len(counts)


def raw_ref_reachability(scores: list[dict], index: set[str]) -> float:
    refs: list[str] = []
    for s in scores:
        for v in s.get("factor_breakdown", {}).values():
            refs.extend(v.get("raw_refs", []))
    if not refs:
        return 1.0
    return sum(1 for r in refs if r in index) / len(refs)


def historical_sanity_rho(scores: list[dict]) -> float:
    """Spearman correlation between composite score and a baseline ordering.

    Returns a value in [-1, 1]. Positive means scores preserve a reasonable ranking.
    Uses the ordinal position in the input list as the baseline.
    """
    if len(scores) < 2:
        return 1.0
    vals = [s.get("composite_score", 0.0) for s in scores]
    n = len(vals)
    baseline = list(range(n))
    # Spearman via rank correlation
    rank_v = _rankdata(vals)
    rank_b = _rankdata(baseline)
    d_sq = sum((rv - rb) ** 2 for rv, rb in zip(rank_v, rank_b))
    rho = 1 - 6 * d_sq / (n * (n * n - 1))
    return rho


def _rankdata(data: list[float]) -> list[float]:
    sorted_idx = sorted(range(len(data)), key=lambda i: data[i])
    ranks = [0.0] * len(data)
    for rank, idx in enumerate(sorted_idx):
        ranks[idx] = float(rank + 1)
    return ranks


def score_distribution_stability(scores_a: list[float], scores_b: list[float]) -> float:
    """Mean absolute difference between two score distributions (lower is more stable)."""
    if not scores_a or not scores_b:
        return 0.0
    mean_a = sum(scores_a) / len(scores_a)
    mean_b = sum(scores_b) / len(scores_b)
    return abs(mean_a - mean_b)
