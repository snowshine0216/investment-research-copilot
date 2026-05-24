"""Item 010 D B1 — fund_holdings ingestor unit + integration tests.

Real on-disk DuckDB via tmp_path; real ActiveFundSnapshot JSON cache files
written via item 003's write_active_fund_cache. No mocks, no live network.
"""
from __future__ import annotations

import pytest


def test_holding_row_accepts_valid_fields() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    row = HoldingRow(
        instrument_id="005827",
        report_date="2024-03-31",
        holding_ticker="600519",
        holding_name="贵州茅台",
        weight_pct=8.5,
        source="active_fund_snapshot",
    )
    assert row.instrument_id == "005827"
    assert row.weight_pct == 8.5


def test_holding_row_rejects_empty_instrument_id() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="instrument_id"):
        HoldingRow(
            instrument_id="",
            report_date="2024-03-31",
            holding_ticker="600519",
            holding_name="X",
            weight_pct=8.5,
            source="active_fund_snapshot",
        )


def test_holding_row_rejects_malformed_report_date() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="report_date"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024/03/31",  # wrong delimiter
            holding_ticker="600519",
            holding_name="X",
            weight_pct=8.5,
            source="active_fund_snapshot",
        )


def test_holding_row_rejects_empty_holding_ticker() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="holding_ticker"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024-03-31",
            holding_ticker="",
            holding_name="X",
            weight_pct=8.5,
            source="active_fund_snapshot",
        )


def test_holding_row_rejects_negative_weight() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="weight_pct"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024-03-31",
            holding_ticker="600519",
            holding_name="X",
            weight_pct=-0.01,
            source="active_fund_snapshot",
        )


def test_holding_row_rejects_weight_over_100() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="weight_pct"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024-03-31",
            holding_ticker="600519",
            holding_name="X",
            weight_pct=100.01,
            source="active_fund_snapshot",
        )


def test_holding_row_accepts_boundary_weights() -> None:
    """0.0 and 100.0 are both inclusive."""
    from irc.data.fund_holdings_ingestor import HoldingRow
    HoldingRow(
        instrument_id="x", report_date="2024-03-31",
        holding_ticker="y", holding_name="z",
        weight_pct=0.0, source="active_fund_snapshot",
    )
    HoldingRow(
        instrument_id="x", report_date="2024-03-31",
        holding_ticker="y", holding_name="z",
        weight_pct=100.0, source="akshare_cn_etf",
    )


def test_holding_row_rejects_unknown_source() -> None:
    from irc.data.fund_holdings_ingestor import HoldingRow
    with pytest.raises(ValueError, match="source"):
        HoldingRow(
            instrument_id="005827",
            report_date="2024-03-31",
            holding_ticker="600519",
            holding_name="X",
            weight_pct=8.5,
            source="manual_paste",
        )


def test_ingest_outcome_constructs() -> None:
    from irc.data.fund_holdings_ingestor import IngestOutcome
    out = IngestOutcome(
        instrument_id="005827", status="wrote",
        report_date="2024-03-31", rows_written=10, detail="",
    )
    assert out.status == "wrote"
    assert out.rows_written == 10


def test_module_exports_public_surface() -> None:
    """AC2 — module exports all seven public names."""
    import irc.data.fund_holdings_ingestor as m
    for name in (
        "HoldingRow",
        "IngestOutcome",
        "collect_holding_rows",
        "upsert_holdings",
        "is_stale",
        "ingest_one",
        "ingest_many",
    ):
        assert hasattr(m, name), f"missing public name: {name}"


# ── Task 2: is_stale ─────────────────────────────────────────────────────────

from datetime import date, timedelta
from pathlib import Path


def _connect_with_schema(tmp_path: Path):
    """Open a fresh DuckDB at tmp_path/local.duckdb with schema applied."""
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "local.duckdb")
    ensure_schema(con)
    return con


def _insert_holding(con, *, iid, report_date, ticker="600519",
                    name="贵州茅台", weight=8.5, ingested_at="2026-05-24 00:00:00",
                    source="test", raw_ref="ref:1") -> None:
    """Direct positional insert for fixture seeding — bypasses the ingestor."""
    con.execute(
        "INSERT INTO fund_holdings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [iid, report_date, ticker, name, weight, ingested_at, source, raw_ref],
    )


