import pytest
from pydantic import ValidationError
from irc.schemas.monitor import MonitorConfig

_MIN = {
    "schema_version": 1,
    "funds": [
        {"id": "008986", "name_cn": "广发上海金ETF联接A", "market": "cn_off_exchange",
         "analysis_profile": "gold", "themes": ["gold_drivers", "geopolitics"],
         "constituent_news": False},
    ],
}


def test_minimal_config_parses():
    cfg = MonitorConfig.model_validate(_MIN)
    assert cfg.funds[0].id == "008986"
    assert cfg.funds[0].analysis_profile == "gold"


def test_id_must_be_six_digits():
    bad = {**_MIN, "funds": [{**_MIN["funds"][0], "id": "ABC123"}]}
    with pytest.raises(ValidationError):
        MonitorConfig.model_validate(bad)


def test_unknown_market_rejected():
    bad = {**_MIN, "funds": [{**_MIN["funds"][0], "market": "nasdaq"}]}
    with pytest.raises(ValidationError):
        MonitorConfig.model_validate(bad)


def test_unknown_profile_rejected():
    bad = {**_MIN, "funds": [{**_MIN["funds"][0], "analysis_profile": "crypto"}]}
    with pytest.raises(ValidationError):
        MonitorConfig.model_validate(bad)
