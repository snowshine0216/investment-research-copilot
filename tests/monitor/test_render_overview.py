from __future__ import annotations

from irc.monitor.render_overview import (
    ActionableFund, BiasFlip, DataHealthCounts, compute_actionable, compute_data_health,
    compute_flips, overview_html,
)


def test_overview_html_all_empty_renders_quiet_line():
    health = DataHealthCounts(dark_factor_fractions={}, gated_fund_count=0, stale_eval_count=0)
    html = overview_html(flips=(), actionable=(), health=health)
    assert "今日无变化，数据健康" in html


def test_overview_html_flip_row_renders_arrow_and_names():
    flip = BiasFlip(fund_id="270023", name_cn="A基金", from_bias="NEUTRAL",
                    to_bias="ADD_BIAS", prior_run_date="2026-06-15")
    health = DataHealthCounts(dark_factor_fractions={}, gated_fund_count=0, stale_eval_count=0)
    html = overview_html(flips=(flip,), actionable=(), health=health)
    assert "A基金(270023)" in html
    assert "NEUTRAL" in html and "ADD_BIAS" in html
    assert "2026-06-15" in html


def test_overview_html_actionable_row_renders_bias_and_restriction():
    fund = ActionableFund(fund_id="519069", name_cn="B基金", bias="ADD_BIAS",
                          purchase_restricted=True)
    health = DataHealthCounts(dark_factor_fractions={}, gated_fund_count=0, stale_eval_count=0)
    html = overview_html(flips=(), actionable=(fund,), health=health)
    assert "B基金(519069)" in html
    assert "ADD_BIAS" in html
    assert "限购" in html


def test_overview_html_health_row_renders_dark_fractions_and_counts():
    health = DataHealthCounts(
        dark_factor_fractions={"flow": (5, 7)}, gated_fund_count=2, stale_eval_count=1,
    )
    html = overview_html(flips=(), actionable=(), health=health)
    assert "flow 5/7" in html
    assert "2" in html   # gated count
    assert "1" in html   # stale count


def test_overview_html_row_dropped_when_that_row_empty_but_others_present():
    fund = ActionableFund(fund_id="519069", name_cn="B基金", bias="ADD_BIAS",
                          purchase_restricted=False)
    health = DataHealthCounts(dark_factor_fractions={}, gated_fund_count=0, stale_eval_count=0)
    html = overview_html(flips=(), actionable=(fund,), health=health)
    assert "偏向变化" not in html   # flip row absent entirely
    assert "可操作" in html


def _sig(fund_id, bias, status="ok"):
    from irc.monitor.types import SignalRecord
    return SignalRecord(fund_id=fund_id, status=status, bias=bias, composite=0.1,
                        signal_confidence=0.9, available_weight=1.0,
                        present_families=(), contributions=(), divergence_codes=())


