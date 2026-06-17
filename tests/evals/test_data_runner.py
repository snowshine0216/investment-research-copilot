from __future__ import annotations

from evals.data.runner import build_freshness_metrics, MAINTAINED_FRESHNESS_PAIRS


def test_build_freshness_metrics_drops_vestigial_openbb_prices():
    """openbb no longer writes the prices table (US is QDII-proxy; prices come
    only from akshare). Grading the dead (openbb, prices) seed is a false FAIL,
    so it must be excluded — while live openbb macro stays graded."""
    per_source = [
        ("openbb", {"prices": 1125, "macro_series": 2}),
        ("akshare", {"prices": 2, "nav_history": 2}),
    ]
    metrics = build_freshness_metrics(per_source)
    names = {m.name for m in metrics}
    assert "freshness_openbb_prices_days" not in names
    assert "freshness_openbb_macro_series_days" in names
    assert "freshness_akshare_prices_days" in names
    assert "freshness_akshare_nav_history_days" in names


def test_build_freshness_metrics_classifies_status():
    per_source = [("akshare", {"prices": 2, "nav_history": 9})]
    by_name = {m.name: m for m in build_freshness_metrics(per_source)}
    assert by_name["freshness_akshare_prices_days"].status == "PASS"   # 2 not > 2
    assert by_name["freshness_akshare_nav_history_days"].status == "FAIL"  # 9 > 7


def test_maintained_pairs_are_what_the_pipeline_writes():
    assert MAINTAINED_FRESHNESS_PAIRS == frozenset({
        ("akshare", "prices"),
        ("akshare", "nav_history"),
        ("openbb", "macro_series"),
    })
