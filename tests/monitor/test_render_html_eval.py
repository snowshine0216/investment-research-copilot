from __future__ import annotations
from datetime import datetime, timedelta, timezone
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.eval.types import GateDecision, StageHealth
from irc.monitor.eval.staleness import STALE_AFTER_DAYS  # noqa: F401 (import sanity)
from irc.monitor.types import SignalRecord, FactorContribution, NarrativeDoc

_NOW = "2026-06-16T09:00:00+08:00"
_NOW_DT = datetime(2026, 6, 16, 9, 0, tzinfo=timezone(timedelta(hours=8)))


def _signal(status="ok", bias="ADD_BIAS"):
    return SignalRecord(fund_id="008986", status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                        divergence_codes=())


def _view(status="ok", bias="ADD_BIAS"):
    return FundView(fund_id="008986", name_cn="测试", latest_nav=2.0, as_of_date="2026-06-16",
                    nav_series=(("2026-06-15", 2.4), ("2026-06-16", 2.5)), signal=_signal(status, bias),
                    narrative=NarrativeDoc("008986", (), (), (), "ok"), evidence_pool=(),
                    return_table={}, factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=())


def _gate(badge="validated", suppressed=False, reason=""):
    return GateDecision("008986", suppressed, ("monitor_signal",) if suppressed else (),
                        badge, reason)


def _render(view, gate):
    from irc.monitor.render_html import render_report
    from irc.monitor.eval.determinism import build_panel_rows
    from irc.monitor.eval.types import StageHealth
    prov = Provenance("1", "1", "1", "")
    # Build panel rows from RAW healths: a clean-but-gated fund's signal health is
    # PASS (divergence 1) — the gate outcome lives in badge_counts/EVAL-GATED.
    sig_health = {"008986": StageHealth("monitor_signal", "PASS", ())}
    det_health = {"008986": StageHealth("deterministic_scoring", "PASS", ())}
    rows = build_panel_rows(sig_health, det_health, now=_NOW)
    return render_report((view,), prov, prior_signal=None, now=_NOW, now_dt=_NOW_DT,
                         gates={"008986": gate}, panel_rows=rows)


def test_eval_gated_badge_rendered():
    html = _render(_view(), _gate(badge="gated", suppressed=True, reason="nav_quality FAIL"))
    assert "eval-gated" in html
    assert "EVAL-GATED" in html


def test_validated_chip_on_published_bias():
    html = _render(_view(bias="ADD_BIAS"), _gate(badge="validated"))
    assert "ADD_BIAS" in html
    assert "✓" in html  # validated chip glyph


def test_caveated_chip_on_published_bias():
    html = _render(_view(bias="REDUCE_BIAS"), _gate(badge="caveated"))
    assert "REDUCE_BIAS" in html
    assert "⚠" in html  # caveated chip glyph


def test_no_call_not_eval_gated_when_status_not_ok():
    html = _render(_view(status="low_confidence", bias=None), _gate(badge="caveated"))
    assert "NO_CALL" in html
    assert "EVAL-GATED" not in html


def test_validation_panel_present_with_monitor_signal_row():
    html = _render(_view(), _gate(badge="validated"))
    assert "Validation" in html
    assert "monitor_signal" in html


def test_render_report_backwards_compatible_without_gates():
    # gates defaults to None → falls back to bare bias badge (no chip/panel crash)
    from irc.monitor.render_html import render_report
    prov = Provenance("1", "1", "1", "")
    html = render_report((_view(),), prov, prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "ADD_BIAS" in html


def test_validation_panel_gate_outcome_visible_via_badge_when_fund_gated():
    # Divergence 1 (spec §5/§8): the monitor_signal ROW now shows RAW signal_health
    # (PASS for a clean fund), NOT the gate outcome. Gate-outcome visibility moves
    # to the EVAL-GATED badge + badge_counts, which still render.
    html = _render(_view(), _gate(badge="gated", suppressed=True, reason="nav_quality FAIL"))
    assert "EVAL-GATED" in html        # gate outcome still visible (badge)
    assert "gated: 1" in html          # gate outcome still visible (badge_counts)
    assert "Validation" in html        # panel still renders


def test_validation_panel_overall_pass_when_all_validated():
    html = _render(_view(), _gate(badge="validated", suppressed=False))
    # With all gates validated (no suppressed, no caveated), panel overall is PASS
    assert "Validation" in html


def test_panel_vocabulary_and_age_e2e_through_real_render_report():
    """e2e wiring check (Phase 6 review fix): seeds a REAL flow_coverage
    informational row (flow_cover below the 0.50 floor) plus the gate-relevant
    monitor_signal row through build_panel_rows -> render_report, and a stale
    ran_at on the gate-relevant row to exercise the age-amber path. Prior to this
    test, panel vocabulary/board-collapse render surfaces had zero coverage
    through a real rendered report (unit tests only used hand-built
    ValidationPanelRow fixtures directly against validation_panel_html)."""
    from irc.monitor.render_html import render_report
    from irc.monitor.eval.determinism import build_panel_rows
    view = _view()
    gate = _gate(badge="validated")
    prov = Provenance("1", "1", "1", "")
    sig_health = {"008986": StageHealth("monitor_signal", "PASS", ())}
    det_health = {"008986": StageHealth("deterministic_scoring", "PASS", ())}
    # Stale ran_at (>=10d before now) so monitor_signal's row exercises age-amber.
    stale_now = "2026-06-06T09:00:00+08:00"  # 10 days before _NOW (2026-06-16)
    rows = build_panel_rows(
        sig_health, det_health, now=stale_now,
        flow_coverage_healths={
            "008986": StageHealth("flow_coverage", "PASS", ("flow_cover 0.2",)),
        },
    )
    html = render_report((view,), prov, prior_signal=None, now=_NOW, now_dt=_NOW_DT,
                         gates={"008986": gate}, panel_rows=rows)
    flow_row_html = html.split("flow_coverage")[1].split("</tr>")[0]
    assert "观测" in flow_row_html
    assert ">PASS<" not in flow_row_html
    assert "panel-amber" in html
    sig_row_html = html.split("monitor_signal")[1].split("</tr>")[0]
    assert ">PASS<" in sig_row_html  # gate-relevant stage keeps raw vocabulary
    assert "age-amber" in html
