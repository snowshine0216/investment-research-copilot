"""TushareProvider (item 003, ADR 0010 §4) — per-method fallback for CN funds.

All network I/O is confined to `_tushare_call`, which does the LOCAL
`import tushare` so this module never imports tushare at load. Frame→DTO mapping
is pure and unit-tested against fixture frames. Every method degrades to
`None`/`()` on any failure / empty / missing-column / empty-token — it never
raises (ADR 0009 degrade-to-None family).

Endpoint mapping (columns matched defensively, the _PE_COLS/_PB_COLS precedent):
  filing digest   → fina_indicator (+income corroboration)
  broker target   → report_rc        (points/paid-tier gated; pinned by the
                                       double-gated live test, never offline)
  index valuation → index_dailybasic

Tushare is CN (api.tushare.pro) → called DIRECT, never through IRC_HTTPS_PROXY.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.types import BrokerReport, FilingDigest

_log = logging.getLogger(__name__)

# Candidate column sets (defensive — Tushare labels can shift across tiers).
_PE_COLS: tuple[str, ...] = ("pe_ttm", "pe")
_PB_COLS: tuple[str, ...] = ("pb",)
_DIV_COLS: tuple[str, ...] = ("dv_ratio", "dv_ttm")
_REV_YOY_COLS: tuple[str, ...] = ("or_yoy", "tr_yoy")
_NI_YOY_COLS: tuple[str, ...] = ("netprofit_yoy", "dt_netprofit_yoy")
_GM_COLS: tuple[str, ...] = ("grossprofit_margin",)
_ROE_COLS: tuple[str, ...] = ("roe", "roe_waa")


def _tushare_call(token: str, fn_name: str, **kwargs: Any) -> Any:
    """Network edge (mirrors akshare `_ak_call`). Local import; direct, no proxy."""
    import tushare as ts  # local import — never at module load

    pro = ts.pro_api(token)
    return getattr(pro, fn_name)(**kwargs)


def _today_iso() -> str:
    return date.today().isoformat()


def _to_ts_code(symbol: str) -> str:
    """'600519.SH' or '600519' → '600519.SH' (Tushare's ts_code form)."""
    code = str(symbol).strip()
    if "." in code:
        return code
    head = code[:1]
    if head in ("5", "6"):
        suffix = "SH"
    elif head in ("4", "8"):
        suffix = "BJ"
    else:
        suffix = "SZ"
    return f"{code}.{suffix}"


def _first_col(df: pd.DataFrame, cols: tuple[str, ...]) -> str | None:
    return next((c for c in cols if c in df.columns), None)


def _pct_to_ratio(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f / 100.0


def _coerce_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _period_from_end_date(end_date: str) -> tuple[str, str] | None:
    """'YYYYMMDD' → (fiscal_period, filed_at_iso), or None if mmdd is unrecognized.

    Recognized mmdd values: '1231' (FY), '0331' (Q1), '0630' (Q2), '0930' (Q3).
    Any other value (e.g. a restatement row dated '0228') returns None so the
    caller can degrade cleanly instead of emitting a malformed fiscal_period.
    """
    year, mmdd = end_date[:4], end_date[4:]
    quarter_map = {"0331": "Q1", "0630": "Q2", "0930": "Q3"}
    if mmdd == "1231":
        period = f"{year}FY"
    elif mmdd in quarter_map:
        period = f"{year}{quarter_map[mmdd]}"
    else:
        return None
    filed = f"{year}-{mmdd[:2]}-{mmdd[2:]}"
    return period, filed


def _map_fina_to_digest(ts_code: str, df: pd.DataFrame) -> FilingDigest | None:
    if not isinstance(df, pd.DataFrame) or df.empty or "end_date" not in df.columns:
        return None
    row = df.sort_values("end_date", ascending=False).iloc[0]
    end_date = str(row["end_date"])
    if len(end_date) != 8 or not end_date.isdigit():
        return None
    result = _period_from_end_date(end_date)
    if result is None:
        return None
    period, filed = result
    rev = _first_col(df, _REV_YOY_COLS)
    ni = _first_col(df, _NI_YOY_COLS)
    gm = _first_col(df, _GM_COLS)
    roe = _first_col(df, _ROE_COLS)
    return FilingDigest(
        symbol=ts_code,
        fiscal_period=period,
        filed_at_iso=filed,
        revenue_yoy=_pct_to_ratio(row[rev]) if rev else None,
        net_income_yoy=_pct_to_ratio(row[ni]) if ni else None,
        gross_margin=_pct_to_ratio(row[gm]) if gm else None,
        source_url="https://tushare.pro/document/2?doc_id=79",
        roe=_pct_to_ratio(row[roe]) if roe else None,
    )


def _map_report_rc_to_brokers(ts_code: str, df: pd.DataFrame) -> tuple[BrokerReport, ...]:
    if not isinstance(df, pd.DataFrame) or df.empty or "report_date" not in df.columns:
        return ()
    out: list[BrokerReport] = []
    has_tp = "target_price" in df.columns
    for _, row in df.iterrows():
        rd = str(row.get("report_date", ""))
        if len(rd) != 8 or not rd.isdigit():
            continue
        out.append(BrokerReport(
            symbol=ts_code,
            broker=str(row.get("org_name", "") or ""),
            rating=str(row.get("rating", "") or ""),
            target_price=_coerce_float(row["target_price"]) if has_tp else None,
            published_iso=f"{rd[:4]}-{rd[4:6]}-{rd[6:]}",
            title=str(row.get("report_title", "") or ""),
            source_url="",
        ))
    return tuple(out)


def _map_index_dailybasic(
    index_key: str, df: pd.DataFrame, *, as_of_iso: str
) -> IndexValuation | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    row = (
        df.sort_values("trade_date", ascending=False).iloc[0]
        if "trade_date" in df.columns
        else df.iloc[-1]
    )
    pe = _first_col(df, _PE_COLS)
    pb = _first_col(df, _PB_COLS)
    dv = _first_col(df, _DIV_COLS)
    if pe is None and pb is None:
        return None
    return IndexValuation(
        index_key=index_key,
        pe_ttm=_coerce_float(row[pe]) if pe else None,
        pb=_coerce_float(row[pb]) if pb else None,
        dividend_yield=_coerce_float(row[dv]) if dv else None,
        as_of_iso=as_of_iso,
    )


# Tushare index code map (only the broad indices the seam reaches; unknown → None).
_INDEX_TS_CODE: dict[str, str] = {
    "csi300": "000300.SH",
    "csi500": "000905.SH",
    "sse50": "000016.SH",
    "chinext": "399006.SZ",
}


class TushareProvider:
    """Per-method Tushare fallback. Holds only the immutable token. Stateless."""

    def __init__(self, token: str) -> None:
        self._token = token

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None:
        if not self._token:
            return None
        ts_code = _to_ts_code(symbol)
        try:
            df = _tushare_call(self._token, "fina_indicator", ts_code=ts_code)
        except Exception as exc:
            _log.warning(
                "TushareProvider.fetch_filing_digest(%r) failed: %s: %s",
                symbol, type(exc).__name__, exc,
            )
            return None
        return _map_fina_to_digest(ts_code, df)

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]:
        if not self._token:
            return ()
        ts_code = _to_ts_code(symbol)
        start = (pd.Timestamp(_today_iso()) - pd.Timedelta(days=days)).strftime("%Y%m%d")
        try:
            df = _tushare_call(
                self._token, "report_rc", ts_code=ts_code, start_date=start
            )
        except Exception as exc:
            _log.warning(
                "TushareProvider.fetch_broker_reports(%r) failed: %s: %s",
                symbol, type(exc).__name__, exc,
            )
            return ()
        return _map_report_rc_to_brokers(ts_code, df)[:max_reports]

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None:
        if not self._token:
            return None
        ts_code = _INDEX_TS_CODE.get(index_key)
        if ts_code is None:
            return None
        try:
            df = _tushare_call(self._token, "index_dailybasic", ts_code=ts_code)
        except Exception as exc:
            _log.warning(
                "TushareProvider.fetch_index_valuation(%r) failed: %s: %s",
                index_key, type(exc).__name__, exc,
            )
            return None
        return _map_index_dailybasic(index_key, df, as_of_iso=_today_iso())
