from __future__ import annotations

from io import StringIO

from rich.console import Console

from irc.observability.progress import progress_iter


def test_progress_iter_yields_all_items_in_order():
    items = list(range(10))
    result = list(progress_iter(items, desc="testing"))
    assert result == items


def test_progress_iter_yields_with_explicit_total():
    items = ["a", "b", "c"]
    result = list(progress_iter(items, desc="testing", total=len(items)))
    assert result == items


def test_progress_iter_handles_empty_iterable():
    result = list(progress_iter([], desc="testing"))
    assert result == []


def test_progress_iter_non_tty_produces_no_ansi_escapes(monkeypatch):
    buf = StringIO()
    captured_console = Console(file=buf, force_terminal=False, width=120)
    monkeypatch.setattr("irc.observability.progress.console", captured_console)
    result = list(progress_iter([1, 2, 3], desc="testing"))
    assert result == [1, 2, 3]
    assert "\x1b[" not in buf.getvalue()  # no ANSI escapes
