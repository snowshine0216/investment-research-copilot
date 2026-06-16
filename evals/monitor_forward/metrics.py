"""PURE: forward rows (+ retro points) -> three MetricReport rows + details dict.
Status ladder applied here (manual WARN; thresholds documentation-only, never
fail_below). details schema is per-metric (§5.3): hit-rate rows carry
random/momentum/buy_hold; rank_ic carries random ONLY."""
from __future__ import annotations
from collections import defaultdict
from typing import Sequence
from evals._shared.report_schema import MetricReport
from irc.monitor.eval.constants import (
    N_MIN_BLOCKS, MIN_CROSS, MIN_DEFINED_DAYS, BOOTSTRAP_B,
)
from irc.monitor.eval.forward_score import ForwardRow
from irc.monitor.eval.stats import (
    sign, bias_to_sign, hit_rate, spearman_ic, effective_n, block_bootstrap_ci,
)
from irc.monitor.eval.baselines import (
    buy_hold_dir, random_null_delta,
)

# direction is higher_is_better for all three; thresholds are documentation-only
_HIT_TH: dict[str, float] = {}      # NO fail_below — WARN set manually
_IC_TH: dict[str, float] = {}


def _composite_rows(rows: Sequence[ForwardRow]) -> list[dict]:
    return [{"run_date": r.run_date, "fund_id": r.fund_id,
             "pred": sign(r.raw_composite), "label": sign(r.raw_composite),
             "fwd": r.fwd_ret} for r in rows]


def _bias_rows(rows: Sequence[ForwardRow]) -> tuple[list[dict], dict[str, int]]:
    out = []
    excl: dict[str, int] = {}
    for r in rows:
        if r.raw_status != "ok" or r.raw_bias is None:
            continue
        try:
            s = bias_to_sign(r.raw_bias)
        except KeyError:
            excl["unknown_bias"] = excl.get("unknown_bias", 0) + 1
            continue
        out.append({"run_date": r.run_date, "fund_id": r.fund_id,
                    "pred": s, "label": s, "fwd": r.fwd_ret})
    return out, excl


def _buy_hold_delta(prepared: list[dict], signal_value: float) -> dict:
    bh = hit_rate([buy_hold_dir() for _ in prepared], [r["fwd"] for r in prepared])
    return {"delta": signal_value - bh, "ci_low": signal_value - bh,
            "ci_high": signal_value - bh}


def _hit_rate_report(name: str, prepared: list[dict], *, seed: int) -> tuple[MetricReport, dict]:
    value = hit_rate([r["pred"] for r in prepared], [r["fwd"] for r in prepared])
    eff_n = effective_n(prepared)
    stat = lambda rs: hit_rate([r["label"] for r in rs], [r["fwd"] for r in rs])  # noqa: E731
    ci = block_bootstrap_ci(prepared, stat, seed=seed, b=BOOTSTRAP_B)
    rnd = random_null_delta(prepared, metric=stat, label_key="label",
                            signal_value=value, seed=seed + 1, b=BOOTSTRAP_B)
    if eff_n < N_MIN_BLOCKS:
        state, status = "insufficient_data", "WARN"
    elif rnd.get("delta") is not None and rnd.get("ci_low", -1) > 0:
        state, status = "ok", "PASS"
    else:
        state, status = "ok", "WARN"
    details = {
        "value": value, "ci_low": ci[0], "ci_high": ci[1],
        "baseline_deltas": {"random": rnd, "momentum": {"state": "baseline_unavailable"},
                            "buy_hold": _buy_hold_delta(prepared, value)},
        "effective_n": eff_n, "excluded": {}, "state": state,
    }
    rep = MetricReport(name=name, value=value, status=status,
                       n_observations=eff_n, threshold=_HIT_TH,
                       details_ref=None)
    return rep, details


def _ic_report(rows: Sequence[ForwardRow], *, seed: int) -> tuple[MetricReport, dict]:
    by_day: dict[str, list[ForwardRow]] = defaultdict(list)
    for r in rows:
        if r.raw_status == "ok":
            by_day[r.run_date].append(r)
    day_ics: list[float] = []
    for _day, grp in by_day.items():
        if len(grp) < MIN_CROSS:
            continue
        ic = spearman_ic([g.raw_composite for g in grp], [g.fwd_ret for g in grp])
        if ic is not None:
            day_ics.append(ic)
    defined = len(day_ics)
    value = sum(day_ics) / defined if defined else 0.0
    if defined == 0:
        state, status = "undefined", "WARN"
    elif defined < MIN_DEFINED_DAYS:
        state, status = "insufficient_data", "WARN"
    else:
        state, status = "ok", "PASS"
    comp_rows = _composite_rows(rows)
    details = {
        "value": value, "ci_low": value, "ci_high": value,
        "baseline_deltas": {"random": {"state": "insufficient_data"}},
        "defined_day_count": defined, "effective_n": effective_n(comp_rows),
        "excluded": {}, "state": state,
    }
    rep = MetricReport(name="rank_ic", value=value, status=status,
                       n_observations=defined, threshold=_IC_TH, details_ref=None)
    return rep, details


def build_metric_reports(
    *, forward_rows: Sequence[ForwardRow], retro_points: Sequence, seed: int,
) -> tuple[list[MetricReport], dict]:
    comp = _composite_rows(forward_rows)
    bias, bias_excl = _bias_rows(forward_rows)
    r_comp, d_comp = _hit_rate_report("raw_composite_directional", comp, seed=seed)
    r_bias, d_bias = _hit_rate_report("publishable_bias_directional", bias, seed=seed + 10)
    if bias_excl:
        d_bias["excluded"] = {**d_bias.get("excluded", {}), **bias_excl}
    r_ic, d_ic = _ic_report(forward_rows, seed=seed + 20)
    details = {
        "raw_composite_directional": d_comp,
        "publishable_bias_directional": d_bias,
        "rank_ic": d_ic,
    }
    return [r_comp, r_bias, r_ic], details
