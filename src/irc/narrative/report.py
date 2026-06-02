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


def _fmt_metric(v: float | None) -> str:
    """`—` for None (AC6); plain float otherwise. No locale/dict leak (ADR 0004)."""
    return "—" if v is None else f"{v}"


def _product_drivers_segment(pm) -> str:
    """M2 drivers next to 质量 (AC6/AC7). pm may be None (→ all —). Passive's
    tracking_error renders when present; — otherwise. Never re-classifies (F-1)."""
    expense = _fmt_metric(pm.expense_ratio if pm else None)
    aum = _fmt_metric(pm.aum_cny if pm else None)
    tenure = _fmt_metric(pm.manager_tenure_years if pm else None)
    track = _fmt_metric(pm.tracking_error if pm else None)
    return f"费率={expense} 规模={aum} 任职={tenure} 跟踪误差={track}"


def _rank_constituents(cas: tuple) -> tuple:
    """weight_pct DESC, symbol ASC tiebreak (mirrors opportunity/report.py:131)."""
    return tuple(sorted(cas, key=lambda c: (-c.weight_pct, c.symbol)))


def _appendix_constituent_line(c) -> str:
    """Self-contained mirror of opportunity/report.py:289
    _format_appendix_constituent_line (5-shape precedence). NOT imported (RD-1)."""
    head = f"- {c.symbol} {c.name_cn} (权重 {c.weight_pct}%): "
    if c.audit_errors:
        return f"{head}⚠️ audit_error: {'; '.join(c.audit_errors)}"
    if c.evidence and c.failure_reasons:
        refs = " ".join(f"[ref:{e.citation_id}]" for e in select_citations(c.evidence, cap=3))
        return f"{head}{c.one_line_view} {refs} ({'; '.join(c.failure_reasons)})"
    if c.failure_reasons:
        return f"{head}❌ {'; '.join(c.failure_reasons)}"
    if c.evidence:
        refs = " ".join(f"[ref:{e.citation_id}]" for e in select_citations(c.evidence, cap=3))
        return f"{head}{c.one_line_view} {refs}"
    return f"{head}⚠️ audit_error: missing_constituent_record"


def _appendix_lines(r: NarrativeFundReport) -> list[str]:
    """Per-constituent prose block (active funds only; passive → empty, AC/Q8)."""
    if not r.constituent_analyses:
        return []
    return ["", "#### 持仓明细 / Holdings",
            *[_appendix_constituent_line(c) for c in _rank_constituents(r.constituent_analyses)]]


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
