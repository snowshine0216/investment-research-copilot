from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from irc.monitor.eval.gate import GATING_STAGES_M0, GATING_STAGES_M1
import irc.commands.monitor_cmd as mc
from irc.monitor.types import (
    MonitorFund, NarrativeDoc, SignalRecord, FactorContribution,
)
from irc.monitor.eval.types import FundTraceBundle
from irc.monitor.render_types import FundView


_TZ = timezone(timedelta(hours=8))


def test_gating_stages_m1_is_m0_plus_two_llm_suites():  # AC17
    assert GATING_STAGES_M1 == GATING_STAGES_M0 | {"monitor_impact", "monitor_narrative"}
    assert GATING_STAGES_M0 < GATING_STAGES_M1  # strict superset


# ── helpers for AC18-AC20 ─────────────────────────────────────────────────────


def _fund(fid="000001"):
    return MonitorFund(id=fid, name_cn="", market="", analysis_profile="gold_etf",
                       themes=(), constituent_news=False, weights={"trend": 1.0},
                       bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5)


def _signal(fid="000001", status="ok", bias="ADD_BIAS"):
    # composite=0.3 and one contribution that sums to 0.3 so signal_consistency passes
    contrib = FactorContribution(name="trend", renorm_weight=1.0, value=0.3,
                                 contribution=0.3, confidence=1.0,
                                 eligible=True, reason="")
    return SignalRecord(fund_id=fid, status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("trend",),
                        contributions=(contrib,) if status == "ok" else (),
                        divergence_codes=())


def _narr(fid="000001"):
    return NarrativeDoc(fund_id=fid, price_action_commentary=(),
                        signal_rationale_commentary=(), risk_commentary=(),
                        status="ok")


def _view(fund, signal):
    """Build a minimal FundView that passes monitor_signal_health for gate tests.
    nav_series has 3 recent observations so nav_quality passes with min_obs=2."""
    today = datetime.now(_TZ).date()
    nav_series = tuple(
        ((today - timedelta(days=i)).isoformat(), 1.0 + i * 0.01)
        for i in range(2, -1, -1)
    )
    return FundView(
        fund_id=fund.id, name_cn=fund.name_cn,
        latest_nav=1.02, as_of_date=today.isoformat(),
        nav_series=nav_series, signal=signal, narrative=_narr(fund.id),
        evidence_pool=(), return_table={}, factor_freshness={},
        missing_factor_reasons=(), factor_scores=(),
    )


def _bundle(fid="000001"):
    return FundTraceBundle(fund_id=fid, macro_impacts=(), constituent_impacts=(),
                           constituent_pool=())


def _stage_report(stage, overall, *, ran_at, metrics=None):
    return {"stage": stage, "ran_at": ran_at, "based_on": [], "metrics": metrics or [],
            "overall": overall, "notes": "", "config_versions": {}}


def _write_report(root: Path, date_str: str, stage: str, payload: dict):
    d = root / "outputs" / date_str / "evals" / stage
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_fresh_fail_impact_gates_funds(tmp_path: Path):  # AC19
    today = datetime.now(_TZ).date().isoformat()
    fresh = datetime.now(_TZ).isoformat()
    _write_report(tmp_path, today, "monitor_impact", _stage_report(
        "monitor_impact", "FAIL", ran_at=fresh,
        metrics=[{"name": "magnitude_band_pass", "value": 0.667, "status": "FAIL"}]))
    _write_report(tmp_path, today, "monitor_narrative", _stage_report("monitor_narrative", "PASS", ran_at=fresh))

    fund, sig = _fund(), _signal()
    view = _view(fund, sig)
    suite_healths, suite_rows = mc._suite_eval(tmp_path, today, datetime.now(_TZ))
    gates, _sig_h, _det_h, _recon_h, _cov_h, _vr_h, _vc_h = mc._compute_gates([fund], [view], [_bundle()], min_obs=2,
                                                                suite_healths=suite_healths, trading_days=None)
    from irc.monitor.eval.gate import published_state
    assert gates[0].suppressed is True
    assert published_state(sig, gates[0]) == "EVAL_GATED"
    # the gating stage is now a visible panel row with its real ran_at + the failing metric
    impact_row = next(r for r in suite_rows if r.stage == "monitor_impact")
    assert impact_row.status == "FAIL" and impact_row.ran_at == fresh
    assert "magnitude_band_pass" in impact_row.reasons


def test_missing_suite_reports_fail_open(tmp_path: Path):  # AC20
    today = datetime.now(_TZ).date().isoformat()
    # no eval reports written → resolve_health → UNKNOWN → caveated (not gated)
    fund, sig = _fund(), _signal()
    view = _view(fund, sig)
    suite_healths, _rows = mc._suite_eval(tmp_path, today, datetime.now(_TZ))
    gates, _sig_h, _det_h, _recon_h, _cov_h, _vr_h, _vc_h = mc._compute_gates([fund], [view], [_bundle()], min_obs=2,
                                                                suite_healths=suite_healths, trading_days=None)
    assert gates[0].suppressed is False
    assert gates[0].badge == "caveated"  # Finding 1: missing report must be caveated, not validated
    # report v4 item 001: the caveated reason is populated end-to-end through
    # _suite_eval -> _compute_gates (absent reports carry no age).
    assert gates[0].reason == ("monitor_impact: UNKNOWN (absent); "
                               "monitor_narrative: UNKNOWN (absent)")


def test_no_call_precedence_when_status_not_ok(tmp_path: Path):  # AC19 NO_CALL branch
    today = datetime.now(_TZ).date().isoformat()
    fresh = datetime.now(_TZ).isoformat()
    _write_report(tmp_path, today, "monitor_impact", _stage_report("monitor_impact", "FAIL", ran_at=fresh))
    fund = _fund()
    sig = _signal(status="insufficient_evidence", bias=None)
    view = _view(fund, sig)
    suite_healths, _rows = mc._suite_eval(tmp_path, today, datetime.now(_TZ))
    gates, _sig_h, _det_h, _recon_h, _cov_h, _vr_h, _vc_h = mc._compute_gates([fund], [view], [_bundle()], min_obs=2,
                                                                suite_healths=suite_healths, trading_days=None)
    from irc.monitor.eval.gate import published_state
    assert published_state(sig, gates[0]) == "NO_CALL"
