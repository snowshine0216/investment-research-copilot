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