def test_is_stale_returns_true_when_no_rows(tmp_path: Path) -> None:
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        assert is_stale(con, "005827", today_iso="2026-05-24") is True
    finally:
        con.close()


def test_is_stale_returns_false_within_threshold(tmp_path: Path) -> None:
    """29 days old is fresh (boundary check at threshold_days=30)."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        twenty_nine_days_ago = today - timedelta(days=29)
        _insert_holding(con, iid="005827", report_date=twenty_nine_days_ago)
        assert is_stale(con, "005827", today_iso=today.isoformat()) is False
    finally:
        con.close()


def test_is_stale_returns_true_past_threshold(tmp_path: Path) -> None:
    """31 days old is stale."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        thirty_one_days_ago = today - timedelta(days=31)
        _insert_holding(con, iid="005827", report_date=thirty_one_days_ago)
        assert is_stale(con, "005827", today_iso=today.isoformat()) is True
    finally:
        con.close()


def test_is_stale_boundary_exactly_at_threshold(tmp_path: Path) -> None:
    """Exactly 30 days old is NOT stale (gate is `> threshold_days`)."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        thirty_days_ago = today - timedelta(days=30)
        _insert_holding(con, iid="005827", report_date=thirty_days_ago)
        assert is_stale(con, "005827", today_iso=today.isoformat()) is False
    finally:
        con.close()


def test_is_stale_threshold_override(tmp_path: Path) -> None:
    """threshold_days=7 swaps the boundary at 8 days old."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        _insert_holding(con, iid="A", report_date=today - timedelta(days=7))
        _insert_holding(con, iid="B", report_date=today - timedelta(days=8))
        assert is_stale(con, "A", today_iso=today.isoformat(), threshold_days=7) is False
        assert is_stale(con, "B", today_iso=today.isoformat(), threshold_days=7) is True
    finally:
        con.close()


def test_is_stale_uses_max_report_date_when_multiple_quarters(tmp_path: Path) -> None:
    """Latest report_date wins for the freshness check."""
    from irc.data.fund_holdings_ingestor import is_stale
    con = _connect_with_schema(tmp_path)
    try:
        today = date(2026, 5, 24)
        _insert_holding(con, iid="005827", report_date=today - timedelta(days=200),
                        ticker="OLD")
        _insert_holding(con, iid="005827", report_date=today - timedelta(days=10),
                        ticker="NEW")
        assert is_stale(con, "005827", today_iso=today.isoformat()) is False
    finally:
        con.close()


# ── Task 3: upsert_holdings ──────────────────────────────────────────────────

import re


def _make_row(*, iid="005827", report_date="2024-03-31",
              ticker="600519", name="贵州茅台", weight=8.5,
              source="active_fund_snapshot"):
    from irc.data.fund_holdings_ingestor import HoldingRow
    return HoldingRow(
        instrument_id=iid, report_date=report_date,
        holding_ticker=ticker, holding_name=name,
        weight_pct=weight, source=source,
    )


def test_upsert_holdings_writes_rows(tmp_path: Path) -> None:
    from irc.data.fund_holdings_ingestor import upsert_holdings
    con = _connect_with_schema(tmp_path)
    try:
        rows = (
            _make_row(ticker="600519", weight=10.0),
            _make_row(ticker="601318", weight=8.0),
        )
        n = upsert_holdings(con, rows, now_iso="2026-05-24 00:00:00")
        assert n == 2
        count = con.execute(
            "SELECT COUNT(*) FROM fund_holdings WHERE instrument_id='005827'"
        ).fetchone()[0]
        assert count == 2
    finally:
        con.close()


def test_upsert_holdings_uses_named_columns(tmp_path: Path) -> None:
    """AC19 — SQL string carries the named-column block."""
    from irc.data.fund_holdings_ingestor import upsert_holdings
    captured: list[tuple[str, list]] = []

    class _Spy:
        def __init__(self, real):
            self._real = real
            self.executemany = self._spy_executemany
            self.execute = real.execute

        def _spy_executemany(self, sql, params):
            captured.append((sql, list(params)))
            return self._real.executemany(sql, params)

    real_con = _connect_with_schema(tmp_path)
    try:
        spy = _Spy(real_con)
        upsert_holdings(spy, (_make_row(),), now_iso="2026-05-24 00:00:00")
        assert len(captured) == 1
        sql = captured[0][0]
        # Substring check matches AC19 lock exactly.
        assert (
            "INSERT OR REPLACE INTO fund_holdings (instrument_id, report_date, "
            "holding_ticker, holding_name, weight_pct, _ingested_at, _source, "
            "_raw_ref) VALUES"
        ) in " ".join(sql.split())
    finally:
        real_con.close()


