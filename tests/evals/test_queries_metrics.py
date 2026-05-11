from __future__ import annotations
from evals.queries.metrics import (
    median_response_time,
    citation_attached_per_response,
    internal_consistency_with_latest_memo,
)

_MEMO = "The portfolio has equity exposure with valuation driven by earnings growth and macro tailwinds."


def _make_queries():
    return [
        {"response_time_s": 5.0, "citations": ["src1"], "response": "equity exposure macro earnings"},
        {"response_time_s": 15.0, "citations": ["src2"], "response": "valuation driven growth"},
        {"response_time_s": 25.0, "citations": [], "response": "portfolio tailwinds"},
        {"response_time_s": 10.0, "citations": ["src3"], "response": "macro driven"},
    ]


def test_median_response_time():
    queries = _make_queries()
    median = median_response_time(queries)
    assert median == 12.5  # median of [5, 10, 15, 25]


def test_median_response_time_empty():
    assert median_response_time([]) == 0.0


def test_citation_attached_per_response():
    queries = _make_queries()
    rate = citation_attached_per_response(queries)
    assert rate == 0.75  # 3 out of 4 have citations


def test_citation_attached_per_response_all():
    queries = [{"citations": ["x"], "response_time_s": 1.0, "response": ""}] * 3
    assert citation_attached_per_response(queries) == 1.0


def test_citation_attached_per_response_empty():
    assert citation_attached_per_response([]) == 1.0


def test_internal_consistency_with_memo():
    queries = _make_queries()
    rate = internal_consistency_with_latest_memo(queries, _MEMO)
    assert rate == 1.0  # all responses share tokens with memo


def test_internal_consistency_no_overlap():
    queries = [{"response": "ZZZZ QQQQ", "citations": [], "response_time_s": 1.0}]
    rate = internal_consistency_with_latest_memo(queries, "hello world something else")
    # "ZZZZ" and "QQQQ" are 4 chars but not in memo
    assert rate == 0.0


def test_internal_consistency_empty():
    assert internal_consistency_with_latest_memo([], _MEMO) == 1.0
