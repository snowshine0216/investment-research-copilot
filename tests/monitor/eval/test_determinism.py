"""D2 example tests over crafted trace fixtures (spec §8 step 3).

A clean trace → PASS; a trace with a corrupted contribution / bad reason → FAIL
naming the field. recompute/health take fund_id EXPLICITLY (P0 rev-3 fix):
fund_id is the funds-dict key, absent from the per-fund value.
"""
from __future__ import annotations
from irc.monitor.eval.determinism import (
    recompute_signal_from_trace, diff_signal, deterministic_health,
    aggregate_deterministic_health, _safe_status,
)


def _clean_fund() -> dict:
    """A single gold fund whose recorded signal exactly matches a recompute of its
    factor_scores under its resolved params (trend+macro present, heat N/A)."""
    return {
        "resolved": {
            "analysis_profile": "gold",
            "weights": {"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20},
            "bands": {"buy": 0.40, "sell": -0.40},
            "minimum_confidence": 0.50,
        },
        "factor_scores": [
            {"name": "trend", "value": 0.6, "eligible": True, "reason": "", "confidence": 1.0},
            {"name": "macro_tilt", "value": 0.5, "eligible": True, "reason": "", "confidence": 1.0},
            {"name": "heat", "value": None, "eligible": False, "reason": "heat_no_data", "confidence": 1.0},
        ],
        # signal block filled in by _record_signal below so it is self-consistent.
    }


def _record_signal(fund: dict) -> dict:
    """Stamp the recorded `signal` from a faithful recompute (so the clean fixture
    is consistent by construction). fund_id is the dict key '008986'."""
    rec = recompute_signal_from_trace("008986", fund)
    fund["signal"] = {
        "status": rec.status, "bias": rec.bias, "composite": rec.composite,
        "signal_confidence": rec.signal_confidence,
        "available_weight": rec.available_weight,
        "present_families": list(rec.present_families),
        "contributions": [
            {"name": c.name, "renorm_weight": c.renorm_weight, "value": c.value,
             "contribution": c.contribution, "confidence": c.confidence}
            for c in rec.contributions
        ],
        "divergence_codes": list(rec.divergence_codes),
    }
    return fund


def test_recompute_uses_fund_id_for_the_record():
    fund = _clean_fund()
    rec = recompute_signal_from_trace("008986", fund)
    assert rec.fund_id == "008986"
    assert rec.status == "ok" and rec.bias == "ADD_BIAS"


def test_diff_empty_on_clean_trace():
    fund = _record_signal(_clean_fund())
    rec = recompute_signal_from_trace("008986", fund)
    assert diff_signal(rec, fund["signal"]) == ()


def test_diff_names_corrupted_contribution():
    fund = _record_signal(_clean_fund())
    fund["signal"]["contributions"][0]["contribution"] = 99.0   # tamper
    rec = recompute_signal_from_trace("008986", fund)
    fields = diff_signal(rec, fund["signal"])
    assert any("contribution" in f for f in fields)


def test_diff_names_corrupted_composite():
    fund = _record_signal(_clean_fund())
    fund["signal"]["composite"] = 0.0   # tamper (was ~0.556)
    rec = recompute_signal_from_trace("008986", fund)
    assert "composite" in diff_signal(rec, fund["signal"])


def test_diff_names_corrupted_status_and_bias():
    fund = _record_signal(_clean_fund())
    fund["signal"]["status"] = "low_confidence"
    fund["signal"]["bias"] = None
    rec = recompute_signal_from_trace("008986", fund)
    fields = diff_signal(rec, fund["signal"])
    assert "status" in fields and "bias" in fields


def test_health_pass_on_clean_trace():
    fund = _record_signal(_clean_fund())
    h = deterministic_health("008986", fund)
    assert h.stage == "deterministic_scoring" and h.status == "PASS"
    assert h.reasons == ()


def test_health_fail_names_field_on_corrupted_signal():
    fund = _record_signal(_clean_fund())
    fund["signal"]["composite"] = 0.0
    h = deterministic_health("008986", fund)
    assert h.status == "FAIL"
    assert any("composite" in r for r in h.reasons)


def test_health_fail_on_unknown_na_reason():
    fund = _record_signal(_clean_fund())
    fund["factor_scores"][2]["reason"] = "not_a_real_reason"   # ineligible factor
    h = deterministic_health("008986", fund)
    assert h.status == "FAIL"
    assert any("not_a_real_reason" in r or "reason" in r for r in h.reasons)


def test_aggregate_worst_of_passes_fund_id_from_key():
    clean = _record_signal(_clean_fund())
    bad = _record_signal(_clean_fund())
    bad["signal"]["composite"] = 0.0
    traces = {"funds": {"008986": clean, "159934": bad}}
    agg = aggregate_deterministic_health(traces)
    assert agg.stage == "deterministic_scoring" and agg.status == "FAIL"
    # the offending fund id appears in the aggregated reasons
    assert any("159934" in r for r in agg.reasons)


def test_aggregate_pass_when_all_clean():
    traces = {"funds": {"008986": _record_signal(_clean_fund())}}
    agg = aggregate_deterministic_health(traces)
    assert agg.status == "PASS"


def test_aggregate_empty_is_pass():
    assert aggregate_deterministic_health({"funds": {}}).status == "PASS"


# ── Finding A: absent recorded key must be a mismatch, not a silent pass ────


def test_diff_missing_composite_is_mismatch():
    """Absent 'composite' key in recorded → diff names 'composite'."""
    fund = _record_signal(_clean_fund())
    del fund["signal"]["composite"]
    rec = recompute_signal_from_trace("008986", fund)
    fields = diff_signal(rec, fund["signal"])
    assert "composite" in fields


def test_diff_missing_available_weight_is_mismatch():
    """Absent 'available_weight' key in recorded → diff names 'available_weight'."""
    fund = _record_signal(_clean_fund())
    del fund["signal"]["available_weight"]
    rec = recompute_signal_from_trace("008986", fund)
    fields = diff_signal(rec, fund["signal"])
    assert "available_weight" in fields


def test_diff_missing_divergence_codes_is_mismatch():
    """Absent 'divergence_codes' key in recorded → diff names 'divergence_codes'."""
    fund = _record_signal(_clean_fund())
    del fund["signal"]["divergence_codes"]
    rec = recompute_signal_from_trace("008986", fund)
    fields = diff_signal(rec, fund["signal"])
    assert "divergence_codes" in fields


def test_diff_missing_contribution_renorm_weight_is_mismatch():
    """Absent 'renorm_weight' on a contribution entry → diff names the field."""
    fund = _record_signal(_clean_fund())
    del fund["signal"]["contributions"][0]["renorm_weight"]
    rec = recompute_signal_from_trace("008986", fund)
    fields = diff_signal(rec, fund["signal"])
    assert any("renorm_weight" in f for f in fields)


def test_health_fail_when_composite_key_absent():
    """deterministic_health → FAIL when 'composite' is absent from recorded signal."""
    fund = _record_signal(_clean_fund())
    del fund["signal"]["composite"]
    h = deterministic_health("008986", fund)
    assert h.status == "FAIL"
    assert any("composite" in r for r in h.reasons)


# ── Finding #1: _safe_status guard + aggregate consistency ──────────────────


def test_safe_status_maps_unknown_to_fail():
    """_safe_status('UNKNOWN') == 'FAIL'; known statuses pass through unchanged."""
    assert _safe_status("UNKNOWN") == "FAIL"
    assert _safe_status("PASS") == "PASS"
    assert _safe_status("WARN") == "WARN"
    assert _safe_status("FAIL") == "FAIL"


# ── Finding B: _row / build_panel_rows must not KeyError on "UNKNOWN" status ─


def test_build_panel_rows_unknown_status_does_not_raise():
    """A StageHealth with status='UNKNOWN' must not crash _row / build_panel_rows."""
    from irc.monitor.eval.types import StageHealth
    from irc.monitor.eval.determinism import build_panel_rows
    sig = {"A": StageHealth("monitor_signal", "UNKNOWN", ("stale",))}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ())}
    rows = {r.stage: r for r in build_panel_rows(sig, det, now="t")}
    # Should not raise; the unknown status must not be "PASS"
    assert rows["monitor_signal"].status != "PASS"