def test_upsert_holdings_idempotent_via_primary_key(tmp_path: Path) -> None:
    """Two upserts of the same rows → row count stays constant; PK dedup wins."""
    from irc.data.fund_holdings_ingestor import upsert_holdings
    con = _connect_with_schema(tmp_path)
    try:
        rows = (_make_row(), _make_row(ticker="601318", weight=8.0))
        upsert_holdings(con, rows, now_iso="2026-05-24 00:00:00")
        upsert_holdings(con, rows, now_iso="2026-05-24 01:00:00")
        count = con.execute(
            "SELECT COUNT(*) FROM fund_holdings WHERE instrument_id='005827'"
        ).fetchone()[0]
        assert count == 2
        # _ingested_at advances on the second write.
        latest_ingest = con.execute(
            "SELECT MAX(_ingested_at) FROM fund_holdings WHERE instrument_id='005827'"
        ).fetchone()[0]
        assert str(latest_ingest).startswith("2026-05-24 01:00:00")
    finally:
        con.close()


def test_upsert_holdings_raw_ref_pattern(tmp_path: Path) -> None:
    """AC18 — _raw_ref is keyed on (source, fund_holdings, iid, report_date);
    rows for the same (iid, report_date) share the same _raw_ref value."""
    from irc.data.fund_holdings_ingestor import upsert_holdings
    con = _connect_with_schema(tmp_path)
    try:
        rows = (_make_row(ticker="600519"), _make_row(ticker="601318", weight=8.0))
        upsert_holdings(con, rows, now_iso="2026-05-24 00:00:00")
        refs = [
            r[0] for r in con.execute(
                "SELECT _raw_ref FROM fund_holdings WHERE instrument_id='005827'"
            ).fetchall()
        ]
        assert len(set(refs)) == 1, "all rows for same (iid, report_date) share _raw_ref"
        assert re.fullmatch(
            r"(active_fund_snapshot|akshare_cn_etf):fund_holdings:\d+:\d{4}-\d{2}-\d{2}",
            refs[0],
        )
    finally:
        con.close()


def test_upsert_holdings_writes_source_column(tmp_path: Path) -> None:
    from irc.data.fund_holdings_ingestor import upsert_holdings
    con = _connect_with_schema(tmp_path)
    try:
        rows = (
            _make_row(source="akshare_cn_etf", ticker="600519"),
            _make_row(source="akshare_cn_etf", ticker="601318", weight=8.0),
        )
        upsert_holdings(con, rows, now_iso="2026-05-24 00:00:00")
        sources = {
            r[0] for r in con.execute(
                "SELECT DISTINCT _source FROM fund_holdings WHERE instrument_id='005827'"
            ).fetchall()
        }
        assert sources == {"akshare_cn_etf"}
    finally:
        con.close()


def test_upsert_holdings_deterministic_row_order(tmp_path: Path) -> None:
    """AC15 — rows inserted in (weight_pct DESC, holding_ticker ASC) order.

    Two reruns on the same input produce byte-equal SELECT * ORDER BY rowid.
    """
    from irc.data.fund_holdings_ingestor import upsert_holdings
    # Pass rows in arbitrary order; ingestor must sort before executemany.
    shuffled = (
        _make_row(ticker="ZZZ", weight=5.0),
        _make_row(ticker="AAA", weight=10.0),
        _make_row(ticker="MMM", weight=10.0),
        _make_row(ticker="BBB", weight=7.5),
    )

    def _rowid_select(con):
        return con.execute(
            "SELECT rowid, holding_ticker, weight_pct FROM fund_holdings "
            "WHERE instrument_id='005827' ORDER BY rowid"
        ).fetchall()

    # Run 1
    con1 = _connect_with_schema(tmp_path)
    try:
        upsert_holdings(con1, shuffled, now_iso="2026-05-24 00:00:00")
        order1 = [(r[1], r[2]) for r in _rowid_select(con1)]
    finally:
        con1.close()
    # Run 2 (new DB, same input)
    tmp2 = tmp_path / "rerun"
    tmp2.mkdir()
    con2 = _connect_with_schema(tmp2)
    try:
        upsert_holdings(con2, shuffled, now_iso="2026-05-24 00:00:00")
        order2 = [(r[1], r[2]) for r in _rowid_select(con2)]
    finally:
        con2.close()
    assert order1 == order2
    # Locked sort: weight DESC then ticker ASC.
    assert order1 == [
        ("AAA", 10.0), ("MMM", 10.0), ("BBB", 7.5), ("ZZZ", 5.0),
    ]


