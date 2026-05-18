from __future__ import annotations
import pandas as pd
from evals.discovery.metrics import (
    candidates_per_role,
    filter_integrity,
    dedup,
    llm_reason_grounding,
)


def _make_watchlist() -> pd.DataFrame:
    """Mirrors the producer's CSV (src/irc/discovery/pipeline.py _WATCHLIST_COLUMNS)."""
    tickers = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN", "META", "NVDA", "AMD", "INTC", "QCOM"]
    return pd.DataFrame({
        "instrument_id": tickers,
        "ticker": tickers,
        "role": ["growth"] * 5 + ["value"] * 5,
        "cited_refs": ["ref1", "ref2", "", "ref4", "ref5", "", "ref7", "ref8", "ref9", ""],
    })


def test_candidates_per_role():
    wl = _make_watchlist()
    result = candidates_per_role(wl)
    assert result["growth"] == 5
    assert result["value"] == 5


def test_candidates_per_role_empty():
    wl = pd.DataFrame({"instrument_id": [], "ticker": [], "role": [], "cited_refs": []})
    result = candidates_per_role(wl)
    assert result == {}


def test_filter_integrity_all_present():
    wl = _make_watchlist()
    assert filter_integrity(wl) == 1.0


def test_filter_integrity_with_nulls():
    """Default `required_cols` is the producer's actual contract:
    instrument_id, ticker, role. Null one of those to exercise the default."""
    wl = _make_watchlist()
    wl.loc[0, "role"] = None
    rate = filter_integrity(wl)
    assert abs(rate - 9 / 10) < 1e-9


def test_filter_integrity_empty():
    wl = pd.DataFrame()
    assert filter_integrity(wl) == 1.0


def test_dedup_all_unique():
    wl = _make_watchlist()
    assert dedup(wl) == 1.0


def test_dedup_with_duplicates():
    wl = _make_watchlist().copy()
    wl.loc[0, "ticker"] = "MSFT"  # duplicate
    rate = dedup(wl)
    assert rate == 9 / 10


def test_llm_reason_grounding():
    wl = _make_watchlist()
    # 7 out of 10 have non-empty cited_refs
    rate = llm_reason_grounding(wl)
    assert abs(rate - 7 / 10) < 1e-9


def test_llm_reason_grounding_empty():
    wl = pd.DataFrame({"instrument_id": [], "ticker": [], "role": [], "cited_refs": []})
    assert llm_reason_grounding(wl) == 1.0
