"""PURE eval_trace serialization (roadmap §3.6). Degradation-safe NAV (AC B);
unified macro ⊕ constituent evidence pool deduped by citation_id (AC C).
ADR 0017 §3.3: no I/O imports."""
from __future__ import annotations
from datetime import date
from irc.monitor.eval.gate import published_state
from irc.monitor.eval.types import FundTraceBundle, GateDecision
from irc.monitor.impact_validate import ValidatedImpact
from irc.monitor.render_types import FundView
from irc.monitor.types import EvidenceItem, MonitorFund

_SCHEMA_VERSION = "3"


def dedup_by_citation_id(items: tuple[EvidenceItem, ...]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for ev in items:
        if ev.citation_id in seen:
            continue
        seen.add(ev.citation_id)
        out.append({"source": ev.source, "title": ev.title, "date": ev.date,
                    "url": ev.url, "owner_fund_id": ev.owner_fund_id,
                    "citation_id": ev.citation_id})
    return out


def _parse(d: str) -> date | None:
    try:
        return date.fromisoformat(d)
    except (ValueError, TypeError):
        return None


# Trailing-activity probe window. The signal's own lookback is up to a year
# (returns.py _WINDOWS max 250), and a year ALWAYS contains a ~11d Spring-Festival
# and National-Day closure — so a full-series gap can never pass for a CN fund.
# We instead measure only the most recent ~month, asking "is the fund still
# reporting NAV on a daily cadence?" — ancient holidays fall out of scope.
_RECENT_GAP_WINDOW = 20


def _max_gap_days(
    series: tuple[tuple[str, float], ...], *, window: int = _RECENT_GAP_WINDOW,
) -> int | None:
    recent = series[-window:] if window else series
    if len(recent) < 2:
        return None
    deltas: list[int] = []
    for (d0, _), (d1, _) in zip(recent, recent[1:]):
        a, b = _parse(d0), _parse(d1)
        if a is not None and b is not None:
            deltas.append((b - a).days)
    return max(deltas) if deltas else None


def _missing_trading_days(
    series: tuple[tuple[str, float], ...],
    trading_days: frozenset[date] | None,
    *, window: int = _RECENT_GAP_WINDOW,
) -> int | None:
    """Max number of SSE-open trading dates strictly inside any recent
    inter-observation gap (spec §3.2). Holidays/weekends aren't in trading_days
    so a holiday gap scores 0. None when the calendar is unavailable OR empty (→
    gate falls back to max_gap_days; an empty set must never score 0-for-every-gap
    and yield a false PASS). <2 parsed observations → 0."""
    if not trading_days:           # None or empty frozenset → degrade to fallback
        return None
    recent = series[-window:] if window else series
    dates = [p for d, _ in recent if (p := _parse(d)) is not None]
    if len(dates) < 2:
        return 0
    return max(
        sum(1 for td in trading_days if d0 < td < d1)
        for d0, d1 in zip(dates, dates[1:])
    )


def _nav(view: FundView, trading_days: frozenset[date] | None) -> dict:
    series = view.nav_series
    nav_acc = series[-1][1] if series else None
    return {
        "as_of_date": view.as_of_date,
        "latest_unit_nav": view.latest_nav,
        "nav_acc": nav_acc,
        "acc_series": [list(pt) for pt in series],
        "obs_count": len(series),
        "max_gap_days": _max_gap_days(series),
        "missing_trading_days": _missing_trading_days(series, trading_days),
    }


def _impact(imp: ValidatedImpact) -> dict:
    return {"key": imp.key, "weight": 1.0, "impact": imp.impact,
            "confidence": imp.confidence, "citation_ids": list(imp.citation_ids)}


def _impacts(bundle: FundTraceBundle) -> dict:
    return {"macro": [_impact(i) for i in bundle.macro_impacts],
            "constituent": [_impact(i) for i in bundle.constituent_impacts]}


def _signal(sig) -> dict:
    return {
        "status": sig.status, "bias": sig.bias, "composite": sig.composite,
        "signal_confidence": sig.signal_confidence, "available_weight": sig.available_weight,
        "present_families": list(sig.present_families),
        "contributions": [{"name": c.name, "renorm_weight": c.renorm_weight, "value": c.value,
                           "contribution": c.contribution, "confidence": c.confidence}
                          for c in sig.contributions],
        "divergence_codes": list(sig.divergence_codes),
    }


def _claims(claims) -> list[dict]:
    return [{"claim": c.claim, "attribution_strength": c.attribution_strength,
             "citation_ids": list(c.citation_ids)} for c in claims]


def _narrative(narr) -> dict:
    return {"status": narr.status,
            "price_action": _claims(narr.price_action_commentary),
            "signal_rationale": _claims(narr.signal_rationale_commentary),
            "risk": _claims(narr.risk_commentary)}


def _fund_entry(fund: MonitorFund, view: FundView, gate: GateDecision,
                bundle: FundTraceBundle, trading_days: frozenset[date] | None) -> dict:
    return {
        "resolved": {"analysis_profile": fund.analysis_profile, "weights": dict(fund.weights),
                     "bands": dict(fund.bands), "minimum_confidence": fund.minimum_confidence},
        "nav": _nav(view, trading_days),
        "evidence_pool": dedup_by_citation_id(view.evidence_pool + bundle.constituent_pool),
        "factor_scores": [{"name": s.name, "value": s.value, "eligible": s.eligible,
                           "reason": s.reason, "confidence": s.confidence}
                          for s in view.factor_scores],
        "signal": _signal(view.signal),
        "impacts": _impacts(bundle),
        "narrative": _narrative(view.narrative),
        "gate": {"suppressed": gate.suppressed, "failed_stages": list(gate.failed_stages),
                 "reason": gate.reason},
        "published_state": published_state(view.signal, gate),
        "validation_badge": gate.badge,
    }


def build_eval_trace(
    items: tuple[tuple[MonitorFund, FundView, GateDecision, FundTraceBundle], ...],
    *, engine_version: str, run_date: str,
    trading_days: frozenset[date] | None = None,
) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "engine_version": engine_version,
        "run_date": run_date,
        "funds": {fund.id: _fund_entry(fund, view, gate, bundle, trading_days)
                  for fund, view, gate, bundle in items},
    }
