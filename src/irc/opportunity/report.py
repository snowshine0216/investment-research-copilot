from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

import yaml

from irc.memo.citation_selector import select_citations
from irc.opportunity.types import (
    DisciplineRow,
    OpportunityRow,
    ThesisCard,
)


def _row_to_dict(row: OpportunityRow) -> dict[str, Any]:
    return {
        "instrument_id": row.instrument_id,
        "name_cn": row.name_cn,
        "asset_class": row.asset_class,
        "theme": row.theme,
        "lookthrough_target": row.lookthrough_target.display_cn,
        "lookthrough_kind": row.lookthrough_target.kind,
        "lookthrough_key": row.lookthrough_target.key,
        "valuation_state": row.valuation_state,
        "heat_state": row.heat_state,
        "thesis_state": row.thesis_state,
        "product_quality_state": row.product_quality_state,
        "opportunity_state": row.opportunity_state,
        "opportunity_reason": row.opportunity_reason,
        "evidence_gaps": list(row.evidence_gaps),
        "expected_omissions": list(row.expected_omissions),
        # New schema (item 002):
        "thesis_evidence": [asdict(e) for e in row.thesis_evidence],
        "contributing_dimensions": sorted(row.contributing_dimensions),
        "constituent_analyses": [
            asdict(c) for c in getattr(row, "constituent_analyses", ())
        ],
        "fetch_types_attempted": list(row.fetch_types_attempted),
    }


def compose_opportunity_report(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    date: str,
) -> dict[str, Any]:
    summary = {
        "core_dca_count": 0,
        "small_watch_count": 0,
        "pause_wait_count": 0,
        "exclude_count": 0,
    }
    for r in rows:
        summary[f"{r.opportunity_state}_count"] += 1
    return {
        "date": date,
        "summary": summary,
        "rows": [_row_to_dict(r) for r in rows],
    }


def _card_to_dict(card: ThesisCard) -> dict[str, Any]:
    d = asdict(card)
    for key in ("falsification_triggers", "trim_triggers",
                "do_not_sell_just_because", "evidence_gaps",
                "expected_omissions"):
        d[key] = list(d.get(key, []))
    # Every ThesisEvidence dict must carry its citation_id (computed in
    # __post_init__; never empty after construction).
    for ev_dict in d.get("thesis_evidence", []):
        if not ev_dict.get("citation_id"):
            raise RuntimeError(
                f"thesis_evidence entry missing citation_id: {ev_dict}"
            )
    # Item 003: also check nested constituent evidence.
    for analysis in d.get("constituent_analyses", []):
        for ev_dict in analysis.get("evidence", []):
            if not ev_dict.get("citation_id"):
                raise RuntimeError(
                    f"constituent evidence entry missing citation_id: {ev_dict}"
                )
    return d


def compose_thesis_cards_yaml(cards: list[ThesisCard] | tuple[ThesisCard, ...]) -> str:
    payload = {"cards": [_card_to_dict(c) for c in cards]}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


_DCA_BUCKET = {
    "accelerate_dca": "今日可定投",
    "normal_dca": "今日可定投",
    "slow_dca": "减速定投",
    "pause_dca": "暂停加仓",
    "do_not_buy": "暂停加仓",
}

_RISK_BUCKET = {
    "review_required": "风险复核",
    "trim_review": "调仓复核",
    "exit_review": "退出复核",
}


def _bucket_rows(rows: list[DisciplineRow] | tuple[DisciplineRow, ...]) -> dict[str, list[DisciplineRow]]:
    buckets: dict[str, list[DisciplineRow]] = {
        "今日可定投": [],
        "减速定投": [],
        "暂停加仓": [],
        "风险复核": [],
        "调仓复核": [],
        "退出复核": [],
    }
    for r in rows:
        if r.risk_action in _RISK_BUCKET:
            buckets[_RISK_BUCKET[r.risk_action]].append(r)
        else:
            # Unknown dca_action values fall back to "今日可定投"; see TODOS.md
            # for a future robustness improvement (log or raise on unknown values).
            buckets[_DCA_BUCKET.get(r.dca_action, "今日可定投")].append(r)
    return buckets


# Item 007 D3b — inline top-5 holdings constants.
TOP_5_HOLDINGS_INLINE_CAP = 5
INLINE_HEADER_LITERAL = "持仓 (Top 5)"


def _rank_constituents_by_weight(
    constituent_analyses: tuple,
) -> tuple:
    """Sort by weight_pct DESC, ties broken by symbol ASC. Pure."""
    return tuple(sorted(
        constituent_analyses,
        key=lambda c: (-c.weight_pct, c.symbol),
    ))


