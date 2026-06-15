import pytest
from irc.monitor.profiles import (
    PROFILES, eligible_factors, default_weights, theme_query_seed, THEME_SEEDS,
)
from irc.schemas.monitor import weights_sum_ok


@pytest.mark.parametrize("profile", list(PROFILES))
def test_default_weights_sum_to_one(profile):
    assert weights_sum_ok(default_weights(profile))


def test_gold_excludes_valuation_and_constituent():
    elig = eligible_factors("gold")
    assert "valuation" not in elig and "constituent" not in elig
    assert {"trend", "macro_tilt", "heat"} == set(elig)


def test_qdii_global_excludes_valuation_keeps_constituent():
    elig = eligible_factors("qdii_global")
    assert "valuation" not in elig
    assert "constituent" in elig


def test_active_cn_equity_full_vector():
    assert set(eligible_factors("active_cn_equity")) == {
        "trend", "valuation", "heat", "macro_tilt", "constituent"
    }


def test_qdii_china_us_internet_valuation_eligible():
    assert "valuation" in eligible_factors("qdii_china_us_internet")


def test_weights_only_cover_eligible_factors():
    for profile in PROFILES:
        assert set(default_weights(profile)) <= set(eligible_factors(profile))


def test_new_theme_seeds_present():
    assert "global_growth" in THEME_SEEDS and "fx_cny" in THEME_SEEDS
    assert theme_query_seed("gold_drivers")        # reused key resolves


def test_lookthrough_kind_per_profile():
    assert PROFILES["gold"].lookthrough is None
    assert PROFILES["active_cn_equity"].lookthrough == "active_fund"
    assert PROFILES["qdii_global"].lookthrough == "fund_level"
    assert PROFILES["qdii_china_us_internet"].lookthrough == "fund_level"
