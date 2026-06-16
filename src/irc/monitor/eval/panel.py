"""PURE Validation panel HTML. M2: N rows (monitor_signal + deterministic_scoring).
No I/O."""
from __future__ import annotations
from html import escape
from irc.monitor.eval.types import ValidationPanelRow

_BADGE_ORDER = ("validated", "caveated", "gated")


def _counts_str(badge_counts: dict[str, int]) -> str:
    parts = [f"{b}: {badge_counts[b]}" for b in _BADGE_ORDER if b in badge_counts]
    return ", ".join(parts)


def _row_html(row: ValidationPanelRow, badges: str) -> str:
    reasons = "; ".join(row.reasons)
    return (
        f"<tr><td>{escape(row.stage)}</td>"
        f"<td>{escape(row.status)}</td>"
        f"<td>{escape(row.ran_at)}</td>"
        f"<td>{escape(badges)}</td></tr>"
        f'<tr class="panel-reasons"><td colspan="4" class="muted">'
        f"{escape(reasons)}</td></tr>"
    )


def validation_panel_html(
    *, rows: tuple[ValidationPanelRow, ...], badge_counts: dict[str, int],
) -> str:
    badges = _counts_str(badge_counts)
    body = "".join(_row_html(r, badges) for r in rows)
    return (
        '<section class="validation-panel"><h2>Validation</h2>'
        '<table class="validation"><tr><th>stage</th><th>overall</th>'
        '<th>ran_at</th><th>badges</th></tr>'
        f"{body}</table></section>"
    )
