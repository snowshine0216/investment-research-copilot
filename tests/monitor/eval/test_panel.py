from __future__ import annotations
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import StageHealth


def test_panel_renders_monitor_signal_row_with_counts():
    health = StageHealth("monitor_signal", "PASS", ())
    html = validation_panel_html(stage_health=health, ran_at="2026-06-16T09:00:00+08:00",
                                 badge_counts={"validated": 2, "caveated": 1, "gated": 1})
    assert "Validation" in html
    assert "monitor_signal" in html
    assert "2026-06-16T09:00:00+08:00" in html
    assert "PASS" in html
    assert "validated: 2" in html and "gated: 1" in html and "caveated: 1" in html


def test_panel_is_pure_string():
    html = validation_panel_html(stage_health=StageHealth("monitor_signal", "FAIL", ("nav",)),
                                 ran_at="t", badge_counts={"gated": 7})
    assert isinstance(html, str) and html.startswith("<section")
    assert "FAIL" in html and "gated: 7" in html
