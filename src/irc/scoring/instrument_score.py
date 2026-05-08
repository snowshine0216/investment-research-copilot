from __future__ import annotations

from dataclasses import dataclass

from irc.schemas.scoring import ScoringConfig
from irc.scoring.factors.valuation_cost import FactorScore


@dataclass(frozen=True)
class InstrumentScore:
    instrument_id: str
    composite_score: float
    action: str
    conviction: str
    factor_breakdown: dict[str, dict[str, object]]
    data_completeness: float
    weights_version: str


def _action_for(score: float, cfg: ScoringConfig) -> str:
    th = cfg.action_thresholds
    if score >= th["strong_buy_candidate"]:
        return "strong_buy_candidate"
    if score >= th["buy_candidate"]:
        return "buy_candidate"
    if score >= th["watch"]:
        return "watch"
    if score >= th["avoid"]:
        return "avoid"
    return "strong_avoid"


def _conviction_for(data_completeness: float, threshold: float) -> str:
    if data_completeness >= threshold + 0.10:
        return "high"
    if data_completeness >= threshold:
        return "med"
    return "low"


def _demote(action: str) -> str:
    chain = ("strong_buy_candidate", "buy_candidate", "watch", "avoid", "strong_avoid")
    idx = chain.index(action)
    return chain[min(idx + 1, len(chain) - 1)]


def compose_score(
    instrument_id: str,
    factors: dict[str, FactorScore],
    data_completeness: float,
    cfg: ScoringConfig,
) -> InstrumentScore:
    """Pure composer: weighted average + action mapping + conviction demotion."""
    composite = sum(cfg.factor_weights[name] * factors[name].score for name in cfg.factor_weights)  # type: ignore[index]
    action = _action_for(composite, cfg)
    conviction = _conviction_for(data_completeness, cfg.conviction_data_completeness_threshold)
    if conviction == "low":
        action = _demote(action)
    breakdown = {
        name: {
            "score": factors[name].score,
            "raw_refs": list(factors[name].raw_refs),
            "components": factors[name].components,
        }
        for name in cfg.factor_weights
    }
    return InstrumentScore(
        instrument_id=instrument_id,
        composite_score=composite,
        action=action,
        conviction=conviction,
        factor_breakdown=breakdown,
        data_completeness=data_completeness,
        weights_version=cfg.weights_version,
    )
