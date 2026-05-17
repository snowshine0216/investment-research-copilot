from __future__ import annotations
import pandas as pd
from irc.allocation.pipeline import run_allocation, AllocationOutput


def _class_targets() -> dict:
    return {
        "gold":           {"center": 0.20, "band": [0.12, 0.28]},
        "us_etf":         {"center": 0.20, "band": [0.15, 0.30]},
        "cn_etf":         {"center": 0.20, "band": [0.15, 0.30]},
        "cn_equity_fund": {"center": 0.10, "band": [0.05, 0.20]},
        "cn_bond_fund":   {"center": 0.15, "band": [0.10, 0.25]},
        "hk_etf":         {"center": 0.10, "band": [0.05, 0.15]},
        "cash":           {"center": 0.05, "band": [0.00, 0.10]},
    }


def test_pipeline_produces_per_class_top_k():
    """Backward compat: with no `role` field, behavior matches the old pure
    top-K-by-score within each class."""
    scores = [
        {"instrument_id": "VTI", "asset_class": "us_etf", "composite_score": 78,
         "action": "buy_candidate", "conviction": "med"},
        {"instrument_id": "VOO", "asset_class": "us_etf", "composite_score": 75,
         "action": "buy_candidate", "conviction": "med"},
        {"instrument_id": "QQQ", "asset_class": "us_etf", "composite_score": 65,
         "action": "watch", "conviction": "med"},
        {"instrument_id": "SPDR", "asset_class": "cn_bond_fund", "composite_score": 70,
         "action": "buy_candidate", "conviction": "med"},
    ]
    corr = pd.DataFrame()
    out = run_allocation(scores=scores, class_targets=_class_targets(),
                         gold_tilt="neutral", correlation=corr,
                         per_class_top_k=2)
    assert isinstance(out, AllocationOutput)
    assert abs(sum(out.target_weights_per_class.values()) - 1.0) < 1e-3
    selected_ids = {row["instrument_id"] for row in out.selected_instruments}
    # us_etf top-2 = VTI + VOO; cn_bond_fund top-1 = SPDR
    assert "VTI" in selected_ids and "VOO" in selected_ids
    assert "SPDR" in selected_ids
    # Diagnostics' total_weight must equal the sum of represented per-class
    # weights (not the count of classes). Regression for the bug where
    # correlation_filter's renormalize-to-1.0 silently inflated total_weight
    # to N_classes, tripping the decision gate's target_weights_invalid.
    represented = {row["asset_class"] for row in out.selected_instruments}
    expected_total = sum(
        out.target_weights_per_class[cls] for cls in represented
    )
    assert abs(out.diagnostics["total_weight"] - expected_total) < 1e-6
    # Unallocated classes (cash, hk_etf etc.) must surface as cash_residual so
    # invested + residual cover the full portfolio. Without this the decision
    # gate's target_weights_invalid would fire even on a correct allocation.
    cash_residual = out.diagnostics["cash_residual_weight"]
    assert abs(out.diagnostics["total_weight"] + cash_residual - 1.0) < 1e-6


