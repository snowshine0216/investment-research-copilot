from __future__ import annotations
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import ValidationPanelRow


def _row(stage, status, reasons=()):
    return ValidationPanelRow(stage=stage, status=status,
                              ran_at="2026-06-16T09:00:00+08:00", reasons=reasons)


def test_panel_renders_both_rows_with_counts():
    rows = (_row("monitor_signal", "PASS"),
            _row("deterministic_scoring", "PASS"))
    html = validation_panel_html(
        rows=rows,
        badge_counts={"validated": 2, "caveated": 1, "gated": 1})
    assert "Validation" in html
    assert "monitor_signal" in html
    assert "deterministic_scoring" in html
    assert "2026-06-16T09:00:00+08:00" in html
    assert "PASS" in html
    assert "validated: 2" in html and "gated: 1" in html and "caveated: 1" in html


def test_panel_is_pure_string():
    html = validation_panel_html(
        rows=(_row("monitor_signal", "FAIL", ("nav",)),),
        badge_counts={"gated": 7})
    assert isinstance(html, str) and html.startswith("<section")
    assert "FAIL" in html and "gated: 7" in html


def test_panel_renders_per_row_reasons():
    rows = (_row("monitor_signal", "WARN", ("gap 7d",)),
            _row("deterministic_scoring", "FAIL", ("159934: composite",)))
    html = validation_panel_html(rows=rows, badge_counts={"gated": 1})
    assert "gap 7d" in html
    assert "159934: composite" in html
