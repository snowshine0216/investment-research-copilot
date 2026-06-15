from __future__ import annotations
import statistics
from irc.monitor.types import FactorContribution, FactorScore, MonitorFund, SignalRecord

_FAMILY_OF = {
    "trend": "price-momentum", "valuation": "valuation",
    "heat": "crowding", "macro_tilt": "news", "constituent": "news",
}
_MIN_FAMILIES = 2
_MIN_AVAILABLE_WEIGHT = 0.60
_DIVERGE = 0.3


def _present(scores: tuple[FactorScore, ...]) -> tuple[FactorScore, ...]:
    return tuple(s for s in scores if s.eligible and s.value is not None)


def present_families(scores: tuple[FactorScore, ...]) -> tuple[str, ...]:
    fams = {_FAMILY_OF[s.name] for s in _present(scores)}
    return tuple(sorted(fams))


def _available_weight(fund: MonitorFund, present: tuple[FactorScore, ...]) -> float:
    return sum(fund.weights.get(s.name, 0.0) for s in present)


def _contributions(fund: MonitorFund, present: tuple[FactorScore, ...], avail: float) -> tuple[FactorContribution, ...]:
    out = []
    for s in present:
        w = fund.weights.get(s.name, 0.0)
        wp = w / avail if avail > 0 else 0.0
        out.append(FactorContribution(
            name=s.name, renorm_weight=wp, value=s.value,
            contribution=wp * s.value, confidence=s.confidence,
            eligible=True, reason="",
        ))
    return tuple(out)


def _divergence(present: tuple[FactorScore, ...]) -> tuple[str, ...]:
    by = {s.name: s.value for s in present}
    codes: list[str] = []
    t, v, m = by.get("trend"), by.get("valuation"), by.get("macro_tilt")
    if t is not None and v is not None and (
        (t >= _DIVERGE and v <= -_DIVERGE) or (t <= -_DIVERGE and v >= _DIVERGE)
    ):
        codes.append("trend_valuation_conflict")
    if t is not None and m is not None and (
        (t > 0) != (m > 0) and abs(t) >= _DIVERGE and abs(m) >= _DIVERGE
    ):
        codes.append("trend_macro_conflict")
    vals = [s.value for s in present]
    if len(vals) >= 2 and (statistics.pstdev(vals) >= 0.5 or (
        any(x > 0 for x in vals) and any(x < 0 for x in vals)
    )):
        codes.append("low_factor_agreement")
    return tuple(codes)


def _bias(c: float, bands: dict[str, float]) -> str:
    if c >= bands["buy"]:
        return "ADD_BIAS"
    if c <= bands["sell"]:
        return "REDUCE_BIAS"
    return "NEUTRAL"


def compute_signal(fund: MonitorFund, scores: tuple[FactorScore, ...]) -> SignalRecord:
    """Pure: resolved fund + factor scores → SignalRecord (status + bias union)."""
    present = _present(scores)
    families = present_families(scores)
    avail = _available_weight(fund, present)
    contribs = _contributions(fund, present, avail)
    composite = round(sum(c.contribution for c in contribs), 4)
    confidence = round(sum(c.renorm_weight * c.confidence for c in contribs), 4)
    divergence = _divergence(present)
    trend_present = any(s.name == "trend" for s in present)

    base = dict(
        fund_id=fund.id, composite=composite, signal_confidence=confidence,
        available_weight=round(avail, 4), present_families=families,
        contributions=contribs, divergence_codes=divergence,
    )
    if not (trend_present and len(families) >= _MIN_FAMILIES and avail >= _MIN_AVAILABLE_WEIGHT):
        return SignalRecord(status="insufficient_evidence", bias=None, **base)
    if confidence < fund.minimum_confidence:
        return SignalRecord(status="low_confidence", bias=None, **base)
    return SignalRecord(status="ok", bias=_bias(composite, fund.bands), **base)
