from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from irc.config_loader import load_repo_configs
from irc.data.akshare_client import fetch_fund_nav_history
from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.manifest import ManifestEntry, write_manifest
from irc.data.openbb_client import fetch_etf_price_history, fetch_macro_series
from irc.data.raw_ref import build_ref_id

_SCHEMA_VERSION = "v1"
_MACRO_SERIES = ("DGS10", "DTWEXBGS")
_LOOK_BACK_DAYS = 365 * 3


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _date_window() -> tuple[str, str]:
    today = datetime.now().date()
    return (today - timedelta(days=_LOOK_BACK_DAYS)).isoformat(), today.isoformat()


def _upsert_instruments(con, instruments: list) -> int:
    ingested_at = _now_iso()
    params = [
        [i.instrument_id, i.ticker, i.market, i.name_cn, i.asset_class,
         i.currency, getattr(i, "tracked_index", None), ingested_at, "universe", i.instrument_id]
        for i in instruments
    ]
    con.executemany(
        """
        INSERT OR REPLACE INTO instruments
            (instrument_id, ticker, market, name_cn, asset_class, currency,
             tracked_index, _ingested_at, _source, _raw_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        params,
    )
    return len(params)


def _upsert_prices(con, instrument_id: str, df: pd.DataFrame) -> int:
    ingested_at = _now_iso()
    params = [
        [instrument_id, str(r.date), r.open, r.high, r.low, r.close, r.volume,
         ingested_at, "openbb", build_ref_id("openbb", "prices", instrument_id, str(r.date))]
        for r in df.itertuples(index=False)
    ]
    if params:
        con.executemany(
            """
            INSERT OR REPLACE INTO prices
                (instrument_id, date, open, high, low, close, volume,
                 _ingested_at, _source, _raw_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
    return len(params)


def _upsert_macro(con, series_id: str, df: pd.DataFrame) -> int:
    ingested_at = _now_iso()
    params = [
        [series_id, str(r.date), float(r.value), ingested_at, "openbb",
         build_ref_id("openbb", "macro_series", series_id, str(r.date))]
        for r in df.itertuples(index=False)
    ]
    if params:
        con.executemany(
            """
            INSERT OR REPLACE INTO macro_series
                (series_id, date, value, _ingested_at, _source, _raw_ref)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            params,
        )
    return len(params)


def _upsert_nav(con, instrument_id: str, df: pd.DataFrame) -> int:
    ingested_at = _now_iso()
    params = [
        [instrument_id, str(r.date), float(r.nav), float(r.nav_acc),
         ingested_at, "akshare", build_ref_id("akshare", "nav_history", instrument_id, str(r.date))]
        for r in df.itertuples(index=False)
    ]
    if params:
        con.executemany(
            """
            INSERT OR REPLACE INTO nav_history
                (instrument_id, date, nav, nav_acc,
                 _ingested_at, _source, _raw_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
    return len(params)


def run_ingest(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    db_path = root / "data" / "local.duckdb"

    con = connect(db_path)
    try:
        ensure_schema(con)
        start, end = _date_window()
        ob_counts: dict[str, int] = {"prices": 0, "macro_series": 0, "instruments": 0}
        ak_counts: dict[str, int] = {"nav_history": 0}

        all_instruments = [
            *bundle.universe_qdii_us.instruments,
            *bundle.universe_qdii_hk.instruments,
            *bundle.universe_gold.instruments,
            *bundle.universe_cn_funds.instruments,
        ]
        ob_counts["instruments"] = _upsert_instruments(con, all_instruments)

        all_price_instruments = [
            *bundle.universe_qdii_us.instruments,
            *bundle.universe_qdii_hk.instruments,
            *bundle.universe_gold.instruments,
        ]
        for instr in all_price_instruments:
            df = fetch_etf_price_history(ticker=instr.ticker, start=start, end=end)
            ob_counts["prices"] += _upsert_prices(con, instr.instrument_id, df)

        for series_id in _MACRO_SERIES:
            df = fetch_macro_series(series_id=series_id, start=start, end=end)
            ob_counts["macro_series"] += _upsert_macro(con, series_id, df)

        for instr in bundle.universe_cn_funds.instruments:
            df = fetch_fund_nav_history(instr.ticker)
            ak_counts["nav_history"] += _upsert_nav(con, instr.instrument_id, df)

    finally:
        con.close()

    data_root = root / "data"
    write_manifest(data_root, ManifestEntry(
        source="openbb", last_run_at=_now_iso(),
        schema_version=_SCHEMA_VERSION, record_counts=ob_counts,
    ))
    write_manifest(data_root, ManifestEntry(
        source="akshare", last_run_at=_now_iso(),
        schema_version=_SCHEMA_VERSION, record_counts=ak_counts,
    ))
    print(f"ingest OK: openbb={ob_counts}, akshare={ak_counts}")
    return 0
