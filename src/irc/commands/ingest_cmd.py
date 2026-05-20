from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from irc.observability import ErrorTally, progress_iter

import pandas as pd
from pydantic_settings import BaseSettings, SettingsConfigDict

from irc.config_loader import load_repo_configs
from irc.data.akshare_client import (
    _is_transient_network_error,
    fetch_etf_metadata_em,
    fetch_fund_metadata,
    fetch_fund_nav_history,
)
from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.manifest import ManifestEntry, write_manifest
from irc.data.openbb_client import fetch_etf_price_history, fetch_macro_series
from irc.data.raw_ref import build_ref_id
from irc.instrument_kind import requires_manager_tenure as _is_active_fund
from irc.pipeline_halt import HaltReason

_log = logging.getLogger(__name__)

_SCHEMA_VERSION = "v1"
@dataclass(frozen=True)
class _MacroSeriesSpec:
    source_id: str
    storage_id: str


_MACRO_SERIES = (
    _MacroSeriesSpec(source_id="DGS10", storage_id="DGS10"),
    _MacroSeriesSpec(source_id="DXY", storage_id="DXY"),
    _MacroSeriesSpec(source_id="DFII10", storage_id="real_yield_10y_tips"),
    _MacroSeriesSpec(source_id="VIXCLS", storage_id="vix"),
    _MacroSeriesSpec(source_id="T5YIFR", storage_id="inflation_5y5y"),
)
_LOOK_BACK_DAYS = 365 * 3
_PRICE_HISTORY_MARKETS = frozenset({"cn_on_exchange"})
_AUM_UNITS = {
    "万亿": 1_000_000_000_000.0,
    "亿元": 100_000_000.0,
    "亿": 100_000_000.0,
    "万元": 10_000.0,
    "万": 10_000.0,
}
_MISSING_TEXT = frozenset({"", "-", "--", "nan", "none", "null"})


