from __future__ import annotations

from collections.abc import Callable
import contextlib
from functools import lru_cache
import os
import re
import threading
import time
from typing import Any, Generator, TypeVar

import pandas as pd

from irc.http_proxy import resolve_proxy

_EM_PROFILE_URL = "https://fundf10.eastmoney.com/jbgk_{symbol}.html"
_EM_HEADERS = {"User-Agent": "Mozilla/5.0"}
_T = TypeVar("_T")
_AKSHARE_PROXY_LOCK = threading.Lock()


class FundNotFound(LookupError):
    """Raised when a fund_code is not present in the akshare fund table."""


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids heavy akshare import at module load."""
    import akshare as ak  # local import
    fn = getattr(ak, fn_name)
    return fn(**kwargs)


@contextlib.contextmanager
def _proxy_env(proxy_url: str) -> Generator[None, None, None]:
    """Temporarily inject HTTP/HTTPS proxy env vars so requests-based libs
    (akshare, etc.) route through the proxy. Restores original values on exit."""
    keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ[k] = proxy_url
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _sleep(seconds: float) -> None:
    """Indirection so tests can fast-forward through retry backoff."""
    time.sleep(seconds)


def _retry_transient(
    operation: Callable[[], _T],
    is_transient: Callable[[BaseException], bool],
    attempts: int,
    backoff_s: float,
) -> _T:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if not is_transient(exc):
                raise
            last_exc = exc
            if attempt < attempts - 1:
                _sleep(backoff_s * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


def _is_transient_network_error(exc: BaseException) -> bool:
    """Match the connection-class errors that bubble up from EastMoney's
    feed: requests.exceptions.ConnectionError (subclass of OSError) and
    urllib3 ProtocolError (RemoteDisconnected, IncompleteRead, etc.).
    Pattern-match on message as a backstop for libraries that wrap the
    cause in a generic Exception."""
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    # Explicit allowlist of OS-level errors that are genuinely network-related.
    # Broad OSError catch-all is intentionally avoided: BlockingIOError,
    # ChildProcessError, InterruptedError, etc. are not network failures and
    # must not be silently retried.
    _NETWORK_OS_ERRORS = (
        ConnectionResetError, ConnectionAbortedError,
        ConnectionRefusedError, BrokenPipeError,
    )
    if isinstance(exc, _NETWORK_OS_ERRORS):
        return True
    msg = str(exc).lower()
    return any(token in msg for token in (
        "connection aborted",
        "remotedisconnected",
        "remote end closed",
        "connection reset",
        "read timed out",
    ))


def _http_get(
    url: str,
    headers: dict[str, str],
    timeout: float,
    attempts: int = 3,
    backoff_s: float = 1.0,
) -> str:
    """HTTP GET with retry on transient network failures (timeout / connection
    reset). Indirection also lets tests mock without touching the network."""
    import requests  # local import

    def _get() -> str:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text

    return _retry_transient(
        _get,
        lambda exc: isinstance(exc, (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        )),
        attempts,
        backoff_s,
    )


def fetch_fund_nav_history(fund_code: str) -> pd.DataFrame:
    """Open-ended fund NAV history. Returns DataFrame with columns: date, nav, nav_acc."""
    df = _ak_call("fund_open_fund_info_em", symbol=fund_code, indicator="单位净值走势")
    if "净值日期" in df.columns:
        df = df.rename(columns={
            "净值日期": "date",
            "单位净值": "nav",
            "累计净值": "nav_acc",
        })
    if "nav_acc" not in df.columns:
        df = df.assign(nav_acc=pd.NA)
    return df[["date", "nav", "nav_acc"]].copy()


def _item_value_dict(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {}
    if {"item", "value"}.issubset(df.columns):
        return {str(r.item): r.value for r in df.itertuples(index=False)}
    if {"项目", "数据"}.issubset(df.columns):
        return dict(zip(df["项目"].astype(str), df["数据"]))
    if len(df) == 1:
        return {str(k): v for k, v in df.iloc[0].to_dict().items()}
    return {}


def _ratios_from_text(value: Any) -> tuple[float, ...]:
    if value is None or pd.isna(value):
        return ()
    text = str(value).strip().replace("％", "%")
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    if matches:
        return tuple(float(match) / 100 for match in matches)
    try:
        return (float(text),)
    except ValueError:
        return ()


def _expense_ratio_from_fee_table(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    total = 0.0
    found = False
    for row in df.itertuples(index=False, name=None):
        row_text = " ".join(str(v) for v in row if not pd.isna(v))
        if not any(label in row_text for label in ("管理费", "托管费", "销售服务费")):
            continue
        ratios = _ratios_from_text(row_text)
        if ratios:
            total += sum(ratios)
            found = True
    return total if found else None


def _raw_fund_table_call() -> pd.DataFrame:
    """Raw call to akshare for open-ended fund table. Extracted for lru_cache wrapping."""
    return _ak_call("fund_open_fund_daily_em")


@lru_cache(maxsize=1)
def _fetch_full_fund_table() -> pd.DataFrame:
    """Fetch the master open-ended fund catalog. Returns DataFrame with 'fund_code' column."""
    df = _raw_fund_table_call()
    if "基金代码" in df.columns:
        rename_map = {"基金代码": "fund_code"}
        if "基金名称" in df.columns:
            rename_map["基金名称"] = "fund_name"
        elif "基金简称" in df.columns:
            rename_map["基金简称"] = "fund_name"
        if "基金类型" in df.columns:
            rename_map["基金类型"] = "fund_type"
        df = df.rename(columns=rename_map)
    return df


def _normalize_fund_code(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


@lru_cache(maxsize=1)
def fetch_open_fund_catalog() -> pd.DataFrame:
    """Fetch Akshare's open-fund catalog with stable internal column names."""
    df = _fetch_full_fund_table()  # reuses existing cache
    required_cols = ["fund_code", "fund_name"]
    missing = [column for column in required_cols if column not in df.columns]
    if missing:
        raise ValueError(f"Akshare open fund catalog missing columns: {', '.join(missing)}")
    out_cols = [c for c in ["fund_code", "fund_name", "fund_type"] if c in df.columns]
    out = df.loc[:, out_cols].copy()
    # Ensure fund_type column exists (may be absent from daily-nav endpoint)
    if "fund_type" not in out.columns:
        out["fund_type"] = ""
    for column in out.columns:
        out[column] = out[column].astype(str).str.strip()
    return out


