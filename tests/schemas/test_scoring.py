from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.scoring import ScoringConfig


def test_scoring_config_default_weights_sum_to_one():
    raw = {
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {
            "strong_buy_candidate": 80, "buy_candidate": 60, "watch": 40, "avoid": 20,
        },
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "2026-05-07-v1",
    }
    cfg = ScoringConfig.model_validate(raw)
    assert sum(cfg.factor_weights.values()) == pytest.approx(1.0)


def test_scoring_weights_must_sum_to_one():
    raw = {
        "factor_weights": {
            "valuation_cost": 0.50, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {"strong_buy_candidate": 80, "buy_candidate": 60, "watch": 40, "avoid": 20},
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v",
    }
    with pytest.raises(ValidationError, match="sum"):
        ScoringConfig.model_validate(raw)


def test_action_thresholds_must_be_descending():
    raw = {
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {
            "strong_buy_candidate": 60, "buy_candidate": 80, "watch": 40, "avoid": 20,
        },
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v",
    }
    with pytest.raises(ValidationError, match="descending"):
        ScoringConfig.model_validate(raw)


def test_action_thresholds_missing_key_raises_validation_error():
    raw = {
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {"strong_buy_candidate": 80},  # 3 keys missing
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v",
    }
    with pytest.raises(ValidationError):
        ScoringConfig.model_validate(raw)
