"""Pure parse: raw EastMoney JSON → the monitor industry leg's frame shapes.

Slotted into the existing injectable `fetch` params of industry_valuation
(fetch_board_pe_frame → fetch_industry_pe; fetch_stock_info_frame →
fetch_stock_industry_map) so the pure parsers / per-day 3-outcome caches are
UNCHANGED. em_raw owns its raw-JSON parsing — NO akshare wrappers here — so
upstream response-shape drift (F4 missing 市盈率 column, F5 dlmkts/dsc keys)
can't recur silently. These parsers are PURE (no I/O, no network); the edge
fetchers land in a subsequent slice step (requests, IRC_CN_PROXY routing).
"""
from __future__ import annotations

import pandas as pd

from irc.http_proxy import resolve_cn_proxy

_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_STOCK_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_PZ = 100
_MAX_PAGES = 10


def _diff_rows(payload: dict) -> list[dict]:
    """Pure: clist/get payload → list of board-row dicts. `data.diff` may be a
    list or a dict-of-index (both observed shapes). `data: null` / missing →
    []."""
    diff = (payload.get("data") or {}).get("diff") if isinstance(payload, dict) else None
    if isinstance(diff, dict):
        return list(diff.values())
    return list(diff) if isinstance(diff, list) else []


def parse_clist_boards(payload: dict) -> pd.DataFrame:
    """Pure: clist/get board payload → frame with 板块名称 (f14) + 市盈率 (f9),
    the columns the existing parse_industry_pe expects. Empty/null → empty frame."""
    rows = _diff_rows(payload)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        {"板块名称": [r.get("f14") for r in rows],
         "市盈率": [r.get("f9") for r in rows]})


def parse_stock_info(payload: dict) -> pd.DataFrame:
    """Pure: stock/get payload → (item,value) long frame. A 行业 row (f127) is
    emitted iff f127 is truthy. data:null / non-dict → empty frame (→ TRANSIENT
    via _is_blank_info_frame). A well-formed data with no f127 → item/value
    frame WITHOUT a 行业 row (→ DEAD), preserving the existing 3-outcome
    contract. Ignores dlmkts/dsc drift keys (F5) — only `data` is read."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return pd.DataFrame()
    items: list[tuple[str, object]] = [("代码", data.get("f57")), ("名称", data.get("f58"))]
    if data.get("f127"):
        items.append(("行业", data.get("f127")))
    return pd.DataFrame({"item": [i for i, _ in items], "value": [v for _, v in items]})


import time  # noqa: E402


def _secid(symbol: str) -> str:
    """ulist/stock secid: 6*→1. (SH+688), else 0. (SZ+300; 8*/4* BJ → 0.)."""
    return ("1." + symbol) if str(symbol).startswith("6") else ("0." + symbol)


def _default_http_get(url, *, params, headers, timeout, proxies=None) -> dict:
    """EDGE: one GET via python requests → JSON. proxies passed through (F3: curl
    false-fails through the proxy; requests succeeds). Raises on transport error
    so the caller's try/except degrades to TRANSIENT (never a fabricated frame)."""
    import requests  # local import — house pattern
    resp = requests.get(url, params=params, headers=headers, timeout=timeout,
                        proxies=proxies)
    resp.raise_for_status()
    return resp.json()


def _proxies() -> dict | None:
    proxy = resolve_cn_proxy()
    return {"http": proxy, "https": proxy} if proxy else None


def fetch_board_pe_frame(*, http_get=None, sleep=time.sleep) -> pd.DataFrame:
    """EDGE: paginated clist/get board PE (pz=100, ≤10 pages, 0.3s pacing) via the
    CN proxy → concatenated 板块名称/市盈率 frame. Stops on a short page. Raises on
    transport error (caller degrades to {})."""
    get = http_get or _default_http_get
    proxies = _proxies()
    frames: list[pd.DataFrame] = []
    for pn in range(1, _MAX_PAGES + 1):
        params = {"ut": _UT, "fltt": "2", "invt": "2", "np": "1", "pz": str(_PZ),
                  "pn": str(pn), "po": "1", "fs": "m:90+t:2", "fields": "f12,f14,f9"}
        payload = get(_CLIST_URL, params=params, headers=_HEADERS, timeout=20,
                      proxies=proxies)
        rows = _diff_rows(payload)
        if not rows:
            break
        frames.append(parse_clist_boards(payload))
        if len(rows) < _PZ:
            break
        sleep(0.3)  # existing pacing posture (ADR 0014)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_stock_info_frame(symbol: str, *, http_get=None) -> pd.DataFrame:
    """EDGE: one stock/get call via the CN proxy → (item,value) frame. Raises on
    transport error (caller classify → TRANSIENT)."""
    get = http_get or _default_http_get
    params = {"ut": _UT, "invt": "2", "fltt": "2", "fields": "f57,f58,f127",
              "secid": _secid(symbol)}
    payload = get(_STOCK_URL, params=params, headers=_HEADERS, timeout=20,
                  proxies=_proxies())
    return parse_stock_info(payload)
