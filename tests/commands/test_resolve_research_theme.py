"""Unit tests for _resolve_research_theme routing branches."""
from __future__ import annotations

import pytest

from irc.commands.opportunity_cmd import _resolve_research_theme
from irc.opportunity.types import OpportunityInput
from irc.research.theme_research import ThemeReport


def _inp(**kwargs) -> OpportunityInput:
    defaults = dict(
        instrument_id="TEST",
        asset_class="cn_equity_fund",
        market="cn",
        theme=None,
    )
    defaults.update(kwargs)
    return OpportunityInput(**defaults)


def _report(name: str) -> ThemeReport:
    return ThemeReport(
        theme=name, query="", locale="en", report_md="", citations=[], failure_reason=""
    )


def test_direct_theme_wins_over_asset_class() -> None:
    """If the instrument has a direct theme that exists in reports, it wins."""
    reports = {"us_monetary": _report("us_monetary"), "geopolitics": _report("geopolitics")}
    inp = _inp(asset_class="us_etf", theme="us_monetary")
    result = _resolve_research_theme(inp, reports)
    assert result is reports["us_monetary"]


def test_gold_asset_class_routes_to_gold_drivers() -> None:
    reports = {"gold_drivers": _report("gold_drivers")}
    inp = _inp(asset_class="gold")
    assert _resolve_research_theme(inp, reports) is reports["gold_drivers"]


def test_cn_bond_fund_routes_to_cn_monetary() -> None:
    reports = {"cn_monetary": _report("cn_monetary")}
    inp = _inp(asset_class="cn_bond_fund")
    assert _resolve_research_theme(inp, reports) is reports["cn_monetary"]


def test_us_etf_routes_to_geopolitics() -> None:
    reports = {"geopolitics": _report("geopolitics")}
    inp = _inp(asset_class="us_etf")
    assert _resolve_research_theme(inp, reports) is reports["geopolitics"]


def test_hk_etf_routes_to_geopolitics() -> None:
    reports = {"geopolitics": _report("geopolitics")}
    inp = _inp(asset_class="hk_etf")
    assert _resolve_research_theme(inp, reports) is reports["geopolitics"]


def test_cn_equity_fund_without_theme_routes_to_holdings_sector() -> None:
    reports = {"holdings_sector": _report("holdings_sector")}
    inp = _inp(asset_class="cn_equity_fund", theme=None)
    assert _resolve_research_theme(inp, reports) is reports["holdings_sector"]


def test_unrecognized_asset_class_returns_none() -> None:
    reports = {"gold_drivers": _report("gold_drivers")}
    inp = _inp(asset_class="unknown_class")
    assert _resolve_research_theme(inp, reports) is None


def test_direct_theme_missing_from_reports_falls_through_to_asset_class() -> None:
    """A theme not in the reports dict should fall through to asset-class routing."""
    reports = {"geopolitics": _report("geopolitics")}
    inp = _inp(asset_class="us_etf", theme="no_such_theme")
    assert _resolve_research_theme(inp, reports) is reports["geopolitics"]
