"""PURE Validation panel HTML. M2: N rows (monitor_signal + deterministic_scoring).
No I/O. Comp 6 (spec §8): informational stages (flow_coverage, valuation_coverage)
render 观测 instead of PASS/FAIL vocabulary — they are panel-only tallies, never
a gate, and 'PASS' previously read as 'data fine' when coverage was 0."""
from __future__ import annotations
import re
from datetime import datetime
from html import escape
from irc.monitor.eval.constants import STALE_EVAL_DAYS
from irc.monitor.eval.types import ValidationPanelRow

_BADGE_ORDER = ("validated", "caveated", "gated")
_INFORMATIONAL_STAGES = frozenset({"flow_coverage", "valuation_coverage"})
_INFORMATIONAL_LABEL = "观测"
_FLOW_COVER_FLOOR = 0.50
_FLOW_COVER_RE = re.compile(r"flow_cover (\d+\.?\d*)")


def _counts_str(badge_counts: dict[str, int]) -> str:
    parts = [f"{b}: {badge_counts[b]}" for b in _BADGE_ORDER if b in badge_counts]
    return ", ".join(parts)


def _flow_cover_value(reasons: tuple[str, ...]) -> float | None:
    for r in reasons:
        m = _FLOW_COVER_RE.match(r)
        if m:
            return float(m.group(1))
    return None


def _is_amber(row: ValidationPanelRow) -> bool:
    if row.stage != "flow_coverage":
        return False
    cover = _flow_cover_value(row.reasons)
    return cover is not None and cover < _FLOW_COVER_FLOOR


def _status_label(row: ValidationPanelRow) -> str:
    if row.stage in _INFORMATIONAL_STAGES:
        return _INFORMATIONAL_LABEL
    return escape(row.status)


def _age_days(ran_at: str, *, now: datetime) -> int | None:
    """Parse ran_at ISO timestamp -> whole days before `now`. None on any
    parse failure (never crashes the panel)."""
    try:
        parsed = datetime.fromisoformat(ran_at)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    return (now - parsed).days


def _ran_at_cell(ran_at: str, *, now: datetime) -> str:
    age = _age_days(ran_at, now=now)
    if age is None:
        return escape(ran_at)
    # >= : spec §11 authoritative boundary ("9 green, 10 amber") over §8's ">10d"
    cls = ' class="age-amber"' if age >= STALE_EVAL_DAYS else ""
    return f'{escape(ran_at)} <span{cls}>· {age}天前</span>'


def _row_html(row: ValidationPanelRow, *, now: datetime) -> str:
    reasons = "; ".join(row.reasons)
    cls = ' class="panel-amber"' if _is_amber(row) else ""
    return (
        f"<tr{cls}><td>{escape(row.stage)}</td>"
        f"<td>{_status_label(row)}</td>"
        f"<td>{_ran_at_cell(row.ran_at, now=now)}</td></tr>"
        f'<tr class="panel-reasons"><td colspan="3" class="muted">'
        f"{escape(reasons)}</td></tr>"
    )


def validation_panel_html(
    *, rows: tuple[ValidationPanelRow, ...], badge_counts: dict[str, int],
    now: datetime,
) -> str:
    """`now` is REQUIRED and threaded from the edge (run_monitor's now_dt,
    monitor_cmd.py:875 — see Step 6.24). Render purity (spec §2, Global
    Constraints): NO datetime.now() fallback, EVER."""
    badges = _counts_str(badge_counts)
    # The badge tally is a run-global fund count, not a per-stage value — render it
    # ONCE at the panel level so it doesn't read as if each stage carried it.
    summary = (f'<p class="badge-summary muted">fund badges — {escape(badges)}</p>'
               if badges else "")
    body = "".join(_row_html(r, now=now) for r in rows)
    return (
        '<section class="validation-panel"><h2>Validation</h2>'
        f"{summary}"
        '<table class="validation"><tr><th>stage</th><th>overall</th>'
        '<th>ran_at</th></tr>'
        f"{body}</table></section>"
    )
