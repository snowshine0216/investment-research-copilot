"""PURE retro backtest — replays the evidence-free sub-composite over nav_history
on the §2.3 retro replay clock. No I/O. Validates the deterministic core, never
the published bias (trend-only cannot clear the >=2-family / avail>=0.60 gate)."""
from __future__ import annotations
from dataclasses import dataclass
from irc.monitor.factors import FactorInputs, build_factor_scores
from irc.monitor.signal import compute_signal
from irc.monitor.types import MonitorFund
from irc.monitor.eval.join import series_entry_outcome


@dataclass(frozen=True)
class RetroPoint:
    as_of_date: str
    as_of_idx: int
    composite: float
    status: str
    entry_nav_date: str
    fwd_ret: float


@dataclass(frozen=True)
class BacktestResult:
    points: tuple[RetroPoint, ...]
    excluded: dict[str, int]


def _evidence_free_composite(
    fund: MonitorFund, acc_slice: tuple[tuple[str, float], ...], minimum_observations: int,
):
    """Build the M0 degraded FactorInputs (evidence legs N/A) and read the
    continuous composite. Trend is the only present factor → weights renormalize."""
    inp = FactorInputs(
        acc_nav=acc_slice, minimum_observations=minimum_observations,
        valuation_state=None, valuation_cached=False, restricted=None,
        aum_delta_pct=None, macro_rows=(), constituent_rows=(),
    )
    scores = build_factor_scores(fund.analysis_profile, inp)
    return compute_signal(fund, scores)


def replay_points(
    fund: MonitorFund, series: tuple[tuple[str, float], ...],
    *, minimum_observations: int, h: int, today: str,
) -> tuple[RetroPoint, ...]:
    return run_backtest(
        fund, series, minimum_observations=minimum_observations, h=h, today=today
    ).points


def run_backtest(
    fund: MonitorFund, series: tuple[tuple[str, float], ...],
    *, minimum_observations: int, h: int, today: str,
) -> BacktestResult:
    points: list[RetroPoint] = []
    excluded: dict[str, int] = {}
    for as_of_idx in range(len(series)):
        # below the floor compute_signal returns composite==0.0 / insufficient_evidence
        if as_of_idx + 1 < minimum_observations:
            excluded["below_minimum_observations"] = excluded.get("below_minimum_observations", 0) + 1
            continue
        as_of_date = series[as_of_idx][0]
        # TRUNCATED input window — compute_signal sees ONLY series[:as_of_idx+1]
        truncated = series[: as_of_idx + 1]
        sig = _evidence_free_composite(fund, truncated, minimum_observations)
        # Degenerate-grid guard (§2.3): exclude ONLY a constant-0 composite (e.g. a flat
        # window → trend ~0), which would feed the IC a constant-0 signal (Spearman None).
        # Do NOT exclude on status: trend-only ALWAYS yields status=="insufficient_evidence"
        # (1 family < the 2-family gate), yet spec §3 scores the continuous composite
        # REGARDLESS of status — excluding on status would make retro permanently empty.
        if sig.composite == 0.0:
            excluded["degenerate_zero_composite"] = (
                excluded.get("degenerate_zero_composite", 0) + 1
            )
            continue
        # retro: run_date == as_of_date; entry strictly > as_of_date
        eo = series_entry_outcome(series, anchor=as_of_date, h=h, today=today)
        if eo.reason != "ok":
            excluded[eo.reason] = excluded.get(eo.reason, 0) + 1
            continue
        points.append(RetroPoint(
            as_of_date=as_of_date, as_of_idx=as_of_idx, composite=sig.composite,
            status=sig.status, entry_nav_date=eo.entry_nav_date, fwd_ret=eo.fwd_ret,
        ))
    return BacktestResult(points=tuple(points), excluded=excluded)
