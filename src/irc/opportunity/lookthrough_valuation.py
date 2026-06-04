"""Pure look-through valuation aggregation core (Phase D PR1, spec §6.3).

Rolls a fund's CURRENT disclosed top-N A-share basket into a synthetic
earnings-yield (harmonic) PE series and a parallel PB series, then percentiles
the latest value via `self_history_percentile`. PE and PB covered sets are
computed INDEPENDENTLY (a name can have usable PE but missing/non-positive PB).

NO I/O, NO mutation — every function is pure and unit-testable without mocks.
Coverage = Σ weight_pct/100.0 (ratio of NAV); the /100 is load-bearing (§3.2).
Non-positive PE/PB excluded (§3.6). Per-date renormalization (§3.1/§3.4).
PE maturity gate = 120 points AND 180 days (mirrors inputs_loader); PB gated
only by self_history_percentile's <30 floor (§3.3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_Metric = Literal["pe", "pb"]


@dataclass(frozen=True)
class HoldingWeight:
    code: str
    weight_pct: float  # percent units 0..100 (matches fund_holdings.weight_pct)


@dataclass(frozen=True)
class MetricSeries:
    code: str
    source: str  # "eastmoney" | "tushare"
    points: tuple[tuple[str, float | None, float | None], ...]  # (date_iso, pe, pb)


@dataclass(frozen=True)
class MetricCoverage:
    percentile: float | None
    coverage_ratio: float
    covered_codes: tuple[str, ...]
    source_mix: tuple[str, ...]


@dataclass(frozen=True)
class FundValuationResult:
    pe: MetricCoverage
    pb: MetricCoverage


def _metric_index(metric: _Metric) -> int:
    return 1 if metric == "pe" else 2


def _has_positive_metric(series: MetricSeries, metric: _Metric) -> bool:
    """True iff the series has at least one strictly-positive value for metric."""
    idx = _metric_index(metric)
    return any(p[idx] is not None and p[idx] > 0.0 for p in series.points)


def _covered_codes_for_metric(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, metric: _Metric,
) -> tuple[str, ...]:
    """Codes that (a) are in the basket, (b) have a series, (c) have ≥1 positive
    metric value. Order follows the holdings input order (deterministic)."""
    return tuple(
        h.code
        for h in holdings
        if h.code in series_by_code
        and _has_positive_metric(series_by_code[h.code], metric)
    )


def _coverage_ratio(
    holdings: tuple[HoldingWeight, ...], covered_codes: tuple[str, ...]
) -> float:
    """Ratio of NAV covered: Σ weight_pct / 100.0 over covered codes (§3.2).
    The /100 is load-bearing — weight_pct is stored in percent units 0..100."""
    covered = set(covered_codes)
    return sum(h.weight_pct for h in holdings if h.code in covered) / 100.0


def _meets_floor(coverage_ratio: float, *, coverage_floor: float) -> bool:
    """Floor is compared on the RATIO (§3.2). >= so a fund exactly at the floor
    is accepted (mirrors the FOREIGN_HEAVY_THRESHOLD >= convention)."""
    return coverage_ratio >= coverage_floor


import pandas as pd


def _present_contributions(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    covered_codes: tuple[str, ...],
    metric: _Metric,
    iso: str,
) -> tuple[dict[str, float], dict[str, float]]:
    """For date `iso`: return (weight_by_code, value_by_code) over covered codes
    whose series has a strictly-positive metric value on that date."""
    idx = _metric_index(metric)
    covered = set(covered_codes)
    weight_by_code: dict[str, float] = {}
    value_by_code: dict[str, float] = {}
    for h in holdings:
        if h.code not in covered:
            continue
        for date_iso, pe, pb in series_by_code[h.code].points:
            if date_iso != iso:
                continue
            value = (pe, pb)[idx - 1]
            if value is not None and value > 0.0:
                weight_by_code[h.code] = h.weight_pct
                value_by_code[h.code] = value
    return weight_by_code, value_by_code


def _all_dates(
    series_by_code: dict[str, MetricSeries], covered_codes: tuple[str, ...]
) -> tuple[str, ...]:
    dates: set[str] = set()
    for code in covered_codes:
        dates.update(p[0] for p in series_by_code[code].points)
    return tuple(sorted(dates))


def _covered_total_weight(
    holdings: tuple[HoldingWeight, ...], covered_codes: tuple[str, ...]
) -> float:
    """Sum of weight_pct over the covered basket (denominator for per-date ratio)."""
    covered = set(covered_codes)
    return sum(h.weight_pct for h in holdings if h.code in covered)


def _aggregate_metric_series(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    covered_codes: tuple[str, ...],
    *, metric: _Metric, coverage_floor: float,
) -> pd.Series:
    """Per-date renormalized harmonic metric series (§3.1/§3.4). Drops dates
    whose present fraction of the covered basket < coverage_floor."""
    covered_total = _covered_total_weight(holdings, covered_codes)
    out_idx: list[str] = []
    out_val: list[float] = []
    for iso in _all_dates(series_by_code, covered_codes):
        weight_by_code, value_by_code = _present_contributions(
            holdings, series_by_code, covered_codes, metric, iso
        )
        if not weight_by_code:
            continue
        present_ratio = sum(weight_by_code.values()) / covered_total if covered_total > 0 else 0.0
        if present_ratio < coverage_floor:
            continue
        total_w = sum(weight_by_code.values())
        ey = sum(
            (weight_by_code[c] / total_w) * (1.0 / value_by_code[c])
            for c in weight_by_code
        )
        if ey <= 0.0:
            continue
        out_idx.append(iso)
        out_val.append(1.0 / ey)
    return pd.Series(out_val, index=pd.to_datetime(out_idx).date)


from irc.opportunity.inputs_loader import _pe_series_is_mature
from irc.opportunity.returns import self_history_percentile


def _percentile_for_metric(
    series: pd.Series, *, metric: _Metric, pb_uses_pe_gate: bool
) -> float | None:
    """PE: requires the 120/180 maturity gate (reused from the index path) AND
    the <30 floor inside self_history_percentile. PB: only the <30 floor unless
    pb_uses_pe_gate is True (§3.3)."""
    if series.empty:
        return None
    apply_pe_gate = metric == "pe" or pb_uses_pe_gate
    if apply_pe_gate and not _pe_series_is_mature(series):
        return None
    return self_history_percentile(series)


def fund_valuation_percentile(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, coverage_floor: float, pb_uses_pe_gate: bool,
) -> FundValuationResult:
    """Stub — implemented in Task 9."""
    raise NotImplementedError
