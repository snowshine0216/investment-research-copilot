from __future__ import annotations

from dataclasses import dataclass, field

from irc.decision.sizing import (
    TriggerSpec,
    evaluate_trigger,
    resolve_trigger_current_value,
)
from irc.opportunity.types import ThesisEvidence


_ACTION_CN: dict[str, str] = {
    "accelerate_dca": "加速定投",
    "normal_dca": "正常定投",
    "slow_dca": "条件性减速定投（触发条件见第7节；未触发则不执行）",
    "pause_dca": "暂停加仓",
    "do_not_buy": "禁止买入",
}

_RISK_CN: dict[str, str] = {
    "none": "",
    "review_required": "（风险复核）",
    "trim_review": "（调仓复核）",
    "exit_review": "（退出复核）",
}

_DECISION_CN: dict[str, str] = {
    "actionable_buy": "候选可执行",
    "blocked": "阻断",
    "watch_only": "观察",
    "avoid": "回避",
}


# Audit P5 (2026-05-20) required composite_score methodology disclosure.
# Single-line footnote keeps the table compact while satisfying the
# transparency requirement and carrying the load-bearing disclaimer.
# Item 003 (2026-05-26) added the 单次定投上限 + 触发状态 explainer
# sentence between the existing weight/score caveat and the closing 不构成
# 投资建议 disclaimer (P5 lock: disclaimer stays at the end).
_SCORING_FOOTNOTE = (
    "> *综合分由内部多因子模型生成（估值百分位 / 热度 / 长期逻辑 / 产品质量 / 宏观契合度 /"
    " 持有成本），仅作为辅助参考，不构成投资建议。表中权重均为上限约束（≤），"
    "非强制建仓目标；条件性减速定投在第7节触发条件未满足时实际执行量为零。"
    "估值维度缺失的综合分不得单独依据分值高低作为配置优先级依据。"
    "单次定投上限 = 目标权重 ÷ 4（build 模式），表示一次建仓的最大占总资产比例；"
    "触发状态反映第7节触发条件相对当前宏观/净值快照的评估结果。"
    "详见评分体系说明文档。"
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
    valuation_state: str = ""
    venue_note: str = ""
    citations: tuple[ThesisEvidence, ...] = field(default_factory=tuple)
    # Gates verdict (actionable_buy / blocked / watch_only / avoid). Defaults
    # to watch_only so callers/tests that omit it stay backwards-compatible.
    decision_status: str = "watch_only"
    # Item 003: Decision Sheet mirror columns. Both default to safe sentinels
    # so legacy callers/tests (21 PickRow(...) call sites — all kwargs) stay
    # green; the renderer emits em-dash for missing values.
    tranche_cap_pct: float | None = None
    trigger_status: str = ""


def _action_cn(row: PickRow) -> str:
    base = _ACTION_CN.get(row.dca_action, row.dca_action)
    suffix = _RISK_CN.get(row.risk_action, "")
    action = f"{base}{suffix}"
    if "venue mismatch" in row.venue_note and "no proxy" in row.venue_note:
        return (
            f"{action}（渠道不匹配，当前无法执行；"
            "触发条件满足后亦须待渠道开通方可执行）"
        )
    if row.target_weight <= 0 and row.opportunity_state == "small_watch":
        return f"仅观察{suffix}"
    return action


def _format_citation(ev: ThesisEvidence) -> str:
    """Render one citation as `[ref:{citation_id}] {type}·{source}·{date}`."""
    return f"[ref:{ev.citation_id}] {ev.type}·{ev.source}·{ev.date}"


def _format_citations_cell(citations: tuple[ThesisEvidence, ...]) -> str:
    """Render the 证据 column cell. Multi-citation cells join by <br> so the
    markdown row stays single-line; empty → `—`."""
    if not citations:
        return "—"
    return "<br>".join(_format_citation(c) for c in citations)


_TRIGGER_STATE_GLYPH: dict[str, str] = {
    "met": "✓",
    "not_met": "✗",
    "missing": "⚠",
}


def _format_trigger_status_compact(
    triggers: tuple[dict, ...] | list[dict],
    macro_snapshot: dict[str, float],
    weekly_return_by_id: dict[str, float],
    instrument_id: str,
) -> str:
    """Render the 触发状态 column cell. One line per trigger
    (`{name} {✓|✗|⚠}`), multi-trigger joined by ``<br>`` to keep the
    markdown row single-line (mirrors `_format_citations_cell`).

    YAML insertion order from `trade_plan.yaml::trades[*].triggers` is
    preserved (no re-sort). Empty tuple → "" (renderer emits em-dash).
    Trigger state is computed by `evaluate_trigger`; current value is
    resolved via `resolve_trigger_current_value`.
    """
    if not triggers:
        return ""
    parts: list[str] = []
    for trig in triggers:
        name = str(trig.get("name") or "trigger")
        spec = TriggerSpec(
            name=name,
            comparator=str(trig.get("comparator") or "<="),
            threshold=(
                0.0 if trig.get("threshold") is None
                else float(trig.get("threshold"))
            ),
        )
        current, _unit = resolve_trigger_current_value(
            trig, instrument_id, macro_snapshot, weekly_return_by_id,
        )
        state = evaluate_trigger(spec, current)
        glyph = _TRIGGER_STATE_GLYPH.get(state, "⚠")
        parts.append(f"{name} {glyph}")
    return "<br>".join(parts)


def _format_tranche_cap_cell(tranche_cap_pct: float | None) -> str:
    """Render the 单次定投上限 cell. None or ≤ 0 → em-dash (matches the
    empty-citations convention; spec AC3)."""
    if tranche_cap_pct is None or tranche_cap_pct <= 0.0:
        return "—"
    return f"≤ {tranche_cap_pct * 100:.2f}%"


def _format_trigger_status_cell(trigger_status: str) -> str:
    """Render the 触发状态 cell. Empty string → em-dash; otherwise verbatim
    (helper precomputed the `{name} ✓/✗/⚠<br>...` form upstream)."""
    if not trigger_status:
        return "—"
    return trigger_status


def _format_score(row: PickRow) -> str:
    score = f"{row.composite_score:.1f}"
    if row.valuation_state == "evidence_insufficient":
        return f"{score}（估值维度缺失，不得用于优先级比较）"
    return score


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
        "| 代码 | 名称 | 角色 | 权重上限 | 综合分* | 决策 | 机会状态 | 本期行动 | "
        "主要理由 | 单次定投上限 | 触发状态 | 证据 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [header]
    for r in unique:
        weight_str = f"{r.target_weight * 100:.1f}%"
        score_str = _format_score(r)
        citations_cell = _format_citations_cell(r.citations)
        decision_cell = _DECISION_CN.get(r.decision_status, r.decision_status)
        tranche_cell = _format_tranche_cap_cell(r.tranche_cap_pct)
        trigger_cell = _format_trigger_status_cell(r.trigger_status)
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {r.role} | "
            f"{weight_str} | {score_str} | {decision_cell} | {r.opportunity_state} | "
            f"{_action_cn(r)} | {r.one_line_reason} | "
            f"{tranche_cell} | {trigger_cell} | {citations_cell} |"
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
            _raw_attempted = op.get("fetch_types_attempted") or ()
            attempted = ", ".join(_raw_attempted) if _raw_attempted else "—"
            parts.append(
                f"- {iid} {name} | 原因: {gaps} | 已尝试: {attempted}"
            )
        parts.append("")
    if not parts:
        return ""
    return "\n" + "\n".join(parts)
