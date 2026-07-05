"""F8 diagnosis probe — paced matrix over EM board endpoints vs the ulist.np control.

Run UNSANDBOXED (a sandboxed shell resets EM connections + the proxy CONNECT):
    uv run python scripts/rotation_f8_diagnose.py

Loads IRC_CN_PROXY from .env into os.environ, then probes each endpoint N times
through the proxy AND direct, classifying every call outcome. Discriminates:
proxy-dead (baidu control fails) / tunnel-rotation-flaky (intermittent) /
EM board-plane throttle (boards fail both proxy+direct while ulist.np works) /
push2his host-block (clist ok, kline fails). Never prints the proxy value.
Paced + bounded (T3: never hammer). Transport = requests through the proxy
(T2: never curl-through-proxy).
"""
from __future__ import annotations

import json
import time

try:  # make IRC_CN_PROXY visible to resolve_cn_proxy() (reads os.environ)
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001 — best-effort
    pass

from irc.http_proxy import resolve_cn_proxy

_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


def _secid(sym: str) -> str:
    return f"1.{sym}" if sym[:1] == "6" or sym[:3] == "688" else f"0.{sym}"


_TARGETS = {
    "ulist.np (flow CONTROL)": (
        "https://push2.eastmoney.com/api/qt/ulist.np/get",
        {"ut": _UT, "fltt": "2", "invt": "2", "np": "1", "dect": "1",
         "secids": f"{_secid('600519')},{_secid('000338')}",
         "fields": "f12,f14,f184,f100"},
    ),
    "clist/get (board snapshot)": (
        "https://push2.eastmoney.com/api/qt/clist/get",
        {"ut": _UT, "fltt": "2", "invt": "2", "np": "1", "pz": "5", "pn": "1",
         "po": "1", "fs": "m:90+t:2", "fields": "f12,f14,f3,f8,f9,f184,f2"},
    ),
    "push2his kline (board hist, f51-f61)": (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        {"ut": _UT, "fqt": "1", "end": "20500101", "lmt": "5", "klt": "101",
         "fields1": "f1,f2,f3",
         "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
         "secid": "90.BK0475"},
    ),
}
_BAIDU = ("https://www.baidu.com", {})


def _one(url: str, params: dict, proxies: dict | None) -> dict:
    import requests

    t0 = time.time()
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=15,
                         proxies=proxies)
        dt = round(time.time() - t0, 2)
        data_ok = None
        sample = None
        if "eastmoney" in url:
            try:
                j = r.json()
                data = j.get("data") or {}
                data_ok = bool(data)
                # tiny non-secret sample so we can read field codes off a success
                diff = data.get("diff") or data.get("klines")
                if isinstance(diff, list) and diff:
                    sample = diff[0]
            except Exception:  # noqa: BLE001
                data_ok = False
        return {"ok": r.status_code == 200 and (data_ok is not False),
                "status": r.status_code, "dt": dt, "data_ok": data_ok,
                "sample": sample}
    except Exception as exc:  # noqa: BLE001 — classify, don't crash
        return {"ok": False, "err": type(exc).__name__,
                "msg": str(exc)[:90], "dt": round(time.time() - t0, 2)}


def _cell(name: str, url: str, params: dict, proxies: dict | None, n: int) -> None:
    print(f"\n  {name}:")
    for i in range(n):
        print("    ", json.dumps(_one(url, params, proxies), ensure_ascii=False))
        if i < n - 1:
            time.sleep(2.5)


def main() -> int:
    proxy = resolve_cn_proxy()
    print("IRC_CN_PROXY set:", proxy is not None, "(value hidden)")
    proxies = {"http": proxy, "https": proxy} if proxy else None
    n = 3
    print("\n=== THROUGH PROXY ===")
    _cell("baidu (tunnel liveness)", _BAIDU[0], _BAIDU[1], proxies, 2)
    for name, (url, params) in _TARGETS.items():
        _cell(name, url, params, proxies, n)
    print("\n=== DIRECT (no proxy) ===")
    for name, (url, params) in _TARGETS.items():
        _cell(name, url, params, None, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