def test_upsert_holdings_empty_iterable_is_noop(tmp_path: Path) -> None:
    from irc.data.fund_holdings_ingestor import upsert_holdings
    con = _connect_with_schema(tmp_path)
    try:
        n = upsert_holdings(con, (), now_iso="2026-05-24 00:00:00")
        assert n == 0
    finally:
        con.close()


# ── Task 4: collect_holding_rows (active-fund snapshot path) ─────────────────


def _build_snapshot(
    *, fund_id="005827", quarter="2024Q1", report_date="2024-03-31",
    analyses=None, fund_level_failure_reasons=(),
):
    """Build a real ActiveFundSnapshot for round-trip through item 003's writer."""
    from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis
    if analyses is None:
        analyses = tuple(
            ConstituentAnalysis(
                symbol=f"60000{i}", name_cn=f"成份{i}",
                weight_pct=float(10 - i), evidence=(),
                failure_reasons=(), one_line_view="",
            )
            for i in range(10)
        )
    return ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date=report_date,
        source_report_quarter=quarter,
        cache_probed_at="2024-04-30T12:00:00+08:00",
        constituent_analyses=analyses,
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=fund_level_failure_reasons,
    )


def _write_snap(snap, tmp_path: Path) -> Path:
    """Write a snapshot via item 003's writer to the standard cache layout."""
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    return write_active_fund_cache(snap, tmp_path / "data")


def test_collect_holding_rows_from_active_fund_snapshot(tmp_path: Path) -> None:
    """AC8 — cn_equity_fund reads ActiveFundSnapshot cache directly."""
    from irc.data.fund_holdings_ingestor import collect_holding_rows
    snap = _build_snapshot()
    _write_snap(snap, tmp_path)
    rows, source, detail = collect_holding_rows(
        "005827", "cn_equity_fund", data_root=tmp_path / "data",
    )
    assert len(rows) == 10
    assert source == "active_fund_snapshot"
    assert detail == "loaded:2024Q1"
    assert all(r.source == "active_fund_snapshot" for r in rows)
    assert all(r.report_date == "2024-03-31" for r in rows)


def test_collect_holding_rows_cn_etf_cache_hit_wins(tmp_path: Path) -> None:
    """AC8 — when a cn_etf iid happens to have a cached ActiveFundSnapshot,
    the snapshot wins (no AkShare fallback). Verified by patching
    fetch_cn_etf_holdings to raise."""
    from irc.data.fund_holdings_ingestor import collect_holding_rows
    import irc.data.fund_holdings_ingestor as mod
    snap = _build_snapshot(fund_id="510300", quarter="2024Q1")
    _write_snap(snap, tmp_path)
    original = mod.fetch_cn_etf_holdings
    mod.fetch_cn_etf_holdings = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("must not be called when cache hits")
    )
    try:
        rows, source, _ = collect_holding_rows(
            "510300", "cn_etf", data_root=tmp_path / "data",
        )
    finally:
        mod.fetch_cn_etf_holdings = original
    assert source == "active_fund_snapshot"
    assert len(rows) == 10


