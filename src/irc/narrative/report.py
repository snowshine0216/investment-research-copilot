from __future__ import annotations

import json

from irc.fundamentals.types import ThesisEvidence
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


def _footnote_line(ev: ThesisEvidence) -> str:
    """One footnote resolving a [ref:hex]. 16-hex id read verbatim (ADR 0001).
    `· {url}` appended only when url is non-empty."""
    base = f"[ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date} · {ev.summary}"
    return f"{base} · {ev.url}" if ev.url else base


def _footnote_lines(thesis_evidence: tuple[ThesisEvidence, ...]) -> list[str]:
    """Full-pool footnote table for one fund, deduped by citation_id, sorted by
    citation_id ASC (RD-4 determinism). Draws from the flattened r.thesis_evidence
    superset so every appendix/inline ref resolves (RD-6, AC4)."""
    if not thesis_evidence:
        return []
    by_id = {ev.citation_id: ev for ev in thesis_evidence}
    return [_footnote_line(by_id[cid]) for cid in sorted(by_id)]


def _appendix_lines(r: NarrativeFundReport) -> list[str]:
    return []  # constituent prose added in Task 5


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
            f"逻辑={r.thesis_state} 质量={r.product_quality_state}"
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
        footnotes = _footnote_lines(r.thesis_evidence)
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
    }


def render_report_json(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str:
    doc = {"narrative": narrative, "funds": [_report_dict(r) for r in reports]}
    return json.dumps(doc, ensure_ascii=False, indent=2)
