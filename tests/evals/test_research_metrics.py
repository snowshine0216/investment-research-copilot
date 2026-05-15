from __future__ import annotations
from evals.research.metrics import (
    theme_coverage,
    research_success_rate,
    research_citation_validity,
    research_failure_visibility,
)


def _status_themes():
    return [
        {"theme": "us_monetary", "citation_count": 2, "failure_reason": ""},
        {"theme": "cn_monetary", "citation_count": 1, "failure_reason": ""},
        {"theme": "gold_drivers", "citation_count": 0, "failure_reason": "timeout"},
    ]


def test_theme_coverage_counts_matching_required_themes():
    themes = _status_themes()
    # us_monetary and cn_monetary match; gold_drivers also matches; 3 total
    assert theme_coverage(themes) == 3


def test_theme_coverage_all_seven():
    themes = [
        {"theme": t, "citation_count": 1, "failure_reason": ""}
        for t in ("us_monetary", "us_fiscal_politics", "cn_monetary",
                  "cn_equity_property_policy", "geopolitics", "gold_drivers", "holdings_sector")
    ]
    assert theme_coverage(themes) == 7


def test_theme_coverage_empty():
    assert theme_coverage([]) == 0


def test_research_success_rate_counts_non_failed_themes():
    assert research_success_rate(_status_themes()) == 2 / 3


def test_research_success_rate_empty():
    assert research_success_rate([]) == 1.0


def test_research_citation_validity_requires_citations_on_successful_themes():
    # 2 successful themes: us_monetary (count=2, ok) and cn_monetary (count=1, ok)
    assert research_citation_validity(_status_themes()) == 1.0


def test_research_citation_validity_no_successful_themes():
    themes = [{"theme": "x", "citation_count": 0, "failure_reason": "error"}]
    assert research_citation_validity(themes) == 1.0


def test_research_failure_visibility_requires_reason_for_failed_themes():
    assert research_failure_visibility(_status_themes()) == 1.0


def test_research_failure_visibility_missing_reason():
    themes = [{"theme": "x", "citation_count": 0, "failure_reason": ""}]
    # failure_reason="" is falsy → not failed → visibility = 1.0
    assert research_failure_visibility(themes) == 1.0


def test_research_failure_visibility_truly_invisible_failure():
    # A theme where failure_reason has whitespace only
    themes = [{"theme": "x", "citation_count": 0, "failure_reason": "  "}]
    # "  " is truthy → this is a failure
    # "  ".strip() = "" → not visible → 0/1 = 0.0
    assert research_failure_visibility(themes) == 0.0
