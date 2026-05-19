"""Holdings-sector query construction (item 001, 2026-05-19)."""
from __future__ import annotations

from irc.research.theme_research import build_holdings_query


def test_empty_keywords_returns_default_query() -> None:
    out = build_holdings_query(())
    assert "用户组合" in out  # the existing placeholder
    # And critically, it does NOT name a specific asset class.
    assert "黄金" not in out
    assert "S&P" not in out


def test_keywords_inject_named_assets() -> None:
    out = build_holdings_query(("黄金", "沪深300", "标普500"))
    assert "黄金" in out
    assert "沪深300" in out
    assert "标普500" in out
    assert "原始出处" in out  # cite-primary-sources directive preserved


def test_empty_strings_filtered() -> None:
    out = build_holdings_query(("", "黄金", "  "))
    assert "黄金" in out
    # Should NOT have stray empty separators
    assert "、、" not in out


def test_keyword_order_is_preserved() -> None:
    """Stable ordering keeps the query deterministic for snapshot tests
    and reproducible logging."""
    a = build_holdings_query(("黄金", "沪深300"))
    b = build_holdings_query(("黄金", "沪深300"))
    assert a == b
    flipped = build_holdings_query(("沪深300", "黄金"))
    assert "沪深300、黄金" in flipped
