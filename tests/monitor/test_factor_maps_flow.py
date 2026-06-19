import pytest
from irc.monitor.factor_maps import flow_score


@pytest.mark.parametrize("pct,score", [
    (3.0, 1.0), (1.0, 0.5), (0.0, 0.0), (-1.0, -0.5), (-3.0, -1.0),
])
def test_flow_score_percent_point_bands(pct, score):
    assert flow_score(pct) == score


@pytest.mark.parametrize("ratio_value", [0.01, 0.03])
def test_flow_score_ratio_canary_lands_in_deadband(ratio_value):
    assert flow_score(ratio_value) == 0.0
