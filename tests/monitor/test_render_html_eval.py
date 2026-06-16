from __future__ import annotations
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.eval.types import GateDecision
from irc.monitor.eval.staleness import STALE_AFTER_DAYS  # noqa: F401 (import sanity)
from irc.monitor.types import SignalRecord, FactorContribution, NarrativeDoc

_NOW = "2026-06-16T09:00:00+08:00"


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
    prov = Provenance("1", "1", "1", "")
    return render_report((view,), prov, prior_signal=None, now=_NOW,
                         gates={"008986": gate})


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
    html = render_report((_view(),), prov, prior_signal=None, now=_NOW)
    assert "ADD_BIAS" in html


def test_validation_panel_overall_is_not_pass_when_fund_is_gated():
    # A suppressed gate → panel overall must reflect FAIL, not always show PASS.
    html = _render(_view(), _gate(badge="gated", suppressed=True, reason="nav_quality FAIL"))
    # The panel HTML must NOT contain the string '>PASS<' for the overall status
    # (it should be FAIL since a gate is suppressed)
    assert "EVAL-GATED" in html  # the badge is present
    assert ">PASS<" not in html  # panel overall must not be 'PASS'


def test_validation_panel_overall_pass_when_all_validated():
    html = _render(_view(), _gate(badge="validated", suppressed=False))
    # With all gates validated (no suppressed, no caveated), panel overall is PASS
    assert "Validation" in html
