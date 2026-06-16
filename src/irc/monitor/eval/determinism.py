"""PURE D2 in-run deterministic-scoring health (spec §4). Recompute the full
signal block from factor_scores + resolved and diff vs the recorded block — NOT
self-referential; catches stale/malformed derived metadata.

ADR 0017 §3.3 ban: I/O, AkShare, providers, LLM gateway, settings, filesystem.
Pure evals._shared helpers are allowed (mirrors structural.py:6) — worst_status
is none of the banned categories.

PANEL-ONLY: deterministic_health is NEVER passed to apply_eval_gate and the
'deterministic_scoring' stage is NEVER added to GATING_STAGES_* (spec §4.3).
"""
from __future__ import annotations
from irc.monitor.factors import KNOWN_NA_REASONS
from irc.monitor.signal import compute_signal
from irc.monitor.types import FactorScore, MonitorFund, SignalRecord
from irc.monitor.eval.types import StageHealth, ValidationPanelRow
from evals._shared.status import worst_status

_STAGE = "deterministic_scoring"
_EPS = 1e-9
_MISSING = object()  # sentinel: key absent from recorded dict


def _rebuild_fund(fund_id: str, resolved: dict) -> MonitorFund:
    """fund_id is the funds-dict KEY (absent from the per-fund value). compute_signal
    reads fund.id (signal.py:80), so it must be supplied — mirrors M0
    metrics._rebuild_fund(fund_id, resolved)."""
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


def recompute_signal_from_trace(fund_id: str, trace_fund: dict) -> SignalRecord:
    """Rebuild MonitorFund from fund_id + `resolved`, FactorScores from
    `factor_scores`, then run compute_signal. fund_id is required (P0 rev-3)."""
    return compute_signal(
        _rebuild_fund(fund_id, trace_fund["resolved"]),
        _scores(trace_fund["factor_scores"]),
    )


def _ne(a: float, b: float) -> bool:
    return abs(a - b) >= _EPS


def _float_diff(name: str, recomputed: float, recorded: dict) -> str | None:
    """Return field name if key absent OR value differs beyond eps; else None."""
    raw = recorded.get(name, _MISSING)
    if raw is _MISSING or _ne(recomputed, raw):
        return name
    return None


def _diff_contributions(recomputed, recorded: list[dict]) -> list[str]:
    out: list[str] = []
    if len(recomputed) != len(recorded):
        out.append("contributions:length")
        return out
    for i, (c, rc) in enumerate(zip(recomputed, recorded)):
        if c.name != rc.get("name"):
            out.append(f"contributions[{i}].name")
        for subfield, val in (("renorm_weight", c.renorm_weight),
                              ("value", c.value),
                              ("contribution", c.contribution),
                              ("confidence", c.confidence)):
            diff = _float_diff(subfield, val, rc)
            if diff is not None:
                out.append(f"contributions[{i}].{diff}")
    return out


def diff_signal(recomputed: SignalRecord, recorded: dict) -> tuple[str, ...]:
    """Names of mismatched fields between a recompute and the recorded signal.
    Float fields via the §3.3 eps; categoricals exact. Absent keys count as
    mismatches (spec §1/§4.1). Does NOT compare fund_id."""
    out: list[str] = []
    for fname, fval in (("available_weight", recomputed.available_weight),
                        ("composite", recomputed.composite),
                        ("signal_confidence", recomputed.signal_confidence)):
        diff = _float_diff(fname, fval, recorded)
        if diff is not None:
            out.append(diff)
    for lname, lval in (("present_families", list(recomputed.present_families)),
                        ("divergence_codes", list(recomputed.divergence_codes))):
        raw = recorded.get(lname, _MISSING)
        if raw is _MISSING or list(raw) != lval:
            out.append(lname)
    if "contributions" not in recorded:
        out.append("contributions")
    else:
        out.extend(_diff_contributions(recomputed.contributions, recorded["contributions"]))
    if recomputed.status != recorded.get("status"):
        out.append("status")
    if recomputed.bias != recorded.get("bias"):
        out.append("bias")
    return tuple(out)


def _bad_reasons(factor_scores: list[dict]) -> tuple[str, ...]:
    return tuple(
        f"reason:{s['name']}={s['reason']}"
        for s in factor_scores
        if not s.get("eligible") and s.get("reason") not in KNOWN_NA_REASONS
    )


def deterministic_health(fund_id: str, trace_fund: dict) -> StageHealth:
    """Per-fund PASS/FAIL. FAIL if the recompute diffs the recorded signal OR any
    ineligible factor's reason is not in KNOWN_NA_REASONS. fund_id required (P0)."""
    rec = recompute_signal_from_trace(fund_id, trace_fund)
    fields = diff_signal(rec, trace_fund["signal"])
    bad = _bad_reasons(trace_fund["factor_scores"])
    reasons = tuple(fields) + bad
    status = "FAIL" if reasons else "PASS"
    return StageHealth(stage=_STAGE, status=status, reasons=reasons)


def aggregate_deterministic_health(traces: dict) -> StageHealth:
    """Worst-of over the funds dict; reasons name the offending funds. Passes
    fund_id from the dict KEY into the per-fund health (P0 rev-3)."""
    funds = traces.get("funds", {})
    per_fund = [
        (fid, deterministic_health(fid, f)) for fid, f in funds.items()
    ]
    overall = worst_status([h.status for _, h in per_fund])
    reasons = tuple(
        f"{fid}: {r}" for fid, h in per_fund for r in h.reasons
    )
    return StageHealth(stage=_STAGE, status=overall, reasons=reasons)


_KNOWN_STATUSES = {"PASS", "WARN", "FAIL"}


def _safe_status(s: str) -> str:
    """Map any unrecognised status (e.g. 'UNKNOWN') to 'FAIL' for worst-of.
    An unknown health state is never better than FAIL."""
    return s if s in _KNOWN_STATUSES else "FAIL"


def _row(stage: str, healths: dict, now: str) -> ValidationPanelRow:
    """Aggregate per-fund StageHealths → worst-of one panel row (spec §5)."""
    statuses = [_safe_status(h.status) for h in healths.values()]
    overall = worst_status(statuses) if statuses else "PASS"
    reasons = tuple(r for h in healths.values() for r in h.reasons)
    return ValidationPanelRow(stage=stage, status=overall, ran_at=now, reasons=reasons)


def build_panel_rows(
    signal_healths: dict, deterministic_healths: dict, *, now: str,
) -> tuple[ValidationPanelRow, ...]:
    """Both panel rows from the per-fund healths. monitor_signal reflects RAW
    signal_health worst-of (divergence 1); deterministic_scoring is panel-only."""
    return (
        _row("monitor_signal", signal_healths, now),
        _row("deterministic_scoring", deterministic_healths, now),
    )