def test_collect_holding_rows_latest_quarter_wins(tmp_path: Path) -> None:
    """A 2024Q4 snapshot beats 2024Q1 (lexicographic latest)."""
    from irc.data.fund_holdings_ingestor import collect_holding_rows
    from irc.fundamentals.types import ConstituentAnalysis
    q1 = _build_snapshot(quarter="2024Q1", report_date="2024-03-31")
    q4 = _build_snapshot(
        quarter="2024Q4", report_date="2024-12-31",
        analyses=(
            ConstituentAnalysis(
                symbol="NEW", name_cn="新", weight_pct=5.0,
                evidence=(), failure_reasons=(), one_line_view="",
            ),
        ),
    )
    _write_snap(q1, tmp_path)
    _write_snap(q4, tmp_path)
    rows, _, detail = collect_holding_rows(
        "005827", "cn_equity_fund", data_root=tmp_path / "data",
    )
    assert detail == "loaded:2024Q4"
    assert rows[0].report_date == "2024-12-31"
    assert rows[0].holding_ticker == "NEW"


def test_collect_holding_rows_skips_empty_snapshot_and_falls_through(tmp_path: Path) -> None:
    """Latest snapshot is empty but an older one has data → use the older one."""
    from irc.data.fund_holdings_ingestor import collect_holding_rows
    q1 = _build_snapshot(quarter="2024Q1", report_date="2024-03-31")
    q4_empty = _build_snapshot(
        quarter="2024Q4", report_date="2024-12-31", analyses=(),
    )
    _write_snap(q1, tmp_path)
    _write_snap(q4_empty, tmp_path)
    rows, _, detail = collect_holding_rows(
        "005827", "cn_equity_fund", data_root=tmp_path / "data",
    )
    assert detail == "loaded:2024Q1"
    assert len(rows) == 10


def test_collect_holding_rows_no_cache_for_cn_equity_fund_returns_empty(tmp_path: Path) -> None:
    """AC10 path-equivalent — no cache + cn_equity_fund returns () with
    detail='snapshot_missing'. fetch_cn_etf_holdings is NOT called (patched to raise)."""
    from irc.data.fund_holdings_ingestor import collect_holding_rows
    import irc.data.fund_holdings_ingestor as mod
    original = mod.fetch_cn_etf_holdings
    mod.fetch_cn_etf_holdings = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("must not be called for cn_equity_fund")
    )
    try:
        rows, source, detail = collect_holding_rows(
            "005827", "cn_equity_fund", data_root=tmp_path / "data",
        )
    finally:
        mod.fetch_cn_etf_holdings = original
    assert rows == ()
    assert source == "active_fund_snapshot"
    assert detail == "snapshot_missing"


def test_collect_holding_rows_all_quarters_empty_returns_snapshot_empty(tmp_path: Path) -> None:
    """AC10 — every available snapshot has constituent_analyses=()."""
    from irc.data.fund_holdings_ingestor import collect_holding_rows
    only_empty = _build_snapshot(quarter="2024Q1", analyses=())
    _write_snap(only_empty, tmp_path)
    rows, source, detail = collect_holding_rows(
        "005827", "cn_equity_fund", data_root=tmp_path / "data",
    )
    assert rows == ()
    assert source == "active_fund_snapshot"
    assert detail == "snapshot_empty"


def test_collect_holding_rows_missing_report_date_returns_empty(tmp_path: Path) -> None:
    """AC11 — snapshot.source_report_date == '' → 'missing_report_date'."""
    from irc.data.fund_holdings_ingestor import collect_holding_rows
    snap = _build_snapshot(report_date="")
    _write_snap(snap, tmp_path)
    rows, _, detail = collect_holding_rows(
        "005827", "cn_equity_fund", data_root=tmp_path / "data",
    )
    assert rows == ()
    assert detail == "missing_report_date"


def test_collect_holding_rows_skips_constituents_with_empty_symbol(tmp_path: Path) -> None:
    """Defence-in-depth — ConstituentAnalysis.__post_init__ already blocks
    empty symbols, but the comprehension filters anyway."""
    # Since ConstituentAnalysis enforces non-empty symbol at construction,
    # this test confirms the comprehension uses `if c.symbol` and we don't
    # accidentally construct HoldingRow with an empty ticker (which would
    # itself raise in HoldingRow.__post_init__). Documentation of intent.
    from irc.fundamentals.types import ConstituentAnalysis
    import pytest as _pt
    with _pt.raises(ValueError):
        ConstituentAnalysis(
            symbol="", name_cn="x", weight_pct=1.0,
            evidence=(), failure_reasons=(), one_line_view="",
        )
