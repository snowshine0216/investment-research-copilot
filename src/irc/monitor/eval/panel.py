"""PURE Validation panel HTML. M0: one row (monitor_signal). No I/O."""
from __future__ import annotations
from html import escape
from irc.monitor.eval.types import StageHealth

_BADGE_ORDER = ("validated", "caveated", "gated")


def _counts_str(badge_counts: dict[str, int]) -> str:
    parts = [f"{b}: {badge_counts[b]}" for b in _BADGE_ORDER if b in badge_counts]
    return ", ".join(parts)


def validation_panel_html(
    *, stage_health: StageHealth, ran_at: str, badge_counts: dict[str, int],
) -> str:
    reasons = "; ".join(stage_health.reasons)
    return (
        '<section class="validation-panel"><h2>Validation</h2>'
        '<table class="validation"><tr><th>stage</th><th>overall</th>'
        '<th>ran_at</th><th>badges</th></tr>'
        f"<tr><td>{escape(stage_health.stage)}</td>"
        f"<td>{escape(stage_health.status)}</td>"
        f"<td>{escape(ran_at)}</td>"
        f"<td>{escape(_counts_str(badge_counts))}</td></tr></table>"
        f'<p class="muted">{escape(reasons)}</p></section>'
    )
