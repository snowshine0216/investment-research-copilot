"""PURE per-fund in-run structural health over the eval_trace projection.
ADR 0017 §3.3: no I/O, no AkShare/LLM/settings imports."""
from __future__ import annotations
import math
from datetime import date
from irc.monitor.eval.types import StageHealth
from evals._shared.status import worst_status

_EPS = 1e-9
_COMPOSITE_DP = 4   # composite is round(Σcontribution, 4) — see signal.py / types.py
# Tolerate routine CN minor-holiday closures (Labour Day / Dragon Boat / New Year ≈
# ≤7 cal days). The two big closures (Spring Festival, National Day ≈ 11d) still WARN
# if they land inside the recent gap window (trace._RECENT_GAP_WINDOW) — a rare, brief
# residual, not the former permanent caveat. See ADR 0018.
_WARN_GAP_DAYS = 8
# Calendar-grounded gap rule (spec §3.3): WARN only when the fund missed >=2
# consecutive SSE-open trading days (a single isolated miss is a transient
# publish/AkShare glitch, tolerated). _WARN_GAP_DAYS above survives only as the
# degraded fallback when the calendar is unavailable. See ADR 0018 D3.
_MISSING_TRADING_WARN = 2


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def signal_consistency(t: dict) -> StageHealth:
    sig = t["signal"]
    contribs = sig.get("contributions", [])
    reasons: list[str] = []
    # A truncated/malformed signal block must FAIL, not silently default a missing
    # numeric key to 0.0 (which can coincidentally satisfy the equality checks).
    if "composite" not in sig:
        reasons.append("missing composite")
    if any("contribution" not in c for c in contribs):
        reasons.append("missing contribution key")
    composite = sig.get("composite", 0.0)
    contrib_values = [c.get("contribution", 0.0) for c in contribs]
    # NaN/±inf (e.g. inf-cancelling contributions → NaN sum) make `abs(nan - x) >= eps`
    # vacuously False → a silent PASS. Guard explicitly before the equality check.
    if not math.isfinite(composite) or any(not math.isfinite(v) for v in contrib_values):
        reasons.append("non-finite composite/contribution")
    else:
        # composite is round(Σcontribution, 4) by contract (signal.py / types.py:
        # "C, rounded 4dp") while contributions stay full-precision — compare there.
        sum_contrib = round(sum(contrib_values), _COMPOSITE_DP)
        if abs(composite - sum_contrib) >= _EPS:
            reasons.append("composite != Σcontribution")
    # Compare Σrenorm_weight at the same 4dp precision as composite (a ~1e-16 renorm
    # artifact must not FAIL; a real off-by-1e-4 normalization still does).
    sum_renorm = round(sum(c.get("renorm_weight", 0.0) for c in contribs), _COMPOSITE_DP)
    if contribs and abs(sum_renorm - 1.0) >= _EPS:
        reasons.append("Σrenorm_weight != 1")
    bias_none = sig.get("bias") is None
    status_ok = sig.get("status") == "ok"
    if bias_none == status_ok:
        reasons.append("bias-None must hold iff status != ok")
    status = "FAIL" if reasons else "PASS"
    return StageHealth(stage="signal_consistency", status=status, reasons=tuple(reasons))


def _pool_ids(t: dict) -> set[str]:
    return {e.get("citation_id") for e in t.get("evidence_pool", [])}


def _claim_ids(t: dict) -> list[str]:
    narr = t.get("narrative", {})
    ids: list[str] = []
    for field in ("price_action", "signal_rationale", "risk"):
        for claim in narr.get(field, []):
            ids.extend(claim.get("citation_ids", ()))
    for leg in ("macro", "constituent"):
        for imp in t.get("impacts", {}).get(leg, []):
            ids.extend(imp.get("citation_ids", ()))
    return ids


def citation_integrity(t: dict) -> StageHealth:
    pool = _pool_ids(t)
    unresolved = [cid for cid in _claim_ids(t) if cid not in pool]
    if unresolved:
        return StageHealth("citation_integrity", "FAIL", (f"unresolved: {unresolved[0]}",))
    return StageHealth("citation_integrity", "PASS", ())


