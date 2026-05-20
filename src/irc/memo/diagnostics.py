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

# Adversarial review §E (2026-05-19): 10 of 16 role buckets returned
# 0 candidates passing both hard and quality filters. The memo treated
# the picks as if the universe were exhaustive. Surface failed roles.
_ROLE_BUCKET_FAILED_REASON: str = "below fail_below"

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


def compose_role_bucket_banner(
    diagnostics_rows: list[dict[str, Any]] | None,
) -> tuple[str, ...]:
    """Surface failed role buckets as a banner.

    Adversarial review §E: in 2026-05-19, 10 of 16 role buckets returned
    zero candidates. The memo's TL;DR didn't say so. Pure function — the
    caller reads ``discovery_diagnostics.csv`` and passes the parsed
    rows in.

    Returns an empty tuple when no role bucket failed.
    """
    if not diagnostics_rows:
        return ()
    failed = [
        str(r.get("role") or "")
        for r in diagnostics_rows
        if str(r.get("stage") or "") == "role_bucket"
        and str(r.get("status") or "") == "failed"
        and r.get("role")
    ]
    total_bucketed = sum(
        1 for r in diagnostics_rows
        if str(r.get("stage") or "") == "role_bucket"
        and str(r.get("status") or "") == "bucketed"
    )
    total_roles = total_bucketed + len(failed) if total_bucketed else len(failed)
    if not failed:
        return ()
    failed_unique = list(dict.fromkeys(failed))
    header = (
        f"发现层覆盖警告：{len(failed_unique)}/{total_roles} 角色桶本期未召回"
        f"任何候选 — {'、'.join(failed_unique)}。"
    )
    caveat = (
        "组合层面缺角，请把当周配置视为「在残缺集合中的最优选」，"
        "而非「全集合最优」。"
    )
    return (header, caveat)


def compose_fx_qdii_lines(
    allocation: dict[str, Any] | None,
    usd_tolerance: tuple[float, float] | None,
    fx_hedge_policy: str | None = None,
) -> tuple[str, ...]:
    """Emit FX & QDII diagnostic lines when QDII weight crosses the floor.

    Adversarial review §C4+§C5: a CNY-based investor running 25% QDII
    weight has unhedged USD exposure plus QDII premium/discount risk
    plus quota-suspension risk. None of these surface today.

    ``fx_hedge_policy`` (E4, 2026-05-20): the user's declared FX policy
    from ``preferences.yaml``. When ``"accept_unhedged"``, the hedge
    line reframes from "数据未配置" (missing feed) to "政策允许" (a
    deliberate choice) — but only while QDII weight stays within the
    USD tolerance band. Breaching the band still warns.

    Returns an empty tuple when QDII weight is below the floor or the
    allocation doesn't carry selected_instruments. Returns a 3-line
    diagnostic when above the floor:
      1. total QDII weight + tolerance status
      2. premium/discount placeholder (data layer to populate later)
      3. hedge-cost / policy line
    """
    if not allocation:
        return ()
    selected = allocation.get("selected_instruments") or []
    qdii_w = _qdii_weight(selected)
    if qdii_w < _QDII_WEIGHT_FLOOR_FOR_DIAGNOSTIC:
        return ()
    tolerance_line = ""
    tolerance_state: str = "unknown"  # "in_band" | "out_of_band" | "unknown"
    if usd_tolerance is not None:
        lo, hi = float(usd_tolerance[0]), float(usd_tolerance[1])
        in_range = lo <= qdii_w <= hi
        tolerance_state = "in_band" if in_range else "out_of_band"
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
    hedge = _compose_hedge_line(fx_hedge_policy, tolerance_state)
    return (header, premium, hedge)


def _compose_hedge_line(policy: str | None, tolerance_state: str) -> str:
    if policy == "accept_unhedged":
        if tolerance_state == "in_band":
            return "对冲成本：未对冲（政策允许——USD 敞口落在容忍带内）。"
        if tolerance_state == "out_of_band":
            return (
                "对冲成本：未对冲（政策允许，但当前 USD 敞口超出容忍带，"
                "请收敛权重或临时上对冲工具）。"
            )
        return "对冲成本：未对冲（政策允许——未配置 USD 容忍带，无法核对敞口）。"
    return "对冲成本：未对冲——未配置 FX 对冲数据。"

