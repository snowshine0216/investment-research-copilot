from __future__ import annotations
import pandas as pd
from irc.allocation.correlation_filter import (
    drop_high_correlation_pairs, FilteredCandidates,
)


def test_drop_high_corr_keeps_higher_score():
    candidates = pd.DataFrame([
        {"instrument_id": "A", "score": 80, "asset_class": "us_etf"},
        {"instrument_id": "B", "score": 70, "asset_class": "us_etf"},
        {"instrument_id": "C", "score": 60, "asset_class": "cn_etf"},
    ])
    corr = pd.DataFrame(
        [[1.0, 0.95, 0.30], [0.95, 1.0, 0.30], [0.30, 0.30, 1.0]],
        index=["A", "B", "C"], columns=["A", "B", "C"],
    )
    out = drop_high_correlation_pairs(candidates, corr, threshold=0.85)
    assert isinstance(out, FilteredCandidates)
    ids = set(out.kept["instrument_id"])
    assert ids == {"A", "C"}
    assert out.dropped[0]["instrument_id"] == "B"


def test_drop_low_corr_keeps_all():
    candidates = pd.DataFrame([
        {"instrument_id": "A", "score": 80, "asset_class": "us_etf"},
        {"instrument_id": "B", "score": 70, "asset_class": "cn_etf"},
    ])
    corr = pd.DataFrame([[1.0, 0.30], [0.30, 1.0]],
                        index=["A", "B"], columns=["A", "B"])
    out = drop_high_correlation_pairs(candidates, corr, threshold=0.85)
    assert len(out.kept) == 2
    assert out.dropped == []


# ── Task 30: drop_correlated_and_renormalize ──────────────────────────────────
from irc.allocation.correlation_filter import drop_correlated_and_renormalize


def test_renormalize_after_drop_preserves_pre_drop_class_total():
    """Renormalization must preserve the within-class sum that was there
    before correlation drops. Rescaling to 1.0 would silently turn
    target_weight back into an intra-class share, breaking the portfolio
    total downstream (diagnostics.total_weight would equal the number of
    represented classes instead of 1.0)."""
    selected = [
        {"instrument_id": "A", "asset_class": "equity", "target_weight": 0.40},
        {"instrument_id": "B", "asset_class": "equity", "target_weight": 0.40},
        {"instrument_id": "C", "asset_class": "equity", "target_weight": 0.20},
    ]
    corr = {("A", "B"): 0.95, ("A", "C"): 0.30, ("B", "C"): 0.30}
    out = drop_correlated_and_renormalize(selected, corr_matrix=corr, threshold=0.85)
    assert len(out) == 2  # one of A/B dropped
    eq_total = sum(r["target_weight"] for r in out)
    pre_drop_total = 0.40 + 0.40 + 0.20
    assert abs(eq_total - pre_drop_total) < 1e-9  # pre-drop class total preserved


def test_renormalize_no_drop_preserves_weights_exactly():
    """When no drops happen, weights must pass through unchanged. This is the
    common case (sparse correlation matrix) and a regression test for the bug
    where weights were always rescaled to sum to 1.0 within class."""
    selected = [
        {"instrument_id": "A", "asset_class": "gold", "target_weight": 0.10},
        {"instrument_id": "B", "asset_class": "gold", "target_weight": 0.10},
        {"instrument_id": "C", "asset_class": "bond", "target_weight": 0.15},
        {"instrument_id": "D", "asset_class": "bond", "target_weight": 0.05},
    ]
    out = drop_correlated_and_renormalize(selected, corr_matrix={}, threshold=0.85)
    assert len(out) == 4
    assert abs(sum(r["target_weight"] for r in out) - 0.40) < 1e-9
    by_id = {r["instrument_id"]: r["target_weight"] for r in out}
    assert by_id == {"A": 0.10, "B": 0.10, "C": 0.15, "D": 0.05}
