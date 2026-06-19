"""D1 properties for build_factor_scores (spec §3.1: properties only).

Each score is (eligible=True, value∈[-1,1], reason="") OR
(eligible=False, value=None, reason∈KNOWN_NA_REASONS); per-profile eligibility
correctness; N/A reason coverage.
"""
from __future__ import annotations
from hypothesis import given, strategies as st
from irc.monitor.factors import build_factor_scores, FactorInputs, KNOWN_NA_REASONS
from irc.monitor.news_factor import ImpactRow
from irc.monitor.profiles import PROFILES, eligible_factors

_PROFILES = tuple(PROFILES.keys())
_FACTOR_NAMES = ("trend", "valuation", "heat", "macro_tilt", "constituent", "flow")


def _nav(n):
    return tuple((f"d{i:04d}", 1.0 + 0.001 * i) for i in range(n))


@st.composite
def _impact_rows(draw, keys):
    n = draw(st.integers(0, 4))
    return tuple(
        ImpactRow(
            key=draw(st.sampled_from(keys)),
            weight=draw(st.floats(0.0, 100.0, allow_nan=False)),
            impact=draw(st.floats(-1.0, 1.0, allow_nan=False)),
            confidence=draw(st.floats(0.0, 1.0, allow_nan=False)),
        )
        for _ in range(n)
    )


@st.composite
def _inputs(draw):
    return FactorInputs(
        acc_nav=_nav(draw(st.integers(0, 300))),
        minimum_observations=draw(st.integers(1, 251)),
        valuation_state=draw(st.sampled_from(
            [None, "cheap", "fair", "expensive", "???"])),
        valuation_cached=draw(st.booleans()),
        restricted=draw(st.sampled_from([None, True, False])),
        aum_delta_pct=draw(st.sampled_from([None, 0.0, 30.0])),
        macro_rows=draw(_impact_rows(("a", "b", "c"))),
        constituent_rows=draw(_impact_rows(("x", "y"))),
    )


@given(profile=st.sampled_from(_PROFILES), inp=_inputs())
def test_every_score_is_eligible_value_coherent(profile, inp):
    for s in build_factor_scores(profile, inp):
        if s.eligible:
            assert s.value is not None and -1.0 <= s.value <= 1.0
            assert s.reason == ""
        else:
            assert s.value is None
            assert s.reason in KNOWN_NA_REASONS


@given(profile=st.sampled_from(_PROFILES), inp=_inputs())
def test_ineligible_factors_are_profile_ineligible(profile, inp):
    elig = set(eligible_factors(profile))
    by_name = {s.name: s for s in build_factor_scores(profile, inp)}
    for name in _FACTOR_NAMES:
        if name not in elig:
            assert by_name[name].eligible is False
            assert by_name[name].reason == "profile_ineligible"


@given(profile=st.sampled_from(_PROFILES), inp=_inputs())
def test_all_six_factor_names_present_exactly_once(profile, inp):
    names = [s.name for s in build_factor_scores(profile, inp)]
    assert names == list(_FACTOR_NAMES)
