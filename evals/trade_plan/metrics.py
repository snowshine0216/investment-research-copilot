"""Trade-plan metric functions.

Reads the producer's current TradePlanRow schema (src/irc/trades/pipeline.py):
``target``, ``asset_class``, ``buy_method``, ``venue_compatible``,
``venue_note``, ``triggers`` (list of dicts).
"""
from __future__ import annotations


_ALLOWED_METHOD_BY_CLASS: dict[str, set[str]] = {
    "cn_etf": {"limit", "market"},
    "global_etf": {"limit", "market"},
    "etf": {"limit", "market"},
    "equity": {"limit", "market"},
    "bond": {"limit"},
}


def venue_compatibility_marked(trades: list[dict]) -> float:
    """Fraction of trades whose venue check ran (venue_note is a non-empty string).

    The producer always writes both ``venue_compatible`` and ``venue_note``,
    so a healthy run reports 1.0. Drift below 1.0 indicates a producer bug.
    """
    if not trades:
        return 1.0
    marked = sum(1 for t in trades if isinstance(t.get("venue_note"), str) and t["venue_note"].strip())
    return marked / len(trades)


def buy_method_class_match(trades: list[dict]) -> float:
    """Fraction of trades where buy_method aligns with the trade's asset_class."""
    if not trades:
        return 1.0
    matched = 0
    for t in trades:
        cls = str(t.get("asset_class", "")).lower()
        method = str(t.get("buy_method", "")).lower()
        allowed = _ALLOWED_METHOD_BY_CLASS.get(cls)
        if allowed is None:
            matched += 1  # unknown class — do not penalise the trade
        elif method in allowed:
            matched += 1
    return matched / len(trades)


def trigger_monitorability(trades: list[dict]) -> float:
    """Fraction of trades whose ``triggers`` list is non-empty."""
    if not trades:
        return 1.0
    monitorable = sum(
        1 for t in trades
        if isinstance(t.get("triggers"), list) and len(t["triggers"]) > 0
    )
    return monitorable / len(trades)
