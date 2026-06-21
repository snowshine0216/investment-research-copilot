"""PURE per-stock drill-down core for `irc monitor` (ADR 0019). No I/O.

Takes already-loaded inputs (top holdings, per-code PE/PB MetricSeries, per-code
FlowSeries) and produces per-stock HoldingMetrics (valuation + flow) plus the
holding-weight-renormalized FlowAggregate that drives the `flow` factor.

Flow units are PERCENT-POINTS throughout (D3/D7). NO /100. Per-stock valuation is
a NEW computation distinct from the fund aggregate: each stock's PE percentile vs
ITS OWN history, reusing the opportunity primitives (no new fetch).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from irc.monitor.valuation import percentile_to_valuation_state
from irc.opportunity.lookthrough_valuation import MetricSeries, _pe_series_is_mature
from irc.opportunity.returns import self_history_percentile

# Flow blend weights (D7 note): steadier 20d favored. Named constants.
_FLOW_W_5D = 0.4
_FLOW_W_20D = 0.6

# Coverage floor (mirrors the valuation factor's covered-NAV gate D6).
_COVERAGE_FLOOR = 0.50

_NA_FLOW_NO_DATA = "flow_no_data"
_NA_FLOW_NO_COVERAGE = "flow_no_coverage"

# Dual-track valuation constants (ADR 0020 D3/D5/D9/D10 — priors, never auto-tuned).
_SELF_W = 0.60
_INDUSTRY_W = 0.40
_FALSE_CHEAP_RICHNESS = 1.2  # r >= this → max rich-vs-peers AND clamp trigger
# Monitor coverage floor (D10/Q8): NAV-denominator, distinct from
# lookthrough._COVERAGE_FLOOR=0.50 — the monitor valuation is a 0.20-weight
# research lean, not a publishability gate.
_MONITOR_COVERAGE_FLOOR = 0.40

_NA_VALUATION_NO_DATA = "valuation_no_data"
_NA_VALUATION_NO_COVERAGE = "valuation_no_coverage"
# Per-stock HoldingMetric reasons (NOT factor reasons, NEVER in KNOWN_NA_REASONS).
_REASON_INDUSTRY_NO_DATA = "industry_no_data"
_REASON_FALSE_CHEAP_CLAMP = "false_cheap_clamp"


def industry_band(r: float) -> float:
    """Pure: industry richness r = stock_pe/industry_avg_pe → score in [-1,+1].
    Cheaper-than-peers → positive. ASYMMETRIC bands (slow to call cheap, quick to
    withhold cheap). The -1.0 edge is pinned to _FALSE_CHEAP_RICHNESS so ONE
    threshold governs both 'max rich-vs-peers' and the clamp trigger."""
    if r <= 0.70:
        return 1.0
    if r <= 0.90:
        return 0.5
    if r <= 1.10:
        return 0.0
    if r < _FALSE_CHEAP_RICHNESS:
        return -0.5
    return -1.0


@dataclass(frozen=True)
class DualTrack:
    industry_score: float | None
    val_score: float | None
    false_cheap: bool
    industry_reason: str | None  # None | industry_no_data | false_cheap_clamp
    industry_richness: float | None


def _industry_leg(stock_pe: float | None, industry_avg_pe: float | None):
    """(richness, score) or (None, None) when the industry denominator is unusable."""
    if (stock_pe is None or stock_pe <= 0.0
            or industry_avg_pe is None or industry_avg_pe <= 0.0):
        return None, None
    r = stock_pe / industry_avg_pe
    return r, industry_band(r)


def dual_track_score(
    *, self_score: float | None, stock_pe: float | None, industry_avg_pe: float | None,
) -> DualTrack:
    """Pure: 0.60·self + 0.40·industry, with industry-N/A → self-only and a
    hard-0 False-Cheap clamp (self>0 AND r>=1.2). self-N/A → no val_score."""
    r, industry_score = _industry_leg(stock_pe, industry_avg_pe)
    if self_score is None:                        # self leg N/A → no score
        return DualTrack(industry_score, None, False, None, r)
    if industry_score is None:                    # industry leg N/A → self-only
        return DualTrack(None, self_score, False, _REASON_INDUSTRY_NO_DATA, None)
    if self_score > 0.0 and r >= _FALSE_CHEAP_RICHNESS:  # value-trap quadrant
        return DualTrack(industry_score, 0.0, True, _REASON_FALSE_CHEAP_CLAMP, r)
    blend = _SELF_W * self_score + _INDUSTRY_W * industry_score
    return DualTrack(industry_score, blend, False, None, r)


def _blend_flow_pct(pct_5d: float, pct_20d: float) -> float:
    """Pure: 0.4*5d + 0.6*20d, percent-points."""
    return _FLOW_W_5D * pct_5d + _FLOW_W_20D * pct_20d


# D7 bands as a pure step function, PERCENT-POINTS.
def flow_band(flow_pct: float) -> float:
    """Pure step function (D7). flow_pct in PERCENT-POINTS. >=3→+1, 1..3→+0.5,
    -1..1→0, -3..-1→-0.5, <=-3→-1."""
    if flow_pct >= 3.0:
        return 1.0
    if flow_pct >= 1.0:
        return 0.5
    if flow_pct > -1.0:
        return 0.0
    if flow_pct > -3.0:
        return -0.5
    return -1.0


def _window_mean(series, n: int) -> float | None:
    """Pure: mean of the last n values (percent-points). <n rows uses what it has;
    empty series → None."""
    if not series:
        return None
    tail = series[-n:]
    return sum(v for _, v in tail) / len(tail)


@dataclass(frozen=True)
class StockValuation:
    """Per-stock valuation: raw latest PE/PB + self-history PE percentile + state."""
    pe: float | None
    pb: float | None
    pe_percentile: float | None
    valuation_state: str | None
    valuation_reason: str | None  # None | pe_not_positive | pe_immature | no_series


def _latest_value(series: MetricSeries, idx: int) -> float | None:
    """Most recent point with a non-null value at tuple index idx (1=pe, 2=pb)."""
    for _date_iso, pe, pb in reversed(series.points):
        value = pe if idx == 1 else pb
        if value is not None:
            return value
    return None


def _positive_pe_pandas(series: MetricSeries) -> pd.Series:
    """Strictly-positive PE sub-series indexed by date (for the maturity gate +
    percentile). Mirrors the opportunity gate's pd.Series shape."""
    pairs = [(d, pe) for d, pe, _pb in series.points if pe is not None and pe > 0.0]
    if not pairs:
        return pd.Series([], dtype=float)
    idx = pd.to_datetime([d for d, _ in pairs])
    return pd.Series([v for _, v in pairs], index=idx)


