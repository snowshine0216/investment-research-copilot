from __future__ import annotations
from evals.research.metrics import theme_coverage, ldr_citation_validity


def _make_reports():
    return [
        {"theme": "macro", "type": "ldr", "citations": ["src1"]},
        {"theme": "sector_rotation", "type": "ldr", "citations": ["src2"]},
        {"theme": "credit", "type": "summary", "citations": []},
        {"theme": "commodity", "type": "ldr", "citations": ["src3"]},
        {"theme": "geopolitics", "type": "ldr", "citations": []},
        {"theme": "rates", "type": "ldr", "citations": ["src4"]},
        {"theme": "equity_valuation", "type": "ldr", "citations": ["src5"]},
    ]


def test_theme_coverage_all_seven():
    reports = _make_reports()
    assert theme_coverage(reports) == 7


def test_theme_coverage_partial():
    reports = [
        {"theme": "macro", "type": "ldr", "citations": ["x"]},
        {"theme": "rates", "type": "ldr", "citations": ["y"]},
    ]
    assert theme_coverage(reports) == 2


def test_theme_coverage_empty():
    assert theme_coverage([]) == 0


def test_ldr_citation_validity_all_valid():
    reports = _make_reports()
    # 6 LDR reports; sample_size=5 takes first 5:
    # macro(valid), sector_rotation(valid), commodity(valid), geopolitics(invalid), rates(valid)
    # → 4/5 = 0.8
    rate = ldr_citation_validity(reports)
    assert abs(rate - 4 / 5) < 1e-9


def test_ldr_citation_validity_no_ldr():
    reports = [{"theme": "macro", "type": "summary", "citations": []}]
    assert ldr_citation_validity(reports) == 1.0


def test_ldr_citation_validity_empty():
    assert ldr_citation_validity([]) == 1.0
