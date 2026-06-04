"""`irc lookthrough-diff` command (Phase D PR1, gate-#5 artifact).

Loads cached fund_holdings (latest quarter per active fund) + stock_valuation_history
(NO live fetch — spec §3.7/§8) and writes the diff report regardless of the
`active_fund_lookthrough.enabled` flag. Effects (DuckDB read + atomic file write)
are confined here; the report builder is pure.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from irc.data.duckdb_helper import connect, ensure_schema
from irc.opportunity.inputs_loader import (
    _latest_quarter_holdings,
    _price_series,
    _stock_series_by_code,
)
from irc.opportunity.lookthrough_diff_report import (
    build_floor_sensitivity,
    build_fund_diff_row,
    render_diff_report,
)
from irc.opportunity.lookthrough_valuation import fund_valuation_percentile
from irc.opportunity.returns import self_history_percentile


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _active_fund_ids(con) -> tuple[str, ...]:
    rows = con.execute(
        "SELECT DISTINCT h.instrument_id FROM fund_holdings h "
        "JOIN instruments i ON i.instrument_id = h.instrument_id "
        "WHERE i.asset_class = 'cn_equity_fund' ORDER BY h.instrument_id"
    ).fetchall()
    return tuple(r[0] for r in rows)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run_lookthrough_diff(
    repo_root: str, *, output_dir: str | None = None,
    coverage_floor: float = 0.50, pb_uses_pe_gate: bool = False,
) -> int:
    """Build and write the Phase D gate-#5 diff report. Cached-only (no live
    fetch). Computes regardless of active_fund_lookthrough.enabled."""
    root = Path(repo_root)
    db_path = root / "data" / "local.duckdb"
    try:
        con = connect(db_path)
        ensure_schema(con)
    except Exception as exc:
        print(f"ERROR: cannot open DuckDB at {db_path}: {exc}")
        return 1
    try:
        diff_rows = []
        coverage_ratios = []
        for iid in _active_fund_ids(con):
            holdings = _latest_quarter_holdings(con, iid)
            if not holdings:
                continue
            series = _stock_series_by_code(con, tuple(h.code for h in holdings))
            result = fund_valuation_percentile(
                holdings, series,
                coverage_floor=coverage_floor, pb_uses_pe_gate=pb_uses_pe_gate,
            )
            nav_series = _price_series(con, iid)
            nav_pct = self_history_percentile(nav_series) if not nav_series.empty else None
            name = con.execute(
                "SELECT name_cn FROM instruments WHERE instrument_id = ?", [iid]
            ).fetchone()
            diff_rows.append(build_fund_diff_row(
                instrument_id=iid, name_cn=(name[0] if name else iid),
                nav_percentile=nav_pct, result=result,
            ))
            coverage_ratios.append(result.pe.coverage_ratio)
        text = render_diff_report(
            diff_rows, build_floor_sensitivity(coverage_ratios)
        )
        out = Path(output_dir) if output_dir else (root / "outputs" / _today())
        _atomic_write_text(out / "lookthrough_diff_report.md", text)
        print(
            f"lookthrough diff report OK: {len(diff_rows)} active funds → "
            f"{out / 'lookthrough_diff_report.md'}"
        )
        return 0
    finally:
        con.close()
