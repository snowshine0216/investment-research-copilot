"""Satellite-QDII sizing cap (adversarial-review item 015, 2026-05-19).

A single-sector QDII sized at 8.8% (000369 广发全球医疗保健) is a sector
bet wearing satellite clothing. These tests pin the deterministic cap +
redistribution behavior added to the allocation pipeline.
"""
from __future__ import annotations

import pandas as pd
import pytest

from irc.allocation.pipeline import run_allocation
from irc.allocation.target_weights import (
    DEFAULT_SATELLITE_QDII_MAX_WEIGHT,
    cap_satellite_qdii,
    is_satellite_qdii,
    redistribute_shaved_to_class,
)


def test_is_satellite_qdii_matches_us_and_hk_etf() -> None:
    assert is_satellite_qdii({"role": "satellite_cn_healthcare", "asset_class": "us_etf"})
    assert is_satellite_qdii({"role": "satellite_us_tech", "asset_class": "us_etf"})
    assert is_satellite_qdii({"role": "satellite_hk_dividend", "asset_class": "hk_etf"})


def test_is_satellite_qdii_excludes_core_role_and_cn_etf() -> None:
    assert not is_satellite_qdii({"role": "core_us_equity", "asset_class": "us_etf"})
    assert not is_satellite_qdii({"role": "satellite_cn_tech", "asset_class": "cn_etf"})
    assert not is_satellite_qdii({"role": "", "asset_class": "us_etf"})


def test_cap_satellite_qdii_shaves_excess_only() -> None:
    rows = [
        {"instrument_id": "000369", "role": "satellite_cn_healthcare",
         "asset_class": "us_etf", "target_weight": 0.088},
        {"instrument_id": "017641", "role": "core_us_equity",
         "asset_class": "us_etf", "target_weight": 0.097},
    ]
    capped, shaved = cap_satellite_qdii(rows, cap=0.05)
    by_id = {r["instrument_id"]: r for r in capped}
    assert by_id["000369"]["target_weight"] == pytest.approx(0.05)
    assert by_id["017641"]["target_weight"] == pytest.approx(0.097)  # core untouched
    assert shaved == pytest.approx(0.088 - 0.05)


def test_cap_satellite_qdii_passes_below_cap_unchanged() -> None:
    rows = [{"instrument_id": "X", "role": "satellite_cn_consumer",
             "asset_class": "us_etf", "target_weight": 0.04}]
    capped, shaved = cap_satellite_qdii(rows, cap=0.05)
    assert capped[0]["target_weight"] == pytest.approx(0.04)
    assert shaved == 0.0


def test_redistribute_shaved_prefers_higher_score_with_headroom() -> None:
    rows = [
        {"instrument_id": "A", "role": "satellite_cn_healthcare",
         "asset_class": "us_etf", "target_weight": 0.05, "composite_score": 60},
        {"instrument_id": "B", "role": "core_us_equity",
         "asset_class": "us_etf", "target_weight": 0.05, "composite_score": 70},
    ]
    out, remainder = redistribute_shaved_to_class(rows, 0.04, "us_etf", cap=0.05)
    by_id = {r["instrument_id"]: r for r in out}
    assert by_id["B"]["target_weight"] == pytest.approx(0.09)  # core absorbs all
    assert by_id["A"]["target_weight"] == pytest.approx(0.05)  # capped, no room
    assert remainder == 0.0


def test_redistribute_falls_to_residual_when_no_headroom() -> None:
    rows = [
        {"instrument_id": "A", "role": "satellite_cn_healthcare",
         "asset_class": "us_etf", "target_weight": 0.05, "composite_score": 60},
        {"instrument_id": "B", "role": "satellite_us_tech",
         "asset_class": "us_etf", "target_weight": 0.05, "composite_score": 70},
    ]
    out, remainder = redistribute_shaved_to_class(rows, 0.04, "us_etf", cap=0.05)
    by_id = {r["instrument_id"]: r for r in out}
    assert by_id["A"]["target_weight"] == pytest.approx(0.05)
    assert by_id["B"]["target_weight"] == pytest.approx(0.05)
    assert remainder == pytest.approx(0.04)


def _class_targets() -> dict[str, dict[str, object]]:
    return {
        "gold":   {"center": 0.20, "band": [0.12, 0.28]},
        "us_etf": {"center": 0.80, "band": [0.60, 0.90]},  # exaggerated for the test
    }


def test_pipeline_caps_satellite_qdii_end_to_end() -> None:
    """A satellite QDII that would naively get the whole us_etf class
    weight is capped at 5%; the residual flows to cash and is reported in
    diagnostics."""
    scores = [
        {"instrument_id": "G", "asset_class": "gold",
         "role": "core_gold_hedge", "composite_score": 60},
        {"instrument_id": "Q", "asset_class": "us_etf",
         "role": "satellite_cn_healthcare", "composite_score": 90},
    ]
    out = run_allocation(
        scores=scores, class_targets=_class_targets(),
        gold_tilt="neutral", correlation=pd.DataFrame(),
        per_class_top_k=4,
    )
    q = next(r for r in out.selected_instruments if r["instrument_id"] == "Q")
    assert q["target_weight"] == pytest.approx(DEFAULT_SATELLITE_QDII_MAX_WEIGHT)
    assert out.diagnostics["satellite_qdii_excess_to_cash"] == pytest.approx(0.75)
    # Cash residual must absorb the shaved weight so total + cash ≈ 1.0.
    assert (
        out.diagnostics["total_weight"]
        + out.diagnostics["cash_residual_weight"]
    ) == pytest.approx(1.0)
