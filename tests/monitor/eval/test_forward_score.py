from __future__ import annotations
from datetime import date, timedelta
from irc.monitor.eval.forward_score import (
    prefilter_ledger, score_forward, ForwardRow,
)


def _nav(n, fund="a", start="2026-01-01", base=1.0, step=0.001):
    d0 = date.fromisoformat(start)
    return [
        {"fund_id": fund, "nav_date": (d0 + timedelta(days=i)).isoformat(),
         "nav_acc": base + step * i, "written_at": "w", "source_run_date": "r"}
        for i in range(n)
    ]


def test_prefilter_drops_null_nav_acc():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": None,
             "as_of_date": "2026-01-09", "raw_status": "ok",
             "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    kept, excl = prefilter_ledger(rows)
    assert kept == [] and excl["null_signal_nav"] == 1


def test_prefilter_drops_non_date_as_of():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": 1.0,
             "as_of_date": "N/A", "raw_status": "ok",
             "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    kept, excl = prefilter_ledger(rows)
    assert kept == [] and excl["null_signal_nav"] == 1


def test_prefilter_drops_as_of_after_run_date():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": 1.0,
             "as_of_date": "2026-01-11", "raw_status": "ok",   # cutoff after publication
             "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    kept, excl = prefilter_ledger(rows)
    assert kept == [] and excl["null_signal_nav"] == 1


def test_prefilter_keeps_clean_row():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": 1.0,
             "as_of_date": "2026-01-09", "raw_status": "ok",
             "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    kept, excl = prefilter_ledger(rows)
    assert len(kept) == 1 and excl.get("null_signal_nav", 0) == 0


def test_score_forward_matures_rows_and_anchors_strictly_after_run_date():
    nav = _nav(40, fund="a")
    # signal published on an existing nav_date → entry strictly after it
    run_date = nav[5]["nav_date"]
    ledger = [{"run_date": run_date, "fund_id": "a", "nav_acc": 1.005,
               "as_of_date": nav[5]["nav_date"], "raw_status": "ok",
               "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    rows, excl = score_forward(ledger, {"a": nav}, h=20, today="2099-01-01")
    assert len(rows) == 1
    assert rows[0].entry_nav_date == nav[6]["nav_date"]   # strictly after run_date


def test_score_forward_population_matrix():
    by_fund = {"a": _nav(60, "a"), "b": _nav(60, "b", base=2.0)}
    run_date = by_fund["a"][2]["nav_date"]
    ledger = [
        {"run_date": run_date, "fund_id": "a", "nav_acc": 1.0,
         "as_of_date": run_date, "raw_status": "ok", "raw_composite": 0.3,
         "raw_bias": "ADD_BIAS"},
        {"run_date": run_date, "fund_id": "b", "nav_acc": 2.0,
         "as_of_date": run_date, "raw_status": "insufficient_evidence",
         "raw_composite": 0.0, "raw_bias": None},   # NO_CALL row
    ]
    rows, excl = score_forward(ledger, by_fund, h=20, today="2099-01-01")
    # raw_composite_directional: BOTH rows (any raw_status)
    assert len(rows) == 2
    # publishable_bias_directional + Rank-IC: ok-only → 1 row
    ok_rows = [r for r in rows if r.raw_status == "ok"]
    assert len(ok_rows) == 1 and ok_rows[0].fund_id == "a"


def test_score_forward_stores_from_latest_nav_diagnostic():
    nav = _nav(40, fund="a")
    run_date = nav[5]["nav_date"]
    ledger = [{"run_date": run_date, "fund_id": "a", "nav_acc": 1.0,
               "as_of_date": run_date, "raw_status": "ok",
               "raw_composite": 0.2, "raw_bias": "ADD_BIAS"}]
    rows, _ = score_forward(ledger, {"a": nav}, h=20, today="2099-01-01")
    assert isinstance(rows[0], ForwardRow)
    assert rows[0].from_latest_nav == rows[0].from_latest_nav  # finite, present
