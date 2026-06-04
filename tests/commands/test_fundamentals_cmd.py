from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import duckdb

from irc.commands.fundamentals_cmd import run_snapshot_rebuild
from irc.data.duckdb_helper import ensure_schema
from irc.fundamentals.types import ConstituentSnapshot


def _snapshot(target: str = "沪深300") -> ConstituentSnapshot:
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=(),
    )


def test_snapshot_rebuild_requires_at_least_one_target(tmp_path: Path) -> None:
    rc = run_snapshot_rebuild(repo_root=str(tmp_path), targets=(), top_n=10)

    assert rc == 2


def test_snapshot_rebuild_builds_and_writes_each_target(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "fundamentals" / "2026Q1" / "沪深300.json"
    with patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        return_value=_snapshot(),
    ) as mock_build, patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=output_path,
    ) as mock_write:
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("沪深300",),
            top_n=5,
        )

    assert rc == 0
    call_args = mock_build.call_args
    assert call_args.args[0].display_cn == "沪深300"
    assert call_args.args[0].kind in ("broad_index", "sector_theme", "qdii_us", "qdii_hk")
    assert call_args.kwargs.get("top_n") == 5
    assert "provider" in call_args.kwargs
    mock_write.assert_called_once()
    assert mock_write.call_args.args[1] == tmp_path / "data"


def test_snapshot_rebuild_target_all_expands_registered_targets(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "fundamentals" / "2026Q1" / "沪深300.json"
    with patch(
        "irc.commands.fundamentals_cmd.registered_snapshot_targets",
        return_value=("沪深300", "中证500"),
    ), patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        side_effect=lambda lt, *, top_n, **kwargs: _snapshot(lt.display_cn),
    ) as mock_build, patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=output_path,
    ) as mock_write:
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("all",),
            top_n=5,
        )

    assert rc == 0
    assert [call.args[0].display_cn for call in mock_build.call_args_list] == ["沪深300", "中证500"]
    assert all(call.kwargs.get("top_n") == 5 for call in mock_build.call_args_list)
    assert mock_write.call_count == 2


def test_snapshot_rebuild_target_all_deduplicates_explicit_targets(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "fundamentals" / "2026Q1" / "沪深300.json"
    with patch(
        "irc.commands.fundamentals_cmd.registered_snapshot_targets",
        return_value=("沪深300", "中证500"),
    ), patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        side_effect=lambda lt, *, top_n, **kwargs: _snapshot(lt.display_cn),
    ) as mock_build, patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=output_path,
    ):
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("沪深300", "all", "中证500"),
            top_n=3,
        )

    assert rc == 0
    assert [call.args[0].display_cn for call in mock_build.call_args_list] == ["沪深300", "中证500"]


def test_snapshot_rebuild_warns_but_completes_when_snapshot_has_failures(tmp_path: Path) -> None:
    failed_snapshot = ConstituentSnapshot(
        lookthrough_target="未知指数",
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=("unknown lookthrough_target: 未知指数",),
    )
    with patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        return_value=failed_snapshot,
    ), patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=tmp_path / "data" / "fundamentals" / "2026Q1" / "未知指数.json",
    ):
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("未知指数",),
            top_n=10,
        )

    assert rc == 0


# ── Task 15: stock-valuation command tests ────────────────────────────────────


def _seed_holdings(db_path):
    con = duckdb.connect(str(db_path))
    ensure_schema(con)
    rows = [
        ("F1", "2026-03-31", "600519", "贵州茅台", 30.0),
        ("F1", "2026-03-31", "000001", "平安银行", 20.0),
        ("F1", "2026-03-31", "00700", "腾讯", 10.0),
        ("F1", "2026-03-31", "AAPL", "Apple", 5.0),
        ("F2", "2026-03-31", "600519", "贵州茅台", 25.0),
    ]
    con.executemany(
        "INSERT INTO fund_holdings VALUES (?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'r')",
        rows,
    )
    con.close()


def test_discover_ashare_codes_filters_to_six_digit_and_dedupes(tmp_path) -> None:
    from irc.commands.fundamentals_cmd import _discover_ashare_codes

    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed_holdings(db)
    con = duckdb.connect(str(db))
    codes = _discover_ashare_codes(con)
    con.close()
    assert codes == ("000001", "600519")
    assert all(re.fullmatch(r"\d{6}", c) for c in codes)


def test_run_returns_zero_on_completed_run_even_with_per_stock_misses(
    tmp_path, monkeypatch
) -> None:
    from irc.commands.fundamentals_cmd import run_stock_valuation_refresh

    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed_holdings(db)
    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd._fetch_stock_valuation",
        lambda code, token: None,
    )
    rc = run_stock_valuation_refresh(str(tmp_path), force=True)
    assert rc == 0


def test_run_writes_rows_for_discovered_ashares(tmp_path, monkeypatch) -> None:
    from irc.commands.fundamentals_cmd import run_stock_valuation_refresh
    from irc.fundamentals.stock_valuation_types import (
        StockValuationHistory, StockValuationPoint,
    )
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed_holdings(db)

    def _fake(code, token):
        return (
            StockValuationHistory(code, (StockValuationPoint("2026-05-30", 18.0, 2.0, None),)),
            "eastmoney",
        )

    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd._fetch_stock_valuation", _fake
    )
    rc = run_stock_valuation_refresh(str(tmp_path), force=True)
    assert rc == 0
    con = duckdb.connect(str(db))
    codes = {
        r[0] for r in con.execute(
            "SELECT DISTINCT stock_code FROM stock_valuation_history"
        ).fetchall()
    }
    con.close()
    assert codes == {"000001", "600519"}


def test_eastmoney_miss_falls_back_to_tushare(tmp_path, monkeypatch) -> None:
    from irc.commands.fundamentals_cmd import run_stock_valuation_refresh
    from irc.fundamentals.stock_valuation_types import (
        StockValuationHistory, StockValuationPoint,
    )
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed_holdings(db)

    calls = {"em": 0, "ts": 0}

    def _fake_em(code):
        calls["em"] += 1
        return None

    def _fake_ts(code, *, token):
        calls["ts"] += 1
        return StockValuationHistory(code, (StockValuationPoint("2026-05-30", 18.0, 2.0, None),))

    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd.fetch_stock_valuation_history", _fake_em
    )
    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd.fetch_stock_valuation_history_tushare", _fake_ts
    )
    monkeypatch.setattr(
        "irc.commands.fundamentals_cmd._read_tushare_token", lambda: "tok"
    )
    rc = run_stock_valuation_refresh(str(tmp_path), force=True)
    assert rc == 0
    assert calls["em"] >= 1 and calls["ts"] >= 1
    con = duckdb.connect(str(db))
    src = con.execute(
        "SELECT DISTINCT _source FROM stock_valuation_history"
    ).fetchall()
    con.close()
    assert ("tushare",) in src
