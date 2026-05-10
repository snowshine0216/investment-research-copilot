from __future__ import annotations
from irc.schemas.overrides import OverridesConfig, OverridesFile


def test_overrides_lists_default_empty():
    cfg = OverridesConfig.model_validate({"boost_list": [], "ban_list": []})
    assert cfg.boost_list == []


def test_populated_overrides_round_trip():
    payload = {"include": [{"instrument_id": "VTI", "reason": "core"}],
                "exclude": [{"instrument_id": "BABA", "reason": "concentration"}]}
    o = OverridesFile.model_validate(payload)
    assert o.include[0].instrument_id == "VTI"
    assert o.exclude[0].instrument_id == "BABA"
