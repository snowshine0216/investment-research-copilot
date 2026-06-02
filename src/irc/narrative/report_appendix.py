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
