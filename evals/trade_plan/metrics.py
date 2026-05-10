from __future__ import annotations


def venue_compatibility_marked(trades: list[dict]) -> float:
    """Fraction of trades that have a venue field set."""
    if not trades:
        return 1.0
    marked = sum(1 for t in trades if t.get("venue", "").strip())
    return marked / len(trades)


def buy_method_class_match(trades: list[dict]) -> float:
    """Fraction of trades where buy_method aligns with instrument class.

    Equity -> limit or market; Bond -> limit; ETF -> limit or market.
    """
    _allowed: dict[str, set[str]] = {
        "equity": {"limit", "market"},
        "etf": {"limit", "market"},
        "bond": {"limit"},
    }
    if not trades:
        return 1.0
    matched = 0
    for t in trades:
        cls = t.get("instrument_class", "").lower()
        method = t.get("buy_method", "").lower()
        allowed = _allowed.get(cls, {method})  # unknown class: always pass
        if method in allowed:
            matched += 1
    return matched / len(trades)


def trigger_monitorability(trades: list[dict]) -> float:
    """Fraction of trades whose trigger conditions can be monitored (non-empty trigger)."""
    if not trades:
        return 1.0
    monitorable = sum(1 for t in trades if t.get("trigger", "").strip())
    return monitorable / len(trades)
