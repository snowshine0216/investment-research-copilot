from __future__ import annotations

import pytest
import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.monitor.types import MonitorFund
from irc.monitor.valuation import (
    ValuationResolution,
    percentile_to_valuation_state,
    resolve_valuation_state,
)


@pytest.mark.parametrize("pct,expected", [
    (0.0, "cheap"),
    (0.19, "cheap"),
    (0.20, "reasonable_low"),   # boundary: < 0.20 is cheap; 0.20 rolls to next band
    (0.39, "reasonable_low"),
    (0.40, "fair"),
    (0.69, "fair"),
    (0.70, "expensive"),
    (0.89, "expensive"),
    (0.90, "very_expensive"),
    (1.0, "very_expensive"),
])
def test_percentile_maps_to_band(pct, expected):
    assert percentile_to_valuation_state(pct) == expected


def test_none_percentile_is_none():
    assert percentile_to_valuation_state(None) is None


def test_nan_percentile_is_none():
    assert percentile_to_valuation_state(float("nan")) is None


def _fund(fund_id: str, profile: str = "active_cn_equity") -> MonitorFund:
    return MonitorFund(
        id=fund_id, name_cn="x", market="cn_off_exchange",
        analysis_profile=profile, themes=(), constituent_news=False,
        weights={}, bands={}, minimum_confidence=0.5,
    )


def _seed_instrument(con, fund_id, tracked_index):
    # NOTE: provenance cols (_ingested_at/_source/_raw_ref) are NOT NULL → name them.
    con.execute(
        "INSERT INTO instruments (instrument_id, ticker, market, name_cn, "
        "asset_class, currency, tracked_index, _ingested_at, _source, _raw_ref) "
        "VALUES (?,?,?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:i')",
        [fund_id, fund_id, "cn_off_exchange", "x", "cn_etf", "cny", tracked_index],
    )


def _seed_index_valuation_history(con, index_key, pe_pb_pairs):
    from datetime import date
    rows = []
    for i, (pe, pb) in enumerate(pe_pb_pairs):
        d = date.fromordinal(date(2025, 1, 1).toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_result_type_is_frozen():
    r = ValuationResolution(state="cheap", cached=True, reason=None)
    with pytest.raises(Exception):
        r.state = "fair"  # frozen dataclass → FrozenInstanceError


def test_index_anchored_present_state(tmp_path):
    # Use csi300 — a REAL _INDEX_VALUATION_KEYS member (china_internet is NOT one;
    # see the SPEC GAP note in the plan header). 200 rising PE points: >120
    # MIN_PE_POINTS, span >180d → mature; latest is max → pct 1.0 → very_expensive.
    con = duckdb.connect(str(tmp_path / "iv.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "csi300", pairs)
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.cached is True
    assert res.state == "very_expensive"   # pct 1.0 → >=0.90 band
    assert res.reason is None
    con.close()


def test_index_anchored_immature_history_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv2.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    _seed_index_valuation_history(con, "csi300", [(12.0, 1.3)] * 10)  # <120 pts → immature
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_china_internet_anchor_is_na_documented_gap(tmp_path):
    # 009225's tracked index china_internet is NOT a valuation key → N/A even with
    # cache. Locks the documented spec gap (plan header) so a future fix is intentional.
    con = duckdb.connect(str(tmp_path / "iv3.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "009225", "china_internet")
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "china_internet", pairs)
    res = resolve_valuation_state(_fund("009225", "qdii_china_us_internet"),
                                  con=con, root=tmp_path)
    assert res.state is None and res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_index_anchored_unactivated_sector_is_na(tmp_path):
    # 018132 → display 中证有色金属矿业主题 → slug csi_nonferrous_mining (a SECTOR key).
    # resolve_valuation_state does NOT pass activated_sector_slugs, so the sector
    # short-circuits to all-None → N/A. (Spec §3: acceptable, surfaced.)
    con = duckdb.connect(str(tmp_path / "iv4.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "018132", "中证有色金属矿业主题")
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]
    _seed_index_valuation_history(con, "csi_nonferrous_mining", pairs)
    res = resolve_valuation_state(_fund("018132", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_lookthrough_branch_is_na_stub(tmp_path):
    # tracked_index is None (pure active fund) → honest N/A placeholder (item 002 fills in).
    con = duckdb.connect(str(tmp_path / "iv5.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "519069", None)
    res = resolve_valuation_state(_fund("519069", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None
    assert res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


def test_unknown_fund_no_instrument_row_is_na(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv5.duckdb"))
    ensure_schema(con)
    res = resolve_valuation_state(_fund("999999", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state is None and res.cached is False
    assert res.reason == "valuation_no_anchor"
    con.close()


# Fix 1 regression tests: resolve_valuation_state must never raise on a DuckDB read error.


def test_missing_instruments_table_degrades_to_na(tmp_path):
    """A DB with NO instruments table → CatalogException must degrade to N/A, not raise."""
    con = duckdb.connect(str(tmp_path / "empty.duckdb"))
    # Intentionally do NOT call ensure_schema — instruments table is absent.
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res == ValuationResolution(None, False, "valuation_no_anchor")
    con.close()


def test_missing_index_valuation_history_table_degrades_to_na(tmp_path):
    """instruments present + tracked_index set, but index_valuation_history absent →
    must degrade to N/A, not raise."""
    con = duckdb.connect(str(tmp_path / "partial.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    # Drop index_valuation_history to simulate a partial / pre-migration DB.
    con.execute("DROP TABLE index_valuation_history")
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res == ValuationResolution(None, False, "valuation_no_anchor")
    con.close()
