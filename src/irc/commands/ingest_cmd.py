from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from irc.config_loader import load_repo_configs
from irc.data.akshare_client import fetch_fund_metadata, fetch_fund_nav_history
from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.manifest import ManifestEntry, write_manifest
from irc.data.openbb_client import fetch_etf_price_history, fetch_macro_series
from irc.data.raw_ref import build_ref_id

_SCHEMA_VERSION = "v1"
_MACRO_SERIES = ("DGS10", "DTWEXBGS")
_LOOK_BACK_DAYS = 365 * 3
_AUM_UNITS = {
    "万亿": 1_000_000_000_000.0,
    "亿元": 100_000_000.0,
    "亿": 100_000_000.0,
    "万元": 10_000.0,
    "万": 10_000.0,
}
_MISSING_TEXT = frozenset({"", "-", "--", "nan", "none", "null"})


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _date_window() -> tuple[str, str]:
    today = datetime.now().date()
    return (today - timedelta(days=_LOOK_BACK_DAYS)).isoformat(), today.isoformat()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _clean_text(value: Any) -> str:
    return str(value).strip().replace(",", "").replace("％", "%")


def _parse_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    text = _clean_text(value)
    if text.lower() in _MISSING_TEXT:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_ratio(value: Any) -> float | None:
    if _is_missing(value):
        return None
    text = _clean_text(value)
    if text.lower() in _MISSING_TEXT:
        return None
    if text.endswith("%"):
        parsed = _parse_float(text[:-1])
        return None if parsed is None else parsed / 100
    return _parse_float(text)


def _parse_aum_cny(value: Any) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = _clean_text(value)
    if text.lower() in _MISSING_TEXT:
        return None
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(万亿|亿元|亿|万元|万)?", text)
    if match is None:
        return None
    unit = match.group(2) or ""
    return float(match.group(1)) * _AUM_UNITS.get(unit, 1.0)


def _normal_date(value: Any) -> str | None:
    if _is_missing(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _metadata_value(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if not _is_missing(value) and _clean_text(value).lower() not in _MISSING_TEXT:
            return value
    return None


def _is_fund_like_ticker(ticker: str) -> bool:
    return ticker.isdigit()


def _is_active_fund(asset_class: str) -> bool:
    return asset_class.endswith("equity_fund") or asset_class.endswith("bond_fund")


def _normalize_fund_metadata(raw: dict[str, Any]) -> dict[str, float | str | None]:
    return {
        "inception_date": _normal_date(_metadata_value(raw, "inception_date", "成立日期")),
        "expense_ratio": _parse_ratio(_metadata_value(raw, "expense_ratio", "费率")),
        "aum": _parse_aum_cny(_metadata_value(raw, "aum", "aum_text", "基金规模")),
        "manager_tenure_years": _parse_float(
            _metadata_value(raw, "manager_tenure_years", "manager_tenure", "基金经理任职年限")
        ),
    }


def _missing_required_metadata(instrument: Any, metadata: dict[str, Any]) -> tuple[str, ...]:
    required = ("inception_date", "expense_ratio", "aum")
    if _is_active_fund(instrument.asset_class):
        required = (*required, "manager_tenure_years")
    return tuple(key for key in required if _is_missing(metadata.get(key)))


def _fetch_metadata_by_id(instruments: list) -> dict[str, dict[str, float | str | None]]:
    metadata_by_id: dict[str, dict[str, float | str | None]] = {}
    for instrument in instruments:
        if not _is_fund_like_ticker(instrument.ticker):
            continue
        metadata = _normalize_fund_metadata(fetch_fund_metadata(instrument.ticker))
        missing = _missing_required_metadata(instrument, metadata)
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"missing required metadata for {instrument.instrument_id}: {joined}")
        metadata_by_id[instrument.instrument_id] = metadata
    return metadata_by_id


def _upsert_instruments(
    con,
    instruments: list,
    metadata_by_id: dict[str, dict[str, float | str | None]] | None = None,
) -> int:
    ingested_at = _now_iso()
    today = datetime.now().date().isoformat()
    metadata_by_id = metadata_by_id or {}
    params = [
        [
            i.instrument_id,
            i.ticker,
            i.market,
            i.name_cn,
            getattr(i, "name_en", None),
            i.asset_class,
            i.currency,
            metadata_by_id.get(i.instrument_id, {}).get("inception_date"),
            metadata_by_id.get(i.instrument_id, {}).get("expense_ratio"),
            metadata_by_id.get(i.instrument_id, {}).get("aum"),
            getattr(i, "tracked_index", None),
            metadata_by_id.get(i.instrument_id, {}).get("manager_tenure_years"),
            ingested_at,
            "akshare" if i.instrument_id in metadata_by_id else "universe",
            build_ref_id(
                "akshare" if i.instrument_id in metadata_by_id else "universe",
                "instruments",
                i.instrument_id,
                today,
            ),
        ]
        for i in instruments
    ]
    con.executemany(
        """
        INSERT OR REPLACE INTO instruments
            (instrument_id, ticker, market, name_cn, name_en, asset_class, currency,
             inception_date, expense_ratio, aum, tracked_index, manager_tenure_years,
             _ingested_at, _source, _raw_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _nullable_float(value) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _upsert_nav(con, instrument_id: str, df: pd.DataFrame) -> int:
    ingested_at = _now_iso()
    params = [
        [instrument_id, str(r.date), float(r.nav), _nullable_float(r.nav_acc),
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
        metadata_by_id = _fetch_metadata_by_id(all_instruments)
        ob_counts["instruments"] = _upsert_instruments(con, all_instruments, metadata_by_id)

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
