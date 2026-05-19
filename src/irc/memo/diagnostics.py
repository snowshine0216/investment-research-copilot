"""Memo diagnostic-bullet composers.

Pure functions. Each compose_* returns either an empty tuple (no
diagnostic to surface) or a tuple of one-line bullets in the order they
should appear in the memo's risk-notes / execution-notes section.

These are deterministic — built from the same allocation / preferences
data the rest of the pipeline already produces — so the LLM cannot
omit them and the audit gate (item 009) can verify their presence.
"""
from __future__ import annotations

from typing import Any


_EXECUTION_DRIFT_FLOOR_PP = 0.05  # 5 percentage points

# Adversarial review §C4+§C5 (2026-05-19): ~25% USD QDII exposure went
# out without any FX-hedge, premium/discount, or quota mention. When
# QDII weight exceeds this floor, the memo gets a dedicated diagnostic.
_QDII_WEIGHT_FLOOR_FOR_DIAGNOSTIC = 0.20
_QDII_ASSET_CLASSES: frozenset[str] = frozenset({"us_etf", "hk_etf"})


def compose_execution_drift_lines(
    allocation: dict[str, Any] | None,
    cash_target_weight: float,
) -> tuple[str, ...]:
    """Emit an alert when actual cash residual exceeds target by ≥5pp.

    Adversarial review §C3 (2026-05-19): in 2026-05-19 the cn_etf rows
    (515080, 510050, 512960) and 511520 collapsed to 0% target_weight
    due to venue mismatch and no proxy; cash_residual hit 15% vs a 5%
    target. The memo treated this as ``现金弹性`` (cash flexibility)
    without surfacing it as a portfolio risk.

    Returns an empty tuple when:
      - allocation is None or missing diagnostics,
      - drift < 5pp,
      - cash residual is at or below the target.
    """
    if not allocation:
        return ()
    diagnostics = allocation.get("diagnostics") or {}
    residual_raw = diagnostics.get("cash_residual_weight")
    if residual_raw is None:
        return ()
    try:
        residual = float(residual_raw)
        target = float(cash_target_weight)
    except (TypeError, ValueError):
        return ()
    drift = residual - target
    if drift < _EXECUTION_DRIFT_FLOOR_PP:
        return ()
    selected = allocation.get("selected_instruments") or []
    blocked_rows = [
        r for r in selected
        if r.get("instrument_id") and float(r.get("target_weight") or 0.0) == 0.0
    ]
    affected = "、".join(
        f"{r['instrument_id']}" + (f" {r.get('name_cn') or ''}".rstrip() if r.get("name_cn") else "")
        for r in blocked_rows
    )
    header = (
        f"执行漂移提醒：现金残留 {residual * 100:.1f}% 高于目标 "
        f"{target * 100:.1f}% 约 {drift * 100:.1f}pp，超出 "
        f"{_EXECUTION_DRIFT_FLOOR_PP * 100:.0f}pp 警戒。"
    )
    if affected:
        detail = f"未填仓标的：{affected}。"
    else:
        detail = "未填仓标的：—"
    remediation = (
        "建议处置：开通缺失的交易渠道 / 为受影响标的注册代理 / "
        "将未填仓权重重分配到同 role 的兼容替代品。"
    )
    return (header, detail, remediation)


def _qdii_weight(selected: list[dict]) -> float:
    return sum(
        float(r.get("target_weight") or 0.0)
        for r in selected
        if str(r.get("asset_class") or "") in _QDII_ASSET_CLASSES
    )


def compose_fx_qdii_lines(
    allocation: dict[str, Any] | None,
    usd_tolerance: tuple[float, float] | None,
) -> tuple[str, ...]:
    """Emit FX & QDII diagnostic lines when QDII weight crosses the floor.

    Adversarial review §C4+§C5: a CNY-based investor running 25% QDII
    weight has unhedged USD exposure plus QDII premium/discount risk
    plus quota-suspension risk. None of these surface today.

    Returns an empty tuple when QDII weight is below the floor or the
    allocation doesn't carry selected_instruments. Returns a 3-line
    diagnostic when above the floor:
      1. total QDII weight + tolerance status
      2. premium/discount placeholder (data layer to populate later)
      3. hedge-cost placeholder (likewise)
    """
    if not allocation:
        return ()
    selected = allocation.get("selected_instruments") or []
    qdii_w = _qdii_weight(selected)
    if qdii_w < _QDII_WEIGHT_FLOOR_FOR_DIAGNOSTIC:
        return ()
    tolerance_line = ""
    if usd_tolerance is not None:
        lo, hi = float(usd_tolerance[0]), float(usd_tolerance[1])
        in_range = lo <= qdii_w <= hi
        tolerance_line = (
            f"配置区间 [{lo * 100:.0f}%, {hi * 100:.0f}%]，当前"
            f"{'落在' if in_range else '超出'}区间。"
        )
    header = (
        f"外汇与QDII敞口提醒：QDII 标的合计目标权重 {qdii_w * 100:.1f}% "
        f"({'≥' if qdii_w >= _QDII_WEIGHT_FLOOR_FOR_DIAGNOSTIC else '<'} "
        f"{_QDII_WEIGHT_FLOOR_FOR_DIAGNOSTIC * 100:.0f}% 触发线)。"
        + (f" {tolerance_line}" if tolerance_line else "")
    )
    premium = "溢价/折价：数据未采集——请在交易前查阅各 QDII 二级市场溢价。"
    hedge = "对冲成本：未对冲——未配置 FX 对冲数据。"
    return (header, premium, hedge)

