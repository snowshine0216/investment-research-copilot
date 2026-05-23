from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

import yaml

from irc.opportunity.citation_selector import select_citations
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


# Item 007 D3b §17 — locked appendix line regex contract. Item 009's
# find_uncited_discipline_rows parses appendix bullets against this.
_APPENDIX_LINE_RE = re.compile(
    r"^- (?P<sym>[0-9A-Z]{4,6}) (?P<nm>[^()\n]+?) "
    r"\(权重 (?P<wpct>\d+(?:\.\d+)?)%\): "
    r"(?:"
    # Shape 1: evidence + failures
    r"(?P<oneline_with_failures>.+?)(?P<refs_with_failures>(?: \[ref:[0-9a-f]{16}\])+) "
    r"\((?P<failures_partial>.+?)\)"
    # Shape 2: failure only
    r"|❌ (?P<failure_only>.+?)"
    # Shape 3 / Shape 5: audit-error only
    r"|⚠️ audit_error: (?P<audit_error>.+?)"
    # Shape 4: evidence only
    r"|(?P<oneline_only>.+?)(?P<refs_only>(?: \[ref:[0-9a-f]{16}\])+)"
    r")$"
)


def _format_appendix_constituent_line(c) -> str:
    """Render one appendix bullet by FIRST-MATCH precedence (spec §17).

    Per ADR 0004 + spec §17:
    1. audit_errors != () → Shape 3 (audit-error only, NO refs).
    2. evidence != () AND failure_reasons != () → Shape 1 (evidence + failures).
    3. evidence == () AND failure_reasons != () → Shape 2 (failure only, NO refs).
    4. evidence != () → Shape 4 (evidence only).
    5. all-empty (defensive) → Shape 5 = Shape 3 with literal sentinel.
    """
    head = f"- {c.symbol} {c.name_cn} (权重 {c.weight_pct}%): "
    if c.audit_errors:
        return f"{head}⚠️ audit_error: {'; '.join(c.audit_errors)}"
    if c.evidence and c.failure_reasons:
        refs = " ".join(
            f"[ref:{ev.citation_id}]"
            for ev in select_citations(c.evidence, cap=3)
        )
        return f"{head}{c.one_line_view} {refs} ({'; '.join(c.failure_reasons)})"
    if not c.evidence and c.failure_reasons:
        return f"{head}❌ {'; '.join(c.failure_reasons)}"
    if c.evidence:
        refs = " ".join(
            f"[ref:{ev.citation_id}]"
            for ev in select_citations(c.evidence, cap=3)
        )
        return f"{head}{c.one_line_view} {refs}"
    # Shape 5 (defensive fallback).
    return f"{head}⚠️ audit_error: missing_constituent_record"


def _render_appendix_subsection(row) -> list[str]:
    """Render one fund subsection: `### {iid} {name} ({asset_class})` + bullets.

    Constituents ordered by weight_pct DESC, symbol ASC tiebreaker.
    """
    header = f"### {row.instrument_id} {row.name_cn} ({row.asset_class})"
    ranked = _rank_constituents_by_weight(row.constituent_analyses)
    return [
        "",
        header,
        "",
        *[_format_appendix_constituent_line(c) for c in ranked],
    ]


def _order_publishable_rows_for_appendix(
    publishable_rows: tuple,
    pick_order_iids: tuple[str, ...],
) -> tuple:
    """Order rows: pick-row order first, then instrument_id ascending."""
    pick_set = set(pick_order_iids)
    by_iid = {r.instrument_id: r for r in publishable_rows}
    pick_ordered = [by_iid[iid] for iid in pick_order_iids if iid in by_iid]
    non_pick = sorted(
        (r for r in publishable_rows if r.instrument_id not in pick_set),
        key=lambda r: r.instrument_id,
    )
    return tuple(pick_ordered + non_pick)


def _render_appendix_section(
    publishable_rows: tuple,
    pick_order_iids: tuple[str, ...],
) -> str:
    """Render the `## 持仓明细` section. Empty case → `（无）` body."""
    eligible = tuple(
        r for r in publishable_rows
        if getattr(r, "constituent_analyses", ())
    )
    if not eligible:
        return "## 持仓明细\n\n（无）\n"
    ordered = _order_publishable_rows_for_appendix(eligible, pick_order_iids)
    parts: list[str] = ["## 持仓明细"]
    for r in ordered:
        parts.extend(_render_appendix_subsection(r))
    parts.append("")  # trailing newline
    return "\n".join(parts)


def compose_discipline_markdown(
    rows: list[DisciplineRow] | tuple[DisciplineRow, ...],
    date: str,
    *,
    publishable_rows: tuple = (),
    pick_order_iids: tuple[str, ...] = (),
) -> str:
    """Compose `discipline_report.md`.

    Q10 (item 007): two keyword-only params control the appendix render.
    Backward-compat: empty defaults render the appendix with body `（无）`
    (no pick-row priority); legacy callers still produce valid markdown.
    """
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
        _render_appendix_section(publishable_rows, pick_order_iids),
    ]
    return "\n".join(parts)