def _raw_fund_rank_call() -> pd.DataFrame:
    """Raw call to akshare's fund-rank table. Extracted for lru_cache wrapping."""
    return _ak_call("fund_open_fund_rank_em", symbol="全部")
    # Per-type fallback if "全部" is unavailable in 1.18.60:
    # frames = [
    #     _ak_call("fund_open_fund_rank_em", symbol=s)
    #     for s in ("股票型", "混合型", "债券型", "指数型", "QDII", "LOF", "FOF")
    # ]
    # return pd.concat(frames, ignore_index=True)


def _parse_percent(value: Any) -> float:
    """Convert '45.32%' / '-3.50%' / '--' / '' / NaN / numeric → float or NaN.

    Note: the akshare fund-rank endpoint returns numeric floats directly (e.g.
    54.85 for 54.85%), not percent-formatted strings. This helper handles both
    forms so tests and real data are both covered.
    """
    if value is None:
        return float("nan")
    if isinstance(value, float):
        import math
        return float("nan") if math.isnan(value) else value
    if isinstance(value, (int,)):
        return float(value)
    text = str(value).strip().rstrip("%")
    if not text or text in {"--", "nan", "None"}:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


@lru_cache(maxsize=1)
def _fetch_full_fund_rank_table() -> pd.DataFrame:
    """Fetch the master fund-rank table with stable internal column names."""
    df = _raw_fund_rank_call()
    rename_map: dict[str, str] = {}
    if "基金代码" in df.columns:
        rename_map["基金代码"] = "fund_code"
    if "近1年" in df.columns:
        rename_map["近1年"] = "return_1y"
    df = df.rename(columns=rename_map)
    if "fund_code" in df.columns:
        df["fund_code"] = df["fund_code"].apply(_normalize_fund_code)
    if "return_1y" in df.columns:
        df["return_1y"] = df["return_1y"].apply(_parse_percent)
    return df


