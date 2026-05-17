from __future__ import annotations

from dataclasses import dataclass


_ACTION_CN: dict[str, str] = {
    "accelerate_dca": "加速定投",
    "normal_dca": "正常定投",
    "slow_dca": "减速定投",
    "pause_dca": "暂停加仓",
    "do_not_buy": "禁止买入",
}

_RISK_CN: dict[str, str] = {
    "none": "",
    "review_required": "（风险复核）",
    "trim_review": "（调仓复核）",
    "exit_review": "（退出复核）",
}


@dataclass(frozen=True)
class PickRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    role: str
    target_weight: float
    composite_score: float
    opportunity_state: str
    dca_action: str
    risk_action: str
    one_line_reason: str


def _action_cn(row: PickRow) -> str:
    base = _ACTION_CN.get(row.dca_action, row.dca_action)
    suffix = _RISK_CN.get(row.risk_action, "")
    if row.target_weight <= 0 and row.opportunity_state == "small_watch":
        return f"仅观察{suffix}"
    return f"{base}{suffix}"


def render_picks_table(rows: list[PickRow] | tuple[PickRow, ...]) -> str:
    # Safety-net dedup; canonical dedup is performed by callers (e.g. _build_pick_rows).
    seen: set[str] = set()
    unique: list[PickRow] = []
    for r in rows:
        if r.instrument_id in seen:
            continue
        seen.add(r.instrument_id)
        unique.append(r)

    header = (
        "| 代码 | 名称 | 角色 | 目标权重 | 综合分 | 状态 | 本期行动 | 主要理由 |\n"
        "|---|---|---|---|---|---|---|---|"
    )
    lines = [header]
    for r in unique:
        weight_str = f"{r.target_weight * 100:.1f}%"
        score_str = f"{r.composite_score:.1f}"
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {r.role} | "
            f"{weight_str} | {score_str} | {r.opportunity_state} | "
            f"{_action_cn(r)} | {r.one_line_reason} |"
        )
    return "\n".join(lines)
