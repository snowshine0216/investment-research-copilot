from __future__ import annotations
import pytest
from irc.allocation.target_weights import (
    apply_gold_tilt, softmax_distribute, compute_target_weights, AssetClassWeight,
)


def test_apply_tilt_within_band():
    new = apply_gold_tilt(center=0.20, band=(0.12, 0.28), tilt="neutral_plus")
    assert 0.20 < new <= 0.28


def test_apply_tilt_clamped_to_band():
    new = apply_gold_tilt(center=0.20, band=(0.12, 0.22), tilt="overweight")
    assert new == 0.22  # clamped


def test_softmax_distribute_preserves_sum():
    w = softmax_distribute(scores=(60.0, 80.0, 50.0), temperature=10.0)
    assert sum(w) == pytest.approx(1.0)
    assert w[1] > w[0] > w[2]


def test_compute_target_weights_returns_per_class():
    out = compute_target_weights(
        class_targets={
            "gold":           {"center": 0.20, "band": [0.12, 0.28]},
            "us_etf":         {"center": 0.25, "band": [0.18, 0.35]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund":   {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf":         {"center": 0.10, "band": [0.05, 0.15]},
            "cash":           {"center": 0.05, "band": [0.00, 0.10]},
        },
        gold_tilt="neutral",
    )
    assert isinstance(out, dict)
    assert all(isinstance(v, AssetClassWeight) for v in out.values())
    total = sum(v.target_weight for v in out.values())
    assert abs(total - 1.0) < 1e-3
