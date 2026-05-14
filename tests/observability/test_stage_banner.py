from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from irc.observability.progress import stage_banner


def _capture_console_into(monkeypatch) -> StringIO:
    buf = StringIO()
    captured = Console(file=buf, force_terminal=False, width=120)
    monkeypatch.setattr("irc.observability.progress.console", captured)
    return buf


def _freeze_time(monkeypatch, values: list[float]) -> None:
    iterator = iter(values)
    monkeypatch.setattr(
        "irc.observability.progress.time.monotonic",
        lambda: next(iterator),
    )


def test_stage_banner_prints_starting_and_done(monkeypatch):
    buf = _capture_console_into(monkeypatch)
    _freeze_time(monkeypatch, [100.0, 142.5])

    with stage_banner("ingest", 1, 8):
        pass

    output = buf.getvalue()
    assert "[1/8] ingest" in output
    assert "starting" in output
    assert "done in 42s" in output


def test_stage_banner_prints_failed_on_exception_and_reraises(monkeypatch):
    buf = _capture_console_into(monkeypatch)
    _freeze_time(monkeypatch, [200.0, 210.0])

    with pytest.raises(RuntimeError, match="boom"):
        with stage_banner("score", 4, 8):
            raise RuntimeError("boom")

    output = buf.getvalue()
    assert "[4/8] score" in output
    assert "FAILED" in output
    assert "10s" in output