def nav_quality(
    t: dict, *, minimum_observations: int, stale_days: int, today: date | None = None,
) -> StageHealth:
    nav = t["nav"]
    obs = nav.get("obs_count", 0)
    as_of = nav.get("as_of_date", "N/A")
    if obs == 0 or nav.get("nav_acc") is None or as_of == "N/A":
        return StageHealth("nav_quality", "FAIL", ("missing NAV",))
    if obs < minimum_observations:
        return StageHealth("nav_quality", "FAIL", (f"obs<{minimum_observations}",))
    parsed = _parse_date(as_of)
    _today = today if today is not None else date.today()
    if parsed is not None and (_today - parsed).days > stale_days:
        return StageHealth("nav_quality", "FAIL", (f"as_of older than {stale_days}d",))
    missing = nav.get("missing_trading_days")
    gap = nav.get("max_gap_days")
    if missing is not None:
        if missing >= _MISSING_TRADING_WARN:
            return StageHealth("nav_quality", "WARN", (f"missed {missing} trading days",))
        return StageHealth("nav_quality", "PASS", ())
    if gap is not None and gap > _WARN_GAP_DAYS:
        return StageHealth("nav_quality", "WARN", (f"gap {gap}d",))
    return StageHealth("nav_quality", "PASS", ())


def monitor_signal_health(
    t: dict, *, minimum_observations: int, stale_days: int, today: date | None = None,
) -> StageHealth:
    parts = (
        signal_consistency(t),
        citation_integrity(t),
        nav_quality(t, minimum_observations=minimum_observations, stale_days=stale_days,
                    today=today),
    )
    overall = worst_status([p.status for p in parts])  # only PASS/WARN/FAIL here (no UNKNOWN)
    reasons = tuple(r for p in parts for r in p.reasons)
    return StageHealth(stage="monitor_signal", status=overall, reasons=reasons)


def _board_flow_value(rows: list[dict]) -> float | None:
    covered = [r for r in rows if r.get("flow_score") is not None]
    cw = sum(r["weight_pct"] for r in covered)
    if cw <= 0.0:
        return None
    return sum(r["weight_pct"] * r["flow_score"] for r in covered) / cw


def _flow_factor_value(t: dict) -> float | None:
    for c in t.get("signal", {}).get("contributions", []):
        if c.get("name") == "flow":
            return c.get("value")
    return None


def flow_reconciliation(t: dict) -> StageHealth:
    """PURE: the board's Σ(wᵢ·sᵢ)/Σ(wᵢ) over covered rows must equal the flow factor
    value (4dp). No flow contribution → nothing to reconcile → PASS (§5.E).
    Panel-only — NOT added to any GATING_STAGES list (mirrors deterministic_health)."""
    factor_value = _flow_factor_value(t)
    if factor_value is None:
        return StageHealth("flow_reconciliation", "PASS", ())
    board_value = _board_flow_value(t.get("holding_metrics", {}).get("rows", []))
    if board_value is None or abs(round(board_value, 4) - round(factor_value, 4)) >= _EPS:
        return StageHealth("flow_reconciliation", "FAIL",
                           (f"board {board_value} != factor {factor_value}",))
    return StageHealth("flow_reconciliation", "PASS", ())


