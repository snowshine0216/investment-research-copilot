"""PHASE-0 verification spike for the monitor flow transport pivot (ADR 0019
addendum "flow transport pivot", Status: Proposed — gated). THROWAWAY: no
production code depends on this; it only proves the two hard gates before any
batch-first code is written.

Two gates, two modes:

  GATE 1 — reachability (default mode): ONE `ulist.np` batch call returns every
    monitored symbol's `f184` (今日主力净流入净占比). Run it AFTER the 15:00 CN
    close so `f184` is the completed-day value, and persist it (stamped with the
    CN trading date) so GATE 2 can diff it tomorrow.

  GATE 2 — equivalence (--equiv-against): for a handful of the captured symbols,
    fetch the per-symbol `daykline` 净占比 for the SAME completed day and compare
    to the stored `f184` to 4dp. ≤4dp → the factor input is the same number from
    a more reliable path → NO `_ENGINE_VERSION` bump. Material gap → bump + ADR.

CRITICAL (measured 2026-06-25): the EastMoney IP block is >40 min and EXTENDS on
every request made while banned. So this spike makes a SINGLE clean call and
ABORTS on the first connection drop — it NEVER retries. Run it on a rested IP,
from THIS machine (a cloud agent has a different IP — the result won't transfer).

Usage:
  uv run python -m scripts.phase0_flow_batch_spike                 # GATE 1 (after close)
  uv run python -m scripts.phase0_flow_batch_spike --equiv-against data/monitor/phase0_flow_spike/<date>.json
  # options: --symbols 000651,600519  --out <path>  --equiv-n 5
"""
from __future__ import annotations

import argparse
import glob
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TZ = timezone(timedelta(hours=8))  # Asia/Shanghai
_UT = "fa5fd1943c7b386f172d6893dbfba10b"  # public EastMoney quote token
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Referer": "https://quote.eastmoney.com/"}
_BLOCK_HINT = ("IP appears blocked. Do NOT retry — retries EXTEND the ban "
               "(ADR 0019). Wait until the IP is fully rested (overnight) and "
               "run once at ~15:45 CN.")
_EQUIV_TOL = 1e-4  # 4dp


# ── pure helpers ───────────────────────────────────────────────────────────
def _secid(symbol: str) -> str:
    """ulist secid: 6*→1. (SH+688), 0*/3*→0. (SZ+300). 8*/4* (BJ) → 0. (UNVERIFIED)."""
    return ("1." + symbol) if symbol[0] == "6" else ("0." + symbol)