def test_pipeline_role_aware_picks_one_per_role_within_class_first():
    """Same-class candidates with different roles: a slightly lower-scored
    candidate from a NEW role wins over a higher-scored duplicate of an
    already-represented role. Ensures sector / factor diversity isn't
    crushed by 4 near-clones of the broad core ETF."""
    scores = [
        # 5 broad CN core ETFs (high scores, same role)
        {"instrument_id": "510310", "asset_class": "cn_etf", "role": "core_cn_equity",
         "composite_score": 64.0, "action": "watch", "conviction": "low"},
        {"instrument_id": "510300", "asset_class": "cn_etf", "role": "core_cn_equity",
         "composite_score": 63.0, "action": "watch", "conviction": "low"},
        {"instrument_id": "510330", "asset_class": "cn_etf", "role": "core_cn_equity",
         "composite_score": 62.0, "action": "watch", "conviction": "low"},
        # Distinct roles, lower scores — must still get represented
        {"instrument_id": "515080", "asset_class": "cn_etf", "role": "satellite_cn_dividend",
         "composite_score": 60.0, "action": "watch", "conviction": "low"},
        {"instrument_id": "512960", "asset_class": "cn_etf", "role": "satellite_cn_soe",
         "composite_score": 59.0, "action": "watch", "conviction": "low"},
    ]
    out = run_allocation(scores=scores, class_targets=_class_targets(),
                         gold_tilt="neutral", correlation=pd.DataFrame(),
                         per_class_top_k=4)
    selected_ids = {row["instrument_id"] for row in out.selected_instruments}
    # Expected: top-1 per role (510310 core, 515080 dividend, 512960 soe) +
    # 1 fill slot from remaining best score (510300). 510330 dropped — same role
    # as already-picked 510310 and lower-scored than the role-novel 515080/512960.
    assert "510310" in selected_ids, "highest-scored core_cn_equity must be picked"
    assert "515080" in selected_ids, "satellite_cn_dividend must be represented"
    assert "512960" in selected_ids, "satellite_cn_soe must be represented even at lower score"
    assert len(selected_ids) == 4
    assert "510330" not in selected_ids, "duplicate core role should lose to role-novel picks"


def test_pipeline_role_aware_falls_back_to_score_when_roles_exhausted():
    """If per_class_top_k > distinct roles, fill remaining slots by raw score."""
    scores = [
        {"instrument_id": "A1", "asset_class": "cn_etf", "role": "core_cn_equity",
         "composite_score": 70.0, "action": "watch", "conviction": "low"},
        {"instrument_id": "A2", "asset_class": "cn_etf", "role": "core_cn_equity",
         "composite_score": 68.0, "action": "watch", "conviction": "low"},
        {"instrument_id": "A3", "asset_class": "cn_etf", "role": "core_cn_equity",
         "composite_score": 65.0, "action": "watch", "conviction": "low"},
        {"instrument_id": "B1", "asset_class": "cn_etf", "role": "satellite_cn_dividend",
         "composite_score": 60.0, "action": "watch", "conviction": "low"},
    ]
    out = run_allocation(scores=scores, class_targets=_class_targets(),
                         gold_tilt="neutral", correlation=pd.DataFrame(),
                         per_class_top_k=3)
    ids = [row["instrument_id"] for row in out.selected_instruments]
    # Phase 1 (role-novel by score): A1 (core), B1 (dividend) — 2 picks
    # Phase 2 (fill by remaining score): A2 (next best) — 3rd pick
    assert set(ids) == {"A1", "B1", "A2"}


def test_pipeline_role_aware_handles_missing_role_field():
    """Backward compat: rows without role field treated as a single anonymous
    role. Old test_pipeline_produces_per_class_top_k still passes via this path."""
    scores = [
        {"instrument_id": "X", "asset_class": "us_etf", "composite_score": 80,
         "action": "watch", "conviction": "low"},
        {"instrument_id": "Y", "asset_class": "us_etf", "composite_score": 75,
         "action": "watch", "conviction": "low"},
    ]
    out = run_allocation(scores=scores, class_targets=_class_targets(),
                         gold_tilt="neutral", correlation=pd.DataFrame(),
                         per_class_top_k=2)
    ids = {row["instrument_id"] for row in out.selected_instruments}
    assert ids == {"X", "Y"}


def test_pipeline_per_class_top_k_zero_selects_none() -> None:
    scores = [
        {"instrument_id": "VTI", "asset_class": "us_etf", "role": "core_us_equity",
         "composite_score": 80, "action": "watch", "conviction": "low"},
    ]
    out = run_allocation(scores=scores, class_targets=_class_targets(),
                         gold_tilt="neutral", correlation=pd.DataFrame(),
                         per_class_top_k=0)

    assert out.selected_instruments == []
    assert out.diagnostics["total_weight"] == 0
