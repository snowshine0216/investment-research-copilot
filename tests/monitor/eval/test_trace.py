from __future__ import annotations
import json
from irc.monitor.eval.trace import build_eval_trace, dedup_by_citation_id
from irc.monitor.eval.gate import apply_eval_gate, published_state, GATING_STAGES_M0
from irc.monitor.eval.structural import monitor_signal_health
from irc.monitor.eval.types import FundTraceBundle, StageHealth
from irc.monitor.evidence import make_evidence_item
from irc.monitor.impact_validate import ValidatedImpact
from irc.monitor.render_types import FundView
from irc.monitor.types import (
    MonitorFund, SignalRecord, FactorScore, FactorContribution, NarrativeDoc, Claim,
)


def _fund(fid="008986", profile="gold_etf"):
    return MonitorFund(id=fid, name_cn="测试", market="CN", analysis_profile=profile,
                       themes=("gold",), constituent_news=False,
                       weights={"trend": 1.0}, bands={"buy": 0.1, "sell": -0.1},
                       minimum_confidence=0.5)


def _ev(fid, url):
    return make_evidence_item("Reuters", "t", "2026-06-16", url, owner_fund_id=fid)


def _signal(fid="008986", bias="ADD_BIAS"):
    return SignalRecord(fund_id=fid, status="ok", bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                        divergence_codes=())


def _good_view(fid="008986", ev=None):
    ev = ev or _ev(fid, "https://a")
    narr = NarrativeDoc(fid, (Claim("x", "consistent_with", (ev.citation_id,)),), (), (), "ok")
    return FundView(fund_id=fid, name_cn="测试", latest_nav=2.0, as_of_date="2026-06-16",
                    nav_series=(("2026-06-15", 2.4), ("2026-06-16", 2.5)), signal=_signal(fid),
                    narrative=narr, evidence_pool=(ev,), return_table={},
                    factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=(FactorScore("trend", 0.3, True, "", 1.0),))


