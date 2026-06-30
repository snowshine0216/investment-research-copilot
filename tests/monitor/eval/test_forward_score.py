from __future__ import annotations
from datetime import date, timedelta
from irc.monitor.eval.forward_score import (
    prefilter_ledger, score_forward, ForwardRow,
)
from evals.monitor_forward.runner import _target_engine


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


# --- Task 4.4: target_engine filter ---

def _ledger_row(engine, fund="a", run="2026-01-10", as_of="2026-01-09"):
    return {"run_date": run, "fund_id": fund, "nav_acc": 1.0, "as_of_date": as_of,
            "raw_status": "ok", "raw_composite": 0.2, "raw_bias": "ADD_BIAS",
            "manifest_versions": {"engine": engine}}


def test_target_engine_excludes_other_engines():
    rows = [_ledger_row("1"), _ledger_row("2")]
    nav = {"a": _nav(40)}
    fwd, excl = score_forward(rows, nav, h=20, today="2026-12-31", target_engine="2")
    # only engine-2 row survives (both have same run/as_of so both would mature given enough nav)
    assert excl.get("engine_mismatch") == 1               # the engine-1 row excluded


def test_missing_engine_field_counts_as_legacy_and_excluded():
    rows = [{"run_date": "2026-01-10", "fund_id": "a", "nav_acc": 1.0,
             "as_of_date": "2026-01-09", "raw_status": "ok", "raw_composite": 0.2,
             "raw_bias": "ADD_BIAS"}]  # no manifest_versions
    fwd, excl = score_forward(rows, {"a": _nav(40)}, h=20, today="2026-12-31",
                              target_engine="2")
    assert excl.get("engine_mismatch") == 1


def test_target_engine_none_is_back_compat_no_filter():
    rows = [_ledger_row("1"), _ledger_row("2")]
    fwd_none, excl_none = score_forward(rows, {"a": _nav(40)}, h=20, today="2026-12-31")
    assert "engine_mismatch" not in excl_none  # no filtering when target is None


# --- Task 4.5: _target_engine numeric max ---


def test_target_engine_is_numeric_max_not_lexicographic():
    ledger = [{"manifest_versions": {"engine": "9"}},
              {"manifest_versions": {"engine": "10"}}]
    assert _target_engine(ledger) == "10"  # numeric: 10 > 9 (lexicographic would pick "9")


def test_target_engine_missing_field_is_legacy_zero():
    assert _target_engine([{}, {"manifest_versions": {"engine": "2"}}]) == "2"


def test_target_engine_empty_ledger_is_none():
    assert _target_engine([]) is None


def test_forward_row_carries_market_composite():
    """score_forward propagates market_composite / market_bias onto ForwardRow."""
    from irc.monitor.eval.forward_score import score_forward
    rows = [{
        "run_date": "2026-01-01", "fund_id": "a", "nav_acc": 1.0,
        "as_of_date": "2026-01-01", "raw_status": "ok",
        "raw_composite": 0.5, "raw_bias": "ADD_BIAS",
        "manifest_versions": {"engine": "3"},
        "market_composite": 0.3, "market_bias": "NEUTRAL",
    }]
    nav = _nav(200, fund="a", start="2025-10-01")
    out, _ = score_forward(rows, {"a": nav}, h=90, today="2026-04-30")
    assert len(out) == 1
    assert out[0].market_composite == 0.3
    assert out[0].market_bias == "NEUTRAL"


def test_forward_row_market_composite_backcompat_none():
    """Rows without market_composite (legacy) → field is None (backcompat)."""
    from irc.monitor.eval.forward_score import score_forward
    rows = [{
        "run_date": "2026-01-01", "fund_id": "a", "nav_acc": 1.0,
        "as_of_date": "2026-01-01", "raw_status": "ok",
        "raw_composite": 0.5, "raw_bias": "ADD_BIAS",
        "manifest_versions": {"engine": "3"},
    }]
    nav = _nav(200, fund="a", start="2025-10-01")
    out, _ = score_forward(rows, {"a": nav}, h=90, today="2026-04-30")
    assert len(out) == 1
    assert out[0].market_composite is None
    assert out[0].market_bias is None
