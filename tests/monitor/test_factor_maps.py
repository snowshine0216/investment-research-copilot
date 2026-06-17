import pytest
from irc.monitor.factor_maps import valuation_state_score, heat_score


@pytest.mark.parametrize("state,expected", [
    ("cheap", 1.0), ("reasonable_low", 0.5), ("fair", 0.0),
    ("expensive", -0.5), ("very_expensive", -1.0),
])
def test_valuation_map(state, expected):
    assert valuation_state_score(state) == expected


def test_valuation_unknown_state_is_none():
    assert valuation_state_score("???") is None


@pytest.mark.parametrize("restricted,aum_delta_pct,expected", [
    (True, 30.0, -1.0),     # 限购 + rapid inflow → overheated
    (True, 0.0, -0.5),      # restricted, flat flow
    (False, 30.0, -0.5),    # rapid inflow alone
    (False, 0.0, 0.3),      # calm
])
def test_heat_map(restricted, aum_delta_pct, expected):
    assert heat_score(restricted=restricted, aum_delta_pct=aum_delta_pct) == expected


def test_heat_no_data_is_none():
    assert heat_score(restricted=None, aum_delta_pct=None) is None
