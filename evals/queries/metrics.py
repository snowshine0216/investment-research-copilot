from __future__ import annotations
import statistics


def median_response_time(queries: list[dict]) -> float:
    """Median response time in seconds across all queries."""
    times = [q.get("response_time_s", 0.0) for q in queries]
    if not times:
        return 0.0
    return statistics.median(times)


def citation_attached_per_response(queries: list[dict]) -> float:
    """Fraction of query responses that have at least one citation."""
    if not queries:
        return 1.0
    with_citation = sum(1 for q in queries if q.get("citations"))
    return with_citation / len(queries)


def internal_consistency_with_latest_memo(
    queries: list[dict],
    memo_text: str,
) -> float:
    """Fraction of query responses whose key facts appear in the latest memo."""
    if not queries:
        return 1.0
    consistent = sum(
        1 for q in queries
        if _response_consistent(q.get("response", ""), memo_text)
    )
    return consistent / len(queries)


def _response_consistent(response: str, memo_text: str) -> bool:
    """Heuristic: response is consistent if it shares at least one significant token with memo."""
    if not response or not memo_text:
        return True
    tokens = {w for w in response.split() if len(w) >= 4}
    memo_tokens = set(memo_text.split())
    return bool(tokens & memo_tokens)
