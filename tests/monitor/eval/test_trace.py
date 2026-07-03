from __future__ import annotations
import dataclasses
import datetime as _dt
import json
import pytest
from irc.monitor.eval.trace import (
    build_eval_trace, dedup_by_citation_id, _max_gap_days, _missing_trading_days,
)
from irc.monitor.eval.gate import apply_eval_gate, GATING_STAGES_M0
from irc.monitor.eval.structural import monitor_signal_health
from irc.monitor.eval.types import FundTraceBundle
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
    assert set(t) == {"schema_version", "engine_version", "run_date", "funds",
                  "macro_narrative"}
    assert t["engine_version"] == "1" and t["run_date"] == "2026-06-16"
    assert "008986" in t["funds"]


def test_per_fund_schema_keys():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    f = t["funds"]["008986"]
    assert set(f) == {"resolved", "nav", "evidence_pool", "factor_scores", "signal",
                      "impacts", "narrative", "gate", "published_state", "validation_badge",
                      "holding_metrics"}
    assert set(f["resolved"]) == {"analysis_profile", "weights", "bands", "minimum_confidence"}
    assert set(f["nav"]) == {"as_of_date", "latest_unit_nav", "nav_acc", "acc_series",
                             "obs_count", "max_gap_days", "missing_trading_days"}


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


def test_max_gap_days_ignores_gaps_older_than_recent_window():
    # An 11-day Spring-Festival/Golden-Week hole sits early in a multi-year series;
    # the trailing-activity probe must ignore it (it is the lunar calendar, not a
    # data outage) and report only the recent daily cadence.
    old = (("2026-01-01", 1.0), ("2026-01-12", 1.0))   # 11d holiday gap
    base = _dt.date(2026, 5, 1)
    recent = tuple(((base + _dt.timedelta(days=i)).isoformat(), 1.0) for i in range(25))
    assert _max_gap_days(old + recent) <= 5


def test_max_gap_days_flags_a_recent_hole():
    # A genuine recent outage (fund stopped reporting for 10 days) IS inside the
    # window and must still surface.
    base = _dt.date(2026, 5, 1)
    head = tuple(((base + _dt.timedelta(days=i)).isoformat(), 1.0) for i in range(18))
    # head ends 2026-05-18; jump 10 days, then resume daily — a single recent hole.
    tail = (("2026-05-28", 1.0), ("2026-05-29", 1.0))
    assert _max_gap_days(head + tail) == 10


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


def _cn_cal(*iso: str):
    return frozenset(_dt.date.fromisoformat(d) for d in iso)


def test_missing_trading_days_none_calendar_returns_none():
    series = (("2026-06-15", 1.0), ("2026-06-16", 1.0))
    assert _missing_trading_days(series, None) is None


def test_missing_trading_days_empty_calendar_returns_none():
    # An empty frozenset must degrade to None (→ max_gap_days fallback), never
    # score 0-for-every-gap and yield a false nav_quality PASS.
    series = (("2026-06-15", 1.0), ("2026-06-30", 1.0))
    assert _missing_trading_days(series, frozenset()) is None


def test_missing_trading_days_fewer_than_two_obs_is_zero():
    assert _missing_trading_days((("2026-06-16", 1.0),), _cn_cal("2026-06-16")) == 0
    assert _missing_trading_days((), _cn_cal("2026-06-16")) == 0


def test_missing_trading_days_holiday_gap_counts_zero():
    # Series jumps across a closure; NONE of the in-between days are trading days,
    # so the fund missed zero open sessions.
    series = (("2026-02-13", 1.0), ("2026-02-23", 1.0))   # Spring-Festival hole
    cal = _cn_cal("2026-02-13", "2026-02-23")             # closure days absent
    assert _missing_trading_days(series, cal) == 0


def test_missing_trading_days_real_interior_miss_counts():
    # The fund skipped 2026-02-17 and 2026-02-18, both of which the market was open.
    series = (("2026-02-16", 1.0), ("2026-02-19", 1.0))
    cal = _cn_cal("2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19")
    assert _missing_trading_days(series, cal) == 2


def test_missing_trading_days_respects_recent_window():
    # An ancient outage (3 missed trading days) sits outside the recent window of
    # 20 obs and must be ignored; only the daily-cadence tail is scored.
    cal_days = [_dt.date(2026, 5, 1) + _dt.timedelta(days=i) for i in range(40)]
    cal = frozenset(cal_days)
    # obs 0 then a 4-day jump (3 interior trading days missed), then 25 daily obs.
    old = (("2026-05-01", 1.0), ("2026-05-05", 1.0))
    recent = tuple((d.isoformat(), 1.0) for d in cal_days[4:29])   # 25 consecutive
    assert _missing_trading_days(old + recent, cal) == 0


def test_nav_missing_trading_days_threaded_from_calendar():
    cal = frozenset(_dt.date.fromisoformat(d) for d in
                    ("2026-06-15", "2026-06-16"))
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16", trading_days=cal)
    nav = t["funds"]["008986"]["nav"]
    # _good_view's series is consecutive trading days → no missed open sessions.
    assert nav["missing_trading_days"] == 0


