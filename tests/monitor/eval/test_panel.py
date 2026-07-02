from __future__ import annotations
from datetime import datetime, timedelta, timezone
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import ValidationPanelRow

_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=timezone(timedelta(hours=8)))


def _row(stage, status, reasons=()):
    return ValidationPanelRow(stage=stage, status=status,
                              ran_at="2026-06-16T09:00:00+08:00", reasons=reasons)


def test_panel_renders_both_rows_with_counts():
    rows = (_row("monitor_signal", "PASS"),
            _row("deterministic_scoring", "PASS"))
    html = validation_panel_html(
        rows=rows,
        badge_counts={"validated": 2, "caveated": 1, "gated": 1}, now=_NOW)
    assert "Validation" in html
    assert "monitor_signal" in html
    assert "deterministic_scoring" in html
    assert "2026-06-16T09:00:00+08:00" in html
    assert "PASS" in html
    assert "validated: 2" in html and "gated: 1" in html and "caveated: 1" in html


def test_panel_is_pure_string():
    html = validation_panel_html(
        rows=(_row("monitor_signal", "FAIL", ("nav",)),),
        badge_counts={"gated": 7}, now=_NOW)
    assert isinstance(html, str) and html.startswith("<section")
    assert "FAIL" in html and "gated: 7" in html


def test_panel_renders_per_row_reasons():
    rows = (_row("monitor_signal", "WARN", ("gap 7d",)),
            _row("deterministic_scoring", "FAIL", ("159934: composite",)))
    html = validation_panel_html(rows=rows, badge_counts={"gated": 1}, now=_NOW)
    assert "gap 7d" in html
    assert "159934: composite" in html


def test_panel_badge_tally_appears_once_not_per_row():
    # The badge tally is a run-global fund count, not a per-stage value — it must
    # render ONCE at the panel level, not be repeated on every stage row (which read
    # as if each stage carried that count).
    rows = (_row("monitor_signal", "WARN", ("gap 11d",)),
            _row("monitor_impact", "FAIL", ("magnitude_band_pass",)),
            _row("monitor_narrative", "PASS"),
            _row("deterministic_scoring", "PASS"))
    html = validation_panel_html(rows=rows, badge_counts={"gated": 7}, now=_NOW)
    assert html.count("gated: 7") == 1
    # per-stage attribution (the gating stage + its reason) is still present
    assert "monitor_impact" in html and "magnitude_band_pass" in html
