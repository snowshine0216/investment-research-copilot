"""Pure helpers for the narrative .md per-fund appendix and footnote table.

Extracted from report.py to stay under the 200-line budget (Task 8 refactor).
All functions are deterministic — no I/O, no dict/set iteration without a sort.
See ADR 0004 (renderer determinism) and RD-1 (narrative report is a display-only,
non-SAME-3 surface).
"""
from __future__ import annotations

from irc.fundamentals.types import ThesisEvidence
from irc.narrative.schemas import NarrativeFundReport
from irc.opportunity.citation_selector import select_citations


def _safe_summary(summary: str) -> str:
    """Collapse any \\n/\\r in summary to a single space and strip edges.
    Returns empty string when summary is blank (FIX 5)."""
    return " ".join(summary.splitlines()).strip()


def _footnote_line(ev: ThesisEvidence) -> str:
    """One footnote resolving a [ref:hex]. 16-hex id read verbatim (ADR 0001).
    `· {url}` appended only when url is non-empty. Summary sanitized (FIX 5)."""
    s = _safe_summary(ev.summary)
    base = f"[ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date}"
    if s:
        base = f"{base} · {s}"
    return f"{base} · {ev.url}" if ev.url else base


def _union_evidence(r: "NarrativeFundReport") -> tuple[ThesisEvidence, ...]:
    """Union of r.thesis_evidence + every constituent's evidence (deduped by citation_id).

    Guarantees every inline [ref:hex] emitted by _appendix_constituent_line resolves
    in the footnote table regardless of whether the constituent evidence is mirrored
    into r.thesis_evidence (FIX 2, RD-6).
    """
    seen: dict[str, ThesisEvidence] = {}
    for ev in r.thesis_evidence:
        if ev.citation_id not in seen:
            seen[ev.citation_id] = ev
    for c in r.constituent_analyses:
        for ev in c.evidence:
            if ev.citation_id not in seen:
                seen[ev.citation_id] = ev
    return tuple(seen[cid] for cid in sorted(seen))


def _footnote_lines(r: "NarrativeFundReport") -> list[str]:
    """Full-pool footnote table for one fund.

    Pool = union of r.thesis_evidence + every constituent's evidence (FIX 2).
    Deduped by citation_id with a deterministic survivor (FIX 3): first-write
    wins over the fixed traversal order (r.thesis_evidence first, then each
    constituent's evidence) — input-order-independent because the source tuples
    are deterministic. Output is sorted by citation_id ASC (RD-4 determinism).
    """
    pool = _union_evidence(r)
    if not pool:
        return []
    # pool is already sorted by citation_id (from _union_evidence), so each cid's
    # survivor is deterministically the first occurrence (dedup via 'if not in seen').
    return [_footnote_line(ev) for ev in pool]


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


def _insufficient_refresh_line(narrative: str, r: NarrativeFundReport) -> str:
    """H3 analog: the single bilingual refresh line that REPLACES the suppressed
    triad/triggers/cadence on an insufficient row. Names evidence_gaps (mirrors
    failure_renderer.py's `原因: {gaps}`), points at the real refresh path
    (`--analyze`, NOT `fundamentals snapshot`). Deterministic — evidence_gaps is a
    stable tuple, risk_rationale a str, narrative an arg; no I/O.

    On both production insufficient paths evidence_gaps is non-empty (error_report
    sets `(reason,)`; _report_from_card reaches insufficient only via non-empty
    view.evidence_gaps), so the fallbacks are defensive-unreachable (grill Q3)."""
    gaps = ", ".join(r.evidence_gaps) or r.risk_rationale or "evidence_insufficient"
    return (
        f"- ⚠️ 证据不足 / insufficient — 行动建议已抑制 (未形成结论)；"
        f"缺口: {gaps}；刷新: `uv run irc narrative {narrative} --analyze`"
    )


def _insufficient_middle(narrative: str, r: NarrativeFundReport) -> list[str]:
    """The verdict-suppressed middle block for an insufficient row: the raw
    产品驱动 numeric segment (a gap-fact, KEEP — grill Q2) on its own line, then
    the refresh line. NO 子状态 line, NO 机会/dca/风险 triad, NO triggers, NO
    review_cadence (all H3-forbidden conclusions — grill Q1)."""
    return [
        f"- 产品驱动: {_product_drivers_segment(r.product_metrics)}",
        _insufficient_refresh_line(narrative, r),
    ]
