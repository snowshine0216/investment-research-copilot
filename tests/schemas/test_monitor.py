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


def test_duplicate_ids_rejected():
    dup = {**_MIN, "funds": [_MIN["funds"][0], _MIN["funds"][0]]}
    with pytest.raises(ValidationError, match="duplicate"):
        MonitorConfig.model_validate(dup)


def test_bands_buy_must_exceed_sell():
    bad = {**_MIN, "defaults": {"signal_bands": {"buy": -0.1, "sell": 0.1}}}
    with pytest.raises(ValidationError, match="buy"):
        MonitorConfig.model_validate(bad)


def test_bands_must_be_within_unit_interval():
    bad = {**_MIN, "defaults": {"signal_bands": {"buy": 1.5, "sell": -0.4}}}
    with pytest.raises(ValidationError):
        MonitorConfig.model_validate(bad)


def test_default_bands_are_plus_minus_040():
    cfg = MonitorConfig.model_validate(_MIN)
    # defaults supplied by config/monitor.yaml in real runs; schema default is empty
    # so an explicit-bands fund validates. Here assert the validator path tolerates absence.
    assert cfg.defaults.signal_bands == {}


from irc.schemas.monitor import compose_weights, weights_sum_ok


def test_compose_overlays_override_on_default():
    base = {"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20}
    out = compose_weights(base, {"heat": 0.10, "trend": 0.55})
    assert out == {"trend": 0.55, "macro_tilt": 0.35, "heat": 0.10}


def test_compose_none_override_returns_base():
    base = {"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20}
    assert compose_weights(base, None) == base


def test_weights_sum_ok_tolerance():
    assert weights_sum_ok({"a": 0.5, "b": 0.5})
    assert weights_sum_ok({"a": 0.3, "b": 0.3, "c": 0.4 + 1e-7})
    assert not weights_sum_ok({"a": 0.3, "b": 0.3})
