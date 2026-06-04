"""Pure look-through valuation core (Phase D PR1, spec §6.3).

Harmonic earnings-yield PE/PB roll-up from a fund's current top-N A-share basket.
PE/PB covered sets computed independently; every gap degrades to None (§3.6).
Coverage = Σ weight_pct/100.0 (ratio of NAV; /100 is load-bearing §3.2).
Per-date renormalization (§3.1/§3.4). PE gate: 120 pts + 180 days (§3.3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from irc.opportunity.returns import self_history_percentile

# PE maturity gate constants (§3.3 / inputs_loader §3). Defined here so
# lookthrough_valuation is the single source of truth; inputs_loader re-imports
# them to avoid a circular dependency.
MIN_PE_POINTS: int = 120
MIN_PE_DAYS: int = 180


def _pe_series_is_mature(pe_series: pd.Series) -> bool:
    """§3 gate: >= MIN_PE_POINTS non-null PE points AND >= MIN_PE_DAYS span."""
    valid = pe_series.dropna()
    if len(valid) < MIN_PE_POINTS:
        return False
    idx = pd.to_datetime(valid.index)
    span_days = (idx.max() - idx.min()).days
    return span_days >= MIN_PE_DAYS

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
    """In basket + has series + has ≥1 positive metric value (deterministic order)."""
    return tuple(
        h.code for h in holdings
        if h.code in series_by_code and _has_positive_metric(series_by_code[h.code], metric)
    )


def _coverage_ratio(
    holdings: tuple[HoldingWeight, ...], covered_codes: tuple[str, ...]
) -> float:
    """Σ weight_pct / 100.0 over covered codes — ratio of NAV (§3.2, /100 load-bearing)."""
    covered = set(covered_codes)
    return sum(h.weight_pct for h in holdings if h.code in covered) / 100.0


def _meets_floor(ratio: float, *, coverage_floor: float) -> bool:
    """Ratio >= floor (§3.2). >= accepts funds exactly at the floor."""
    return ratio >= coverage_floor


def _all_dates(
    series_by_code: dict[str, MetricSeries], covered_codes: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(sorted({p[0] for c in covered_codes for p in series_by_code[c].points}))


def _present_contributions(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    covered_codes: tuple[str, ...],
    metric: _Metric,
    iso: str,
) -> tuple[dict[str, float], dict[str, float]]:
    """(weight_by_code, value_by_code) for covered codes with positive metric on `iso`."""
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


def _aggregate_metric_series(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    covered_codes: tuple[str, ...],
    *, metric: _Metric, coverage_floor: float,
) -> pd.Series:
    """Per-date renormalized harmonic series (§3.1/§3.4). Drops a date when the
    present covered+positive weight is < coverage_floor as a fraction of NAV
    (Σ weight_pct/100, §3.2 units) — so a single mega-cap can't masquerade as
    the whole basket (§3.4)."""
    out_idx: list[str] = []
    out_val: list[float] = []
    for iso in _all_dates(series_by_code, covered_codes):
        wb, vb = _present_contributions(holdings, series_by_code, covered_codes, metric, iso)
        if not wb:
            continue
        present_ratio = sum(wb.values()) / 100.0
        if present_ratio < coverage_floor:
            continue
        total_w = sum(wb.values())
        ey = sum((wb[c] / total_w) * (1.0 / vb[c]) for c in wb)
        if ey <= 0.0:
            continue
        out_idx.append(iso)
        out_val.append(1.0 / ey)
    return pd.Series(out_val, index=pd.to_datetime(out_idx).date)


def _percentile_for_metric(
    series: pd.Series, *, metric: _Metric, pb_uses_pe_gate: bool
) -> float | None:
    """PE: 120/180 gate + <30 floor. PB: only <30 floor unless pb_uses_pe_gate (§3.3)."""
    if series.empty:
        return None
    if (metric == "pe" or pb_uses_pe_gate) and not _pe_series_is_mature(series):
        return None
    return self_history_percentile(series)


def _source_mix(
    series_by_code: dict[str, MetricSeries], covered_codes: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(sorted({series_by_code[c].source for c in covered_codes}))


def _metric_coverage(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, metric: _Metric, coverage_floor: float, pb_uses_pe_gate: bool,
) -> MetricCoverage:
    covered = _covered_codes_for_metric(holdings, series_by_code, metric=metric)
    ratio = _coverage_ratio(holdings, covered)
    mix = _source_mix(series_by_code, covered)
    if not _meets_floor(ratio, coverage_floor=coverage_floor):
        return MetricCoverage(None, ratio, covered, mix)
    series = _aggregate_metric_series(
        holdings, series_by_code, covered, metric=metric, coverage_floor=coverage_floor
    )
    pct = _percentile_for_metric(series, metric=metric, pb_uses_pe_gate=pb_uses_pe_gate)
    return MetricCoverage(pct, ratio, covered, mix)


def fund_valuation_percentile(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, coverage_floor: float, pb_uses_pe_gate: bool,
) -> FundValuationResult:
    """Pure public entry (§6.3). PE and PB covered sets computed independently;
    every gap path degrades to a None percentile."""
    return FundValuationResult(
        pe=_metric_coverage(
            holdings, series_by_code,
            metric="pe", coverage_floor=coverage_floor, pb_uses_pe_gate=pb_uses_pe_gate,
        ),
        pb=_metric_coverage(
            holdings, series_by_code,
            metric="pb", coverage_floor=coverage_floor, pb_uses_pe_gate=pb_uses_pe_gate,
        ),
    )