def per_stock_valuation(code: str, series: MetricSeries | None) -> StockValuation:
    """Pure: per-stock latest PE/PB + self-history percentile (gated). Each stock
    vs ITS OWN PE history — NOT the fund-aggregate percentile. Negative/zero PE →
    no positive metric → percentile None → state None (board shows raw PE)."""
    if series is None:
        return StockValuation(None, None, None, None, "no_series")
    pe = _latest_value(series, 1)
    pb = _latest_value(series, 2)
    pos = _positive_pe_pandas(series)
    if pos.empty:
        return StockValuation(pe, pb, None, None, "pe_not_positive")
    if not _pe_series_is_mature(pos):
        return StockValuation(pe, pb, None, None, "pe_immature")
    pct = self_history_percentile(pos)
    return StockValuation(pe, pb, pct, percentile_to_valuation_state(pct), None)


@dataclass(frozen=True)
class HoldingMetric:
    symbol: str
    name: str
    weight_pct: float
    pe: float | None
    pb: float | None
    pe_percentile: float | None
    valuation_state: str | None
    valuation_reason: str | None
    flow_pct_5d: float | None
    flow_pct_20d: float | None
    flow_score: float | None
    flow_reason: str | None  # None | flow_no_data


def _flow_metric(series) -> tuple[float | None, float | None, float | None, str | None]:
    """(5d, 20d, score, reason). None series → flow_no_data."""
    if series is None:
        return None, None, None, "flow_no_data"
    p5 = _window_mean(series, 5)
    p20 = _window_mean(series, 20)
    if p5 is None or p20 is None:
        return p5, p20, None, "flow_no_data"
    return p5, p20, flow_band(_blend_flow_pct(p5, p20)), None


def per_stock_metrics(top_holdings, series_by_code, flow_series_by_code) -> tuple[HoldingMetric, ...]:
    """Pure: top holdings + per-code PE/PB series + per-code flow series →
    HoldingMetric rows (valuation + flow). No I/O; consumes already-loaded inputs."""
    out: list[HoldingMetric] = []
    for h in top_holdings:
        val = per_stock_valuation(h.symbol, series_by_code.get(h.symbol))
        p5, p20, score, reason = _flow_metric(flow_series_by_code.get(h.symbol))
        out.append(HoldingMetric(
            symbol=h.symbol, name=h.name_cn, weight_pct=h.weight_pct,
            pe=val.pe, pb=val.pb, pe_percentile=val.pe_percentile,
            valuation_state=val.valuation_state, valuation_reason=val.valuation_reason,
            flow_pct_5d=p5, flow_pct_20d=p20, flow_score=score, flow_reason=reason,
        ))
    return tuple(out)


@dataclass(frozen=True)
class FlowAggregate:
    value: float | None
    reason: str | None
    covered_weight_ratio: float


def build_holding_metrics(top_holdings, series_by_code, flow_series_by_code) -> tuple[HoldingMetric, ...]:
    """Pure assembly entry called from the edge (monitor_cmd). Identical to
    per_stock_metrics — named so the command imports one stable name. Effects
    (fetch_flow_series, _stock_series_by_code) stay in monitor_cmd."""
    return per_stock_metrics(top_holdings, series_by_code, flow_series_by_code)


def aggregate_flow(metrics: tuple[HoldingMetric, ...]) -> FlowAggregate:
    """Pure: Σ(wᵢ·sᵢ)/Σ(wᵢ) over holdings with a non-None flow_score, renormalized
    over covered top holdings (D5). covered_weight_ratio = Σ covered wᵢ / Σ all wᵢ.
    Zero covered → flow_no_data; covered but ratio < 0.50 → flow_no_coverage."""
    total_w = sum(m.weight_pct for m in metrics)
    covered = [m for m in metrics if m.flow_score is not None]
    covered_w = sum(m.weight_pct for m in covered)
    ratio = covered_w / total_w if total_w > 0.0 else 0.0
    if not covered or covered_w <= 0.0:
        return FlowAggregate(None, _NA_FLOW_NO_DATA, ratio)
    if ratio < _COVERAGE_FLOOR:
        return FlowAggregate(None, _NA_FLOW_NO_COVERAGE, ratio)
    value = sum(m.weight_pct * m.flow_score for m in covered) / covered_w
    return FlowAggregate(value, None, ratio)
