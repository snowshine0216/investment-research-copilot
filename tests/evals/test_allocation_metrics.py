from __future__ import annotations
from evals.allocation.metrics import (
    weight_sum,
    in_band_per_class,
    effective_n,
    currency_in_tolerance,
    max_pair_correlation_1y,
)


def _make_allocation():
    return {
        "target_weights_per_class": {"equity": 0.6, "bond": 0.3, "cash": 0.1},
        "selected_instruments": [
            {"ticker": "VTI", "target_weight": 0.3},
            {"ticker": "AGG", "target_weight": 0.3},
            {"ticker": "GLD", "target_weight": 0.2},
            {"ticker": "TLT", "target_weight": 0.2},
        ],
        "currency_exposure": {"USD": 0.7, "EUR": 0.2, "JPY": 0.1},
    }


def test_weight_sum():
    alloc = _make_allocation()
    assert abs(weight_sum(alloc) - 1.0) < 1e-9


def test_in_band_per_class_all_in():
    alloc = _make_allocation()
    bands = {"equity": (0.5, 0.7), "bond": (0.2, 0.4)}
    assert in_band_per_class(alloc, bands) == 1.0


def test_in_band_per_class_some_out():
    alloc = _make_allocation()
    bands = {"equity": (0.7, 0.9), "bond": (0.2, 0.4)}  # equity out of band
    assert in_band_per_class(alloc, bands) == 0.5


def test_in_band_per_class_empty_bands():
    alloc = _make_allocation()
    assert in_band_per_class(alloc, {}) == 1.0


def test_effective_n():
    alloc = _make_allocation()
    en = effective_n(alloc)
    # weights: 0.3, 0.3, 0.2, 0.2 -> sum of squares = 0.09+0.09+0.04+0.04 = 0.26
    expected = 1.0 / (0.3**2 + 0.3**2 + 0.2**2 + 0.2**2)
    assert abs(en - expected) < 1e-9


def test_effective_n_equal_weights():
    alloc = {"selected_instruments": [{"target_weight": 0.25}] * 4, "target_weights_per_class": {}}
    en = effective_n(alloc)
    assert abs(en - 4.0) < 1e-9


def test_currency_in_tolerance_all_in():
    alloc = _make_allocation()
    targets = {"USD": 0.7, "EUR": 0.2}
    assert currency_in_tolerance(alloc, targets) == 1.0


def test_currency_in_tolerance_out():
    alloc = _make_allocation()
    targets = {"USD": 0.5}  # actual is 0.7, diff = 0.2 > 0.05
    assert currency_in_tolerance(alloc, targets) == 0.0


def test_max_pair_correlation_1y():
    matrix = {
        "VTI": {"VTI": 1.0, "AGG": 0.3, "GLD": 0.1},
        "AGG": {"VTI": 0.3, "AGG": 1.0, "GLD": -0.2},
        "GLD": {"VTI": 0.1, "AGG": -0.2, "GLD": 1.0},
    }
    max_corr = max_pair_correlation_1y(matrix)
    assert abs(max_corr - 0.3) < 1e-9


def test_max_pair_correlation_1y_empty():
    assert max_pair_correlation_1y({}) == 0.0
