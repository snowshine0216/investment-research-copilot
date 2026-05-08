from __future__ import annotations
import pandas as pd
from irc.allocation.pipeline import run_allocation, AllocationOutput


def test_pipeline_produces_per_class_top_k():
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
    class_targets = {
        "gold":           {"center": 0.20, "band": [0.12, 0.28]},
        "us_etf":         {"center": 0.25, "band": [0.18, 0.35]},
        "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
        "cn_bond_fund":   {"center": 0.15, "band": [0.10, 0.25]},
        "hk_etf":         {"center": 0.10, "band": [0.05, 0.15]},
        "cash":           {"center": 0.05, "band": [0.00, 0.10]},
    }
    corr = pd.DataFrame()  # empty; no filtering
    out = run_allocation(scores=scores, class_targets=class_targets,
                         gold_tilt="neutral", correlation=corr,
                         per_class_top_k=2)
    assert isinstance(out, AllocationOutput)
    target_weights = out.target_weights_per_class
    assert abs(sum(target_weights.values()) - 1.0) < 1e-3
    selected_ids = {row["instrument_id"] for row in out.selected_instruments}
    # us_etf top-2 = VTI + VOO; cn_bond_fund top-1 = SPDR
    assert "VTI" in selected_ids and "VOO" in selected_ids
    assert "SPDR" in selected_ids