@lru_cache(maxsize=1)
def fetch_open_fund_ranks() -> pd.DataFrame:
    """Public accessor for the fund-rank table. Returns DataFrame with
    'fund_code' and 'return_1y' columns; return_1y is float (NaN for missing)."""
    df = _fetch_full_fund_rank_table()
    required = ["fund_code", "return_1y"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Akshare fund-rank table missing columns: {', '.join(missing)}")
    return df.loc[:, required].copy()


def fetch_fund_metadata(fund_code: str) -> dict[str, Any]:
    """Single-row metadata dict via XueQiu — the only akshare path that returns
    individual-fund metadata in 1.18.60. XueQiu is auth-restricted and may fail
    intermittently; callers handle the exception by skipping the instrument.

    Raises FundNotFound if the fund_code is absent from the full fund table.
    """
    normalized_fund_code = _normalize_fund_code(fund_code)
    table = _fetch_full_fund_table()
    if "fund_code" in table.columns:
        catalog_codes = table["fund_code"].map(_normalize_fund_code)
        matches = table[catalog_codes == normalized_fund_code]
        if matches.empty:
            raise FundNotFound(f"fund_code {normalized_fund_code!r} not in akshare fund table")
    basic = _item_value_dict(_ak_call("fund_individual_basic_info_xq", symbol=normalized_fund_code))
    basic_code = _normalize_fund_code(basic.get("基金代码") or basic.get("fund_code") or "")
    if not basic or basic_code != normalized_fund_code:
        raise ValueError(f"fund {normalized_fund_code!r} not found in AKShare basic info")
    fees = _ak_call("fund_fee_em", symbol=normalized_fund_code, indicator="运作费用")
    return {
        "fund_code": _normalize_fund_code(basic.get("基金代码") or basic.get("fund_code") or normalized_fund_code),
        "name_cn": str(basic.get("基金名称") or basic.get("基金简称") or basic.get("name_cn") or ""),
        "fund_type": str(basic.get("基金类型") or basic.get("fund_type") or ""),
        "aum_text": str(basic.get("最新规模") or basic.get("基金规模") or basic.get("资产规模") or basic.get("aum_text") or ""),
        "inception_date": str(basic.get("成立时间") or basic.get("成立日期") or "") or None,
        "expense_ratio": _expense_ratio_from_fee_table(fees),
        "manager_tenure_years": basic.get("manager_tenure_years") or basic.get("基金经理任职年限"),
    }


_EM_LABEL_PATTERN = (
    r"<th>{label}</th>\s*<td[^>]*>(.*?)</td>"
)


def _grab_em_label(html: str, label: str) -> str | None:
    pattern = _EM_LABEL_PATTERN.format(label=re.escape(label))
    match = re.search(pattern, html, re.DOTALL)
    if match is None:
        return None
    return re.sub(r"<[^>]+>", "", match.group(1)).strip()


def _percent_to_ratio(text: str | None) -> float:
    if not text:
        return 0.0
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return 0.0 if match is None else float(match.group(1)) / 100


def _parse_inception_date_em(raw: str | None) -> str | None:
    if not raw:
        return None
    match = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})", raw)
    if match is None:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _parse_aum_em(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = raw.replace(",", "")
    match = re.match(r"([\d.]+\s*[万亿元]+)", cleaned)
    return match.group(1) if match else cleaned


def fetch_etf_metadata_em(symbol: str) -> dict[str, Any]:
    """On-exchange ETF metadata via EastMoney's fund-profile page (fundf10.eastmoney.com).

    DanJuanFunds (the API behind ``fund_individual_basic_info_xq``) only carries
    open-ended retail funds — it returns ``{"result_code":600001,...}`` for any
    exchange-traded ETF. EastMoney's profile page is the unauthenticated source
    that does carry exchange-traded ETFs."""
    html = _http_get(_EM_PROFILE_URL.format(symbol=symbol), _EM_HEADERS, timeout=30)
    name = _grab_em_label(html, "基金简称")
    fund_type = _grab_em_label(html, "基金类型")
    inception_raw = _grab_em_label(html, "成立日期/规模") or _grab_em_label(html, "成立日期")
    aum_raw = _grab_em_label(html, "净资产规模")
    expense_ratio = (
        _percent_to_ratio(_grab_em_label(html, "管理费率"))
        + _percent_to_ratio(_grab_em_label(html, "托管费率"))
        + _percent_to_ratio(_grab_em_label(html, "销售服务费率"))
    )
    if not name and not inception_raw and not aum_raw:
        raise ValueError(f"ETF {symbol!r} not found on EastMoney profile page")
    return {
        "fund_code": symbol,
        "name_cn": name or "",
        "fund_type": fund_type or "",
        "aum_text": _parse_aum_em(aum_raw),
        "inception_date": _parse_inception_date_em(inception_raw),
        "expense_ratio": expense_ratio if expense_ratio > 0 else None,
        "manager_tenure_years": None,
    }


_AKSHARE_MACRO_HANDLERS: dict[str, str] = {
    # macro series_id → akshare resolver-method name (registered below).
    # DGS10 is a FRED series; DXY is an akshare-only proxy (no FRED equivalent
    # at the same level — DTWEXBGS sits ~120 vs DXY ~98).
    "DGS10": "_fetch_dgs10_via_akshare",
    "DXY": "_fetch_dxy_via_akshare",
}


def _fetch_dgs10_via_akshare(start: str, end: str) -> pd.DataFrame:
    raw = _ak_call("bond_zh_us_rate")
    df = raw[["日期", "美国国债收益率10年"]].rename(columns={"日期": "date", "美国国债收益率10年": "value"})
    df = df.dropna(subset=["value"])
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)