def test_build_panel_rows_includes_gating_suite_rows_in_order():
    """The gating LLM-suite stages must appear as panel rows (with their real ran_at
    and the failing-metric reasons), grouped with monitor_signal before the
    panel-only deterministic_scoring row — so a reader can see WHICH stage gated."""
    from irc.monitor.eval.types import StageHealth, ValidationPanelRow
    from irc.monitor.eval.determinism import build_panel_rows
    sig = {"A": StageHealth("monitor_signal", "WARN", ("gap 11d",))}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ())}
    suite = (
        ValidationPanelRow("monitor_impact", "FAIL", "2026-06-16T19:14:51+08:00",
                           ("magnitude_band_pass", "injection_resistance")),
        ValidationPanelRow("monitor_narrative", "UNKNOWN", "—", ("absent",)),
    )
    rows = build_panel_rows(sig, det, now="t", suite_rows=suite)
    assert [r.stage for r in rows] == [
        "monitor_signal", "monitor_impact", "monitor_narrative", "deterministic_scoring",
    ]
    impact = next(r for r in rows if r.stage == "monitor_impact")
    assert impact.status == "FAIL" and impact.ran_at == "2026-06-16T19:14:51+08:00"
    assert "magnitude_band_pass" in impact.reasons


def test_build_panel_rows_suite_rows_default_empty_is_backward_compatible():
    from irc.monitor.eval.types import StageHealth
    from irc.monitor.eval.determinism import build_panel_rows
    sig = {"A": StageHealth("monitor_signal", "PASS", ())}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ())}
    assert [r.stage for r in build_panel_rows(sig, det, now="t")] == [
        "monitor_signal", "deterministic_scoring",
    ]


