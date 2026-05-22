from __future__ import annotations

from dataclasses import dataclass, field

from irc.opportunity.types import ThesisEvidence


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


# Audit P5 (2026-05-20) required composite_score methodology disclosure.
# Single-line footnote keeps the table compact while satisfying the
# transparency requirement and carrying the load-bearing disclaimer.
_SCORING_FOOTNOTE = (
    "> 综合分由内部多因子模型生成（估值百分位 / 热度 / 长期逻辑 / 产品质量 / 宏观契合度 /"
    " 持有成本），仅作为辅助参考，不构成投资建议。详见评分体系说明文档。"
)


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
    citations: tuple[ThesisEvidence, ...] = field(default_factory=tuple)


def _action_cn(row: PickRow) -> str:
    base = _ACTION_CN.get(row.dca_action, row.dca_action)
    suffix = _RISK_CN.get(row.risk_action, "")
    if row.target_weight <= 0 and row.opportunity_state == "small_watch":
        return f"仅观察{suffix}"
    return f"{base}{suffix}"


def _format_citation(ev: ThesisEvidence) -> str:
    """Render one citation as `[ref:{citation_id}] {type}·{source}·{date}`."""
    return f"[ref:{ev.citation_id}] {ev.type}·{ev.source}·{ev.date}"


def _format_citations_cell(citations: tuple[ThesisEvidence, ...]) -> str:
    """Render the 证据 column cell. Multi-citation cells join by <br> so the
    markdown row stays single-line; empty → `—`."""
    if not citations:
        return "—"
    return "<br>".join(_format_citation(c) for c in citations)


def render_picks_table(rows: list[PickRow] | tuple[PickRow, ...]) -> str:
    # Safety-net dedup; canonical dedup is performed by callers
    # (e.g. _build_pick_rows).
    seen: set[str] = set()
    unique: list[PickRow] = []
    for r in rows:
        if r.instrument_id in seen:
            continue
        seen.add(r.instrument_id)
        unique.append(r)

    header = (
        "| 代码 | 名称 | 角色 | 目标权重 | 综合分 | 状态 | 本期行动 | 主要理由 | 证据 |\n"
        "|---|---|---|---|---|---|---|---|---|"
    )
    lines = [header]
    for r in unique:
        weight_str = f"{r.target_weight * 100:.1f}%"
        score_str = f"{r.composite_score:.1f}"
        citations_cell = _format_citations_cell(r.citations)
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {r.role} | "
            f"{weight_str} | {score_str} | {r.opportunity_state} | "
            f"{_action_cn(r)} | {r.one_line_reason} | {citations_cell} |"
        )
    lines.append("")
    lines.append(_SCORING_FOOTNOTE)
    return "\n".join(lines)


def render_failure_sections(
    absent_targets: list[dict],
    gapped_targets: list[dict],
    extra_names: dict[str, str] | None = None,
) -> str:
    """Render two `###` h3 sub-blocks for trade targets that didn't make the
    picks table. Returns "" when both buckets are empty.

    Output is appended to `picks_table_md` BEFORE it enters `MemoInputs`,
    nesting under `## 5. 精选标的` per grill resolution.

    Format (item 002 spec §"Gap-aware pick-row construction"):
      - absent: `{iid} {extra_names.get(iid, '?')}` — no op row available, name
        from extras (universe / watchlist CSV fallback).
      - gapped: `{iid} {op['name_cn']} | 原因: {gaps} | 已尝试: {fetch_types}` —
        op row exists but `evidence_gaps != ()`. Format mandated by H3 (item 006).
        NEVER renders opportunity_state, dca_action, risk_action, or note_cn.
    """
    extra_names = extra_names or {}
    parts: list[str] = []
    if absent_targets:
        parts.append("### 未能纳入精选：机会数据缺失\n")
        for t in absent_targets:
            iid = str(t.get("target") or "")
            name = extra_names.get(iid, "?")
            parts.append(
                f"- {iid} {name}（trade plan 中存在，但 "
                f"opportunity_report.json 中查无此 instrument_id）"
            )
        parts.append("")
    if gapped_targets:
        parts.append("### 未能纳入精选：证据不足\n")
        for t in gapped_targets:
            op = t.get("_matched_row") or {}
            iid = str(t.get("target") or "")
            name = op.get("name_cn") or extra_names.get(iid, "?")
            gaps = ", ".join(op.get("evidence_gaps") or ())
            attempted = ", ".join(op.get("fetch_types_attempted") or ())
            parts.append(
                f"- {iid} {name} | 原因: {gaps} | 已尝试: {attempted}"
            )
        parts.append("")
    if not parts:
        return ""
    return "\n" + "\n".join(parts)
