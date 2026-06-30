from __future__ import annotations

import logging
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

_log = logging.getLogger(__name__)


def _row_to_dict(
    row: OpportunityRow,
    discipline_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    disc = (discipline_by_id or {}).get(row.instrument_id, {})
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
        "advisory_gaps": list(row.advisory_gaps),
        # New schema (item 002):
        "thesis_evidence": [asdict(e) for e in row.thesis_evidence],
        "contributing_dimensions": sorted(row.contributing_dimensions),
        "constituent_analyses": [
            asdict(c) for c in getattr(row, "constituent_analyses", ())
        ],
        "fetch_types_attempted": list(row.fetch_types_attempted),
        # Item 001: discipline-derived sell-side fields for the decision layer.
        # Default (no map / id absent) is byte-identical to pre-change.
        "risk_action": disc.get("risk_action", "none"),
        "dca_action": disc.get("dca_action"),
        "portfolio_weight": disc.get("portfolio_weight"),
        "is_holding": disc.get("is_holding", False),
    }


def compose_opportunity_report(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    date: str,
    *,
    discipline_by_id: dict[str, dict[str, Any]] | None = None,
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
        "rows": [_row_to_dict(r, discipline_by_id) for r in rows],
    }


def _card_to_dict(card: ThesisCard) -> dict[str, Any]:
    d = asdict(card)
    for key in ("falsification_triggers", "trim_triggers",
                "do_not_sell_just_because", "evidence_gaps",
                "expected_omissions", "advisory_gaps"):
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
        elif r.dca_action in _DCA_BUCKET:
            buckets[_DCA_BUCKET[r.dca_action]].append(r)
        else:
            # Unknown dca_action: preserve the historical default bucket but WARN
            # so a new DcaAction variant missing from _DCA_BUCKET is visible in
            # logs rather than silently misbucketed into 今日可定投.
            _log.warning(
                "unknown dca_action %r for %s; defaulting to 今日可定投",
                r.dca_action, r.instrument_id,
            )
            buckets["今日可定投"].append(r)
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

    Precedence — distinct from the appendix's 5-shape contract (spec §17)
    in that inline still uses a single-bullet body that APPENDS audit_errors
    + failure_reasons to one_line_view when evidence is present. The bug
    closed in this revision: audit_errors used to be silently dropped when
    `evidence == () AND failure_reasons != ()` (the failure-only branch
    short-circuited before the audit append), AND failure_reasons were
    dropped when `evidence != () AND failure_reasons != ()`.

    Rules:
    - `evidence == () AND audit_errors != ()` (irrespective of failure_reasons) →
      `⚠️ audit_error: {audit_errors_joined}` (Shape 3-analog; highest precedence
      for no-evidence rows so audit signals always win over failure-only).
    - `evidence == () AND failure_reasons != ()` → `❌ {failure_reasons_joined}`.
    - `evidence == () AND failure_reasons == () AND audit_errors == ()` →
      `⚠️ audit_error: missing_constituent_record` (Shape 5-analog defensive).
    - `evidence != ()` (the happy path) → `{one_line_view}`, with optional
      `(⚠️ {failure_reasons_joined})` partial-failure suffix and optional
      ` ⚠️ {audit_errors_joined}` audit suffix — both visible when both present.
    """
    head = f"    - {c.symbol} {c.name_cn} (权重 {c.weight_pct}%): "
    # Branch A: no evidence. Audit > failure > defensive.
    if not c.evidence:
        if c.audit_errors:
            return f"{head}⚠️ audit_error: {'; '.join(c.audit_errors)}"
        if c.failure_reasons:
            return f"{head}❌ {'; '.join(c.failure_reasons)}"
        return f"{head}⚠️ audit_error: missing_constituent_record"
    # Branch B: evidence present. Render one_line_view + suffixes.
    body = c.one_line_view
    if c.failure_reasons:
        body = f"{body} (⚠️ {'; '.join(c.failure_reasons)})"
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
        advisory_notes: list[str] = []
        gaps = getattr(r, "advisory_gaps", ())
        if "top_holdings_broker_thin" in gaps:
            advisory_notes.append("核心持仓券商覆盖不足")
        if "valuation_price_fundamental_divergence" in gaps:
            advisory_notes.append("价格与基本面估值背离")
        advisory_suffix = (
            " ｜ 证据缺口：" + "；".join(advisory_notes) if advisory_notes else ""
        )
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** "
            f"｜ {r.opportunity_state} ｜ dca={r.dca_action} ｜ risk={r.risk_action}"
            f"{advisory_suffix} "
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
#
# Deviations from the plan's "Locked appendix line regex contract", surfaced
# by the high-effort code-review on PR #61:
#   - `nm` uses `[^\n]+?` (non-greedy, non-newline only) — NOT `[^()\n]+?`.
#     Real CN fund names routinely embed parentheses
#     (`大成纳斯达克100ETF联接(QDII)A`, `易方达标普信息科技指数(QDII-LOF)A`); the
#     `[^()\n]+?` pattern silently rejected every such row.
#   - `sym` uses `[0-9A-Z.]{1,8}` — NOT `[0-9A-Z]{4,6}`. Real symbols include
#     dot-bearing tickers like `BRK.B` (S&P 500 top-10) and `BF.B`, and CN
#     symbols can be 4-6 chars while HK symbols can be 5; widening to 1-8
#     covers all real cases without admitting noise.
#   - Compiled with `re.MULTILINE` so item 009 can call `.findall(text)` /
#     `.search(text)` on the full discipline_report.md and have `^`/`$` match
#     line boundaries (not just string boundaries — the prior compile-without-
#     flag had item 009 silent-no-op on bulk-document scans).
# All three relaxations are LOCKED by regression tests in
# `tests/opportunity/test_report_appendix.py`.
_APPENDIX_LINE_RE = re.compile(
    r"^- (?P<sym>[0-9A-Z.]{1,8}) (?P<nm>[^\n]+?) "
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
    r")$",
    re.MULTILINE,
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