def _fetch_dxy_via_akshare(start: str, end: str) -> pd.DataFrame:
    """DXY (ICE 6-currency US Dollar Index) is the broad-USD proxy used by gold
    scoring; thresholds in scoring/gold_score.py and scoring/gold_scenarios.py
    are calibrated for DXY's ~95–115 range. FRED's DTWEXBGS sits ~120 and is
    not interchangeable, so this path is the canonical DXY source.

    If IRC_HTTPS_PROXY is set in the environment, the EastMoney request is
    routed through that proxy (useful when the host is geo-restricted).

    The DXY path is the only akshare call that opts in — other akshare
    sources serve mainland-CN domains where a non-CN proxy would hurt."""
    proxy_url = resolve_proxy()
    ctx = _proxy_env(proxy_url) if proxy_url else contextlib.nullcontext()
    # _proxy_env temporarily mutates process env; lock to avoid cross-thread bleed.
    with _AKSHARE_PROXY_LOCK:
        with ctx:
            raw = _ak_call("index_global_hist_em", symbol="美元指数")
    df = raw[["日期", "最新价"]].rename(columns={"日期": "date", "最新价": "value"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)


def _to_sina_symbol(ticker: str) -> str:
    """Map 6-digit CN ticker to Sina finance symbol (sh510300 / sz159919).
    Shanghai codes start with 5/6 → sh prefix; Shenzhen codes 0/1/2/3 → sz."""
    if not ticker or not ticker.isdigit():
        raise ValueError(f"Expected 6-digit numeric CN ticker, got: {ticker!r}")
    prefix = "sh" if ticker[0] in ("5", "6") else "sz"
    return f"{prefix}{ticker}"


def _fetch_etf_price_history_sina(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Sina finance ETF history. Independent host (finance.sina.com.cn) —
    used as fallback when EastMoney's push2his.* endpoint is being dropped
    (the host is sometimes blocked at network layer for non-CN-mainland IPs).
    Sina returns full-history rows (1999+); we filter client-side."""
    df = _ak_call("fund_etf_hist_sina", symbol=_to_sina_symbol(symbol))
    out = df.assign(date=pd.to_datetime(df["date"]).dt.date)
    start_d = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    mask = (out["date"] >= start_d) & (out["date"] <= end_d)
    return out.loc[mask, ["date", "open", "high", "low", "close", "volume"]].copy()


def fetch_etf_price_history_akshare(
    symbol: str,
    start: str,
    end: str,
    attempts: int = 3,
    backoff_s: float = 1.0,
    skip_eastmoney: bool = False,
    on_eastmoney_exhausted: Callable[[], None] | None = None,
) -> pd.DataFrame:
    """OHLCV for on-exchange CN ETFs. Tries EastMoney's `fund_etf_hist_em`
    first (forward-adjusted, official-feel), retries transient connection
    errors, then falls back to Sina finance (`fund_etf_hist_sina`) if
    EastMoney remains unreachable. Accepts ISO dates (YYYY-MM-DD).

    Why two backends: EastMoney's `push2his.eastmoney.com` host has been
    intermittently dropping connections at the TLS layer (network-level
    block for some egress IPs), even when other EastMoney subdomains like
    `fundf10.eastmoney.com` work fine. Sina finance uses an unrelated host
    so the failure modes don't correlate."""
    if skip_eastmoney:
        return _fetch_etf_price_history_sina(symbol, start, end)

    def _fetch_eastmoney() -> pd.DataFrame:
        return _ak_call(
            "fund_etf_hist_em",
            symbol=symbol,
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
        )

    try:
        df = _retry_transient(_fetch_eastmoney, _is_transient_network_error, attempts, backoff_s)
    except Exception as exc:
        if not _is_transient_network_error(exc):
            raise
        if on_eastmoney_exhausted is not None:
            on_eastmoney_exhausted()
        return _fetch_etf_price_history_sina(symbol, start, end)
    out = df.rename(columns={
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
    })
    out["date"] = pd.to_datetime(out["date"]).dt.date
    return out[["date", "open", "high", "low", "close", "volume"]].copy()


def fetch_macro_series_akshare(series_id: str, start: str, end: str) -> pd.DataFrame:
    """No-auth akshare fallback for FRED macro series."""
    handler_name = _AKSHARE_MACRO_HANDLERS.get(series_id)
    if handler_name is None:
        raise ValueError(f"no akshare fallback for FRED series {series_id!r}")
    return globals()[handler_name](start, end)


def _raw_etf_table_call() -> pd.DataFrame:
    """Raw call to akshare for ETF category table. Extracted for lru_cache wrapping."""
    return _ak_call("fund_etf_category_sina", symbol="ETF基金")


@lru_cache(maxsize=1)
def _fetch_full_etf_table() -> pd.DataFrame:
    """Fetch the master on-exchange ETF catalog. Returns DataFrame with ETF data."""
    return _raw_etf_table_call()


def fetch_etf_metadata(symbol: str) -> dict[str, Any]:
    """On-exchange ETF metadata; symbol is 6-digit code (e.g. '510300')."""
    df = _fetch_full_etf_table()
    if isinstance(df, pd.DataFrame):
        code_col = "代码" if "代码" in df.columns else "symbol"
        rows = df[df[code_col].astype(str).str.contains(symbol, regex=False)]
        row = rows.iloc[0].to_dict() if not rows.empty else {}
    else:
        row = dict(df)
    return {
        "ticker": symbol,
        "name_cn": str(row.get("名称") or row.get("name") or ""),
    }