class _IngestFeatureFlags(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    active_fund_tenure_proxy_enabled: bool = True


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _china_today() -> str:
    """Return today's date as ISO string in the China Standard Time (UTC+8) zone."""
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _date_window() -> tuple[str, str]:
    today = datetime.now(timezone(timedelta(hours=8))).date()
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


def _has_price_history_source(instrument: Any) -> bool:
    return instrument.market in _PRICE_HISTORY_MARKETS


def _is_off_exchange_fund(instrument: Any) -> bool:
    return instrument.market == "cn_off_exchange" and instrument.ticker.isdigit()


def _years_since_iso_date(iso_date: str | None) -> float | None:
    """Years between iso_date (YYYY-MM-DD) and today, rounded to 2dp."""
    if iso_date is None:
        return None
    try:
        anchor = datetime.fromisoformat(iso_date).date()
    except ValueError:
        return None
    today = datetime.now(timezone(timedelta(hours=8))).date()
    return round((today - anchor).days / 365.25, 2)


def _normalize_fund_metadata(raw: dict[str, Any]) -> dict[str, float | str | None]:
    return {
        "inception_date": _normal_date(_metadata_value(raw, "inception_date", "成立日期")),
        "expense_ratio": _parse_ratio(_metadata_value(raw, "expense_ratio", "费率")),
        "aum": _parse_aum_cny(_metadata_value(raw, "aum", "aum_text", "基金规模")),
        "manager_tenure_years": _parse_float(
            _metadata_value(raw, "manager_tenure_years", "manager_tenure", "基金经理任职年限")
        ),
    }


def _apply_active_fund_tenure_fallback(
    instrument: Any,
    metadata: dict[str, float | str | None],
    enabled: bool = True,
) -> dict[str, float | str | None]:
    """For active funds without explicit tenure, use fund age as a temporary
    proxy. XueQiu's basic-info endpoint doesn't expose manager tenure for active
    funds, so without this fallback well-known long-running funds get silently
    dropped. This may overstate current-manager tenure after manager changes.
    Passive ETFs are unaffected — they don't need tenure.
    TODO: wire up `fund_manager_em` for accurate per-fund tenure."""
    if not enabled or not _is_active_fund(instrument):
        return metadata
    if metadata.get("manager_tenure_years") is not None:
        return metadata
    fallback = _years_since_iso_date(metadata.get("inception_date"))
    if fallback is None or fallback <= 0:
        return metadata
    return {**metadata, "manager_tenure_years": fallback}


def _missing_required_metadata(instrument: Any, metadata: dict[str, Any]) -> tuple[str, ...]:
    required = ("inception_date", "expense_ratio", "aum")
    if _is_active_fund(instrument):
        required = (*required, "manager_tenure_years")
    return tuple(key for key in required if _is_missing(metadata.get(key)))


def _price_source_for(instrument: Any) -> str:
    if instrument.market == "cn_on_exchange":
        return "akshare"
    return "openbb"


def _coerce_price_history(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in ("open", "high", "low", "close", "volume"):
        out[column] = pd.to_numeric(out[column], errors="raise")
    return out


def _coerce_nav_history(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["nav"] = pd.to_numeric(out["nav"], errors="raise")
    out["nav_acc"] = pd.to_numeric(out["nav_acc"], errors="coerce")
    return out


def _metadata_fetcher_for(instrument: Any):
    """On-exchange ETFs are sold on the exchange, not via DanJuanFunds — they need
    the EastMoney profile-page scraper. Off-exchange retail funds use DanJuan."""
    if instrument.market == "cn_on_exchange":
        return fetch_etf_metadata_em
    return fetch_fund_metadata


def _fetch_metadata_by_id(
    instruments: list,
    active_fund_tenure_proxy_enabled: bool = True,
) -> tuple[dict[str, dict[str, float | str | None]], ErrorTally]:
    metadata_by_id: dict[str, dict[str, float | str | None]] = {}
    tally = ErrorTally("metadata")
    for instrument in progress_iter(instruments, "metadata", total=len(instruments)):
        if not _is_fund_like_ticker(instrument.ticker):
            continue
        try:
            fetch = _metadata_fetcher_for(instrument)
            metadata = _apply_active_fund_tenure_fallback(
                instrument,
                _normalize_fund_metadata(fetch(instrument.ticker)),
                enabled=active_fund_tenure_proxy_enabled,
            )
        except Exception as exc:
            tally.add(instrument.instrument_id, exc)
            _log.warning(
                "skipping %s: metadata fetch error: %s",
                instrument.instrument_id,
                exc,
            )
            continue
        missing = _missing_required_metadata(instrument, metadata)
        if missing:
            joined = ", ".join(missing)
            tally.add(instrument.instrument_id, KeyError(f"missing required metadata: {joined}"))
            _log.warning(
                "skipping %s: missing required metadata fields: %s",
                instrument.instrument_id,
                joined,
            )
            continue
        metadata_by_id[instrument.instrument_id] = metadata
    return metadata_by_id, tally


def _upsert_instruments(
    con,
    instruments: list,
    metadata_by_id: dict[str, dict[str, float | str | None]] | None = None,
) -> int:
    ingested_at = _now_iso()
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
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


def _upsert_prices(con, instrument_id: str, df: pd.DataFrame, source: str = "openbb") -> int:
    ingested_at = _now_iso()
    params = [
        [instrument_id, str(r.date), r.open, r.high, r.low, r.close, r.volume,
         ingested_at, source, build_ref_id(source, "prices", instrument_id, str(r.date))]
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


def _preflight_call() -> None:
    """One cheap akshare call exercising the HTTP pathway. Overridable in tests.

    Uses 510300 (CSI300 ETF) as the canary symbol — it is one of the oldest
    and most stable funds, so a successful return implies broad akshare
    reachability. We discard the returned frame; only the network outcome
    matters here.
    """
    fetch_fund_nav_history("510300")


def _ingest_preflight() -> HaltReason | None:
    """Run the preflight canary. Returns a HaltReason on failure, None on success.

    KeyboardInterrupt and SystemExit propagate (BaseException, not Exception).
    """
    try:
        _preflight_call()
        return None
    except Exception as exc:  # noqa: BLE001 — we re-classify below
        first_error = f"{type(exc).__name__}: {exc}"
        if _is_transient_network_error(exc):
            return HaltReason(
                kind="akshare_unreachable",
                stage="ingest",
                detail="preflight canary failed with a transient network error",
                first_error=first_error,
            )
        return HaltReason(
            kind="akshare_error",
            stage="ingest",
            detail="preflight canary raised a non-network exception",
            first_error=first_error,
        )


def run_ingest(repo_root: str) -> int:
    root = Path(repo_root)
    # Stale-guard: remove any sidecar from a prior run for today.
    today_iso = _china_today()
    sidecar_path = root / "outputs" / today_iso / ".halt_reason.json"
    if sidecar_path.exists():
        sidecar_path.unlink()

    # Preflight: one cheap akshare call to fail fast on outages.
    preflight = _ingest_preflight()
    if preflight is not None:
        HaltReason.write_sidecar(sidecar_path, preflight)
        print(f"ERROR: ingest preflight failed: {preflight.kind} — {preflight.detail}")
        return 1

    bundle = load_repo_configs(root)
    try:
        feature_flags = _IngestFeatureFlags(_env_file=root / ".env")
    except Exception as exc:
        print(f"ERROR: invalid config in .env — {exc}")
        return 1
    db_path = root / "data" / "local.duckdb"

    con = connect(db_path)
    try:
        ensure_schema(con)
        start, end = _date_window()
        ob_counts: dict[str, int] = {"prices": 0, "macro_series": 0, "instruments": 0}
        ak_counts: dict[str, int] = {"prices": 0, "nav_history": 0}

        all_instruments = [
            *bundle.universe_qdii_us.instruments,
            *bundle.universe_qdii_hk.instruments,
            *bundle.universe_gold.instruments,
            *bundle.universe_cn_funds.instruments,
        ]
        try:
            from irc.settings import Settings as _S
            _verbose = _S().debug
        except Exception:
            import os
            _verbose = os.environ.get("DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}

        metadata_by_id, metadata_tally = _fetch_metadata_by_id(
            all_instruments,
            active_fund_tenure_proxy_enabled=feature_flags.active_fund_tenure_proxy_enabled,
        )
        ob_counts["instruments"] = _upsert_instruments(con, all_instruments, metadata_by_id)

        price_failures: list[str] = []
        price_first_exc: str | None = None
        price_attempts = 0
        price_successes = 0
        eastmoney_unavailable = False

        def _mark_eastmoney_unavailable() -> None:
            nonlocal eastmoney_unavailable
            eastmoney_unavailable = True

        prices_tally = ErrorTally("prices")
        price_candidates = [i for i in all_instruments if _has_price_history_source(i)]
        for instr in progress_iter(price_candidates, "prices", total=len(price_candidates)):
            price_attempts += 1
            try:
                df = fetch_etf_price_history(
                    ticker=instr.ticker,
                    start=start,
                    end=end,
                    skip_cn_eastmoney=eastmoney_unavailable,
                    on_cn_eastmoney_exhausted=_mark_eastmoney_unavailable,
                )
                if df.empty:
                    raise ValueError("empty price history")
                df = _coerce_price_history(df)
            except Exception as exc:
                price_failures.append(instr.instrument_id)
                if price_first_exc is None:
                    price_first_exc = f"{type(exc).__name__}: {exc}"
                prices_tally.add(instr.instrument_id, exc)
                _log.warning(
                    "skipping price ingest for %s (ticker=%s): %s. "
                    "Other instruments will still be processed; rerun once "
                    "the upstream source recovers.",
                    instr.instrument_id, instr.ticker, exc,
                )
                continue
            try:
                price_source = _price_source_for(instr)
                inserted = _upsert_prices(
                    con,
                    instr.instrument_id,
                    df,
                    source=price_source,
                )
                if price_source == "akshare":
                    ak_counts["prices"] += inserted
                else:
                    ob_counts["prices"] += inserted
            except Exception as exc:
                print(
                    f"ERROR: ingest failed while writing prices for "
                    f"{instr.instrument_id}: {exc}"
                )
                return 1
            price_successes += 1
        # Log warning for instruments outside price_candidates that are not off-exchange
        for instr in all_instruments:
            if not _has_price_history_source(instr) and not _is_off_exchange_fund(instr):
                _log.warning(
                    "skipping price/nav ingest for %s (market=%s, ticker=%s): no source available",
                    instr.instrument_id, instr.market, instr.ticker,
                )

        for series in _MACRO_SERIES:
            try:
                df = fetch_macro_series(series_id=series.source_id, start=start, end=end)
                ob_counts["macro_series"] += _upsert_macro(con, series.storage_id, df)
            except Exception as exc:
                _log.warning(
                    "skipping macro series %s: %s. Set FRED_API_KEY for live "
                    "data (https://fred.stlouisfed.org/docs/api/api_key.html); "
                    "downstream stages fall back to defaults when absent.",
                    series.source_id, exc,
                )

        nav_candidates = [
            i for i in all_instruments
            if _is_off_exchange_fund(i)
        ]
        seen_nav_ids: set[str] = set()
        nav_instruments = []
        for instr in nav_candidates:
            if instr.instrument_id in seen_nav_ids:
                continue
            seen_nav_ids.add(instr.instrument_id)
            nav_instruments.append(instr)
        nav_tally = ErrorTally("nav")
        nav_failures: list[str] = []
        nav_first_exc: str | None = None
        nav_attempts = 0
        nav_successes = 0
        for instr in progress_iter(nav_instruments, "nav", total=len(nav_instruments)):
            nav_attempts += 1
            try:
                df = fetch_fund_nav_history(instr.ticker)
                if df.empty:
                    raise ValueError("empty NAV history")
                df = _coerce_nav_history(df)
            except Exception as exc:
                nav_failures.append(instr.instrument_id)
                if nav_first_exc is None:
                    nav_first_exc = f"{type(exc).__name__}: {exc}"
                nav_tally.add(instr.instrument_id, exc)
                _log.warning(
                    "skipping NAV ingest for %s (ticker=%s): %s. "
                    "Other instruments will still be processed.",
                    instr.instrument_id, instr.ticker, exc,
                )
                continue
            try:
                ak_counts["nav_history"] += _upsert_nav(con, instr.instrument_id, df)
            except Exception as exc:
                print(
                    f"ERROR: ingest failed while writing NAV for "
                    f"{instr.instrument_id}: {exc}"
                )
                return 1
            nav_successes += 1

    finally:
        con.close()

    fatal_failures: list[str] = []
    if price_attempts and price_successes == 0:
        fatal_failures.append("prices")
    if nav_attempts and nav_successes == 0:
        fatal_failures.append("nav")
    if fatal_failures:
        first_error = price_first_exc or nav_first_exc or ""
        halt = HaltReason(
            kind="akshare_empty",
            stage="ingest",
            detail=f"no successful {', '.join(fatal_failures)} ingest",
            stats={
                "price_attempts": price_attempts,
                "price_successes": price_successes,
                "nav_attempts": nav_attempts,
                "nav_successes": nav_successes,
            },
            first_error=first_error or None,
        )
        HaltReason.write_sidecar(sidecar_path, halt)
        print(f"ERROR: ingest failed: {halt.detail}")
        if price_failures or nav_failures:
            print(
                f"  skipped due to upstream errors — prices: {price_failures or 'none'}; "
                f"nav: {nav_failures or 'none'}"
            )
        return 1

    data_root = root / "data"
    write_manifest(data_root, ManifestEntry(
        source="openbb", last_run_at=_now_iso(),
        schema_version=_SCHEMA_VERSION, record_counts=ob_counts,
    ))
    write_manifest(data_root, ManifestEntry(
        source="akshare", last_run_at=_now_iso(),
        schema_version=_SCHEMA_VERSION, record_counts=ak_counts,
    ))
    metadata_tally.render(ok_count=len(metadata_by_id), verbose=_verbose)
    prices_tally.render(ok_count=price_successes, verbose=_verbose)
    nav_tally.render(ok_count=nav_successes, verbose=_verbose)
    # A successful ingest invalidates any prior PIPELINE_HALTED.md sentinel for
    # today. Without this, a stale halt from an earlier failed run would keep
    # poisoning the decision stage's pipeline_halted gate forever — even after
    # the underlying network/data issue has cleared.
    halted_path = root / "outputs" / today_iso / "PIPELINE_HALTED.md"
    halted_path.unlink(missing_ok=True)
    print(f"ingest OK: openbb={ob_counts}, akshare={ak_counts}")
    if price_failures or nav_failures:
        print(
            f"  skipped due to upstream errors — prices: {price_failures or 'none'}; "
            f"nav: {nav_failures or 'none'}"
        )
    return 0
