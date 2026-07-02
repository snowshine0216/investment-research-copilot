"""EDGE + pure parse: monitor flow via ONE ulist.np batch call (B2 §5.B, D5).

`push2/ulist.np/get?secids=<our list>&fields=f12,f14,f184` returns each secid's
today 主力净流入净占比 (f184, percent-points) in ONE request — no per-symbol
throttle. Routed through IRC_CN_PROXY at the edge (D2); python requests (curl
false-fails through the proxy, F3). f184 is INTRADAY until CN close; the store
(flow_series_store) accepts only COMPLETED days — this fetcher is unaware of
completeness (the caller decides). Percent-points, NO /100."""
from __future__ import annotations

import logging

from irc.http_proxy import resolve_cn_proxy

_log = logging.getLogger(__name__)

_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
_ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"


def _secid(symbol: str) -> str:
    return ("1." + symbol) if str(symbol).startswith("6") else ("0." + symbol)


def build_secids(symbols) -> str:
    """Pure: comma-joined secids for the batch call (dedup-order preserved)."""
    return ",".join(_secid(s) for s in dict.fromkeys(symbols))


def _coerce(value: object) -> float | None:
    if value in (None, "-", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_ulist(payload: dict) -> dict[str, float | None]:
    """Pure: {f12 → f184} percent-points (NO /100). Tolerant of list/dict diff
    shape. Blank/missing data → {} (→ all None upstream, never fabricated)."""
    diff = (payload.get("data") or {}).get("diff") if isinstance(payload, dict) else None
    rows = list(diff.values()) if isinstance(diff, dict) else (list(diff) if isinstance(diff, list) else [])
    return {str(r.get("f12")): _coerce(r.get("f184")) for r in rows}


def _default_http_get(url, *, params, headers, timeout, proxies=None) -> dict:
    import requests  # local import — house pattern
    resp = requests.get(url, params=params, headers=headers, timeout=timeout,
                        proxies=proxies)
    resp.raise_for_status()
    return resp.json()


def fetch_flow_today_batch(symbols, *, http_get=None) -> dict[str, float | None]:
    """EDGE: ONE ulist.np call for all symbols via the CN proxy. Every requested
    symbol is present in the result (None when the endpoint returned no row for it).
    Non-A-share lines never enter secids (uncovered, as today)."""
    get = http_get or _default_http_get
    proxy = resolve_cn_proxy()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    params = {"ut": _UT, "fltt": "2", "invt": "2", "np": "1", "dect": "1",
              "secids": build_secids(symbols), "fields": "f12,f14,f184"}
    payload = get(_ULIST_URL, params=params, headers=_HEADERS, timeout=20,
                  proxies=proxies)
    by_symbol = parse_ulist(payload)
    return {s: by_symbol.get(s) for s in dict.fromkeys(symbols)}
