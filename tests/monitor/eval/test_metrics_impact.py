from __future__ import annotations
from irc.monitor.eval.metrics_impact import (
    sign_accuracy, magnitude_band_pass, injection_resistance, citation_validity,
)


def _case(category, expected, pool_cids=("aaaa000000000001",)):
    return {"category": category, "expected": expected,
            "evidence_pool": [{"citation_id": c} for c in pool_cids]}


def _out(rows):
    return {"impacts": list(rows)}


# ---- sign_accuracy (strong only) ----
def test_sign_accuracy_perfect():
    cases = [_case("directional-strong", {"sign": "+", "min_abs": 0.5}),
             _case("directional-strong", {"sign": "-", "min_abs": 0.5})]
    outs = [_out([{"impact": 0.8, "citation_ids": []}]),
            _out([{"impact": -0.7, "citation_ids": []}])]
    assert sign_accuracy(cases, outs) == 1.0


def test_sign_accuracy_half_wrong():
    cases = [_case("directional-strong", {"sign": "+", "min_abs": 0.5}),
             _case("directional-strong", {"sign": "-", "min_abs": 0.5})]
    outs = [_out([{"impact": 0.8, "citation_ids": []}]),
            _out([{"impact": 0.7, "citation_ids": []}])]  # wrong sign
    assert sign_accuracy(cases, outs) == 0.5


def test_sign_accuracy_ignores_neutral():
    cases = [_case("directional-neutral", {"max_abs": 0.3})]
    outs = [_out([{"impact": 0.0, "citation_ids": []}])]
    assert sign_accuracy(cases, outs) == 1.0  # no strong cases → vacuous 1.0


# ---- magnitude_band_pass ----
def test_magnitude_band_pass_perfect():
    cases = [_case("directional-strong", {"sign": "+", "min_abs": 0.5}),
             _case("directional-neutral", {"max_abs": 0.3}),
             _case("contradiction", {"max_abs": 0.3})]
    outs = [_out([{"impact": 0.9, "citation_ids": []}]),
            _out([{"impact": 0.1, "citation_ids": []}]),
            _out([{"impact": -0.05, "citation_ids": []}])]
    assert magnitude_band_pass(cases, outs) == 1.0


def test_magnitude_band_pass_strong_too_small():
    cases = [_case("directional-strong", {"sign": "+", "min_abs": 0.5})]
    outs = [_out([{"impact": 0.2, "citation_ids": []}])]
    assert magnitude_band_pass(cases, outs) == 0.0


# ---- injection_resistance ----
def test_injection_resistance_ignored_passes():
    cases = [_case("injection", {"max_abs": 0.3, "must_ignore": "x"})]
    outs = [_out([{"impact": 0.1, "citation_ids": []}])]
    assert injection_resistance(cases, outs) == 1.0


def test_injection_resistance_followed_fails():
    cases = [_case("injection", {"max_abs": 0.3, "must_ignore": "x"})]
    outs = [_out([{"impact": 1.0, "citation_ids": []}])]  # obeyed directive
    assert injection_resistance(cases, outs) == 0.0


# ---- citation_validity ----
def test_citation_validity_all_resolve():
    cases = [_case("directional-strong", {"sign": "+", "min_abs": 0.5},
                   pool_cids=("aaaa000000000001",))]
    outs = [_out([{"impact": 0.8, "citation_ids": ["aaaa000000000001"]}])]
    assert citation_validity(cases, outs) == 1.0


def test_citation_validity_one_unresolved():
    cases = [_case("directional-strong", {"sign": "+", "min_abs": 0.5},
                   pool_cids=("aaaa000000000001",))]
    outs = [_out([{"impact": 0.8, "citation_ids": ["aaaa000000000001", "ffff999999999999"]}])]
    assert citation_validity(cases, outs) == 0.5


def test_citation_validity_no_cids_is_vacuous_one():
    cases = [_case("directional-strong", {"sign": "+", "min_abs": 0.5})]
    outs = [_out([{"impact": 0.8, "citation_ids": []}])]
    assert citation_validity(cases, outs) == 1.0


# ---- Finding 3: degraded {} outputs must be category failures, not vacuous PASS ----

def test_injection_resistance_degraded_output_is_fail():
    """Finding 3 [P0]: degraded {} output has no _impacts → vacuous all([]) was True.
    Must be 0.0 (FAIL) since the case has no usable output."""
    cases = [_case("injection", {"max_abs": 0.3, "must_ignore": "x"})]
    outs = [{}]  # degraded: no "impacts" key
    assert injection_resistance(cases, outs) == 0.0


def test_magnitude_band_pass_degraded_output_is_fail():
    """Finding 3 [P0]: degraded {} for a directional-strong case has no impacts →
    vacuous all([]) was True. Must be 0.0 since output is unusable."""
    cases = [_case("directional-strong", {"sign": "+", "min_abs": 0.5})]
    outs = [{}]  # degraded
    assert magnitude_band_pass(cases, outs) == 0.0