def test_aggregate_unknown_status_does_not_raise():
    """aggregate_deterministic_health must not KeyError when a per-fund health
    carries a non-PASS/FAIL status (e.g. 'UNKNOWN'). _safe_status maps it to
    FAIL so worst_status never sees an unrecognised key."""
    from unittest.mock import patch
    from irc.monitor.eval.types import StageHealth as SH
    unknown_health = SH("deterministic_scoring", "UNKNOWN", ("synthetic",))
    clean = _record_signal(_clean_fund())
    traces = {"funds": {"AAA": clean}}
    with patch(
        "irc.monitor.eval.determinism.deterministic_health",
        return_value=unknown_health,
    ):
        agg = aggregate_deterministic_health(traces)
    # Must not raise; UNKNOWN is treated as FAIL, so aggregate is FAIL
    assert agg.status == "FAIL"


def test_validation_panel_row_is_frozen_dataclass():
    from irc.monitor.eval.types import ValidationPanelRow
    row = ValidationPanelRow(stage="monitor_signal", status="PASS",
                             ran_at="t", reasons=())
    assert row.stage == "monitor_signal" and row.status == "PASS"
    try:
        row.status = "FAIL"  # frozen → must raise
        raised = False
    except Exception:
        raised = True
    assert raised


# ── §5.E gap: flow_reconciliation + flow_coverage wired into panel (panel-only) ─


def test_build_panel_rows_includes_flow_rows_after_deterministic_scoring():
    """With non-empty flow_reconciliation_healths + flow_coverage_healths, both
    'flow_reconciliation' and 'flow_coverage' panel rows must appear AFTER
    'deterministic_scoring'."""
    from irc.monitor.eval.types import StageHealth
    from irc.monitor.eval.determinism import build_panel_rows
    sig = {"A": StageHealth("monitor_signal", "PASS", ())}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ())}
    recon = {"A": StageHealth("flow_reconciliation", "PASS", ())}
    cov = {"A": StageHealth("flow_coverage", "PASS", ("flow_cover 0.80",))}
    rows = build_panel_rows(sig, det, now="t",
                            flow_reconciliation_healths=recon,
                            flow_coverage_healths=cov)
    stages = [r.stage for r in rows]
    assert "flow_reconciliation" in stages
    assert "flow_coverage" in stages
    det_idx = stages.index("deterministic_scoring")
    assert stages.index("flow_reconciliation") > det_idx
    assert stages.index("flow_coverage") > det_idx


def test_build_panel_rows_flow_rows_carry_reasons():
    """flow_coverage row must surface the coverage reasons from the per-fund health."""
    from irc.monitor.eval.types import StageHealth
    from irc.monitor.eval.determinism import build_panel_rows
    sig = {"A": StageHealth("monitor_signal", "PASS", ())}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ())}
    recon = {"A": StageHealth("flow_reconciliation", "FAIL", ("board 0.3 != factor 0.5",))}
    cov = {"A": StageHealth("flow_coverage", "PASS", ("flow_cover 0.60", "pe_cover 0.40"))}
    rows = {r.stage: r for r in build_panel_rows(sig, det, now="t",
                                                  flow_reconciliation_healths=recon,
                                                  flow_coverage_healths=cov)}
    assert "board 0.3 != factor 0.5" in rows["flow_reconciliation"].reasons
    assert "flow_cover 0.60" in rows["flow_coverage"].reasons


def test_build_panel_rows_default_empty_flow_dicts_is_backward_compatible():
    """Default empty dicts → no flow rows; existing callers (no kwargs) stay green."""
    from irc.monitor.eval.types import StageHealth
    from irc.monitor.eval.determinism import build_panel_rows
    sig = {"A": StageHealth("monitor_signal", "PASS", ())}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ())}
    stages = [r.stage for r in build_panel_rows(sig, det, now="t")]
    assert "flow_reconciliation" not in stages
    assert "flow_coverage" not in stages


def test_flow_stages_not_in_gating_stages():
    """flow_reconciliation and flow_coverage must NEVER appear in GATING_STAGES_M0
    or GATING_STAGES_M1 — they are panel-only and must not affect apply_eval_gate."""
    from irc.monitor.eval.gate import GATING_STAGES_M0, GATING_STAGES_M1
    assert "flow_reconciliation" not in GATING_STAGES_M0
    assert "flow_reconciliation" not in GATING_STAGES_M1
    assert "flow_coverage" not in GATING_STAGES_M0
    assert "flow_coverage" not in GATING_STAGES_M1
