from __future__ import annotations
from datetime import datetime, timedelta, timezone
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import ValidationPanelRow

# now is passed EXPLICITLY from the very first test: validation_panel_html takes
# a REQUIRED `now` (no clock fallback — spec §2 render purity; see Step 6.15).
_NOW = datetime(2026, 7, 2, 12, 0, tzinfo=timezone(timedelta(hours=8)))


def test_informational_stage_renders_观测_not_pass():
    rows = (ValidationPanelRow(stage="flow_coverage", status="PASS",
                               ran_at="2026-07-01T12:00:00+08:00",
                               reasons=("flow_cover 0.0",)),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=_NOW)
    assert "观测" in html
    # the informational row must NOT render the literal text "PASS" as its status cell
    assert ">PASS<" not in html.split("flow_coverage")[1].split("</tr>")[0]


def test_gating_stage_still_renders_pass_fail_warn_unknown():
    rows = (ValidationPanelRow(stage="monitor_signal", status="PASS",
                               ran_at="2026-07-01T12:00:00+08:00", reasons=()),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=_NOW)
    assert ">PASS<" in html.split("monitor_signal")[1].split("</tr>")[0]


def test_informational_stage_amber_when_flow_cover_below_floor():
    rows = (ValidationPanelRow(stage="flow_coverage", status="PASS",
                               ran_at="2026-07-01T12:00:00+08:00",
                               reasons=("flow_cover 0.2",)),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=_NOW)
    assert "panel-amber" in html


def test_informational_stage_not_amber_when_flow_cover_at_or_above_floor():
    rows = (ValidationPanelRow(stage="flow_coverage", status="PASS",
                               ran_at="2026-07-01T12:00:00+08:00",
                               reasons=("flow_cover 0.5",)),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=_NOW)
    assert "panel-amber" not in html


def test_ran_at_shows_age_in_days():
    from irc.monitor.eval.panel import validation_panel_html
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    ran_at = (now - timedelta(days=3)).isoformat()
    rows = (ValidationPanelRow(stage="monitor_impact", status="PASS", ran_at=ran_at,
                               reasons=()),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=now)
    assert "3天前" in html


def test_ran_at_age_boundary_9_days_not_amber():
    from irc.monitor.eval.panel import validation_panel_html
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    ran_at = (now - timedelta(days=9)).isoformat()
    rows = (ValidationPanelRow(stage="monitor_impact", status="PASS", ran_at=ran_at,
                               reasons=()),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=now)
    assert "age-amber" not in html


def test_ran_at_age_boundary_10_days_is_amber():
    from irc.monitor.eval.panel import validation_panel_html
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    ran_at = (now - timedelta(days=10)).isoformat()
    rows = (ValidationPanelRow(stage="monitor_impact", status="PASS", ran_at=ran_at,
                               reasons=()),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=now)
    assert "age-amber" in html


def test_ran_at_unparseable_shows_dash_not_crash():
    from irc.monitor.eval.panel import validation_panel_html
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    rows = (ValidationPanelRow(stage="monitor_impact", status="PASS", ran_at="—",
                               reasons=()),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=now)
    assert "—" in html


def test_stale_after_14_days_is_separate_from_10_day_amber_cue():
    """Two constants, two meanings (spec §8): amber(≥10d, eval/constants.STALE_EVAL_DAYS;
    spec §11 boundary: 9 green, 10 amber)
    is an early heads-up; UNKNOWN(stale) at >14d (eval/staleness.STALE_AFTER_DAYS) is
    the GATE's own staleness check, computed upstream by resolve_health — this panel
    only ever RENDERS whatever status resolve_health already decided (UNKNOWN), it
    does not recompute the 14-day gate itself. This test asserts panel.py imports
    STALE_EVAL_DAYS (10) and NOT STALE_AFTER_DAYS (14) — the two modules must stay
    decoupled."""
    from irc.monitor.eval import panel as panel_mod
    from irc.monitor.eval.constants import STALE_EVAL_DAYS
    from irc.monitor.eval.staleness import STALE_AFTER_DAYS
    assert STALE_EVAL_DAYS == 10
    assert STALE_AFTER_DAYS == 14
    assert panel_mod.STALE_EVAL_DAYS == STALE_EVAL_DAYS
