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


def fund_valuation_percentile(
    holdings: tuple[HoldingWeight, ...],
    series_by_code: dict[str, MetricSeries],
    *, coverage_floor: float, pb_uses_pe_gate: bool,
) -> FundValuationResult:
    """Stub — implemented in Task 9."""
    raise NotImplementedError
