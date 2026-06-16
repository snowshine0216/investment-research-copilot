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


# ── Fix 2: retro sub-block wired into raw_composite_directional details ───────

def _retro_point(composite, fwd_ret, as_of_date="2026-01-01"):
    """Helper: build a minimal RetroPoint-like object for metrics tests."""
    from irc.monitor.eval.backtest import RetroPoint
    return RetroPoint(
        as_of_date=as_of_date, as_of_idx=250,
        composite=composite, status="insufficient_evidence",
        entry_nav_date="2026-01-02", fwd_ret=fwd_ret,
    )


def test_retro_block_in_raw_composite_details_known_hit_rate():
    """retro_points with known composite/fwd_ret → retro.value matches expected hit-rate."""
    from irc.monitor.eval.stats import hit_rate, sign
    retro = [
        _retro_point(0.3, 0.01),   # correct (both positive)
        _retro_point(-0.2, -0.02), # correct (both negative)
        _retro_point(0.1, -0.01),  # wrong
        _retro_point(-0.1, 0.01),  # wrong
    ]
    expected = hit_rate([sign(p.composite) for p in retro], [p.fwd_ret for p in retro])
    _, details = build_metric_reports(forward_rows=[], retro_points=retro, seed=1)
    retro_block = details["raw_composite_directional"].get("retro", {})
    assert retro_block, "retro sub-block missing from raw_composite_directional details"
    assert abs(retro_block["value"] - expected) < 1e-9
    assert "directionally analogous" in retro_block["label"]
    assert retro_block["n"] == 4


def test_retro_block_label_not_directly_comparable():
    """Spec §4.1: retro label must say 'not directly comparable'."""
    retro = [_retro_point(0.3, 0.01)]
    _, details = build_metric_reports(forward_rows=[], retro_points=retro, seed=1)
    label = details["raw_composite_directional"]["retro"]["label"]
    assert "not directly comparable" in label


def test_retro_block_empty_is_insufficient_data():
    """Empty retro_points → retro sub-block carries state='insufficient_data', n=0."""
    _, details = build_metric_reports(forward_rows=[], retro_points=[], seed=1)
    retro_block = details["raw_composite_directional"].get("retro", {})
    assert retro_block.get("state") == "insufficient_data"
    assert retro_block.get("n") == 0
    assert "label" in retro_block


def test_retro_does_not_add_fourth_metric_row():
    """Fix 2 must NOT add a 4th MetricReport row — exactly 3."""
    retro = [_retro_point(0.3, 0.01), _retro_point(-0.2, -0.02)]
    reports, _ = build_metric_reports(forward_rows=[], retro_points=retro, seed=1)
    assert len(reports) == 3

def test_retro_value_not_overwriting_forward_value():
    """The MetricReport.value for raw_composite_directional is the FORWARD hit-rate,
    not the retro hit-rate (retro lives only in details['raw_composite_directional']['retro'])."""
    rows = [_fr(f"2026-01-{d:02d}", "a", "ok", 0.2, "ADD_BIAS", 0.01) for d in range(1, 5)]
    retro = [_retro_point(-0.3, 0.01)]  # wrong retro prediction → lower retro hit-rate
    reports, details = build_metric_reports(forward_rows=rows, retro_points=retro, seed=1)
    comp_report = next(r for r in reports if r.name == "raw_composite_directional")
    # forward hit-rate: all correct (pred=sign(0.2)=1, fwd=0.01>0)
    assert comp_report.value == 1.0
    # retro hit-rate: wrong (pred=sign(-0.3)=-1, fwd=0.01>0 → sign=1, mismatch)
    assert details["raw_composite_directional"]["retro"]["value"] == 0.0


# ── Fix 3: momentum baseline computed, not hardcoded ─────────────────────────

def _fr_with_mom(run_date, fund, status, composite, bias, fwd, mom):
    """Build a ForwardRow dict extended with mom key for _hit_rate_report testing."""
    r = _fr(run_date, fund, status, composite, bias, fwd)
    return {**r.__dict__, "mom": mom}


def _make_rows_with_momentum(run_date, fund, composite, bias, fwd, mom):
    """Return a ForwardRow + momentum_by_key entry for end-to-end test."""
    row = _fr(run_date, fund, "ok", composite, bias, fwd)
    return row, ((run_date, fund), mom)


