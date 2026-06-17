"""PURE per-fund in-run structural health over the eval_trace projection.
ADR 0017 §3.3: no I/O, no AkShare/LLM/settings imports."""
from __future__ import annotations
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
    # composite is round(Σcontribution, 4) by contract (signal.py / types.py: "C, rounded
    # 4dp") while contributions stay full-precision — compare at that same precision.
    sum_contrib = round(sum(c.get("contribution", 0.0) for c in contribs), _COMPOSITE_DP)
    sum_renorm = sum(c.get("renorm_weight", 0.0) for c in contribs)
    reasons: list[str] = []
    if abs(sig.get("composite", 0.0) - sum_contrib) >= _EPS:
        reasons.append("composite != Σcontribution")
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
