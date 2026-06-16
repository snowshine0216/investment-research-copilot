"""PURE metrics over the eval_trace.json projection (roadmap §2.7).
oracle_signal_match re-runs compute_signal from resolved + factor_scores (OQ1):
compute_signal reads ONLY fund.{id, weights, bands, minimum_confidence}."""
from __future__ import annotations
from irc.monitor.signal import compute_signal
from irc.monitor.types import FactorScore, MonitorFund


def _rebuild_fund(fund_id: str, resolved: dict) -> MonitorFund:
    return MonitorFund(
        id=fund_id, name_cn="", market="", analysis_profile=resolved["analysis_profile"],
        themes=(), constituent_news=False, weights=dict(resolved["weights"]),
        bands=dict(resolved["bands"]), minimum_confidence=resolved["minimum_confidence"],
    )


def _scores(factor_scores: list[dict]) -> tuple[FactorScore, ...]:
    return tuple(
        FactorScore(name=s["name"], value=s["value"], eligible=s["eligible"],
                    reason=s["reason"], confidence=s.get("confidence", 1.0))
        for s in factor_scores
    )


def _frac(numer: int, denom: int) -> float:
    return numer / denom if denom else 1.0


def oracle_signal_match(trace: dict) -> float:
    funds = trace.get("funds", {})
    if not funds:
        return 1.0
    matched = 0
    for fund_id, f in funds.items():
        rec = compute_signal(_rebuild_fund(fund_id, f["resolved"]), _scores(f["factor_scores"]))
        sig = f["signal"]
        if (rec.status == sig["status"] and rec.bias == sig["bias"]
                and rec.composite == sig["composite"]
                and rec.signal_confidence == sig["signal_confidence"]):
            matched += 1
    return _frac(matched, len(funds))


def _claim_ids(f: dict) -> list[str]:
    ids: list[str] = []
    narr = f.get("narrative", {})
    for field in ("price_action", "signal_rationale", "risk"):
        for claim in narr.get(field, []):
            ids.extend(claim.get("citation_ids", ()))
    for leg in ("macro", "constituent"):
        for imp in f.get("impacts", {}).get(leg, []):
            ids.extend(imp.get("citation_ids", ()))
    return ids


def citation_resolution(trace: dict) -> float:
    total = resolved = 0
    for f in trace.get("funds", {}).values():
        pool = {e["citation_id"] for e in f.get("evidence_pool", [])}
        for cid in _claim_ids(f):
            total += 1
            if cid in pool:
                resolved += 1
    return _frac(resolved, total)


def nav_completeness(trace: dict, *, minimum_observations: int = 2) -> float:
    funds = trace.get("funds", {})
    if not funds:
        return 1.0
    complete = sum(1 for f in funds.values()
                   if f["nav"].get("obs_count", 0) >= minimum_observations)
    return _frac(complete, len(funds))
