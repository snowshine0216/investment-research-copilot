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
