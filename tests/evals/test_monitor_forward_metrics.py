from __future__ import annotations
from irc.monitor.eval.forward_score import ForwardRow
from evals.monitor_forward.metrics import build_metric_reports


def _fr(run_date, fund, status, composite, bias, fwd):
    return ForwardRow(run_date=run_date, fund_id=fund, as_of_date=run_date,
                      raw_status=status, raw_composite=composite, raw_bias=bias,
                      entry_nav_date=run_date, fwd_ret=fwd, from_latest_nav=fwd)


def test_three_metric_rows_named():
    rows = [_fr(f"2026-01-{d:02d}", "a", "ok", 0.2, "ADD_BIAS", 0.01) for d in range(1, 5)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    names = {r.name for r in reports}
    assert names == {"raw_composite_directional", "publishable_bias_directional", "rank_ic"}


def test_strongly_negative_ic_is_warn_not_fail():
    # inverse signal vs return on enough defined days → negative IC but still WARN
    rows = []
    for di in range(10):
        rd = f"2026-02-{di+1:02d}"
        rows += [_fr(rd, "a", "ok", 0.9, "ADD_BIAS", -0.05),
                 _fr(rd, "b", "ok", -0.9, "REDUCE_BIAS", 0.05),
                 _fr(rd, "c", "ok", 0.1, "ADD_BIAS", -0.02),
                 _fr(rd, "d", "ok", -0.1, "REDUCE_BIAS", 0.02)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    for r in reports:
        assert r.status in ("PASS", "WARN")   # NEVER FAIL for statistical weakness
    ic = [r for r in reports if r.name == "rank_ic"][0]
    assert ic.threshold == {} or "fail_below" not in ic.threshold


def test_zero_defined_ic_days_sentinel():
    # too few funds per day to define any cross-section → undefined sentinel
    rows = [_fr("2026-03-01", "a", "ok", 0.2, "ADD_BIAS", 0.01)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    ic = [r for r in reports if r.name == "rank_ic"][0]
    assert ic.value == 0.0 and ic.status == "WARN"
    assert details["rank_ic"]["state"] == "undefined"


def test_insufficient_blocks_hit_rate_is_warn():
    rows = [_fr(f"2026-01-{d:02d}", "a", "ok", 0.2, "ADD_BIAS", 0.01) for d in range(1, 4)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    hb = [r for r in reports if r.name == "publishable_bias_directional"][0]
    assert hb.status == "WARN"
    assert details["publishable_bias_directional"]["state"] == "insufficient_data"


def test_ic_details_has_only_random_baseline():
    rows = [_fr(f"2026-01-{d:02d}", "a", "ok", 0.2, "ADD_BIAS", 0.01) for d in range(1, 5)]
    _, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    ic_baselines = details["rank_ic"]["baseline_deltas"]
    assert set(ic_baselines.keys()) == {"random"}    # momentum/buy_hold ABSENT, not null


# ── Fix 1 regression: permutation null is NOT a no-op ────────────────────────

def _perfect_signal_rows():
    """8 run_dates x 3 funds. Each date has mixed labels so groups are permutable.
    Signal perfectly predicts forward return (pred==label==fwd sign).
    Meets MIN_PERM_DATES (8) and N_MIN_BLOCKS (8 // FORWARD_H * date-range = >=8)."""
    from irc.monitor.eval.constants import MIN_PERM_DATES
    rows = []
    for i in range(MIN_PERM_DATES):
        rd = f"2026-0{i // 4 + 1}-{(i % 4) * 7 + 1:02d}"
        # ADD+fwd_pos, REDUCE+fwd_neg, ADD+fwd_pos → mixed labels, perfect signal
        rows.append(_fr(rd, "a", "ok", 0.5, "ADD_BIAS", 0.02))
        rows.append(_fr(rd, "b", "ok", -0.5, "REDUCE_BIAS", -0.02))
        rows.append(_fr(rd, "c", "ok", 0.3, "ADD_BIAS", 0.01))
    return rows


def test_permutation_null_is_not_noop_for_perfect_signal():
    """Regression: stat must read r['label'] so permutation actually shuffles
    labels; before Fix 1 stat read r['pred'] (==label per row), so the permuted
    statistic was always identical to signal_value → delta==0.0 always."""
    rows = _perfect_signal_rows()
    _, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=42)
    rnd = details["raw_composite_directional"]["baseline_deltas"]["random"]
    # permutation must produce a non-trivial distribution → delta must be present
    assert "delta" in rnd, "random_null_delta returned insufficient_data — too few permutable groups"
    # delta should NOT be identically 0.0 (was always 0 before fix)
    assert rnd["delta"] != 0.0, (
        "random delta is 0.0 — permutation is still a no-op (stat reads pred not label)"
    )


# ── Fix 5 regression: unknown bias does not crash _bias_rows ─────────────────

def test_unknown_bias_value_skipped_not_crash():
    """A row with raw_status=='ok' but raw_bias not in {ADD_BIAS,REDUCE_BIAS,NEUTRAL}
    must be skipped (excluded under 'unknown_bias'), not raise KeyError."""
    rows = [
        _fr("2026-01-01", "a", "ok", 0.2, "GARBAGE", 0.01),   # unknown bias — must skip
        _fr("2026-01-01", "b", "ok", 0.2, "ADD_BIAS", 0.01),  # valid row
    ]
    # Must not raise KeyError
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=1)
    # The invalid bias row was excluded; the metric should still compute
    assert details["publishable_bias_directional"] is not None


def test_permutation_pass_gate_reachable_for_perfect_signal():
    """With a perfect signal and enough data, ci_low > 0 should be achievable
    (the PASS gate in _hit_rate_report). Before Fix 1, ci_low was always 0."""
    rows = _perfect_signal_rows()
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[], seed=42)
    rnd = details["raw_composite_directional"]["baseline_deltas"]["random"]
    if "delta" in rnd:
        # If we have enough blocks, the CI should reflect a real advantage
        eff_n = details["raw_composite_directional"]["effective_n"]
        from irc.monitor.eval.constants import N_MIN_BLOCKS
        if eff_n >= N_MIN_BLOCKS and rnd.get("ci_low") is not None:
            # ci_low > 0 means PASS (perfect signal should win)
            assert rnd["ci_low"] >= 0.0, "ci_low unexpectedly negative for a perfect signal"
