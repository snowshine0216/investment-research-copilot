from __future__ import annotations

from io import StringIO

from rich.console import Console

from irc.observability.errors import ErrorTally


def _capture_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


def test_tally_starts_empty():
    tally = ErrorTally("metadata")
    assert tally.total_skipped() == 0


def test_tally_groups_by_category():
    tally = ErrorTally("metadata")
    tally.add("000001", KeyError("data"))
    tally.add("000002", KeyError("data"))
    tally.add("000003", ValueError("empty NAV"))
    assert tally.total_skipped() == 3
    assert tally.counts() == {"data-key": 2, "empty": 1}


def test_tally_render_with_zero_skips_shows_only_ok_line():
    console, buf = _capture_console()
    tally = ErrorTally("metadata")
    tally.render(ok_count=50, console=console)
    output = buf.getvalue()
    assert "metadata: 50 ok / 0 skipped" in output


def test_tally_render_with_skips_shows_tree():
    console, buf = _capture_console()
    tally = ErrorTally("metadata")
    for i in range(27):
        tally.add(f"fund_{i:06d}", KeyError("data"))
    tally.add("fund_999999", ValueError("empty price history"))
    tally.render(ok_count=89, console=console)
    output = buf.getvalue()
    assert "metadata: 89 ok / 28 skipped" in output
    assert "27" in output and "data-key" in output
    assert "1" in output and "empty" in output


def test_tally_render_verbose_lists_all_ids():
    console, buf = _capture_console()
    tally = ErrorTally("metadata")
    for i in range(10):
        tally.add(f"fund_{i:06d}", KeyError("data"))
    tally.render(ok_count=5, console=console, verbose=True)
    output = buf.getvalue()
    for i in range(10):
        assert f"fund_{i:06d}" in output


def test_tally_render_non_verbose_caps_id_list():
    console, buf = _capture_console()
    tally = ErrorTally("metadata")
    for i in range(20):
        tally.add(f"fund_{i:06d}", KeyError("data"))
    tally.render(ok_count=5, console=console, verbose=False)
    output = buf.getvalue()
    # Should not dump all 20 ids in non-verbose mode
    listed = sum(1 for i in range(20) if f"fund_{i:06d}" in output)
    assert listed <= 5
