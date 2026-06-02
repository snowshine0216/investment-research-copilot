from __future__ import annotations

import json

from irc.fundamentals.types import ThesisEvidence
from irc.narrative.report_appendix import (
    _appendix_lines,
    _footnote_lines,
    _product_drivers_segment,
)
from irc.narrative.schemas import NarrativeFundReport, ShortlistRow
from irc.opportunity.citation_selector import select_citations


def render_shortlist_md(narrative: str, rows: tuple[ShortlistRow, ...]) -> str:
    lines = [f"# 主题选基 / Narrative shortlist — {narrative}", ""]
    lines.append(f"## 候选清单（{len(rows)}）")
    lines.append("| 代码 | 名称 | 篮子权重% | 重合数 | 命中 |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        ov = r.overlap
        hits = "、".join(ov.matched_symbols + ov.industry_credit_symbols) or "—"
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {ov.basket_weight_pct:.1f} | "
            f"{ov.overlap_count} | {hits} |"
        )
    return "\n".join(lines) + "\n"


def _shortlist_row_dict(r: ShortlistRow) -> dict:
    ov = r.overlap
    return {
        "instrument_id": r.instrument_id,
        "name_cn": r.name_cn,
        "asset_class": r.asset_class,
        "basket_weight_pct": ov.basket_weight_pct,
        "overlap_count": ov.overlap_count,
        "matched_symbols": list(ov.matched_symbols),
        "industry_credit_symbols": list(ov.industry_credit_symbols),
    }


def render_shortlist_json(narrative: str, rows: tuple[ShortlistRow, ...]) -> str:
    doc = {"narrative": narrative, "funds": [_shortlist_row_dict(r) for r in rows]}
    return json.dumps(doc, ensure_ascii=False, indent=2)


def render_diagnostics_json(excluded: tuple[tuple[str, str, str], ...]) -> str:
    doc = {
        "excluded": [
            {"instrument_id": iid, "name_cn": name, "reason": reason}
            for iid, name, reason in excluded
        ]
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)


def _evidence_bullets(thesis_evidence: tuple[ThesisEvidence, ...]) -> list[str]:
    """Inline cell: locked `- [ref:{id}] {type} · {source} · {date}` prefix
    (opportunity/report.py:210, mirrored not imported) with a trailing
    ` · {summary}` prose segment (AC1). Capped at 3 via select_citations."""
    if not thesis_evidence:
        return []
    selected = select_citations(thesis_evidence, cap=3)
    return [
        f"  - [ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date} · {ev.summary}"
        for ev in selected
    ]


def render_report_md(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str:
    lines = [f"# 主题深度分析 / Narrative report — {narrative}", ""]
    for r in reports:
        lines.append(f"## {r.instrument_id} {r.name_cn}")
        lines.append(f"- 仓位风险等级 / position_risk_level: **{r.position_risk_level}**")
        lines.append(f"- 主因 / drivers: {', '.join(r.risk_drivers) or '—'}")
        lines.append(f"- 说明: {r.risk_rationale}")
        lines.append(
            f"- 机会 / dca / 风险: {r.opportunity_state} ｜ {r.dca_action} ｜ {r.risk_action}"
        )
        lines.append(
            f"- 子状态: 估值={r.valuation_state} 热度={r.heat_state} "
            f"逻辑={r.thesis_state} 质量={r.product_quality_state} "
            f"｜ 产品驱动: {_product_drivers_segment(r.product_metrics)}"
        )
        lines.append(f"- 复核节奏 / review_cadence: {r.review_cadence}")
        lines.append(f"- 证伪触发: {', '.join(r.falsification_triggers) or '—'}")
        lines.append(f"- 减仓触发: {', '.join(r.trim_triggers) or '—'}")
        bullets = _evidence_bullets(r.thesis_evidence)
        if bullets:
            lines.append("- 证据 / evidence:")
            lines.extend(bullets)
        appendix = _appendix_lines(r)
        lines.extend(appendix)
        footnotes = _footnote_lines(r)
        if footnotes:
            lines.append("")
            lines.append("### 证据明细 / Evidence appendix")
            lines.extend(footnotes)
        lines.append("")
    return "\n".join(lines) + "\n"


def _evidence_dict(ev: ThesisEvidence) -> dict:
    return {
        "citation_id": ev.citation_id,
        "type": ev.type,
        "source": ev.source,
        "date": ev.date,
        "scope": ev.scope,
        "citation_kind": ev.citation_kind,
        "summary": ev.summary,
        "url": ev.url,
    }


def _product_metrics_dict(pm) -> dict | None:
    if pm is None:
        return None
    return {
        "expense_ratio": pm.expense_ratio,
        "aum_cny": pm.aum_cny,
        "manager_tenure_years": pm.manager_tenure_years,
        "tracking_error": pm.tracking_error,
    }


def _constituent_dict(c) -> dict:
    return {
        "symbol": c.symbol,
        "name_cn": c.name_cn,
        "weight_pct": c.weight_pct,
        "one_line_view": c.one_line_view,
        "failure_reasons": list(c.failure_reasons),
        "audit_errors": list(c.audit_errors),
        "evidence": [_evidence_dict(e) for e in c.evidence],
    }


def _report_dict(r: NarrativeFundReport) -> dict:
    return {
        "instrument_id": r.instrument_id,
        "name_cn": r.name_cn,
        "position_risk_level": r.position_risk_level,
        "risk_rationale": r.risk_rationale,
        "risk_drivers": list(r.risk_drivers),
        "valuation_state": r.valuation_state,
        "heat_state": r.heat_state,
        "thesis_state": r.thesis_state,
        "product_quality_state": r.product_quality_state,
        "opportunity_state": r.opportunity_state,
        "dca_action": r.dca_action,
        "risk_action": r.risk_action,
        "falsification_triggers": list(r.falsification_triggers),
        "trim_triggers": list(r.trim_triggers),
        "review_cadence": r.review_cadence,
        "evidence_gaps": list(r.evidence_gaps),
        "thesis_evidence": [_evidence_dict(ev) for ev in r.thesis_evidence],
        "product_metrics": _product_metrics_dict(r.product_metrics),
        "constituent_analyses": [_constituent_dict(c) for c in r.constituent_analyses],
    }


def render_report_json(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str:
    doc = {"narrative": narrative, "funds": [_report_dict(r) for r in reports]}
    return json.dumps(doc, ensure_ascii=False, indent=2)
