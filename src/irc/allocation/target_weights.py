from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AssetClassWeight:
    asset_class: str
    target_weight: float
    band: tuple[float, float]


_TILT_DELTA = {"overweight": 0.05, "neutral_plus": 0.02,
                "neutral": 0.0, "neutral_minus": -0.02, "underweight": -0.05}


def apply_gold_tilt(center: float, band: tuple[float, float], tilt: str) -> float:
    """Adjust gold center by tilt magnitude, clamped to band."""
    new = center + _TILT_DELTA.get(tilt, 0.0)
    return max(band[0], min(band[1], new))


def softmax_distribute(scores: tuple[float, ...], temperature: float = 10.0) -> tuple[float, ...]:
    """Score-weighted softmax. temperature controls concentration: higher → more equal."""
    if not scores:
        return ()
    exps = [math.exp(s / temperature) for s in scores]
    total = sum(exps)
    return tuple(e / total for e in exps)


def compute_target_weights(
    class_targets: dict[str, dict[str, object]],
    gold_tilt: str,
) -> dict[str, AssetClassWeight]:
    """Compute per-class target weights. Applies gold tilt, redistributes the
    delta proportionally across the other 5 classes."""
    out: dict[str, AssetClassWeight] = {}
    gold_cfg = class_targets["gold"]
    new_gold = apply_gold_tilt(
        center=float(gold_cfg["center"]),  # type: ignore[arg-type]
        band=tuple(gold_cfg["band"]),       # type: ignore[arg-type]
        tilt=gold_tilt,
    )
    delta = new_gold - float(gold_cfg["center"])  # type: ignore[arg-type]
    others = [k for k in class_targets if k != "gold"]
    others_total = sum(float(class_targets[k]["center"]) for k in others)  # type: ignore[arg-type]
    if others_total == 0:
        others_total = 1.0  # guard against all-zero non-gold config
    for k in class_targets:
        if k == "gold":
            new_w = new_gold
        else:
            share = float(class_targets[k]["center"]) / others_total      # type: ignore[arg-type]
            new_w = float(class_targets[k]["center"]) - delta * share     # type: ignore[arg-type]
        out[k] = AssetClassWeight(
            asset_class=k, target_weight=new_w,
            band=tuple(class_targets[k]["band"]),                          # type: ignore[arg-type]
        )
    return out