def test_nav_missing_trading_days_is_none_without_calendar():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    assert t["funds"]["008986"]["nav"]["missing_trading_days"] is None


def test_schema_version_is_7():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="3", run_date="2026-06-21")
    assert t["schema_version"] == "7"


def test_caveated_gate_reason_lands_in_trace_non_empty():
    # Criterion 10: schema 7's only content change — gate.reason stops being
    # empty for caveated funds; shape is untouched.
    from irc.monitor.eval.types import GateDecision
    reason = ("monitor_impact: UNKNOWN (stale, 15d); "
              "monitor_narrative: UNKNOWN (stale, 16d)")
    gate = GateDecision("008986", False, (), "caveated", reason)
    t = build_eval_trace(((_fund(), _good_view(), gate, _bundle()),),
                         engine_version="4", run_date="2026-07-03")
    entry = t["funds"]["008986"]
    assert entry["validation_badge"] == "caveated"
    assert entry["gate"]["reason"] == reason


def test_trace_emits_holding_metrics_block():
    from irc.monitor.holding_metrics import HoldingMetric
    # weight_pct=50.0 → coverage 0.50 >= monitor floor 0.40 so valuation_aggregate computes.
    hm = HoldingMetric("600519", "贵州茅台", 50.0, 30.0, 8.0, 0.8, "expensive",
                       None, 4.0, 3.5, 1.0, None,
                       self_score=-0.5, industry="酿酒行业", industry_pe=20.0,
                       industry_richness=1.5, industry_score=-1.0, val_score=-0.7,
                       false_cheap=False, industry_reason=None)
    view = _good_view()
    view = dataclasses.replace(view, holding_metrics=(hm,))
    fund = _fund("519069", profile="active_cn_equity")
    bundle = FundTraceBundle("519069", (), (), ())
    gate = apply_eval_gate(view.signal, health=(), gating_stages=GATING_STAGES_M0)
    t = build_eval_trace(((fund, view, gate, bundle),), engine_version="3",
                         run_date="2026-06-21")
    block = t["funds"]["519069"]["holding_metrics"]
    row = block["rows"][0]
    assert row["symbol"] == "600519"
    assert row["flow_score"] == 1.0
    assert row["val_score"] == -0.7
    assert row["industry"] == "酿酒行业"
    assert row["industry_score"] == -1.0
    assert row["false_cheap"] is False
    assert block["aggregate"]["value"] == 1.0
    assert block["aggregate"]["covered_weight_ratio"] == 1.0
    assert "valuation_aggregate" in block
    assert block["valuation_aggregate"]["value"] == pytest.approx(-0.7)


# ── flow_rows warm-up curve: REAL builder → REAL trace → REAL structural check ──


def test_flow_rows_flows_through_real_builder_into_trace_and_warmup_check():
    """P0 regression: flow_rows must be POPULATED by the real per-stock builder
    (build_holding_metrics), survive the real trace serialization (_holding_metrics
    via build_eval_trace), and be read by the real structural warm-up check
    (flow_coverage_health) — not a hand-built dict. Before the fix, HoldingMetric
    has no flow_rows field, so trace.py's getattr(m, "flow_rows", 0) is always 0 and
    flow_rows_min is permanently inert."""
    from irc.monitor.eval.structural import flow_coverage_health
    from irc.monitor.holding_metrics import build_holding_metrics

    class _Holding:
        def __init__(self, symbol, name_cn, weight_pct):
            self.symbol, self.name_cn, self.weight_pct = symbol, name_cn, weight_pct

    top_holdings = (
        _Holding("600519", "贵州茅台", 60.0),
        _Holding("000858", "五粮液", 40.0),
    )
    # 600519 has a real 3-row flow series; 000858 has none (flow_no_data).
    flow_series_by_code = {
        "600519": (("2026-06-14", 1.0), ("2026-06-15", 2.0), ("2026-06-16", 3.0)),
        "000858": None,
    }
    metrics = build_holding_metrics(top_holdings, series_by_code={},
                                    flow_series_by_code=flow_series_by_code)

    view = dataclasses.replace(_good_view(), holding_metrics=metrics)
    fund = _fund("519069", profile="active_cn_equity")
    bundle = FundTraceBundle("519069", (), (), ())
    gate = apply_eval_gate(view.signal, health=(), gating_stages=GATING_STAGES_M0)
    t = build_eval_trace(((fund, view, gate, bundle),), engine_version="3",
                         run_date="2026-06-21")

    rows = t["funds"]["519069"]["holding_metrics"]["rows"]
    by_symbol = {r["symbol"]: r["flow_rows"] for r in rows}
    assert by_symbol["600519"] == 3
    assert by_symbol["000858"] == 0

    health = flow_coverage_health(t["funds"]["519069"])
    assert health.status == "PASS"
    assert "flow_rows_min 0" in health.reasons