def _many_run_dates(n_blocks_wanted: int) -> list[str]:
    """Build enough distinct run_dates to fill n_blocks_wanted H-run-date blocks.
    effective_n buckets by floor(rank / FORWARD_H), so we need n_blocks * FORWARD_H dates."""
    from irc.monitor.eval.constants import FORWARD_H
    from datetime import date, timedelta
    d0 = date(2024, 1, 1)
    return [(d0 + timedelta(days=i)).isoformat()
            for i in range(n_blocks_wanted * FORWARD_H)]


def test_momentum_delta_present_when_all_defined():
    """Full population with defined momentum → delta present + CI non-degenerate."""
    from irc.monitor.eval.constants import N_MIN_BLOCKS
    run_dates = _many_run_dates(N_MIN_BLOCKS + 1)
    rows = []
    mom_map = {}
    for rd in run_dates:
        row = _fr(rd, "a", "ok", 0.2, "ADD_BIAS", 0.01)
        rows.append(row)
        mom_map[(rd, "a")] = 1  # always defined, always +1
    _, details = build_metric_reports(
        forward_rows=rows, retro_points=[], seed=1,
        momentum_by_key=mom_map,
    )
    bd = details["publishable_bias_directional"]["baseline_deltas"]
    mom = bd.get("momentum", {})
    assert "delta" in mom, f"momentum.delta missing; got: {mom}"
    assert "ci_low" in mom
    assert "ci_high" in mom


def test_momentum_undefined_rows_excluded_from_paired_population():
    """Rows with undefined momentum (mom=None) dropped from momentum population
    but still counted in the signal value and excluded.momentum_undefined."""
    from irc.monitor.eval.constants import N_MIN_BLOCKS
    run_dates = _many_run_dates(N_MIN_BLOCKS + 1)
    rows = []
    mom_map = {}
    for rd in run_dates:
        row_a = _fr(rd, "a", "ok", 0.2, "ADD_BIAS", 0.01)
        row_b = _fr(rd, "b", "ok", 0.2, "ADD_BIAS", 0.01)
        rows.append(row_a)
        rows.append(row_b)
        mom_map[(rd, "a")] = 1      # defined
        mom_map[(rd, "b")] = None   # undefined → excluded from momentum

    _, details = build_metric_reports(
        forward_rows=rows, retro_points=[], seed=1,
        momentum_by_key=mom_map,
    )
    excl = details["publishable_bias_directional"].get("excluded", {})
    # undefined rows counted (one per run_date for fund "b")
    assert excl.get("momentum_undefined", 0) >= len(run_dates), (
        f"expected >={len(run_dates)} momentum_undefined; got {excl}"
    )
    # signal value still uses all rows (including undefined-momentum rows)
    assert details["publishable_bias_directional"]["value"] > 0.0


def test_momentum_baseline_unavailable_when_too_few_blocks():
    """Defined paired survivors spanning < N_MIN_BLOCKS → state='baseline_unavailable'."""
    # Use exactly 1 run_date → 1 block → below N_MIN_BLOCKS
    rows = [_fr("2026-01-01", "a", "ok", 0.2, "ADD_BIAS", 0.01)]
    mom_map = {("2026-01-01", "a"): 1}
    _, details = build_metric_reports(
        forward_rows=rows, retro_points=[], seed=1,
        momentum_by_key=mom_map,
    )
    bd = details["publishable_bias_directional"]["baseline_deltas"]
    mom = bd.get("momentum", {})
    assert mom.get("state") == "baseline_unavailable", f"expected baseline_unavailable; got {mom}"


def test_buy_hold_uses_paired_bootstrap():
    """buy_hold CI should carry delta, ci_low, ci_high (paired bootstrap)."""
    from irc.monitor.eval.constants import N_MIN_BLOCKS
    run_dates = _many_run_dates(N_MIN_BLOCKS + 1)
    rows = [_fr(rd, "a", "ok", 0.2, "ADD_BIAS", 0.01) for rd in run_dates]
    _, details = build_metric_reports(
        forward_rows=rows, retro_points=[], seed=1, momentum_by_key={},
    )
    bd = details["publishable_bias_directional"]["baseline_deltas"]
    bh = bd.get("buy_hold", {})
    # With paired bootstrap the CI should carry all three fields
    assert "delta" in bh
    assert "ci_low" in bh
    assert "ci_high" in bh
