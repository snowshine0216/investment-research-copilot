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
    mean_bootstrap_ci,
)
from irc.monitor.eval.baselines import (
    buy_hold_dir, random_null_delta,
)

_RETRO_LABEL = (
    "evidence-free core (retro) — directionally analogous, not directly comparable"
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


def _retro_details(retro_points: Sequence) -> dict:
    """Build the retro sub-block for raw_composite_directional details (§4.1)."""
    if not retro_points:
        return {"state": "insufficient_data", "n": 0, "label": _RETRO_LABEL}
    preds = [sign(p.composite) for p in retro_points]
    fwds = [p.fwd_ret for p in retro_points]
    # count only non-zero fwd_ret (same as hit_rate exclusion)
    scored = [(p, f) for p, f in zip(preds, fwds) if sign(f) != 0]
    value = hit_rate(preds, fwds)
    return {"value": value, "n": len(scored), "label": _RETRO_LABEL}


def _buy_hold_delta_paired(prepared: list[dict], signal_value: float, *, seed: int) -> dict:
    """Paired block bootstrap CI for buy_hold delta (spec §4.4)."""
    # freeze the buy_hold baseline ONCE so the point estimate and the bootstrap CI
    # use the same per-row baseline values (robust if buy_hold_dir ever varies).
    bh_rows = [{**r, "bh": buy_hold_dir()} for r in prepared]
    bh_value = hit_rate([r["bh"] for r in bh_rows], [r["fwd"] for r in bh_rows])
    delta = signal_value - bh_value
    # paired bootstrap: resample buckets together, compute delta for each resample
    def _bh_stat(rs: Sequence[dict]) -> float:
        return (hit_rate([r["label"] for r in rs], [r["fwd"] for r in rs])
                - hit_rate([r["bh"] for r in rs], [r["fwd"] for r in rs]))
    ci = block_bootstrap_ci(bh_rows, _bh_stat, seed=seed, b=BOOTSTRAP_B)
    return {"delta": delta, "ci_low": ci[0], "ci_high": ci[1]}


def _momentum_delta(
    prepared: list[dict],
    momentum_by_key: dict,
    signal_value: float,
    *,
    seed: int,
) -> tuple[dict, int]:
    """Compute momentum paired delta; return (baseline_entry, momentum_undefined_count).

    Rows with undefined momentum (None) are excluded from the paired population
    but still counted in the signal's own value. Survivors spanning < N_MIN_BLOCKS
    run-date blocks → state='baseline_unavailable'."""
    defined = []
    undefined_count = 0
    for r in prepared:
        mom = momentum_by_key.get((r["run_date"], r["fund_id"]))
        if mom is None:
            undefined_count += 1
        else:
            defined.append({**r, "mom": mom})
    if not defined or effective_n(defined) < N_MIN_BLOCKS:
        return {"state": "baseline_unavailable"}, undefined_count
    mom_base = hit_rate([r["mom"] for r in defined], [r["fwd"] for r in defined])
    mom_sig = hit_rate([r["pred"] for r in defined], [r["fwd"] for r in defined])
    delta = mom_sig - mom_base

    def _paired_delta(rs: Sequence[dict]) -> float:
        return (hit_rate([r["label"] for r in rs], [r["fwd"] for r in rs])
                - hit_rate([r["mom"] for r in rs], [r["fwd"] for r in rs]))

    ci = block_bootstrap_ci(defined, _paired_delta, seed=seed, b=BOOTSTRAP_B)
    return {"delta": delta, "ci_low": ci[0], "ci_high": ci[1]}, undefined_count


def _hit_rate_report(
    name: str, prepared: list[dict], *,
    seed: int,
    momentum_by_key: dict | None = None,
) -> tuple[MetricReport, dict]:
    value = hit_rate([r["pred"] for r in prepared], [r["fwd"] for r in prepared])
    eff_n = effective_n(prepared)
    stat = lambda rs: hit_rate([r["label"] for r in rs], [r["fwd"] for r in rs])  # noqa: E731
    ci = block_bootstrap_ci(prepared, stat, seed=seed, b=BOOTSTRAP_B)
    rnd = random_null_delta(prepared, metric=stat, label_key="label",
                            signal_value=value, seed=seed + 1, b=BOOTSTRAP_B)
    bh = _buy_hold_delta_paired(prepared, value, seed=seed + 3)
    mbk = momentum_by_key or {}
    mom, mom_undef = _momentum_delta(prepared, mbk, value, seed=seed + 2)
    if eff_n < N_MIN_BLOCKS:
        state, status = "insufficient_data", "WARN"
    elif rnd.get("delta") is not None and rnd.get("ci_low", -1) > 0:
        state, status = "ok", "PASS"
    else:
        state, status = "ok", "WARN"
    excl: dict[str, int] = {}
    if mom_undef:
        excl["momentum_undefined"] = mom_undef
    details = {
        "value": value, "ci_low": ci[0], "ci_high": ci[1],
        "baseline_deltas": {"random": rnd, "momentum": mom, "buy_hold": bh},
        "effective_n": eff_n, "excluded": excl, "state": state,
    }
    rep = MetricReport(name=name, value=value, status=status,
                       n_observations=eff_n, threshold=_HIT_TH,
                       details_ref=None)
    return rep, details


def _avg_day_ic(rows: Sequence[dict]) -> float:
    """Time-averaged cross-sectional Spearman IC over DEFINED days (>= MIN_CROSS
    funds, non-constant signal & return ranks). Empty → 0.0. This single definition
    is shared by the observed point estimate AND the permuted statistic in the IC
    random null, so the null is the metric under test (§4.4)."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_day[r["run_date"]].append(r)
    ics = []
    for grp in by_day.values():
        if len(grp) < MIN_CROSS:
            continue
        ic = spearman_ic([r["sig"] for r in grp], [r["fwd"] for r in grp])
        if ic is not None:
            ics.append(ic)
    return sum(ics) / len(ics) if ics else 0.0


def _ic_day_breakdown(rows: Sequence[ForwardRow]) -> tuple[list[float], list[dict]]:
    """ok rows → (per-day IC over defined days, defined-day rows as permutation-ready
    {run_date, sig, fwd} dicts). Population is raw_status=='ok' rows scored on
    raw_composite, NEUTRAL composites included (§4.2)."""
    by_day: dict[str, list[ForwardRow]] = defaultdict(list)
    for r in rows:
        if r.raw_status == "ok":
            by_day[r.run_date].append(r)
    day_ics: list[float] = []
    defined_rows: list[dict] = []
    for day, grp in by_day.items():
        if len(grp) < MIN_CROSS:
            continue
        ic = spearman_ic([g.raw_composite for g in grp], [g.fwd_ret for g in grp])
        if ic is None:
            continue
        day_ics.append(ic)
        defined_rows.extend(
            {"run_date": day, "sig": g.raw_composite, "fwd": g.fwd_ret} for g in grp)
    return day_ics, defined_rows


def _ic_ci_status(day_ics, defined_rows, value, defined, *, seed):
    """Own CI (bootstrap over defined days) + random permutation-null delta +
    status ladder (§4.2). A real CI is reported ONLY at defined >= MIN_DEFINED_DAYS
    (the statistically-reportable threshold); below that ci=None ('CI pending') and
    the random baseline stays insufficient_data. Returns (ci_low, ci_high, rnd,
    state, status). WARN-max: never FAIL for statistical weakness."""
    if defined < MIN_DEFINED_DAYS:
        state = "undefined" if defined == 0 else "insufficient_data"
        return None, None, {"state": "insufficient_data"}, state, "WARN"
    ci_low, ci_high = mean_bootstrap_ci(day_ics, seed=seed, b=BOOTSTRAP_B)
    rnd = random_null_delta(defined_rows, metric=_avg_day_ic, label_key="sig",
                            signal_value=value, seed=seed + 1, b=BOOTSTRAP_B)
    passed = rnd.get("delta") is not None and rnd.get("ci_low", -1) > 0
    return ci_low, ci_high, rnd, "ok", ("PASS" if passed else "WARN")


def _ic_report(rows: Sequence[ForwardRow], *, seed: int) -> tuple[MetricReport, dict]:
    day_ics, defined_rows = _ic_day_breakdown(rows)
    defined = len(day_ics)
    value = sum(day_ics) / defined if defined else 0.0
    # nit #2: effective_n is the block span of the ok-status IC population, NOT
    # all-status rows — aligned to the population the IC is computed over (§4.2).
    eff_n = effective_n([{"run_date": r.run_date} for r in rows if r.raw_status == "ok"])
    ci_low, ci_high, rnd, state, status = _ic_ci_status(
        day_ics, defined_rows, value, defined, seed=seed)
    details = {
        "value": value, "ci_low": ci_low, "ci_high": ci_high,
        "baseline_deltas": {"random": rnd},
        "defined_day_count": defined, "effective_n": eff_n,
        "excluded": {}, "state": state,
    }
    rep = MetricReport(name="rank_ic", value=value, status=status,
                       n_observations=defined, threshold=_IC_TH, details_ref=None)
    return rep, details


def build_metric_reports(
    *, forward_rows: Sequence[ForwardRow], retro_points: Sequence, seed: int,
    momentum_by_key: dict | None = None,
) -> tuple[list[MetricReport], dict]:
    comp = _composite_rows(forward_rows)
    bias, bias_excl = _bias_rows(forward_rows)
    mbk = momentum_by_key or {}
    r_comp, d_comp = _hit_rate_report("raw_composite_directional", comp,
                                      seed=seed, momentum_by_key=mbk)
    r_bias, d_bias = _hit_rate_report("publishable_bias_directional", bias,
                                      seed=seed + 10, momentum_by_key=mbk)
    if bias_excl:
        d_bias["excluded"] = {**d_bias.get("excluded", {}), **bias_excl}
    r_ic, d_ic = _ic_report(forward_rows, seed=seed + 20)
    # Wire retro sub-block into raw_composite_directional details (§4.1)
    d_comp["retro"] = _retro_details(retro_points)
    details = {
        "raw_composite_directional": d_comp,
        "publishable_bias_directional": d_bias,
        "rank_ic": d_ic,
    }
    return [r_comp, r_bias, r_ic], details
