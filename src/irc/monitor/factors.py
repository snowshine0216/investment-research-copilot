from __future__ import annotations
from dataclasses import dataclass
from irc.monitor.profiles import eligible_factors
from irc.monitor.trend import trend_score
from irc.monitor.factor_maps import valuation_state_score, heat_score
from irc.monitor.news_factor import ImpactRow, aggregate_news_factor
from irc.monitor.types import FactorScore

# ── N/A reason codes (single source — spec §6) ────────────────────────────────
# The producer owns these; eval/determinism.py imports them. Do NOT move the set
# into the eval overlay (would invert the eval → core layering).
_NA_PROFILE_INELIGIBLE = "profile_ineligible"
_NA_TREND_INSUFFICIENT_HISTORY = "trend_insufficient_history"
_NA_VALUATION_NO_ANCHOR = "valuation_no_anchor"
_NA_VALUATION_UNKNOWN_STATE = "valuation_unknown_state"
_NA_HEAT_NO_DATA = "heat_no_data"
_NA_MACRO_INSUFFICIENT_FAMILIES = "macro_insufficient_families"
_NA_MACRO_EMPTY_POOL = "macro_empty_pool"
_NA_CONSTITUENT_NO_COVERAGE = "constituent_no_coverage"

KNOWN_NA_REASONS: frozenset[str] = frozenset({
    _NA_PROFILE_INELIGIBLE,
    _NA_TREND_INSUFFICIENT_HISTORY,
    _NA_VALUATION_NO_ANCHOR,
    _NA_VALUATION_UNKNOWN_STATE,
    _NA_HEAT_NO_DATA,
    _NA_MACRO_INSUFFICIENT_FAMILIES,
    _NA_MACRO_EMPTY_POOL,
    _NA_CONSTITUENT_NO_COVERAGE,
})

_MACRO_MIN_FAMILIES = 2


@dataclass(frozen=True)
class FactorInputs:
    acc_nav: tuple[tuple[str, float], ...]
    minimum_observations: int
    valuation_state: str | None
    valuation_cached: bool
    restricted: bool | None
    aum_delta_pct: float | None
    macro_rows: tuple[ImpactRow, ...]
    constituent_rows: tuple[ImpactRow, ...]


def _na(name: str, reason: str) -> FactorScore:
    return FactorScore(name=name, value=None, eligible=False, reason=reason)


def _trend(inp: FactorInputs) -> FactorScore:
    if len(inp.acc_nav) < inp.minimum_observations:
        return _na("trend", _NA_TREND_INSUFFICIENT_HISTORY)
    return FactorScore("trend", trend_score(inp.acc_nav), True, "", 1.0)


def _valuation(profile: str, inp: FactorInputs) -> FactorScore:
    if "valuation" not in eligible_factors(profile):
        return _na("valuation", _NA_PROFILE_INELIGIBLE)
    if not inp.valuation_cached or inp.valuation_state is None:
        return _na("valuation", _NA_VALUATION_NO_ANCHOR)
    score = valuation_state_score(inp.valuation_state)
    if score is None:
        return _na("valuation", _NA_VALUATION_UNKNOWN_STATE)
    return FactorScore("valuation", score, True, "", 1.0)


def _heat(profile: str, inp: FactorInputs) -> FactorScore:
    if "heat" not in eligible_factors(profile):
        return _na("heat", _NA_PROFILE_INELIGIBLE)
    score = heat_score(restricted=inp.restricted, aum_delta_pct=inp.aum_delta_pct)
    if score is None:
        return _na("heat", _NA_HEAT_NO_DATA)
    return FactorScore("heat", score, True, "", 1.0)


def _macro(profile: str, inp: FactorInputs) -> FactorScore:
    if "macro_tilt" not in eligible_factors(profile):
        return _na("macro_tilt", _NA_PROFILE_INELIGIBLE)
    families = {r.key for r in inp.macro_rows}
    if len(families) < _MACRO_MIN_FAMILIES:
        return _na("macro_tilt", _NA_MACRO_INSUFFICIENT_FAMILIES)
    value, conf = aggregate_news_factor(inp.macro_rows)
    if value is None:
        return _na("macro_tilt", _NA_MACRO_EMPTY_POOL)
    return FactorScore("macro_tilt", value, True, "", conf)


def _constituent(profile: str, inp: FactorInputs) -> FactorScore:
    if "constituent" not in eligible_factors(profile):
        return _na("constituent", _NA_PROFILE_INELIGIBLE)
    if not inp.constituent_rows:
        return _na("constituent", _NA_CONSTITUENT_NO_COVERAGE)
    value, conf = aggregate_news_factor(inp.constituent_rows)
    if value is None:
        return _na("constituent", _NA_CONSTITUENT_NO_COVERAGE)
    return FactorScore("constituent", value, True, "", conf)


def build_factor_scores(profile: str, inp: FactorInputs) -> tuple[FactorScore, ...]:
    """Pure: one fund's inputs → the five FactorScores (eligible or N/A + reason)."""
    return (
        _trend(inp), _valuation(profile, inp), _heat(profile, inp),
        _macro(profile, inp), _constituent(profile, inp),
    )