def _view(fund_id, name_cn, bias):
    from irc.monitor.render_types import FundView
    from irc.monitor.types import NarrativeDoc
    return FundView(fund_id=fund_id, name_cn=name_cn, latest_nav=1.0, as_of_date="2026-06-16",
                    nav_series=(), signal=_sig(fund_id, bias),
                    narrative=NarrativeDoc(fund_id, (), (), (), "empty_pool"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=())


def test_compute_flips_detects_bias_change():
    view = _view("270023", "A基金", "ADD_BIAS")
    prior = {"270023": {"status": "ok", "bias": "NEUTRAL"}}
    flips = compute_flips((view,), prior, "2026-06-15")
    assert len(flips) == 1
    assert flips[0].from_bias == "NEUTRAL"
    assert flips[0].to_bias == "ADD_BIAS"
    assert flips[0].prior_run_date == "2026-06-15"


def test_compute_flips_no_change_yields_empty():
    view = _view("270023", "A基金", "NEUTRAL")
    prior = {"270023": {"status": "ok", "bias": "NEUTRAL"}}
    assert compute_flips((view,), prior, "2026-06-15") == ()


def test_compute_flips_no_prior_yields_empty():
    view = _view("270023", "A基金", "ADD_BIAS")
    assert compute_flips((view,), None, None) == ()


def test_compute_flips_fund_absent_from_prior_yields_no_flip():
    view = _view("270023", "A基金", "ADD_BIAS")
    prior = {}   # fund wasn't in yesterday's run
    assert compute_flips((view,), prior, "2026-06-15") == ()


def _gate(fund_id, suppressed=False, badge="validated"):
    from irc.monitor.eval.types import GateDecision
    return GateDecision(fund_id, suppressed, (), badge, "")


def test_compute_actionable_add_bias_included():
    view = _view("519069", "B基金", "ADD_BIAS")
    gates = {"519069": _gate("519069")}
    result = compute_actionable((view,), gates, {"519069": None})
    assert len(result) == 1
    assert result[0].bias == "ADD_BIAS"
    assert result[0].purchase_restricted is False


def test_compute_actionable_neutral_excluded():
    view = _view("519069", "B基金", "NEUTRAL")
    gates = {"519069": _gate("519069")}
    result = compute_actionable((view,), gates, {"519069": None})
    assert result == ()


def test_compute_actionable_eval_gated_never_included():
    """EVAL-GATED ADD_BIAS fund must NEVER appear in 可操作 (spec §11 acceptance
    criterion)."""
    view = _view("519069", "B基金", "ADD_BIAS")
    gates = {"519069": _gate("519069", suppressed=True)}
    result = compute_actionable((view,), gates, {"519069": None})
    assert result == ()


def test_compute_actionable_purchase_restricted_flag_set():
    view = _view("519069", "B基金", "REDUCE_BIAS")
    gates = {"519069": _gate("519069")}
    result = compute_actionable((view,), gates, {"519069": "限购：单日限1000元"})
    assert result[0].purchase_restricted is True


def test_compute_actionable_no_call_status_excluded():
    view = _view("519069", "B基金", None, )
    # status defaults to "ok" in the _view helper; build a NO_CALL view directly
    from irc.monitor.render_types import FundView
    from irc.monitor.types import NarrativeDoc
    sig = _sig("519069", None, status="insufficient_evidence")
    view = FundView(fund_id="519069", name_cn="B基金", latest_nav=1.0, as_of_date="2026-06-16",
                    nav_series=(), signal=sig,
                    narrative=NarrativeDoc("519069", (), (), (), "empty_pool"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=())
    gates = {"519069": _gate("519069")}
    result = compute_actionable((view,), gates, {"519069": None})
    assert result == ()


def _score(name, eligible, reason=""):
    from irc.monitor.types import FactorScore
    return FactorScore(name=name, value=(0.1 if eligible else None), eligible=eligible,
                       reason=reason, confidence=1.0)


def _view_with_scores(fund_id, name_cn, scores):
    from irc.monitor.render_types import FundView
    from irc.monitor.types import NarrativeDoc
    return FundView(fund_id=fund_id, name_cn=name_cn, latest_nav=1.0, as_of_date="2026-06-16",
                    nav_series=(), signal=_sig(fund_id, "NEUTRAL"),
                    narrative=NarrativeDoc(fund_id, (), (), (), "empty_pool"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=scores)


def test_compute_data_health_dark_fraction_excludes_profile_ineligible():
    """Gold/QDII funds structurally lack 'flow' (profile_ineligible) — they must
    NOT inflate the eligible_n denominator (spec §7 acceptance criterion)."""
    fund_a = _view_with_scores("519069", "A", (_score("flow", eligible=False, reason="flow_no_data"),))
    fund_b = _view_with_scores("008986", "金", (_score("flow", eligible=False, reason="profile_ineligible"),))
    fund_c = _view_with_scores("260112", "C", (_score("flow", eligible=True),))
    health = compute_data_health((fund_a, fund_b, fund_c), {}, (), stale_eval_days=10,
                                 today="2026-06-16")
    # gold fund (profile_ineligible) excluded entirely from eligible_n
    assert health.dark_factor_fractions["flow"] == (1, 2)   # 1 dark / 2 eligible


def test_compute_data_health_gated_fund_count():
    from irc.monitor.eval.types import GateDecision
    gates = {"519069": GateDecision("519069", True, ("monitor_signal",), "gated", "x"),
             "260112": GateDecision("260112", False, (), "validated", "")}
    health = compute_data_health((), gates, (), stale_eval_days=10, today="2026-06-16")
    assert health.gated_fund_count == 1


def test_compute_data_health_stale_eval_count_from_panel_rows():
    from irc.monitor.eval.types import ValidationPanelRow
    rows = (
        ValidationPanelRow(stage="monitor_impact", status="PASS", ran_at="2026-06-01T00:00:00+08:00", reasons=()),
        ValidationPanelRow(stage="monitor_narrative", status="PASS", ran_at="2026-06-15T00:00:00+08:00", reasons=()),
    )
    # today passed EXPLICITLY (required — no clock read in render code, spec §2)
    health = compute_data_health((), {}, rows, stale_eval_days=10, today="2026-06-16")
    assert health.stale_eval_count == 1   # only the 2026-06-01 row is stale (15d ≥ 10d)


def test_compute_data_health_stale_count_includes_stale_predictive_artifact():
    """spec §7: 过期评估 K = stale suite stamps PLUS the stale predictive-artifact
    component (PredictivePanelModel.stale, computed at the edge, passed as a bool)."""
    from irc.monitor.eval.types import ValidationPanelRow
    rows = (
        ValidationPanelRow(stage="monitor_impact", status="PASS",
                           ran_at="2026-06-01T00:00:00+08:00", reasons=()),
    )
    health = compute_data_health((), {}, rows, stale_eval_days=10,
                                 today="2026-06-16", predictive_stale=True)
    assert health.stale_eval_count == 2   # 1 stale suite stamp + 1 stale predictive artifact


# ── report v4 item 001: caveat label map / tooltip / segment classification ──


def test_caveat_tooltip_maps_stage_labels_and_stale_age():
    from irc.monitor.render_overview import caveat_tooltip
    reason = ("monitor_impact: UNKNOWN (stale, 15d); "
              "monitor_narrative: UNKNOWN (stale, 16d)")
    assert caveat_tooltip(reason) == (
        "影响评分质量评估: UNKNOWN (上次质量评估已过期 15天); "
        "叙事质量评估: UNKNOWN (上次质量评估已过期 16天)")


def test_caveat_tooltip_unmapped_stage_and_reasons_pass_raw():
    # P2 locks only the three Chinese labels — monitor_signal and raw metric
    # strings (gap 12d etc.) pass through untranslated (open question 11).
    from irc.monitor.render_overview import caveat_tooltip
    assert caveat_tooltip("monitor_signal: WARN (gap 12d)") == "monitor_signal: WARN (gap 12d)"
    assert caveat_tooltip("") == ""


def test_fund_specific_segments_filters_run_global_prefixes():
    from irc.monitor.render_overview import fund_specific_segments
    reason = ("monitor_signal: WARN (gap 12d); "
              "monitor_impact: UNKNOWN (stale, 15d)")
    assert fund_specific_segments(reason) == ("monitor_signal: WARN (gap 12d)",)
    assert fund_specific_segments("") == ()
    assert fund_specific_segments(
        "monitor_impact: UNKNOWN (stale, 15d); monitor_narrative: UNKNOWN (stale, 16d)"
    ) == ()
