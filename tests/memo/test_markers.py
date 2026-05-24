"""Item 007 D1a — marker grammar lock.

Locked format: `[stock:{symbol}] [ref:{citation_id}] ...` per ADR 0004 / Q1.
"""
import pytest


def test_format_ref_marker_full_16_hex() -> None:
    from irc.memo.markers import format_ref_marker
    cid = "a1b2c3d4e5f60718"
    assert format_ref_marker(cid) == "[ref:a1b2c3d4e5f60718]"


def test_format_ref_marker_empty_raises() -> None:
    from irc.memo.markers import format_ref_marker
    with pytest.raises(ValueError, match="citation_id must be non-empty"):
        format_ref_marker("")


def test_format_stock_marker_cn_symbol() -> None:
    from irc.memo.markers import format_stock_marker
    assert format_stock_marker("600519") == "[stock:600519]"


def test_format_stock_marker_hk_symbol() -> None:
    """HK 5-digit codes pass through verbatim."""
    from irc.memo.markers import format_stock_marker
    assert format_stock_marker("00700") == "[stock:00700]"


def test_format_stock_marker_empty_raises() -> None:
    from irc.memo.markers import format_stock_marker
    with pytest.raises(ValueError, match="symbol must be non-empty"):
        format_stock_marker("")


def test_format_combined_marker_with_symbol() -> None:
    from irc.memo.markers import format_combined_marker
    out = format_combined_marker("a1b2c3d4e5f60718", "600519")
    assert out == "[stock:600519] [ref:a1b2c3d4e5f60718]"


def test_format_combined_marker_without_symbol() -> None:
    """When symbol is None/empty, stock marker is OMITTED (no placeholder)."""
    from irc.memo.markers import format_combined_marker
    assert format_combined_marker("a1b2c3d4e5f60718", None) == "[ref:a1b2c3d4e5f60718]"
    assert format_combined_marker("a1b2c3d4e5f60718", "") == "[ref:a1b2c3d4e5f60718]"


def test_marker_grammar_format_constants_present() -> None:
    """Both format strings exposed as module-level constants for cross-test reuse."""
    from irc.memo import markers
    assert markers.REF_MARKER_FMT == "[ref:{citation_id}]"
    assert markers.STOCK_MARKER_FMT == "[stock:{symbol}]"


def test_combined_marker_parses_with_locked_regex() -> None:
    """Item 009's parser keys off this regex — locked here."""
    import re
    from irc.memo.markers import format_combined_marker
    line = format_combined_marker("a1b2c3d4e5f60718", "600519") + " content..."
    m = re.match(r"^(?:\[stock:(?P<sym>[^\]]+)\] )?\[ref:(?P<cid>[0-9a-f]{16})\]", line)
    assert m is not None
    assert m.group("sym") == "600519"
    assert m.group("cid") == "a1b2c3d4e5f60718"


def test_combined_marker_no_stock_parses_with_locked_regex() -> None:
    import re
    from irc.memo.markers import format_combined_marker
    line = format_combined_marker("a1b2c3d4e5f60718", None) + " content..."
    m = re.match(r"^(?:\[stock:(?P<sym>[^\]]+)\] )?\[ref:(?P<cid>[0-9a-f]{16})\]", line)
    assert m is not None
    assert m.group("sym") is None
    assert m.group("cid") == "a1b2c3d4e5f60718"
