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


def test_renormalize_after_drop_keeps_class_weight_one():
    selected = [
        {"instrument_id": "A", "asset_class": "equity", "target_weight": 0.40},
        {"instrument_id": "B", "asset_class": "equity", "target_weight": 0.40},
        {"instrument_id": "C", "asset_class": "equity", "target_weight": 0.20},
    ]
    corr = {("A", "B"): 0.95, ("A", "C"): 0.30, ("B", "C"): 0.30}
    out = drop_correlated_and_renormalize(selected, corr_matrix=corr, threshold=0.85)
    assert len(out) == 2  # one of A/B dropped
    eq_total = sum(r["target_weight"] for r in out)
    assert abs(eq_total - 1.0) < 1e-9  # class total preserved at 1.0
