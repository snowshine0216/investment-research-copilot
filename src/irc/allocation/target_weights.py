from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import math


# Adversarial review §C2 (2026-05-19): a single-sector QDII sized at 8.8%
# is a sector bet wearing satellite clothing. Cap any satellite-role QDII
# at this fraction of NAV. Excess weight is redistributed to a non-capped
# same-class peer first; if no peer has headroom, it falls to cash residual.
DEFAULT_SATELLITE_QDII_MAX_WEIGHT = 0.05
_QDII_ASSET_CLASSES: frozenset[str] = frozenset({"us_etf", "hk_etf"})


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


def is_satellite_qdii(row: dict[str, Any]) -> bool:
    role = str(row.get("role") or "")
    asset_class = str(row.get("asset_class") or "")
    return role.startswith("satellite_") and asset_class in _QDII_ASSET_CLASSES


def cap_satellite_qdii(
    selected: list[dict[str, Any]],
    cap: float = DEFAULT_SATELLITE_QDII_MAX_WEIGHT,
) -> tuple[list[dict[str, Any]], float]:
    """Cap every satellite-role QDII row at ``cap``. Returns the new rows
    and the total weight shaved off (caller should redistribute or treat
    as cash residual).

    Pure function. Rows are returned in their original order with
    ``target_weight`` lowered where it exceeded ``cap``; non-QDII and
    core-role rows are passed through unchanged.
    """
    capped: list[dict[str, Any]] = []
    shaved = 0.0
    for row in selected:
        if is_satellite_qdii(row) and float(row["target_weight"]) > cap:
            shaved += float(row["target_weight"]) - cap
            capped.append({**row, "target_weight": cap})
        else:
            capped.append(dict(row))
    return capped, shaved


def redistribute_shaved_to_class(
    rows: list[dict[str, Any]],
    shaved: float,
    target_class: str,
    cap: float = DEFAULT_SATELLITE_QDII_MAX_WEIGHT,
) -> tuple[list[dict[str, Any]], float]:
    """Pour ``shaved`` weight into non-capped rows of ``target_class`` in
    score order. Returns updated rows and any unabsorbed remainder (which
    the caller folds into cash residual).

    A non-capped row is one where either:
      - it is NOT a satellite QDII (no cap applies), or
      - it is a satellite QDII with current weight < cap.
    """
    if shaved <= 0:
        return [dict(r) for r in rows], 0.0
    same_class = [r for r in rows if r["asset_class"] == target_class]
    same_class_sorted = sorted(
        same_class, key=lambda r: float(r.get("composite_score", 0.0)), reverse=True
    )
    headroom_by_id: dict[str, float] = {}
    for r in same_class_sorted:
        if is_satellite_qdii(r):
            headroom_by_id[r["instrument_id"]] = max(0.0, cap - float(r["target_weight"]))
        else:
            headroom_by_id[r["instrument_id"]] = float("inf")
    remaining = shaved
    deltas: dict[str, float] = {}
    for r in same_class_sorted:
        if remaining <= 0:
            break
        take = min(remaining, headroom_by_id[r["instrument_id"]])
        if take > 0:
            deltas[r["instrument_id"]] = deltas.get(r["instrument_id"], 0.0) + take
            remaining -= take
    out = [
        {**r, "target_weight": float(r["target_weight"]) + deltas.get(r["instrument_id"], 0.0)}
        for r in rows
    ]
    return out, max(0.0, remaining)


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
