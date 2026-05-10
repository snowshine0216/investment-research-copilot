from __future__ import annotations
from evals.trade_plan.metrics import (
    venue_compatibility_marked,
    buy_method_class_match,
    trigger_monitorability,
)


def _make_trades():
    return [
        {"venue": "NYSE", "instrument_class": "equity", "buy_method": "limit", "trigger": "price < 150"},
        {"venue": "LSE", "instrument_class": "equity", "buy_method": "market", "trigger": "open"},
        {"venue": "BOND_MKT", "instrument_class": "bond", "buy_method": "limit", "trigger": "yield > 4%"},
        {"venue": "NYSE", "instrument_class": "etf", "buy_method": "limit", "trigger": "NAV discount > 1%"},
    ]


def test_venue_compatibility_marked_all():
    trades = _make_trades()
    assert venue_compatibility_marked(trades) == 1.0


def test_venue_compatibility_marked_partial():
    trades = _make_trades()
    trades[0]["venue"] = ""
    assert venue_compatibility_marked(trades) == 0.75


def test_venue_compatibility_marked_empty():
    assert venue_compatibility_marked([]) == 1.0


def test_buy_method_class_match_all_valid():
    trades = _make_trades()
    assert buy_method_class_match(trades) == 1.0


def test_buy_method_class_match_invalid():
    trades = _make_trades()
    trades[2]["buy_method"] = "market"  # bond with market order - invalid
    assert buy_method_class_match(trades) == 0.75


def test_buy_method_class_match_empty():
    assert buy_method_class_match([]) == 1.0


def test_trigger_monitorability_all():
    trades = _make_trades()
    assert trigger_monitorability(trades) == 1.0


def test_trigger_monitorability_partial():
    trades = _make_trades()
    trades[0]["trigger"] = ""
    assert trigger_monitorability(trades) == 0.75


def test_trigger_monitorability_empty():
    assert trigger_monitorability([]) == 1.0
