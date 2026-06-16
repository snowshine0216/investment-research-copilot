"""PURE human-review trigger. The headline metric (publishable_bias_directional)
random delta < 0 for >= K consecutive ISO-week reports → review flag. A None week
(insufficient_data / missing details) breaks the streak — conservative, no false
alarm. Never EVAL_GATED."""
from __future__ import annotations
from irc.monitor.eval.constants import REVIEW_TRIGGER_K


def review_trigger(
    weekly_headline_random_deltas: list[float | None], *, k: int = REVIEW_TRIGGER_K,
) -> bool:
    """True iff the most recent k weekly deltas are all present (non-None) and < 0."""
    if len(weekly_headline_random_deltas) < k:
        return False
    recent = weekly_headline_random_deltas[-k:]
    return all(d is not None and d < 0 for d in recent)


from datetime import date


def _iso_week_key(artifact_date: str) -> tuple[int, int]:
    y, w, _ = date.fromisoformat(artifact_date).isocalendar()
    return (y, w)


def dedup_iso_weeks(entries: list, *, k: int) -> list:
    """Keep one entry per ISO year-week (highest artifact_date; tiebreak by
    report.ran_at), most-recent weeks first, capped at k. Pure — entries are any
    objects with .artifact_date (str) and .report.ran_at (str)."""
    by_week: dict[tuple[int, int], object] = {}
    for e in sorted(entries, key=lambda x: (x.artifact_date, x.report.ran_at)):
        by_week[_iso_week_key(e.artifact_date)] = e   # later sort order wins → highest kept
    ordered = sorted(by_week.values(), key=lambda x: x.artifact_date, reverse=True)
    return ordered[:k]
