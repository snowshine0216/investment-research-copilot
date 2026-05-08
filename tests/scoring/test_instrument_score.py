from __future__ import annotations

from irc.schemas.scoring import ScoringConfig
from irc.scoring.factors.valuation_cost import FactorScore
from irc.scoring.instrument_score import InstrumentScore, compose_score


def _cfg() -> ScoringConfig:
    return ScoringConfig.model_validate({
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {
            "strong_buy_candidate": 80, "buy_candidate": 60,
            "watch": 40, "avoid": 20,
        },
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v1",
    })


def _all_high() -> dict[str, FactorScore]:
    refs = ("r",)
    return {
        "valuation_cost": FactorScore(score=90, raw_refs=refs, components={}),
        "risk":           FactorScore(score=85, raw_refs=refs, components={}),
        "quality":        FactorScore(score=80, raw_refs=refs, components={}),
        "macro_fit":      FactorScore(score=85, raw_refs=refs, components={}),
        "thesis_news":    FactorScore(score=80, raw_refs=refs, components={}),
    }


def test_compose_high_scores_to_strong_buy() -> None:
    out = compose_score(instrument_id="VTI", factors=_all_high(), data_completeness=0.95, cfg=_cfg())
    assert isinstance(out, InstrumentScore)
    assert out.composite_score >= 80
    assert out.action == "strong_buy_candidate"
    assert out.conviction == "high"


def test_low_completeness_demotes_conviction() -> None:
    out = compose_score(instrument_id="VTI", factors=_all_high(), data_completeness=0.50, cfg=_cfg())
    assert out.conviction in ("low", "med")
    assert out.action != "strong_buy_candidate" or out.conviction != "high"


def test_avoid_zone() -> None:
    refs = ("r",)
    factors = {
        k: FactorScore(score=10, raw_refs=refs, components={})
        for k in ("valuation_cost", "risk", "quality", "macro_fit", "thesis_news")
    }
    out = compose_score(instrument_id="X", factors=factors, data_completeness=1.0, cfg=_cfg())
    assert out.action == "strong_avoid"
