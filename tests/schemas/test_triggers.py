from __future__ import annotations
from irc.schemas.triggers import TriggersConfig


def test_triggers_config_minimal():
    raw = {
        "triggers": {
            "real_yield_low": {"data_field": "macro.real_yield_10y_tips", "comparator": "<=", "threshold": 0.0},
            "vix_high": {"data_field": "macro.vix", "comparator": ">", "threshold": 25.0},
        }
    }
    cfg = TriggersConfig.model_validate(raw)
    assert "real_yield_low" in cfg.triggers


import pytest
from pydantic import ValidationError
from irc.schemas.triggers import TriggerSpec


def test_invalid_comparator_rejected():
    with pytest.raises(ValidationError):
        TriggerSpec(data_field="macro.vix", comparator="????", threshold=20.0)