def _coerce(value: object) -> float | None:
    """f184 → float percent-points, or None for blank/'-'/non-numeric."""
    if value in (None, "-", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ulist(payload: dict) -> dict[str, float | None]:
    """{f12 → f184} from a ulist.np body; tolerant of list/dict diff shape."""
    diff = (payload.get("data") or {}).get("diff")
    rows = list(diff.values()) if isinstance(diff, dict) else (diff or [])
    return {str(r.get("f12")): _coerce(r.get("f184")) for r in rows}


def _daykline_market(symbol: str) -> str:
    return "sh" if symbol[0] == "6" else "sz" if symbol[0] in "03" else "bj"


# ── symbol universe ────────────────────────────────────────────────────────
def _monitored_symbols(root: Path, override: str | None) -> list[str]:
    """--symbols override, else the union of keys across the per-day fund_flow
    caches (the actual monitored top-5 union the production batch would request)."""
    if override:
        return [s.strip() for s in override.split(",") if s.strip()]
    syms: set[str] = set()
    for f in glob.glob(str(root / "data" / "monitor" / "fund_flow" / "*.json")):
        try:
            syms |= set(json.loads(Path(f).read_text(encoding="utf-8")).keys())
        except (OSError, ValueError):
            continue
    return sorted(syms)


# ── GATE 1: reachability capture ───────────────────────────────────────────
def capture(symbols: list[str], out_path: Path) -> int:
    now = datetime.now(_TZ)
    after_close = (now.hour, now.minute) >= (15, 0)
    secids = ",".join(_secid(s) for s in symbols)
    params = {"ut": _UT, "fltt": "2", "invt": "2", "np": "1", "dect": "1",
              "secids": secids, "fields": "f12,f14,f184"}
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    print(f"GATE 1 — reachability: ONE call for {len(symbols)} symbols "
          f"@ {now.isoformat(timespec='seconds')} (after_close={after_close})")
    if not after_close:
        print("  ⚠ run is BEFORE the 15:00 close — f184 is intraday-provisional; "
              "rerun after close for a valid capture.")
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:  # SINGLE call, no retry
            body = r.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 — abort, never retry
        print(f"  ✗ GATE 1 FAIL: {type(exc).__name__}: {exc}\n  {_BLOCK_HINT}")
        return 1
    by_symbol = _parse_ulist(json.loads(body))
    covered = {s: by_symbol.get(s) for s in symbols}
    numeric = {s: v for s, v in covered.items() if v is not None}
    missing = [s for s in symbols if s not in by_symbol]
    print(f"  rc ok, rows={len(by_symbol)}  numeric f184={len(numeric)}/{len(symbols)}"
          f"  missing(no row)={missing}")
    for s in symbols:
        print(f"    {s}  f184={covered[s]}")
    record = {"run_date": now.date().isoformat(), "run_time_cst": now.isoformat(timespec="seconds"),
              "after_close": after_close, "endpoint": "ulist.np", "requested": len(symbols),
              "numeric": len(numeric), "by_symbol": covered, "missing": missing}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8")
    verdict = "PASS" if (not missing and len(numeric) == len(symbols) and after_close) else "PARTIAL"
    print(f"  → GATE 1 {verdict}; capture saved {out_path}")
    print(f"  next: tomorrow run  --equiv-against {out_path}")
    return 0


# ── GATE 2: same-day equivalence ───────────────────────────────────────────
def equiv(prior_path: Path, n: int) -> int:
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    target_date = prior["run_date"]
    candidates = [(s, v) for s, v in sorted(prior["by_symbol"].items()) if v is not None][:n]
    print(f"GATE 2 — equivalence: daykline 净占比({target_date}) vs stored f184, "
          f"{len(candidates)} symbols (single pass, abort on first block)")
    if not candidates:
        print("  ✗ prior capture has no numeric f184 — nothing to compare.")
        return 1
    import akshare as ak  # lazy, house pattern
    max_abs = 0.0
    compared = 0
    for symbol, f184 in candidates:
        try:
            df = ak.stock_individual_fund_flow(stock=symbol, market=_daykline_market(symbol))
        except Exception as exc:  # noqa: BLE001 — abort, never retry
            print(f"    {symbol}: ✗ {type(exc).__name__} — ABORT.\n  {_BLOCK_HINT}")
            return 1
        match = df[df["日期"].astype(str).str.strip() == target_date] if "日期" in df.columns else df.iloc[0:0]
        if match.empty:
            print(f"    {symbol}: f184={f184}  daykline({target_date})=ABSENT "
                  "(EOD row not posted yet — rerun later this evening)")
            continue
        dk = _coerce(match["主力净流入-净占比"].iloc[0])
        diff = None if dk is None else round(f184 - dk, 6)
        if diff is not None:
            max_abs = max(max_abs, abs(diff))
            compared += 1
        print(f"    {symbol}: f184={f184}  daykline={dk}  Δ={diff}")
    if compared == 0:
        print("  → GATE 2 INCONCLUSIVE: no overlapping completed-day rows yet.")
        return 1
    verdict = ("EQUIVALENT → no _ENGINE_VERSION bump" if max_abs <= _EQUIV_TOL
               else "DIVERGENT → engine bump + ADR 0019 entry required")
    print(f"  → GATE 2: max|Δ|={max_abs} over {compared} symbols → {verdict}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase-0 flow batch-transport spike (ADR 0019).")
    ap.add_argument("--symbols", default=None, help="comma list; default = fund_flow cache union")
    ap.add_argument("--equiv-against", default=None, help="prior GATE-1 capture json → run GATE 2")
    ap.add_argument("--equiv-n", type=int, default=5, help="symbols to daykline-check (keep ≤ burst ceiling)")
    ap.add_argument("--out", default=None, help="GATE-1 capture output path")
    ap.add_argument("--root", default=".", help="repo root")
    args = ap.parse_args()
    root = Path(args.root)
    if args.equiv_against:
        return equiv(Path(args.equiv_against), args.equiv_n)
    symbols = _monitored_symbols(root, args.symbols)
    if not symbols:
        print("no symbols (empty fund_flow cache) — pass --symbols")
        return 2
    run_date = datetime.now(_TZ).date().isoformat()
    out = Path(args.out) if args.out else root / "data" / "monitor" / "phase0_flow_spike" / f"{run_date}.json"
    return capture(symbols, out)


if __name__ == "__main__":
    raise SystemExit(main())
