"""D1 oracle + properties for valuation_state_score / heat_score (spec §3.1).

re-expressed lookup / decision table oracle; ordering monotonicity (cheaper→higher;
more crowded→lower); None on unrecognised state / no data.
"""
from __future__ import annotations
from hypothesis import given, strategies as st
from irc.monitor.factor_maps import valuation_state_score, heat_score
from tests.monitor import _oracle

_KNOWN_STATES = ("cheap", "fair_cheap", "fair", "fair_expensive", "expensive")


@given(state=st.sampled_from(_KNOWN_STATES + ("???", "", "unknown")))
def test_valuation_matches_oracle(state):
    assert valuation_state_score(state) == _oracle.valuation_oracle(state)


def test_valuation_ordering_cheaper_is_higher():
    scores = [valuation_state_score(s) for s in _KNOWN_STATES]
    assert scores == sorted(scores, reverse=True)  # strictly descending cheap→expensive
    assert scores[0] == 1.0 and scores[-1] == -1.0


@given(state=st.text(min_size=0, max_size=12))
def test_valuation_none_on_unrecognised(state):
    if state not in _KNOWN_STATES:
        assert valuation_state_score(state) is None


@given(
    restricted=st.sampled_from([None, True, False]),
    aum=st.sampled_from([None, 0.0, 19.9, 20.0, 30.0]),
)
def test_heat_matches_oracle(restricted, aum):
    assert heat_score(restricted=restricted, aum_delta_pct=aum) == \
        _oracle.heat_oracle(restricted=restricted, aum_delta_pct=aum)


def test_heat_more_crowded_is_lower():
    calm = heat_score(restricted=False, aum_delta_pct=0.0)
    one = heat_score(restricted=True, aum_delta_pct=0.0)
    both = heat_score(restricted=True, aum_delta_pct=30.0)
    assert calm > one > both


def test_heat_none_when_no_data():
    assert heat_score(restricted=None, aum_delta_pct=None) is None
