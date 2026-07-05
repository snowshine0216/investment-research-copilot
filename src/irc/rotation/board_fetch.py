"""EDGE + pure parse: EM industry-board snapshot (1 call) + paced backfill.

Transport = raw push2 via IRC_CN_PROXY (T2: requests, never curl-through-proxy).
Field codes are INTERFACE-SPECIFIC and were recorded by the AC1 probe
(001-probe-notes.md). Snapshot rides the SAME clist/get interface em_raw uses
(fs=m:90+t:2). Parsers are PURE + tolerant (parse_ulist posture); fetchers RAISE
on transport error so cached_fetch classifies TRANSIENT (never a fabricated row).
"""
from __future__ import annotations

import math
import time

from irc.http_proxy import resolve_cn_proxy
from irc.monitor.em_raw import _diff_rows
from irc.rotation.types import BoardDay

_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_PZ = 100
_MAX_PAGES = 2  # ~86 boards → 1 full page + tail


def _f(value: object) -> float | None:
    """Pure: tolerant float coercion. Rejects non-finite results (NaN/inf, incl.
    the strings "nan"/"inf" which `float()` parses successfully) — a NaN/inf would
    otherwise poison composite._percentile_ranks (non-transitive </== comparisons
    → order-dependent ranks → AC3 determinism risk)."""
    if value in (None, "-", ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_board_spot(payload: dict, *, today: str) -> tuple[BoardDay, ...]:
    """Pure: clist/get board payload → today's BoardDay per board. Tolerant of
    list/dict diff shape; blank/missing → (). f12=code, f14=name, f3=chg%,
    f9=市盈率 (board PE), f184=main-inflow net %, f8=turnover% (probe-confirmed
    field codes). f9 tolerant like the others → None on missing/'-'/non-numeric."""
    out = []
    for r in _diff_rows(payload):
        code = r.get("f12")
        chg = _f(r.get("f3"))
        if not code or chg is None:
            continue
        out.append(BoardDay(
            date=today, board_code=str(code), board_name=str(r.get("f14") or ""),
            chg_pct=chg, main_inflow_ratio=_f(r.get("f184")),
            turnover_pct=_f(r.get("f8")), board_pe=_f(r.get("f9")),
            source="snapshot"))
    return tuple(out)


def parse_board_hist(payload: dict, board_code: str, board_name: str
                     ) -> tuple[BoardDay, ...]:
    """Pure: kline/get payload → ascending daily BoardDay series. kline CSV is
    'date,open,close,high,low,volume,amount,amplitude' (f51..f58) — NO turnover
    field. chg% derived from close vs prev close; flow AND turnover are
    INTENTIONALLY None on every backfill row (kline gives price/momentum only;
    the turn leg accrues from live snapshot turnover f8 as snapshot days
    accumulate, exactly like the flow leg). Fetching kline turnover is a deferred
    follow-up (F7): akshare's board-hist interface reportedly carries turnover on
    **f61** (换手率), but field codes are interface-specific here (see T1/f100-f127
    scar) — do NOT add f61 without an AC1-style live probe first. Blank → ()."""
    data = payload.get("data") if isinstance(payload, dict) else None
    klines = data.get("klines") if isinstance(data, dict) else None
    if not klines:
        return ()
    rows = []
    prev_close = None
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 3:
            continue
        d, close = parts[0], _f(parts[2])
        if close is None:
            continue
        chg = 0.0 if prev_close in (None, 0) else (close / prev_close - 1) * 100
        prev_close = close
        rows.append(BoardDay(date=d, board_code=board_code, board_name=board_name,
                             chg_pct=round(chg, 4), main_inflow_ratio=None,
                             turnover_pct=None,  # kline fields2 (f51-f58) carry NO turnover — see F7
                             board_pe=None,  # kline carries no PE (only the snapshot does)
                             source="backfill"))
    return tuple(rows)


def _proxies() -> dict | None:
    proxy = resolve_cn_proxy()
    return {"http": proxy, "https": proxy} if proxy else None


def _default_http_get(url, *, params, headers, timeout, proxies=None) -> dict:
    import requests  # local import — house pattern
    resp = requests.get(url, params=params, headers=headers, timeout=timeout,
                        proxies=proxies)
    resp.raise_for_status()
    return resp.json()


def fetch_board_spot(today: str, *, http_get=None, sleep=time.sleep
                     ) -> tuple[BoardDay, ...]:
    """EDGE: ≤2-page clist/get board snapshot via CN proxy → today's BoardDays.
    Raises on transport error (caller degrades / classifies TRANSIENT)."""
    get = http_get or _default_http_get
    out: list[BoardDay] = []
    for pn in range(1, _MAX_PAGES + 1):
        params = {"ut": _UT, "fltt": "2", "invt": "2", "np": "1", "pz": str(_PZ),
                  "pn": str(pn), "po": "1", "fs": "m:90+t:2",
                  "fields": "f12,f14,f3,f8,f9,f184,f2"}
        payload = get(_CLIST, params=params, headers=_HEADERS, timeout=20,
                      proxies=_proxies())
        rows = parse_board_spot(payload, today=today)
        out.extend(rows)
        if len(_diff_rows(payload)) < _PZ:
            break
        sleep(0.3)
    return tuple(out)


def fetch_board_hist(board_code: str, board_name: str, *, http_get=None
                     ) -> tuple[BoardDay, ...]:
    """EDGE: one kline/get call for a board (secid=90.<code>, ≥60 daily bars) via
    CN proxy → ascending BoardDay series. Raises on transport error."""
    get = http_get or _default_http_get
    params = {"ut": _UT, "fqt": "1", "end": "20500101", "lmt": "120", "klt": "101",
              "fields1": "f1,f2,f3", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
              "secid": f"90.{board_code}"}
    payload = get(_KLINE, params=params, headers=_HEADERS, timeout=20,
                  proxies=_proxies())
    return parse_board_hist(payload, board_code, board_name)
