from __future__ import annotations

from pathlib import Path

import duckdb

EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "instruments",
        "prices",
        "nav_history",
        "macro_series",
        "fund_holdings",
        "fund_metrics",
        "events_log",
        "index_valuation_history",
        "stock_valuation_history",
    }
)

_PROVENANCE_COLS = """
    _ingested_at TIMESTAMP NOT NULL,
    _source      VARCHAR    NOT NULL,
    _raw_ref     VARCHAR    NOT NULL
"""

_DDL_STATEMENTS: tuple[str, ...] = (
    f"""CREATE TABLE IF NOT EXISTS instruments (
        instrument_id    VARCHAR PRIMARY KEY,
        ticker           VARCHAR NOT NULL,
        market           VARCHAR NOT NULL,
        name_cn          VARCHAR NOT NULL,
        name_en          VARCHAR,
        asset_class      VARCHAR NOT NULL,
        currency         VARCHAR NOT NULL,
        inception_date   DATE,
        expense_ratio    DOUBLE,
        aum              DOUBLE,
        tracked_index    VARCHAR,
        manager_tenure_years DOUBLE,
        {_PROVENANCE_COLS}
    )""",
    f"""CREATE TABLE IF NOT EXISTS prices (
        instrument_id VARCHAR NOT NULL,
        date          DATE    NOT NULL,
        open          DOUBLE,
        high          DOUBLE,
        low           DOUBLE,
        close         DOUBLE NOT NULL,
        volume        DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS nav_history (
        instrument_id VARCHAR NOT NULL,
        date          DATE    NOT NULL,
        nav           DOUBLE  NOT NULL,
        nav_acc       DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS macro_series (
        series_id VARCHAR NOT NULL,
        date      DATE    NOT NULL,
        value     DOUBLE  NOT NULL,
        {_PROVENANCE_COLS},
        PRIMARY KEY (series_id, date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS fund_holdings (
        instrument_id     VARCHAR NOT NULL,
        report_date       DATE    NOT NULL,
        holding_ticker    VARCHAR NOT NULL,
        holding_name      VARCHAR,
        weight_pct        DOUBLE  NOT NULL,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, report_date, holding_ticker)
    )""",
    f"""CREATE TABLE IF NOT EXISTS fund_metrics (
        instrument_id    VARCHAR NOT NULL,
        as_of_date       DATE    NOT NULL,
        drawdown_3y      DOUBLE,
        vol_1y           DOUBLE,
        downside_capture DOUBLE,
        tracking_error   DOUBLE,
        sharpe_3y        DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, as_of_date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS events_log (
        ts        TIMESTAMP NOT NULL,
        stage     VARCHAR   NOT NULL,
        severity  VARCHAR   NOT NULL,
        message   VARCHAR   NOT NULL,
        {_PROVENANCE_COLS}
    )""",
    f"""CREATE TABLE IF NOT EXISTS index_valuation_history (
        index_key      VARCHAR NOT NULL,
        date           DATE    NOT NULL,
        pe_ttm         DOUBLE,
        pb             DOUBLE,
        dividend_yield DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (index_key, date)
    )""",
    f"""CREATE TABLE IF NOT EXISTS stock_valuation_history (
        stock_code     VARCHAR NOT NULL,
        date           DATE    NOT NULL,
        pe_ttm         DOUBLE,
        pb             DOUBLE,
        dividend_yield DOUBLE,
        {_PROVENANCE_COLS},
        PRIMARY KEY (stock_code, date)
    )""",
)


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open or create a DuckDB file. Caller is responsible for closing."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Idempotently create all expected tables."""
    con.execute("BEGIN")
    try:
        for stmt in _DDL_STATEMENTS:
            con.execute(stmt)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