def _format_inline_constituent_line(c) -> str:
    """Render one constituent line for the inline top-5 block.

    Precedence (single-bullet shape — distinct from the appendix's 5-shape
    contract per spec §17):
    - `evidence == () AND failure_reasons != ()` → `❌ {failure_reasons_joined}` in place of one_line_view.
    - `audit_errors != ()` → append ` ⚠️ {audit_errors_joined}` after one_line_view.
    - `evidence != ()` (no failures) → bare `{one_line_view}`.
    - all-empty (defensive) → ` ⚠️ audit_error: missing_constituent_record`.
    """
    head = f"    - {c.symbol} {c.name_cn} (权重 {c.weight_pct}%): "
    if not c.evidence and c.failure_reasons:
        return f"{head}❌ {'; '.join(c.failure_reasons)}"
    if not c.evidence and not c.failure_reasons and not c.audit_errors:
        return f"{head}⚠️ audit_error: missing_constituent_record"
    body = c.one_line_view
    if c.audit_errors:
        body = f"{body} ⚠️ {'; '.join(c.audit_errors)}"
    return f"{head}{body}"


def _render_inline_holdings_block(constituent_analyses: tuple) -> list[str]:
    """Render the inline top-5 holdings block for a discipline row.

    Returns empty list when `constituent_analyses == ()`. Always renders
    the literal `持仓 (Top 5):` header even when N < 5 (per OQ4 lock).
    """
    if not constituent_analyses:
        return []
    ranked = _rank_constituents_by_weight(constituent_analyses)
    top = ranked[:TOP_5_HOLDINGS_INLINE_CAP]
    return [
        f"  - {INLINE_HEADER_LITERAL}:",
        *[_format_inline_constituent_line(c) for c in top],
    ]


def _render_thesis_evidence_bullets(thesis_evidence: tuple) -> list[str]:
    """Render top-3 nested thesis_evidence bullets for a discipline row.

    Format: `  - [ref:{citation_id}] {type} · {source} · {date}`. Two-space
    indentation (markdown nested list). Empty evidence → empty list (no
    `（无）` placeholder — caller renders the parent line only).

    Same selector as picks-table + evidence-pool — the SAME-3 invariant
    locked by ADR 0004 §3.
    """
    if not thesis_evidence:
        return []
    selected = select_citations(thesis_evidence, cap=3)
    return [
        f"  - [ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date}"
        for ev in selected
    ]


def _render_section(title: str, rows: list[DisciplineRow]) -> str:
    if not rows:
        return f"## {title}\n\n（无）\n"
    lines = [f"## {title}\n"]
    for r in rows:
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** "
            f"｜ {r.opportunity_state} ｜ dca={r.dca_action} ｜ risk={r.risk_action} "
            f"｜ {r.note_cn}"
        )
        # Item 007 D3a: nested thesis_evidence bullets (top-3 via select_citations).
        lines.extend(_render_thesis_evidence_bullets(r.thesis_evidence))
        # Item 007 D3b: inline top-5 holdings for active-fund rows.
        lines.extend(_render_inline_holdings_block(
            getattr(r, "constituent_analyses", ()),
        ))
    lines.append("")
    return "\n".join(lines)


_DRAWDOWN_NOTE_CN = (
    "## 关于回撤的说明\n\n"
    "持仓回撤达到 20% 或更高时，本系统**不会**自动卖出。\n"
    "回撤只触发风险复核，是否减仓或退出需结合：\n"
    "- 主题长期逻辑是否被证伪；\n"
    "- 产品质量是否变差；\n"
    "- 组合权重是否超出目标区间。\n"
    "短期价格下跌、单日波动不构成卖出理由。\n"
)


def compose_discipline_markdown(
    rows: list[DisciplineRow] | tuple[DisciplineRow, ...],
    date: str,
) -> str:
    buckets = _bucket_rows(rows)
    parts = [
        f"# Discipline Report — {date}\n",
        _render_section("今日可定投", buckets["今日可定投"]),
        _render_section("减速定投", buckets["减速定投"]),
        _render_section("暂停加仓", buckets["暂停加仓"]),
        _render_section("风险复核", buckets["风险复核"]),
        _render_section("调仓复核", buckets["调仓复核"]),
        _render_section("退出复核", buckets["退出复核"]),
        _DRAWDOWN_NOTE_CN,
    ]
    return "\n".join(parts)