def _degraded_view(fid="600000"):
    return FundView(fund_id=fid, name_cn="降级", latest_nav=0.0, as_of_date="N/A",
                    nav_series=(), signal=_signal(fid), narrative=NarrativeDoc(fid, (), (), (), "ok"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=())


def _bundle(fid="008986", macro=()):
    return FundTraceBundle(fund_id=fid, macro_impacts=macro, constituent_impacts=(), constituent_pool=())


def _gate(view):
    h = (monitor_signal_health(_project(view), minimum_observations=2, stale_days=7),)
    return apply_eval_gate(view.signal, health=h, gating_stages=GATING_STAGES_M0)


def _project(view):
    # helper mirroring build_eval_trace's per-fund dict (only fields monitor_signal_health needs)
    trace = build_eval_trace(((_fund(view.fund_id), view, _stub_gate(view), _bundle(view.fund_id)),),
                             engine_version="1", run_date="2026-06-16")
    return trace["funds"][view.fund_id]


def _stub_gate(view):
    from irc.monitor.eval.types import GateDecision
    return GateDecision(view.fund_id, False, (), "validated", "")


def test_top_level_keys():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    assert set(t) == {"schema_version", "engine_version", "run_date", "funds"}
    assert t["engine_version"] == "1" and t["run_date"] == "2026-06-16"
    assert "008986" in t["funds"]


def test_per_fund_schema_keys():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    f = t["funds"]["008986"]
    assert set(f) == {"resolved", "nav", "evidence_pool", "factor_scores", "signal",
                      "impacts", "narrative", "gate", "published_state", "validation_badge"}
    assert set(f["resolved"]) == {"analysis_profile", "weights", "bands", "minimum_confidence"}
    assert set(f["nav"]) == {"as_of_date", "latest_unit_nav", "nav_acc", "acc_series",
                             "obs_count", "max_gap_days"}


def test_round_trip_json_serializable():
    t = build_eval_trace(
        ((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),
         (_fund("600000", "qdii_proxy"), _degraded_view(), _stub_gate(_degraded_view()), _bundle("600000"))),
        engine_version="1", run_date="2026-06-16")
    reloaded = json.loads(json.dumps(t))
    assert reloaded == t


def test_degraded_nav_no_indexerror_and_nulls():
    t = build_eval_trace(((_fund("600000"), _degraded_view(), _stub_gate(_degraded_view()), _bundle("600000")),),
                         engine_version="1", run_date="2026-06-16")
    nav = t["funds"]["600000"]["nav"]
    assert nav["nav_acc"] is None and nav["obs_count"] == 0
    assert nav["max_gap_days"] is None and nav["latest_unit_nav"] == 0.0


def test_good_nav_fields_computed():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    nav = t["funds"]["008986"]["nav"]
    assert nav["nav_acc"] == 2.5 and nav["obs_count"] == 2
    assert nav["max_gap_days"] == 1


def test_dedup_by_citation_id_merges_overlap():
    ev1 = _ev("008986", "https://a")
    ev2 = _ev("008986", "https://a")   # same preimage → same id
    ev3 = _ev("008986", "https://b")
    out = dedup_by_citation_id((ev1, ev2, ev3))
    ids = [e["citation_id"] for e in out]
    assert len(ids) == len(set(ids)) == 2


def test_unified_pool_contains_macro_and_constituent_ids():
    macro_ev = _ev("008986", "https://macro")
    const_ev = _ev("008986", "https://const")
    view = _good_view("008986", ev=macro_ev)
    bundle = FundTraceBundle("008986", macro_impacts=(), constituent_impacts=(),
                             constituent_pool=(const_ev,))
    t = build_eval_trace(((_fund(), view, _stub_gate(view), bundle),),
                         engine_version="1", run_date="2026-06-16")
    pool_ids = {e["citation_id"] for e in t["funds"]["008986"]["evidence_pool"]}
    assert macro_ev.citation_id in pool_ids and const_ev.citation_id in pool_ids


def test_constituent_impact_citation_resolves_against_unified_pool():
    from irc.monitor.eval.structural import citation_integrity
    const_ev = _ev("008986", "https://const")
    view = _good_view("008986")
    const_imp = ValidatedImpact(key="600519", impact=0.5, confidence=0.8,
                                citation_ids=(const_ev.citation_id,))
    bundle = FundTraceBundle("008986", macro_impacts=(), constituent_impacts=(const_imp,),
                             constituent_pool=(const_ev,))
    t = build_eval_trace(((_fund(), view, _stub_gate(view), bundle),),
                         engine_version="1", run_date="2026-06-16")
    assert citation_integrity(t["funds"]["008986"]).status == "PASS"


def test_impacts_macro_and_constituent_serialized():
    macro_imp = ValidatedImpact("gold", 0.3, 0.9, ())
    const_imp = ValidatedImpact("600519", 0.5, 0.8, ())
    view = _good_view()
    bundle = FundTraceBundle("008986", macro_impacts=(macro_imp,),
                             constituent_impacts=(const_imp,), constituent_pool=())
    t = build_eval_trace(((_fund(), view, _stub_gate(view), bundle),),
                         engine_version="1", run_date="2026-06-16")
    imp = t["funds"]["008986"]["impacts"]
    assert imp["macro"][0]["key"] == "gold" and imp["constituent"][0]["key"] == "600519"


def test_gate_and_published_state_serialized():
    view = _good_view()
    g = _stub_gate(view)
    t = build_eval_trace(((_fund(), view, g, _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    f = t["funds"]["008986"]
    assert f["gate"] == {"suppressed": False, "failed_stages": [], "reason": ""}
    assert f["validation_badge"] == "validated"
    # status==ok, not suppressed → published_state is the bias
    assert f["published_state"] == "ADD_BIAS"
