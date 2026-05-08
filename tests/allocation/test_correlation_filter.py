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
