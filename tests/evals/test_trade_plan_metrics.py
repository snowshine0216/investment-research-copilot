"""Trade-plan metric tests against the current TradePlanRow schema.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/008-spec.md
"""
from __future__ import annotations

from evals.trade_plan.metrics import (
    buy_method_class_match,
    trigger_monitorability,
    venue_compatibility_marked,
)


def _make_trades() -> list[dict]:
    """Shape mirrors src/irc/trades/pipeline.py:TradePlanRow."""
    return [
        {
            "target": "VTI", "asset_class": "equity", "buy_method": "limit",
            "venue_compatible": True, "venue_note": "direct",
            "triggers": [{"condition": "price < 150"}],
        },
        {
            "target": "VXUS", "asset_class": "equity", "buy_method": "market",
            "venue_compatible": True, "venue_note": "direct",
            "triggers": [{"condition": "open"}],
        },
        {
            "target": "BND", "asset_class": "bond", "buy_method": "limit",
            "venue_compatible": True, "venue_note": "direct",
            "triggers": [{"condition": "yield > 4%"}],
        },
        {
            "target": "510300", "asset_class": "cn_etf", "buy_method": "limit",
            "venue_compatible": True, "venue_note": "direct",
            "triggers": [{"condition": "NAV discount > 1%"}],
        },
    ]


def test_venue_compatibility_marked_all() -> None:
    assert venue_compatibility_marked(_make_trades()) == 1.0


def test_venue_compatibility_marked_partial() -> None:
    trades = _make_trades()
    trades[0]["venue_note"] = ""
    assert venue_compatibility_marked(trades) == 0.75


def test_venue_compatibility_marked_empty() -> None:
    assert venue_compatibility_marked([]) == 1.0


def test_buy_method_class_match_all_valid() -> None:
    assert buy_method_class_match(_make_trades()) == 1.0


def test_buy_method_class_match_invalid() -> None:
    trades = _make_trades()
    trades[2]["buy_method"] = "market"  # bond with market order
    assert buy_method_class_match(trades) == 0.75


def test_buy_method_class_match_empty() -> None:
    assert buy_method_class_match([]) == 1.0


def test_buy_method_class_match_unknown_class_passes() -> None:
    """Unknown asset_class does not penalise the trade (defensive default)."""
    trades = [{"target": "X", "asset_class": "weird", "buy_method": "limit",
               "venue_note": "n", "triggers": [{"x": 1}]}]
    assert buy_method_class_match(trades) == 1.0


def test_trigger_monitorability_all() -> None:
    assert trigger_monitorability(_make_trades()) == 1.0


def test_trigger_monitorability_partial() -> None:
    trades = _make_trades()
    trades[0]["triggers"] = []
    assert trigger_monitorability(trades) == 0.75


def test_trigger_monitorability_empty() -> None:
    assert trigger_monitorability([]) == 1.0
