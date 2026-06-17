"""Tests for the pure constituent symbol matcher (v2.1 keying-drift fix).

match_impact_to_holding maps an LLM impact key back to a snapshot holding's
canonical symbol, robust to exchange suffixes, whitespace, case, leading zeros,
and name_cn variants. Pure — no I/O, no mocks.
"""
from __future__ import annotations

from irc.fundamentals.types import ConstituentAnalysis
from irc.monitor.constituent_match import (
    match_impact_to_holding,
    select_impacts_by_holding,
)
from irc.monitor.impact_validate import ValidatedImpact


def _holding(symbol: str, name_cn: str, weight_pct: float = 5.0) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn=name_cn, weight_pct=weight_pct,
        evidence=(), failure_reasons=(), one_line_view="",
    )


def test_exact_symbol_matches() -> None:
    holdings = (_holding("300750", "宁德时代"), _holding("600519", "贵州茅台"))
    assert match_impact_to_holding("300750", holdings) == "300750"


def test_exchange_suffix_matches_bare_symbol() -> None:
    holdings = (_holding("300750", "宁德时代"), _holding("600519", "贵州茅台"))
    assert match_impact_to_holding("300750.SZ", holdings) == "300750"
    assert match_impact_to_holding("600519.SH", holdings) == "600519"


def test_other_exchange_suffixes_match() -> None:
    holdings = (_holding("430139", "晨光生物"), _holding("600519", "贵州茅台"))
    assert match_impact_to_holding("430139.BJ", holdings) == "430139"
    assert match_impact_to_holding("600519.SS", holdings) == "600519"


def test_whitespace_and_case_variants_match() -> None:
    holdings = (_holding("300750", "宁德时代"),)
    assert match_impact_to_holding("  300750  ", holdings) == "300750"
    assert match_impact_to_holding("300750.sz", holdings) == "300750"  # lowercase suffix


def test_name_cn_fallback_matches() -> None:
    holdings = (_holding("300750", "宁德时代"), _holding("600519", "贵州茅台"))
    assert match_impact_to_holding("宁德时代", holdings) == "300750"
    assert match_impact_to_holding(" 贵州茅台 ", holdings) == "600519"


def test_leading_zeros_stripped_when_numeric() -> None:
    holdings = (_holding("000858", "五粮液"),)
    assert match_impact_to_holding("858", holdings) == "000858"
    assert match_impact_to_holding("00858", holdings) == "000858"


def test_unmatched_key_returns_none() -> None:
    holdings = (_holding("300750", "宁德时代"),)
    assert match_impact_to_holding("999999", holdings) is None
    assert match_impact_to_holding("某不存在的公司", holdings) is None
    assert match_impact_to_holding("", holdings) is None


# ── select_impacts_by_holding (pure dedup) ────────────────────────────────────


def _imp(key: str, impact: float, confidence: float) -> ValidatedImpact:
    return ValidatedImpact(key, impact, confidence, ())


def test_select_maps_each_impact_to_its_holding() -> None:
    holdings = (_holding("300750", "宁德时代"), _holding("600519", "贵州茅台"))
    best, unmatched = select_impacts_by_holding(
        (_imp("300750.SZ", 0.5, 0.9), _imp("贵州茅台", -0.2, 0.7)), holdings)
    assert unmatched == ()
    assert set(best) == {"300750", "600519"}
    assert best["300750"].impact == 0.5


def test_select_dedups_to_highest_confidence_no_double_count() -> None:
    """Two impacts for the same holding → one entry, highest confidence wins."""
    holdings = (_holding("300750", "宁德时代"),)
    best, unmatched = select_impacts_by_holding(
        (_imp("300750", 0.5, 0.6), _imp("300750.SZ", -0.9, 0.95)), holdings)
    assert unmatched == ()
    assert set(best) == {"300750"}
    assert best["300750"].confidence == 0.95
    assert best["300750"].impact == -0.9


def test_select_reports_unmatched_keys() -> None:
    holdings = (_holding("300750", "宁德时代"),)
    best, unmatched = select_impacts_by_holding(
        (_imp("300750", 0.5, 0.9), _imp("999999", 0.8, 0.8)), holdings)
    assert set(best) == {"300750"}
    assert unmatched == ("999999",)