def flow_coverage_health(t: dict) -> StageHealth:
    """PURE informational coverage tally over holding_metrics (§5.E, panel-only).
    Status always PASS — observability, never a gate. Surfaces:
      flow_cover <ratio>  — from aggregate.covered_weight_ratio or row-fraction fallback.
      pe_cover <ratio>    — fraction of rows with pe_percentile not None.
      flow_no_data <n>    — count of rows where flow_reason == 'flow_no_data'.
      flow_no_coverage <0|1> — 1 when aggregate.reason == 'flow_no_coverage'.
    Empty/missing holding_metrics → PASS with no reasons, never raises."""
    hm = t.get("holding_metrics") or {}
    rows = hm.get("rows") or []
    agg = hm.get("aggregate") or {}
    if not rows and not agg:
        return StageHealth("flow_coverage", "PASS", ())
    n = len(rows)
    ratio = agg.get("covered_weight_ratio")
    if ratio is None and n > 0:
        ratio = sum(1 for r in rows if r.get("flow_score") is not None) / n
    pe_cov = (sum(1 for r in rows if r.get("pe_percentile") is not None) / n) if n > 0 else 0.0
    no_data = sum(1 for r in rows if r.get("flow_reason") == "flow_no_data")
    no_cov = 1 if agg.get("reason") == "flow_no_coverage" else 0
    reasons: list[str] = []
    if ratio is not None:
        reasons.append(f"flow_cover {round(ratio, 2)}")
    reasons.append(f"pe_cover {round(pe_cov, 2)}")
    reasons.append(f"flow_no_data {no_data}")
    reasons.append(f"flow_no_coverage {no_cov}")
    return StageHealth("flow_coverage", "PASS", tuple(reasons))


def _board_valuation_value(rows: list[dict]) -> float | None:
    """Pure: Σ(wᵢ·val_scoreᵢ)/Σ(wᵢ) over rows with non-None val_score.
    Clamped rows have val_score==0.0 and are included (contribute 0)."""
    covered = [r for r in rows if r.get("val_score") is not None]
    cw = sum(r["weight_pct"] for r in covered)
    if cw <= 0.0:
        return None
    return sum(r["weight_pct"] * r["val_score"] for r in covered) / cw


def _valuation_factor_value(t: dict) -> float | None:
    for c in t.get("signal", {}).get("contributions", []):
        if c.get("name") == "valuation":
            return c.get("value")
    return None


def valuation_reconciliation(t: dict) -> StageHealth:
    """PURE: the board's Σ(wᵢ·val_scoreᵢ)/Σ(wᵢ) over covered rows (clamped rows
    sum as 0) must equal the valuation factor value (4dp). No valuation
    contribution → PASS. Panel-only — NOT in any GATING_STAGES list (§5.E)."""
    factor_value = _valuation_factor_value(t)
    if factor_value is None:
        return StageHealth("valuation_reconciliation", "PASS", ())
    board = _board_valuation_value(t.get("holding_metrics", {}).get("rows", []))
    if board is None or abs(round(board, 4) - round(factor_value, 4)) >= _EPS:
        return StageHealth("valuation_reconciliation", "FAIL",
                           (f"board {board} != factor {factor_value}",))
    return StageHealth("valuation_reconciliation", "PASS", ())


def valuation_coverage_health(t: dict) -> StageHealth:
    """PURE informational dual-track coverage tally (§5.E, panel-only, always PASS).
    Surfaces NAV coverage, industry-leg coverage over covered rows, and false_cheap
    tally. Empty holding_metrics → PASS with no reasons, never raises."""
    hm = t.get("holding_metrics") or {}
    rows = hm.get("rows") or []
    agg = hm.get("valuation_aggregate") or {}
    if not rows and not agg:
        return StageHealth("valuation_coverage", "PASS", ())
    covered = [r for r in rows if r.get("val_score") is not None]
    cw = sum(r["weight_pct"] for r in covered)
    industry_cov = (
        sum(r["weight_pct"] for r in covered if r.get("industry_score") is not None) / cw
        if cw > 0.0 else 0.0
    )
    nav_cov = agg.get("covered_weight_ratio")
    false_cheap = sum(1 for r in rows if r.get("false_cheap"))
    reasons: list[str] = []
    if nav_cov is not None:
        reasons.append(f"nav_cover {round(nav_cov, 2)}")
    reasons.append(f"industry_cover {round(industry_cov, 2)}")
    reasons.append(f"false_cheap {false_cheap}")
    return StageHealth("valuation_coverage", "PASS", tuple(reasons))
