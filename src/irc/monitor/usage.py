from __future__ import annotations

from irc.schemas.monitor import MonitorConfig

_RETRY_HEADROOM = 1.5          # average completed calls incl. some schema-retries
_HOLDING_QUERIES_PER_FUND = 5  # top-N holdings news when constituent_news=True


def monitor_usage_overrides(cfg: MonitorConfig) -> dict[str, float]:
    """Pure: per-run average call counts for the monitor LLM tasks, derived from the
    monitor config (NOT a fixed 7). Feeds the estimator's per-run UsageProfile."""
    impact_units = 0
    for f in cfg.funds:
        impact_units += len(f.themes)
        if f.constituent_news:
            impact_units += _HOLDING_QUERIES_PER_FUND
    return {
        "monitor_impact": impact_units * _RETRY_HEADROOM,
        "monitor_narrative": len(cfg.funds) * _RETRY_HEADROOM,
    }
