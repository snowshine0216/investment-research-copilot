"""AC1 live-probe: record EM board-snapshot + board-history field codes.

Run through the CN proxy (NEVER curl-through-proxy, trap T2):
    IRC_CN_PROXY=<proxy> uv run python scripts/rotation_probe.py
Prints the raw first row of each interface so field codes can be read off and
recorded in 001-probe-notes.md. If live CN egress is unavailable, this exits
non-zero and the fallback path (akshare-known field codes + defensive parsers +
fixture regression) documented in 001-probe-notes.md applies.
"""
from __future__ import annotations

import json
import sys

from irc.http_proxy import resolve_cn_proxy

_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


def _get(url, params):
    import requests
    proxy = resolve_cn_proxy()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, params=params, headers=_HEADERS, timeout=20, proxies=proxies)
    r.raise_for_status()
    return r.json()


def main() -> int:
    try:
        spot = _get(_CLIST, {"ut": _UT, "fltt": "2", "invt": "2", "np": "1",
                             "pz": "5", "pn": "1", "po": "1", "fs": "m:90+t:2",
                             "fields": "f12,f14,f3,f8,f9,f184,f2"})
        print("SPOT diff[0]:", json.dumps(
            (spot.get("data") or {}).get("diff", [None])[0], ensure_ascii=False))
        # a board code from the spot payload for the kline probe
        code = ((spot.get("data") or {}).get("diff") or [{}])[0].get("f12", "BK0475")
        hist = _get(_KLINE, {"ut": _UT, "fqt": "1", "end": "20500101", "lmt": "3",
                             "klt": "101", "fields1": "f1,f2,f3",
                             "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                             "secid": f"90.{code}"})
        print("HIST klines[:3]:", json.dumps(
            (hist.get("data") or {}).get("klines", [])[:3], ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — probe is best-effort
        print(f"PROBE FAILED (no live CN egress?): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
