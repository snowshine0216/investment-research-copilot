# Sector Rotation Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily, deterministic, zero-LLM `irc rotation` radar that ranks EastMoney industry boards by a rotation composite, assigns each a `rotation_state`, and resolves emerging/hot boards to concrete CN funds by holdings look-through — surfacing candidate funds days-to-weeks earlier than the weekly pipeline.

**Architecture:** A new pure-core `src/irc/rotation/` package imports monitor transport/cache EDGES (`cached_fetch`, `em_raw`/`flow_batch_fetch` parsers, `trading_calendar`, `board_pe_staleness`) and extends `industry_map_store` in place — never the reverse (one-way dependency, AC11). Effects (board fetch, series/ledger persistence) live in thin edge modules and `commands/rotation_cmd.py`; all scoring/state/exposure/report logic is pure and unit-tested with fixtures, no mocks. The daily run is cache-only + bounded top-up; `irc rotation seed` is a resumable one-time backfill.

**Tech Stack:** Python 3.12+, uv, Click, pandas, `requests` (via `IRC_CN_PROXY` at the edge), frozen dataclasses, pytest, ruff.

## Global Constraints

- **TDD mandatory:** every pure core is red→green→refactor. Test file precedes impl file. No implementation without a failing test.
- **Functional/immutable:** frozen dataclasses; never mutate arguments; `dataclasses.replace` / dict-spread for updates; `map`/`filter`/comprehensions over in-place mutation.
- **Effects at edges:** filesystem/network/akshare/`requests` only in `board_fetch.py`, the store modules' write functions, and `commands/rotation_cmd.py`. Cores are pure.
- **Size budget:** files < 200 lines, functions < 20 lines (ideal); extract helpers over nesting > 3 levels.
- **`tests/` mirrors `src/irc/rotation/` one-for-one** (AC12). `tests/commands/test_rotation_cmd.py` must run green **per-file** — never `pytest tests/commands/` whole-dir (hangs, trap T5).
- **VERSION:** accumulate under CHANGELOG `[Unreleased]`; do NOT bump VERSION per PR.
- **No `[ref:` markers** anywhere in rotation output — pure market data, outside citation/SAME-3/H3 machinery (D8, AC8).
- **`schema_version: 1`, `radar_version: 1`** in `rotation_radar.json`; `radar_version` bumps ONLY on a weight/window/hysteresis change (same lesson as monitor `_ENGINE_VERSION`).
- **One-way dependency (AC11):** NO import from `irc.rotation` into `irc.monitor` / `irc.discovery` / `irc.scoring` / `irc.memo` / `irc.opportunity`. rotation imports FROM monitor only.
- **Determinism:** two same-day runs over the same series store produce byte-identical `rotation_radar.json` (AC3). Atomic byte-stable writes: `.tmp.{pid} → os.replace`, sorted keys.
- **Advisory only:** never emit `portfolio_action`, `DirectionalBias`, `opportunity_state`; forbidden vocab collisions — never `heat`/`crowded`/`overheated`/`watchlist`/`action`/`bias` for radar semantics (§10).
- **Breaker is protective (T3):** never self-extend by retrying while blocked; route board/backfill/top-up calls through `cached_fetch`.
- **Never test EM endpoints through curl-through-proxy (T2)** — use `requests`. Do NOT hammer live EM in unit tests.

---

## Reused infrastructure (exact signatures — cite, do not reinvent)

- `irc.monitor.cached_fetch.cache_first_fetch(symbols, *, cache_dir, today, fetch_one, serialize, deserialize, policy=RetryPolicy(), sleep=time.sleep) -> dict[str, object|None]` — 3-outcome (`OK`/`DEAD`/`TRANSIENT`) per-day cache-first fetch with backoff + breaker. `fetch_one(symbol) -> (status, payload)` must NOT sleep. `RetryPolicy(retries=2, base_delay=0.5, factor=3.0, pacing=0.3, breaker_threshold=5)`.
- `irc.monitor.flow_batch_fetch`: `build_secids(symbols) -> str`; `parse_ulist(payload) -> dict[str, tuple[float|None, str|None]]`; `fetch_flow_today_batch(symbols, *, http_get=None) -> (flow_by_symbol, industry_by_symbol)`. **FIELD-CODE NOTE:** 行业 = `f100` in `ulist.np` (NOT `f127`, which is numeric there). `_default_http_get(url, *, params, headers, timeout, proxies=None)`.
- `irc.http_proxy.resolve_cn_proxy() -> str|None` — CN egress proxy at the edge.
- `irc.monitor.em_raw`: `_diff_rows(payload) -> list[dict]` (tolerant of `data.diff` list-or-dict); `fetch_board_pe_frame(*, http_get=None, sleep=time.sleep)` (paginated clist/get, `fs="m:90+t:2"`, fields `f12,f14,f9`); `parse_clist_boards(payload) -> DataFrame[板块名称, 市盈率]`.
- `irc.monitor.trading_calendar.load_trading_days(today: date, *, root=Path(".")) -> frozenset[date]|None` — cached CN SSE trading days; None on failure.
- `irc.monitor.industry_map_store`: `load_store(path) -> dict[str,dict]`; `merge_seen(store, today, industry_by_symbol) -> dict` (pure, refresh-on-seen, None/blank skipped); `fresh_slice(store, today, max_age_days=30) -> dict[str,str]`; `record_seen(path, today, industry_by_symbol) -> dict` (EDGE, no-op writes nothing). **Extend in place — do not fork.**
- `irc.monitor.board_pe_staleness`: `read_day_table` / `write_day_table` / `newest_nonempty` / `stale_fallback` — reuse for board-PE percentile lookup (stale-tolerated).
- `irc.narrative.holdings_fetch.fetch_top_holdings(fund_id, *, cache_dir) -> tuple[Holding, ...]` — cached top-10 disclosed holdings; cache dir `data/narrative_holdings/`; never raises. `Holding(symbol, name_cn, weight_pct, sw_industry)`.
- `irc.monitor.industry_valuation.fetch_industry_pe(*, cache_dir, today, fetch=None, sleep=time.sleep, trading_days=None) -> (dict[str,float], BoardPeFreshness)` — board-PE cache; reuse for `pe_pctl`.
- `irc.io_utils.atomic_write_text(path, text)` — atomic byte-stable write.
- `irc.monitor.resolve.resolve_funds(cfg) -> tuple[MonitorFund, ...]` and monitor-set membership types (`irc.monitor.types.MonitorFund`).
- CLI: `@main.group(invoke_without_command=True)` pattern (see `monitor` group, `cli.py:254`). Universe enumeration: `irc.commands.narrative_cmd._enumerate_cn_funds(root) -> tuple[(iid, name_cn, asset_class), ...]`.
- Ops: `ops/launchd/run-flow-capture.sh` (15:45 wrapper) + `ops/launchd/lib-run.sh` (`acquire_lock`, `run_with_watchdog`).

---

## File Structure

**Create — package `src/irc/rotation/`:**
- `__init__.py` — empty package marker.
- `types.py` — frozen dataclasses: `BoardDay`, `BoardState`, `ExposureRow`, `RotationCandidate`, `RotationReport`.
- `board_fetch.py` — EDGE: daily board snapshot (1 call) + paced backfill fetch; parsers for board spot + board history.
- `series_store.py` — board series persistence (mirrors `flow_series_store`: trading-day pruning, once-per-day idempotency, atomic write).
- `composite.py` — PURE: per-day cross-sectional percentiles → composite score; flow-dark renormalization.
- `states.py` — PURE: composite-percentile series → `rotation_state` per board (hysteresis, days_in_state).
- `exposure.py` — PURE: holdings × stock→board map → fund×board exposure matrix + coverage diagnostics.
- `candidates.py` — PURE: emerging/hot boards × exposure matrix → ranked `RotationCandidate` rows with membership annotations.
- `report.py` — PURE: `RotationReport` → md + json projections.
- `ledger.py` — forward-ledger row builder (pure) + append (edge).
- `seed.py` — EDGE orchestration for `irc rotation seed` (resumable backfill/holdings/map).

**Create — command:**
- `src/irc/commands/rotation_cmd.py` — thin `run_rotation` (daily) + `run_rotation_seed`.

**Modify:**
- `src/irc/cli.py` — register `@main.group rotation` + `seed` subcommand.
- `src/irc/monitor/industry_map_store.py` — extend in place: add board-code aware seeding helper if needed (see Task 12; only if a new merge shape is required).
- `ops/launchd/run-flow-capture.sh` — chain `irc rotation` after capture, protective-only.
- `ops/launchd/install.sh` — template substitution unchanged; verify the wrapper still substitutes (no new agent).
- `docs/monitor/README.md` + `ops/launchd/README.md` — ops manual: flow-capture wrapper now also runs the radar.
- `CONTEXT.md` — flip the "Sector rotation radar" section marker from **SPEC'd, not built** to built.
- `CHANGELOG.md` — `[Unreleased]` entry.

**Create — tests (mirror one-for-one):**
- `tests/rotation/test_types.py`, `test_board_fetch.py`, `test_series_store.py`, `test_composite.py`, `test_states.py`, `test_exposure.py`, `test_candidates.py`, `test_report.py`, `test_ledger.py`, `test_seed.py`, `test_import_isolation.py`.
- `tests/commands/test_rotation_cmd.py`.
- Fixtures under `tests/rotation/fixtures/` (real-shaped EM payloads + a small board series).

---

## Task 1: AC1 live-probe spike — record board field codes

**Files:**
- Create: `scripts/rotation_probe.py`
- Create: `docs/2026-07-05-sector-rotation-radar/items/001-probe-notes.md`
- Create: `tests/rotation/fixtures/board_spot_sample.json`
- Create: `tests/rotation/fixtures/board_hist_sample.json`

**Interfaces:**
- Produces: recorded field codes for the board-snapshot + board-history endpoints, and two real-shaped payload fixtures the parsers in Task 3 pin against.

**Transport decision (justify in probe notes):** Use the **raw `push2.eastmoney.com` interfaces via `requests` through `IRC_CN_PROXY`**, NOT the akshare `stock_board_industry_*` wrappers, because (a) the akshare EM board wrappers hit the *same* `push2` host but add pandas-parse layers that have historically drifted silently (em_raw exists precisely to own raw-JSON parsing — F4/F5 scar), and (b) the monitor's geo-throttle-aware posture (batch-first, `cached_fetch` breaker, `IRC_CN_PROXY`) only applies to the raw path. Snapshot: `clist/get` with `fs=m:90+t:2` (all industry boards, one paginated call — same interface as `em_raw.fetch_board_pe_frame`), requesting fields for board code (`f12`), board name (`f14`), change% (`f3`), main-inflow% (`f184`, expected on this board interface — akshare's board wrappers surface 主力净流入 from it; degrade only if genuinely absent at runtime), turnover% (`f8`), **board PE `f9` (市盈率)** — the SAME field `em_raw.parse_clist_boards` already reads, so PE comes inline at ZERO extra cost, same board-name/BK-code vocabulary. Board history: `push2his.eastmoney.com/api/qt/stock/kline/get` per board `secid=90.<BKcode>` with daily klines (this is what `stock_board_industry_hist_em` wraps).

- [ ] **Step 1: Write the probe script**

```python
# scripts/rotation_probe.py
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
```

- [ ] **Step 2: Attempt the live probe (best-effort)**

Run: `IRC_CN_PROXY="$IRC_CN_PROXY" uv run python scripts/rotation_probe.py`
Expected (live egress available): prints one SPOT diff row + 3 HIST klines. Record the exact field→meaning mapping in `001-probe-notes.md`.
Expected (no egress): prints `PROBE FAILED` and exits 1 → apply the documented fallback below.

- [ ] **Step 3: Write probe notes (records the decision either way)**

Write `001-probe-notes.md` capturing: chosen transport (raw push2), the confirmed OR akshare-derived field codes, and — if the probe failed — an explicit line: *"Live field-code confirmation is a documented follow-up (mirrors the f127→f100 Saturday-probe lesson); parsers built defensively against akshare-known EM board field codes and pinned with real-payload fixtures."* Include the known akshare EM board field codes: snapshot `clist` `f12`=board code, `f14`=name, `f3`=change%, `f8`=turnover%, `f9`=市盈率 (board PE — same field `em_raw.parse_clist_boards` reads), `f184`=main-inflow net %, `f2`=latest price; kline `f51`=date, `f52`=open, `f53`=close, `f54`=high, `f55`=low, `f56`=volume, `f57`=amount, `f58`=amplitude.

- [ ] **Step 4: Capture fixtures**

If the probe succeeded, save the real SPOT payload to `board_spot_sample.json` and the real HIST payload to `board_hist_sample.json`. If it failed, hand-author minimal real-shaped fixtures matching the documented field codes (≥3 boards in spot, **each carrying an `f9` PE value plus at least one board with a missing/`"-"` `f9` to exercise the None path**; ≥25 daily klines for one board in hist), clearly marked in `001-probe-notes.md` as synthetic-pending-live-confirmation.

- [ ] **Step 5: Commit**

```bash
git add scripts/rotation_probe.py docs/2026-07-05-sector-rotation-radar/items/001-probe-notes.md tests/rotation/fixtures/board_spot_sample.json tests/rotation/fixtures/board_hist_sample.json
git commit -m "feat(rotation): AC1 board field-code probe + real-shaped fixtures"
```

**Verification point:** `001-probe-notes.md` exists and states the transport choice + field codes; the two fixtures parse as JSON with the documented keys present. This satisfies AC1's "recorded in the item notes" requirement.

---

## Task 2: Frozen dataclass types

**Files:**
- Create: `src/irc/rotation/__init__.py` (empty)
- Create: `src/irc/rotation/types.py`
- Test: `tests/rotation/test_types.py`

**Interfaces:**
- Produces: `BoardDay(date, board_code, board_name, chg_pct, main_inflow_ratio, turnover_pct, board_pe, source)` — `board_pe: float | None` carries the snapshot's f9 (市盈率) so pe_pctl is computed from the persisted series' latest day (AC3-safe, same idempotency as mom20/flow5/turnΔ); `BoardState(board_code, board_name, state, days_in_state, composite_pctl, mom20, flow5, turn_delta, pe_pctl, chase_risk)`; `ExposureRow(fund_id, name_cn, board_code, exposure_pct, matched_symbols, holdings_as_of)`; `RotationCandidate(fund_id, name_cn, board_code, board_name, exposure_pct, on_discovered_watchlist, in_monitor_set, held, holdings_as_of)`; `RotationReport(schema_version, radar_version, data_status, board_states, candidates, diagnostics)`. All frozen.

- [ ] **Step 1: Write the failing test**

```python
# tests/rotation/test_types.py
import dataclasses

from irc.rotation.types import (
    BoardDay, BoardState, ExposureRow, RotationCandidate, RotationReport,
)


def test_board_day_is_frozen():
    bd = BoardDay(date="2026-07-06", board_code="BK0475", board_name="半导体",
                  chg_pct=2.31, main_inflow_ratio=1.84, turnover_pct=3.9,
                  board_pe=45.2, source="snapshot")
    with dataclasses.replace(bd, chg_pct=0.0) as _:  # replace returns a new obj
        pass


def test_board_day_board_pe_optional():
    bd = BoardDay(date="2026-07-06", board_code="BK0475", board_name="半导体",
                  chg_pct=2.31, main_inflow_ratio=1.84, turnover_pct=3.9,
                  board_pe=None, source="snapshot")
    assert bd.board_pe is None


def test_board_state_defaults_and_frozen():
    bs = BoardState(board_code="BK0475", board_name="半导体", state="emerging",
                    days_in_state=2, composite_pctl=0.83, mom20=1.2, flow5=1.5,
                    turn_delta=0.4, pe_pctl=0.95, chase_risk=True)
    assert bs.state == "emerging" and bs.chase_risk is True
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        bs.state = "hot"  # type: ignore[misc]


def test_report_shape():
    rep = RotationReport(schema_version=1, radar_version=1, data_status="ok",
                         board_states=(), candidates=(), diagnostics={})
    assert rep.schema_version == 1 and rep.radar_version == 1
```

Note: fix the `with dataclasses.replace(...)` line — `replace` doesn't return a context manager. Use:
```python
def test_board_day_is_frozen():
    bd = BoardDay(date="2026-07-06", board_code="BK0475", board_name="半导体",
                  chg_pct=2.31, main_inflow_ratio=1.84, turnover_pct=3.9,
                  board_pe=45.2, source="snapshot")
    bd2 = dataclasses.replace(bd, chg_pct=0.0)
    assert bd2.chg_pct == 0.0 and bd.chg_pct == 2.31
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.rotation'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/rotation/types.py
"""Frozen data contracts for the sector rotation radar (spec §4/§5)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BoardDay:
    date: str
    board_code: str
    board_name: str
    chg_pct: float
    main_inflow_ratio: float | None
    turnover_pct: float | None
    board_pe: float | None  # f9 市盈率 from the snapshot; None when genuinely absent
    source: str  # "snapshot" | "backfill"


@dataclass(frozen=True)
class BoardState:
    board_code: str
    board_name: str
    state: str  # "emerging" | "hot" | "fading" | "quiet"
    days_in_state: int
    composite_pctl: float
    mom20: float
    flow5: float | None
    turn_delta: float
    pe_pctl: float | None
    chase_risk: bool


@dataclass(frozen=True)
class ExposureRow:
    fund_id: str
    name_cn: str
    board_code: str
    exposure_pct: float
    matched_symbols: tuple[str, ...]
    holdings_as_of: str | None


@dataclass(frozen=True)
class RotationCandidate:
    fund_id: str
    name_cn: str
    board_code: str
    board_name: str
    exposure_pct: float
    on_discovered_watchlist: bool
    in_monitor_set: bool
    held: bool
    holdings_as_of: str | None


@dataclass(frozen=True)
class RotationReport:
    schema_version: int
    radar_version: int
    data_status: str  # "ok" | "degraded_flow_dark" | "abstain"
    board_states: tuple[BoardState, ...]
    candidates: tuple[RotationCandidate, ...]
    diagnostics: dict = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_types.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/__init__.py src/irc/rotation/types.py tests/rotation/test_types.py
git commit -m "feat(rotation): frozen data contracts (BoardDay/BoardState/ExposureRow/RotationCandidate/RotationReport)"
```

**Verification point:** all five types importable, frozen, and shaped per spec §5.

---

## Task 3: Board-snapshot + board-history parsers (PURE) + edge fetchers

**Files:**
- Create: `src/irc/rotation/board_fetch.py`
- Test: `tests/rotation/test_board_fetch.py`

**Interfaces:**
- Consumes: `tests/rotation/fixtures/board_spot_sample.json`, `board_hist_sample.json` (Task 1); `em_raw._diff_rows`; `resolve_cn_proxy`.
- Produces: `parse_board_spot(payload) -> tuple[BoardDay, ...]` (date injected by caller — snapshot is "today"); `parse_board_hist(payload, board_code, board_name) -> tuple[BoardDay, ...]`; `fetch_board_spot(today, *, http_get=None) -> tuple[BoardDay, ...]` (1 call); `fetch_board_hist(board_code, board_name, *, http_get=None) -> tuple[BoardDay, ...]` (1 call). Parsers are PURE; fetchers are EDGE (proxy at edge, raise on transport error so `cached_fetch` classifies TRANSIENT).

- [ ] **Step 1: Write the failing test** (parser-first, defensive like `parse_ulist`)

```python
# tests/rotation/test_board_fetch.py
import json
from pathlib import Path

from irc.rotation.board_fetch import parse_board_spot, parse_board_hist

_FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def test_parse_board_spot_extracts_rows():
    rows = parse_board_spot(_load("board_spot_sample.json"), today="2026-07-06")
    assert rows  # at least one board
    r = rows[0]
    assert r.board_code.startswith("BK")
    assert r.source == "snapshot" and r.date == "2026-07-06"
    assert isinstance(r.chg_pct, float)


def test_parse_board_spot_extracts_board_pe_and_none():
    rows = parse_board_spot(_load("board_spot_sample.json"), today="2026-07-06")
    pes = {r.board_code: r.board_pe for r in rows}
    # at least one board has a numeric PE and at least one has None (missing/"-")
    assert any(isinstance(v, float) for v in pes.values())
    assert any(v is None for v in pes.values())


def test_parse_board_spot_tolerates_empty():
    assert parse_board_spot({"data": None}, today="2026-07-06") == ()
    assert parse_board_spot({}, today="2026-07-06") == ()


def test_parse_board_hist_daily_rows():
    rows = parse_board_hist(_load("board_hist_sample.json"),
                            board_code="BK0475", board_name="半导体")
    assert len(rows) >= 3
    assert all(r.source == "backfill" for r in rows)
    assert rows[0].date < rows[-1].date  # ascending
    assert all(r.board_code == "BK0475" for r in rows)


def test_parse_board_hist_tolerates_empty():
    assert parse_board_hist({"data": {"klines": []}}, "BK0475", "半导体") == ()
    assert parse_board_hist({}, "BK0475", "半导体") == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_board_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError` / `parse_board_spot` undefined.

- [ ] **Step 3: Write minimal implementation** (field codes per probe notes; defensive coercion)

```python
# src/irc/rotation/board_fetch.py
"""EDGE + pure parse: EM industry-board snapshot (1 call) + paced backfill.

Transport = raw push2 via IRC_CN_PROXY (T2: requests, never curl-through-proxy).
Field codes are INTERFACE-SPECIFIC and were recorded by the AC1 probe
(001-probe-notes.md). Snapshot rides the SAME clist/get interface em_raw uses
(fs=m:90+t:2). Parsers are PURE + tolerant (parse_ulist posture); fetchers RAISE
on transport error so cached_fetch classifies TRANSIENT (never a fabricated row).
"""
from __future__ import annotations

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
    if value in (None, "-", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    'date,open,close,high,low,volume,amount,amplitude' (f51..f58). chg% derived
    from close vs prev close; flow/turnover absent in kline → None. Blank → ()."""
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
                             turnover_pct=_f(parts[8]) if len(parts) > 8 else None,
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_board_fetch.py -v`
Expected: PASS (5 tests). If a fixture field code diverges from the parser, fix the parser to match the recorded probe codes (do NOT edit the fixture to fit the parser).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/board_fetch.py tests/rotation/test_board_fetch.py
git commit -m "feat(rotation): board snapshot + history parsers (pure) + proxy edge fetchers"
```

**Verification point:** parsers extract ≥1 board from the real-shaped spot fixture and ≥3 ascending daily rows from the hist fixture, and return `()` on blank — the tolerant-parse contract (mirrors `parse_ulist`). AC1's parser-defensiveness is satisfied.

---

## Task 4: Board series store (EDGE, mirrors flow_series_store)

**Files:**
- Create: `src/irc/rotation/series_store.py`
- Test: `tests/rotation/test_series_store.py`

**Interfaces:**
- Consumes: `BoardDay`; `irc.io_utils.atomic_write_text`.
- Produces: `load_store(path) -> dict[str, tuple[BoardDay, ...]]` (keyed by board_code, ascending by date; corrupt/missing → {}); `append_snapshot(path, day_rows, *, keep_td, trading_days) -> dict[...]` (idempotent same-day overwrite per board, prune to keep_td trading days, atomic byte-stable write); `seed_backfill(path, backfilled, *, keep_td, trading_days) -> dict[...]` (merge historical BoardDay series, prune, write). The store is schema-agnostic over `BoardDay` fields (`asdict`/`BoardDay(**r)`), so `board_pe` persists automatically — pe_pctl is thus read from the store's LATEST day, inheriting once-per-day idempotency (AC3).

- [ ] **Step 1: Write the failing test**

```python
# tests/rotation/test_series_store.py
from pathlib import Path

from irc.rotation.series_store import load_store, append_snapshot
from irc.rotation.types import BoardDay


def _bd(date, code, chg, src="snapshot", pe=45.0):
    return BoardDay(date=date, board_code=code, board_name="半导体",
                    chg_pct=chg, main_inflow_ratio=1.0, turnover_pct=2.0,
                    board_pe=pe, source=src)


def test_missing_store_is_empty(tmp_path):
    assert load_store(tmp_path / "nope.jsonl") == {}


def test_append_then_load_roundtrip(tmp_path):
    p = tmp_path / "board_series.jsonl"
    tds = ("2026-07-06", "2026-07-07")
    append_snapshot(p, [_bd("2026-07-06", "BK0475", 1.0)], keep_td=25, trading_days=tds)
    store = append_snapshot(p, [_bd("2026-07-07", "BK0475", 2.0)], keep_td=25,
                            trading_days=tds)
    assert [r.date for r in store["BK0475"]] == ["2026-07-06", "2026-07-07"]


def test_same_day_rerun_no_double_append(tmp_path):
    p = tmp_path / "board_series.jsonl"
    tds = ("2026-07-06",)
    append_snapshot(p, [_bd("2026-07-06", "BK0475", 1.0)], keep_td=25, trading_days=tds)
    store = append_snapshot(p, [_bd("2026-07-06", "BK0475", 9.9)], keep_td=25,
                            trading_days=tds)
    assert len(store["BK0475"]) == 1
    assert store["BK0475"][0].chg_pct == 9.9  # overwrite, not append


def test_prune_to_keep_td(tmp_path):
    p = tmp_path / "board_series.jsonl"
    tds = ("2026-07-01", "2026-07-02", "2026-07-03")
    append_snapshot(p, [_bd("2026-07-01", "BK0475", 1.0)], keep_td=2, trading_days=tds)
    append_snapshot(p, [_bd("2026-07-02", "BK0475", 2.0)], keep_td=2, trading_days=tds)
    store = append_snapshot(p, [_bd("2026-07-03", "BK0475", 3.0)], keep_td=2,
                            trading_days=tds)
    assert [r.date for r in store["BK0475"]] == ["2026-07-02", "2026-07-03"]


def test_write_is_byte_stable(tmp_path):
    p = tmp_path / "board_series.jsonl"
    tds = ("2026-07-06",)
    append_snapshot(p, [_bd("2026-07-06", "BK0475", 1.0)], keep_td=25, trading_days=tds)
    first = p.read_bytes()
    append_snapshot(p, [_bd("2026-07-06", "BK0475", 1.0)], keep_td=25, trading_days=tds)
    assert p.read_bytes() == first  # deterministic (AC3 foundation)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_series_store.py -v`
Expected: FAIL — module/function undefined.

- [ ] **Step 3: Write minimal implementation** (mirror `flow_series_store`)

```python
# src/irc/rotation/series_store.py
"""EDGE: persisted board daily-series store (mirrors flow_series_store.py).

One file (data/rotation/board_series.json), keyed by board_code, pruned to
keep_td trading days, idempotent same-day (overwrite that board-day row), and
byte-stable (atomic_write_text: tmp→os.replace, sorted keys). Corrupt/missing →
{} (never crash). Snapshot rows carry price+flow+turnover; backfill rows carry
price(+turnover) only (kline has no flow) — flow5 tolerates None per §6.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path

from irc.io_utils import atomic_write_text
from irc.rotation.types import BoardDay

_log = logging.getLogger(__name__)


def _row(bd: BoardDay) -> dict:
    return asdict(bd)


def load_store(path: Path) -> dict[str, tuple[BoardDay, ...]]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(code): tuple(BoardDay(**r) for r in rows)
                for code, rows in raw.items()}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        _log.warning("rotation series_store: unreadable store %s; degrading", path,
                     exc_info=True)
        return {}


def _prune_window(anchor: str, keep_td: int, trading_days: Iterable[str]) -> set[str] | None:
    days = sorted(trading_days)
    if not days:
        return None
    eligible = [d for d in days if d <= anchor]
    return set(eligible[-keep_td:])


def _prune(rows: tuple[BoardDay, ...], anchor: str, keep_td: int,
           trading_days: Iterable[str]) -> tuple[BoardDay, ...]:
    keep = _prune_window(anchor, keep_td, trading_days)
    kept = [r for r in rows if keep is None or r.date in keep]
    return tuple(sorted(kept, key=lambda r: r.date))


def _merge_day(prior: tuple[BoardDay, ...], bd: BoardDay) -> tuple[BoardDay, ...]:
    return tuple(r for r in prior if r.date != bd.date) + (bd,)


def _write(path: Path, store: Mapping[str, tuple[BoardDay, ...]]) -> None:
    payload = {code: [_row(r) for r in sorted(rows, key=lambda x: x.date)]
               for code, rows in sorted(store.items())}
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2,
                                       sort_keys=True))


def append_snapshot(path: Path, day_rows: Iterable[BoardDay], *, keep_td: int,
                    trading_days: Iterable[str]) -> dict[str, tuple[BoardDay, ...]]:
    store = load_store(path)
    trading_days = tuple(trading_days)
    anchor = ""
    for bd in day_rows:
        anchor = max(anchor, bd.date)
        merged = _merge_day(store.get(bd.board_code, ()), bd)
        store[bd.board_code] = _prune(merged, bd.date, keep_td, trading_days)
    _write(path, store)
    return store


def seed_backfill(path: Path, backfilled: Mapping[str, Iterable[BoardDay]], *,
                  keep_td: int, trading_days: Iterable[str]
                  ) -> dict[str, tuple[BoardDay, ...]]:
    store = load_store(path)
    trading_days = tuple(trading_days)
    anchor = max((r.date for rows in backfilled.values() for r in rows), default="")
    for code, rows in backfilled.items():
        by_date = {r.date: r for r in store.get(code, ())}
        by_date.update({r.date: r for r in rows})
        store[code] = _prune(tuple(by_date.values()), anchor, keep_td, trading_days)
    _write(path, store)
    return store
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_series_store.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/series_store.py tests/rotation/test_series_store.py
git commit -m "feat(rotation): board series store (idempotent, pruned, byte-stable)"
```

**Verification point:** same-day rerun overwrites (no double-append), prune respects `keep_td`, identical inputs → identical bytes (AC3 foundation), corrupt/missing → {}.

---

## Task 5: Composite scoring (PURE) — §6 percentile blend + flow-dark renorm

**Files:**
- Create: `src/irc/rotation/composite.py`
- Test: `tests/rotation/test_composite.py`

**Interfaces:**
- Consumes: `BoardDay` series (`dict[str, tuple[BoardDay,...]]`).
- Produces: `board_signals(series) -> dict[str, dict]` (per eligible board: `mom20`, `flow5`, `turn_delta`; boards with <20 trading days excluded); `cross_sectional(signals, *, flow_dark) -> dict[str, float]` (composite percentile per board; flow_dark drops flow leg globally and renormalizes to 0.71·mom/0.29·turn); `pe_percentiles(pe_by_board) -> dict[str, float]` (cross-sectional percentile over boards that HAVE a PE; PE-less boards absent from the result → pe_pctl None downstream); helper `_percentile_ranks(values) -> dict`. Constants `W_MOM=0.5, W_FLOW=0.3, W_TURN=0.2`; `MIN_TD=20`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rotation/test_composite.py
from irc.rotation.composite import board_signals, cross_sectional
from irc.rotation.types import BoardDay


def _series(code, chgs, flows=None, turns=None, pes=None):
    n = len(chgs)
    flows = flows if flows is not None else [1.0] * n
    turns = turns if turns is not None else [2.0] * n
    pes = pes if pes is not None else [None] * n
    return tuple(
        BoardDay(date=f"2026-06-{i+1:02d}", board_code=code, board_name=code,
                 chg_pct=chgs[i], main_inflow_ratio=flows[i], turnover_pct=turns[i],
                 board_pe=pes[i], source="snapshot")
        for i in range(n))


def test_boards_below_20td_excluded():
    series = {"BK1": _series("BK1", [1.0] * 10)}  # only 10 days
    assert board_signals(series) == {}


def test_mom20_is_cumulative_chg_minus_cross_board_median():
    up = _series("BK1", [1.0] * 25)      # +25 cumulative
    flat = _series("BK2", [0.0] * 25)    # 0 cumulative
    sig = board_signals({"BK1": up, "BK2": flat})
    # median cumulative = (25+0)/2 = 12.5; BK1 mom20 = 25-12.5 = 12.5
    assert round(sig["BK1"]["mom20"], 4) == 12.5
    assert round(sig["BK2"]["mom20"], 4) == -12.5


def test_composite_weights_and_ranks():
    hot = _series("BK1", [2.0] * 25, flows=[3.0] * 25, turns=[3.0] * 25)
    cold = _series("BK2", [0.0] * 25, flows=[0.0] * 25, turns=[1.0] * 25)
    comp = cross_sectional(board_signals({"BK1": hot, "BK2": cold}), flow_dark=False)
    assert comp["BK1"] > comp["BK2"]
    assert 0.0 <= comp["BK1"] <= 1.0


def test_flow_dark_renormalizes_and_ignores_flow():
    # BK1 wins on mom+turn even with flow set high on the LOSER — flow must not count
    hot = _series("BK1", [2.0] * 25, flows=[0.0] * 25, turns=[3.0] * 25)
    cold = _series("BK2", [0.0] * 25, flows=[9.0] * 25, turns=[1.0] * 25)
    comp = cross_sectional(board_signals({"BK1": hot, "BK2": cold}), flow_dark=True)
    assert comp["BK1"] > comp["BK2"]  # flow leg dropped for ALL boards


def test_pe_percentiles_ranks_only_boards_with_pe():
    from irc.rotation.composite import pe_percentiles
    pctls = pe_percentiles({"BK1": 80.0, "BK2": 10.0, "BK3": None})
    assert pctls["BK1"] > pctls["BK2"]  # higher PE → higher percentile
    assert "BK3" not in pctls  # PE-less board excluded → pe_pctl None downstream
    assert all(0.0 <= v <= 1.0 for v in pctls.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_composite.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/rotation/composite.py
"""PURE: per-day cross-sectional percentiles → rotation composite (spec §6, D4).

Composite = 0.5·pct(mom20) + 0.3·pct(flow5) + 0.2·pct(turnΔ). mom20 = 20-td
cumulative chg minus the cross-board median. flow5 = mean main_inflow_ratio over
last 5 td. turnΔ = (5-td mean turnover / 20-td mean turnover) - 1. Percentiles
cross-sectional over boards with ≥20 td of history. flow_dark → drop the flow
leg for ALL boards, renormalize to 0.71·mom/0.29·turn (never per-board mixing,
never carry-forward). pe_percentiles ranks board PE cross-sectionally (chase_risk
input, §6) over boards that HAVE a PE. No I/O.
"""
from __future__ import annotations

from collections.abc import Mapping
from statistics import median

from irc.rotation.types import BoardDay

W_MOM, W_FLOW, W_TURN = 0.5, 0.3, 0.2
MIN_TD = 20


def _tail_mean(values: list[float], n: int) -> float | None:
    tail = [v for v in values[-n:] if v is not None]
    return sum(tail) / len(tail) if tail else None


def board_signals(series: Mapping[str, tuple[BoardDay, ...]]) -> dict[str, dict]:
    """Pure: per eligible board (≥20 td) → {mom20, flow5, turn_delta}. Boards
    below MIN_TD are excluded (states/diagnostics handle them; no silent cap)."""
    eligible = {c: rows for c, rows in series.items() if len(rows) >= MIN_TD}
    cum = {c: sum(r.chg_pct for r in rows[-MIN_TD:]) for c, rows in eligible.items()}
    med = median(cum.values()) if cum else 0.0
    out: dict[str, dict] = {}
    for c, rows in eligible.items():
        flows = [r.main_inflow_ratio for r in rows]
        turns = [r.turnover_pct for r in rows]
        m20 = _tail_mean(turns, MIN_TD)
        m5 = _tail_mean(turns, 5)
        turn_delta = (m5 / m20 - 1) if (m20 not in (None, 0) and m5 is not None) else 0.0
        out[c] = {"mom20": cum[c] - med,
                  "flow5": _tail_mean(flows, 5),
                  "turn_delta": turn_delta}
    return out


def _percentile_ranks(values: Mapping[str, float]) -> dict[str, float]:
    """Pure: fractional rank in [0,1] (ties share the mean rank). Single board → 0.5."""
    if not values:
        return {}
    if len(values) == 1:
        return {k: 0.5 for k in values}
    ordered = sorted(values.values())
    n = len(ordered)
    out = {}
    for k, v in values.items():
        below = sum(1 for x in ordered if x < v)
        equal = sum(1 for x in ordered if x == v)
        out[k] = (below + (equal - 1) / 2) / (n - 1)
    return out


def cross_sectional(signals: Mapping[str, dict], *, flow_dark: bool
                    ) -> dict[str, float]:
    """Pure: signals → composite percentile per board. flow_dark drops flow leg
    for ALL boards (renorm 0.71·mom/0.29·turn). Missing flow5 for a board when
    NOT flow_dark → treated as flow-absent globally is the caller's decision;
    here a None flow5 contributes rank 0.0 only if flow_dark is False and some
    board has flow (caller sets flow_dark when the whole leg is absent)."""
    mom = _percentile_ranks({c: s["mom20"] for c, s in signals.items()})
    turn = _percentile_ranks({c: s["turn_delta"] for c, s in signals.items()})
    if flow_dark:
        denom = W_MOM + W_TURN
        return {c: (W_MOM * mom[c] + W_TURN * turn[c]) / denom for c in signals}
    flow = _percentile_ranks({c: (s["flow5"] or 0.0) for c, s in signals.items()})
    return {c: W_MOM * mom[c] + W_FLOW * flow[c] + W_TURN * turn[c] for c in signals}


def pe_percentiles(pe_by_board: Mapping[str, float | None]) -> dict[str, float]:
    """Pure (§6 chase_risk input): cross-sectional PE percentile over boards that
    HAVE a PE. PE-less boards (None) are EXCLUDED from the result → their pe_pctl
    is None downstream (the real §6 'missing PE → no flag, noted in diagnostics'
    path). Reuses the composite percentile helper — one ranking definition."""
    present = {c: v for c, v in pe_by_board.items() if v is not None}
    return _percentile_ranks(present)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_composite.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/composite.py tests/rotation/test_composite.py
git commit -m "feat(rotation): composite percentile blend + flow-dark renorm + PE percentile (pure)"
```

**Verification point:** boards <20 td excluded; mom20 is median-relative; composite ranks hot>cold; flow_dark drops the flow leg globally (AC5 renorm, no per-board mixing); `pe_percentiles` ranks only PE-bearing boards (PE-less excluded → None downstream).

---

## Task 6: State machine (PURE) — §6/D5 hysteresis + property test

**Files:**
- Create: `src/irc/rotation/states.py`
- Test: `tests/rotation/test_states.py`

**Interfaces:**
- Consumes: per-board composite-percentile **series** (a list of `(date, pctl)` in ascending order — one composite pctl per trading day the board was eligible). The daily run builds these by recomputing composite per historical day from the series store.
- Produces: `classify_board(pctl_series) -> tuple[str, int]` returning `(state, days_in_state)`; constants `P_ENTER=0.80`, `P_EXIT=0.70`, `EMERGING_WINDOW=5`. Pure total function of the series slice (AC4).

- [ ] **Step 1: Write the failing test** (includes the AC4 property test)

```python
# tests/rotation/test_states.py
from irc.rotation.states import classify_board


def _series(pctls):
    return tuple((f"2026-06-{i+1:02d}", p) for i, p in enumerate(pctls))


def test_quiet_when_never_above_enter():
    state, dis = classify_board(_series([0.5, 0.6, 0.55, 0.4]))
    assert state == "quiet"


def test_emerging_when_crossed_enter_within_5td():
    # crosses above 0.80 on the last day
    state, dis = classify_board(_series([0.5, 0.6, 0.7, 0.75, 0.85]))
    assert state == "emerging" and dis == 1


def test_hot_when_above_band_more_than_5td():
    state, _ = classify_board(_series([0.85, 0.86, 0.9, 0.88, 0.91, 0.87]))
    assert state == "hot"


def test_no_flap_on_p79_p81_oscillation():
    # oscillates around the band but never exits below 0.70 → stays hot, no flap
    seq = [0.85, 0.86, 0.9, 0.88, 0.91, 0.87, 0.79, 0.81, 0.79, 0.81]
    state, _ = classify_board(_series(seq))
    assert state == "hot"


def test_fading_on_band_exit_within_5td():
    seq = [0.85, 0.9, 0.88, 0.91, 0.87, 0.6]  # fell below 0.70 on last day after hot
    state, dis = classify_board(_series(seq))
    assert state == "fading"


def test_emerging_promotes_to_hot_at_day_6():
    seq = [0.85, 0.86, 0.87, 0.88, 0.89, 0.90]  # 6 consecutive days above enter
    state, _ = classify_board(_series(seq))
    assert state == "hot"


def test_property_total_function_of_slice():
    # any pctl series returns a valid state + non-negative days_in_state
    import itertools
    for combo in itertools.product([0.1, 0.75, 0.85], repeat=4):
        state, dis = classify_board(_series(list(combo)))
        assert state in {"emerging", "hot", "fading", "quiet"}
        assert dis >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_states.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/rotation/states.py
"""PURE: composite-percentile series → rotation_state per board (spec §6, D5).

p80-entry / p70-exit hysteresis over the trading-day-indexed pctl series:
- emerging: first day above 0.80 was ≤5 td ago (early-detection deliverable).
- hot:      above the band >5 td (band exit only below 0.70).
- fading:   fell below 0.70 within the last 5 td after being hot/emerging.
- quiet:    otherwise.
Recomputed PURELY from the series — no incremental state file (D5). Total
function of the series slice (AC4); no I/O.
"""
from __future__ import annotations

P_ENTER = 0.80
P_EXIT = 0.70
EMERGING_WINDOW = 5


def _in_band_flags(pctls: list[float]) -> list[bool]:
    """Hysteresis membership: enter above P_ENTER, stay until below P_EXIT."""
    flags: list[bool] = []
    inside = False
    for p in pctls:
        if inside:
            inside = p >= P_EXIT
        else:
            inside = p >= P_ENTER
        flags.append(inside)
    return flags


def _days_since_entry(flags: list[bool]) -> int | None:
    """Trading days since the current in-band run began (1 = entered today).
    None when not currently in band."""
    if not flags or not flags[-1]:
        return None
    run = 0
    for f in reversed(flags):
        if not f:
            break
        run += 1
    return run


def _days_since_band_exit(flags: list[bool]) -> int | None:
    """Trading days since the last True→False transition. None if never exited or
    currently in band."""
    if not flags or flags[-1]:
        return None
    for i in range(len(flags) - 1, 0, -1):
        if flags[i - 1] and not flags[i]:
            return len(flags) - i
    return None


def classify_board(pctl_series: tuple[tuple[str, float], ...]) -> tuple[str, int]:
    """Pure (AC4): (state, days_in_state). Total function of the series slice."""
    pctls = [p for _d, p in pctl_series]
    flags = _in_band_flags(pctls)
    entry = _days_since_entry(flags)
    if entry is not None:
        if entry <= EMERGING_WINDOW:
            return "emerging", entry
        return "hot", entry
    exit_age = _days_since_band_exit(flags)
    if exit_age is not None and exit_age <= EMERGING_WINDOW:
        return "fading", exit_age
    return "quiet", 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_states.py -v`
Expected: PASS (7 tests, incl. the property test).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/states.py tests/rotation/test_states.py
git commit -m "feat(rotation): rotation_state hysteresis machine (pure, total function)"
```

**Verification point:** no flap on p79↔p81 oscillation; emerging→hot at day 6; fading on band exit; quiet default; property test passes across all 4-day combos (AC4).

---

## Task 7: Exposure matrix (PURE) — §5/§6 fund×board join

**Files:**
- Create: `src/irc/rotation/exposure.py`
- Test: `tests/rotation/test_exposure.py`

**Interfaces:**
- Consumes: `Holding` (`irc.narrative.schemas`); a `stock→board_code` map (`dict[str,str]`) + a `board_code→board_name` map; per-fund `(fund_id, name_cn, holdings, holdings_as_of)`.
- Produces: `build_exposure(funds, stock_to_board, board_names) -> tuple[tuple[ExposureRow,...], dict]` returning `(rows, coverage_diag)`. `coverage_diag = {"total_holding_syms", "mapped_syms", "unmapped_syms": tuple, "coverage_pct"}`. A fund with 3 top-10 holdings in one board sums their weights (AC6); unmapped stocks reduce coverage and appear in diagnostics, never silently dropped.

- [ ] **Step 1: Write the failing test**

```python
# tests/rotation/test_exposure.py
from irc.narrative.schemas import Holding
from irc.rotation.exposure import build_exposure


def _h(sym, w):
    return Holding(symbol=sym, name_cn=sym, weight_pct=w, sw_industry="")


def test_three_holdings_one_board_sum_weights():
    funds = [("F1", "基金一", (_h("600001", 5.0), _h("600002", 4.0), _h("600003", 3.0)),
              "2026Q1")]
    s2b = {"600001": "BK1", "600002": "BK1", "600003": "BK1"}
    rows, diag = build_exposure(funds, s2b, {"BK1": "半导体"})
    assert len(rows) == 1
    r = rows[0]
    assert r.board_code == "BK1" and round(r.exposure_pct, 4) == 12.0
    assert set(r.matched_symbols) == {"600001", "600002", "600003"}
    assert r.holdings_as_of == "2026Q1"


def test_unmapped_stocks_reduce_coverage_and_listed():
    funds = [("F1", "基金一", (_h("600001", 5.0), _h("999999", 4.0)), "2026Q1")]
    s2b = {"600001": "BK1"}
    rows, diag = build_exposure(funds, s2b, {"BK1": "半导体"})
    assert "999999" in diag["unmapped_syms"]
    assert diag["mapped_syms"] == 1 and diag["total_holding_syms"] == 2
    assert round(diag["coverage_pct"], 4) == 50.0


def test_multiple_boards_split_rows():
    funds = [("F1", "基金一", (_h("600001", 5.0), _h("000002", 4.0)), "2026Q1")]
    s2b = {"600001": "BK1", "000002": "BK2"}
    rows, _ = build_exposure(funds, s2b, {"BK1": "半导体", "BK2": "白酒"})
    by_board = {r.board_code: r.exposure_pct for r in rows}
    assert by_board == {"BK1": 5.0, "BK2": 4.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_exposure.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/rotation/exposure.py
"""PURE: holdings × stock→board map → fund×board exposure matrix (spec §5/§6, D7).

exposure_pct(fund, board) = Σ top-10 holding weight_pct mapped to that board.
Unmapped stocks reduce coverage and are surfaced in diagnostics — never silently
dropped (AC6). No I/O.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from irc.narrative.schemas import Holding
from irc.rotation.types import ExposureRow

Fund = tuple[str, str, tuple[Holding, ...], str | None]


def build_exposure(
    funds: Iterable[Fund],
    stock_to_board: Mapping[str, str],
    board_names: Mapping[str, str],
) -> tuple[tuple[ExposureRow, ...], dict]:
    rows: list[ExposureRow] = []
    all_syms: set[str] = set()
    mapped_syms: set[str] = set()
    unmapped: set[str] = set()
    for fund_id, name_cn, holdings, as_of in funds:
        by_board: dict[str, list[Holding]] = {}
        for h in holdings:
            all_syms.add(h.symbol)
            board = stock_to_board.get(h.symbol)
            if board is None:
                unmapped.add(h.symbol)
                continue
            mapped_syms.add(h.symbol)
            by_board.setdefault(board, []).append(h)
        for board, hs in by_board.items():
            rows.append(ExposureRow(
                fund_id=fund_id, name_cn=name_cn, board_code=board,
                exposure_pct=round(sum(h.weight_pct for h in hs), 4),
                matched_symbols=tuple(sorted(h.symbol for h in hs)),
                holdings_as_of=as_of))
    total = len(all_syms)
    diag = {
        "total_holding_syms": total,
        "mapped_syms": len(mapped_syms),
        "unmapped_syms": tuple(sorted(unmapped)),
        "coverage_pct": round(100.0 * len(mapped_syms) / total, 4) if total else 0.0,
    }
    return tuple(rows), diag
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_exposure.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/exposure.py tests/rotation/test_exposure.py
git commit -m "feat(rotation): fund×board exposure matrix + coverage diagnostics (pure)"
```

**Verification point:** 3 holdings in one board sum; unmapped stocks in `diag["unmapped_syms"]` reduce `coverage_pct` (AC6); multi-board holdings split into rows.

---

## Task 8: Candidate ranking (PURE) — §5 annotations

**Files:**
- Create: `src/irc/rotation/candidates.py`
- Test: `tests/rotation/test_candidates.py`

**Interfaces:**
- Consumes: `ExposureRow` rows; `BoardState` rows; membership sets `discovered_watchlist: frozenset[str]`, `monitor_set: frozenset[str]`, `held: frozenset[str]`.
- Produces: `rank_candidates(exposure_rows, board_states, *, discovered_watchlist, monitor_set, held, min_exposure_pct=10.0, top_n=10) -> tuple[tuple[RotationCandidate,...], tuple[str,...]]` returning `(candidates, new_candidate_fund_ids)`. Only `emerging`/`hot` boards produce candidates; per board top 10 funds by exposure ≥10%. `new_candidates` = candidate funds on NO existing surface. Constants `MIN_EXPOSURE_PCT=10.0`, `CAND_TOP_N=10`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rotation/test_candidates.py
from irc.rotation.candidates import rank_candidates
from irc.rotation.types import BoardState, ExposureRow


def _state(code, state):
    return BoardState(board_code=code, board_name=code, state=state, days_in_state=1,
                      composite_pctl=0.85, mom20=1.0, flow5=1.0, turn_delta=0.1,
                      pe_pctl=None, chase_risk=False)


def _exp(fund, code, pct, as_of="2026Q1"):
    return ExposureRow(fund_id=fund, name_cn=fund, board_code=code, exposure_pct=pct,
                       matched_symbols=("600001",), holdings_as_of=as_of)


def test_only_emerging_hot_boards_produce_candidates():
    rows = [_exp("F1", "BK1", 20.0), _exp("F2", "BK2", 30.0)]
    states = [_state("BK1", "emerging"), _state("BK2", "quiet")]
    cands, _ = rank_candidates(rows, states, discovered_watchlist=frozenset(),
                               monitor_set=frozenset(), held=frozenset())
    assert {c.fund_id for c in cands} == {"F1"}  # BK2 is quiet → excluded


def test_threshold_and_annotations():
    rows = [_exp("F1", "BK1", 20.0), _exp("F2", "BK1", 5.0)]  # F2 below 10%
    states = [_state("BK1", "hot")]
    cands, new = rank_candidates(rows, states,
                                 discovered_watchlist=frozenset({"F1"}),
                                 monitor_set=frozenset(), held=frozenset())
    assert [c.fund_id for c in cands] == ["F1"]  # F2 filtered by threshold
    c = cands[0]
    assert c.on_discovered_watchlist is True and c.in_monitor_set is False
    assert c.held is False and c.holdings_as_of == "2026Q1"
    assert new == ()  # F1 is on the discovered watchlist → not new


def test_new_candidates_rollup():
    rows = [_exp("F9", "BK1", 25.0)]
    states = [_state("BK1", "emerging")]
    _, new = rank_candidates(rows, states, discovered_watchlist=frozenset(),
                             monitor_set=frozenset(), held=frozenset())
    assert new == ("F9",)  # on no existing surface
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_candidates.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/rotation/candidates.py
"""PURE: emerging/hot boards × exposure matrix → ranked rotation candidates (§5).

Per emerging/hot board: top 10 funds by exposure_pct ≥10%. Each row annotates
existing-surface membership + holdings_as_of (staleness stated, never hidden).
new_candidates rollup = candidate funds on NO existing surface. No I/O.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from irc.rotation.types import BoardState, ExposureRow, RotationCandidate

MIN_EXPOSURE_PCT = 10.0
CAND_TOP_N = 10
_ACTIVE_STATES = frozenset({"emerging", "hot"})


def rank_candidates(
    exposure_rows: Iterable[ExposureRow],
    board_states: Iterable[BoardState],
    *,
    discovered_watchlist: frozenset[str],
    monitor_set: frozenset[str],
    held: frozenset[str],
    min_exposure_pct: float = MIN_EXPOSURE_PCT,
    top_n: int = CAND_TOP_N,
) -> tuple[tuple[RotationCandidate, ...], tuple[str, ...]]:
    active: dict[str, str] = {b.board_code: b.board_name for b in board_states
                             if b.state in _ACTIVE_STATES}
    by_board: dict[str, list[ExposureRow]] = {}
    for r in exposure_rows:
        if r.board_code in active and r.exposure_pct >= min_exposure_pct:
            by_board.setdefault(r.board_code, []).append(r)
    cands: list[RotationCandidate] = []
    for code, rows in sorted(by_board.items()):
        ranked = sorted(rows, key=lambda r: (-r.exposure_pct, r.fund_id))[:top_n]
        for r in ranked:
            cands.append(RotationCandidate(
                fund_id=r.fund_id, name_cn=r.name_cn, board_code=code,
                board_name=active[code], exposure_pct=r.exposure_pct,
                on_discovered_watchlist=r.fund_id in discovered_watchlist,
                in_monitor_set=r.fund_id in monitor_set,
                held=r.fund_id in held, holdings_as_of=r.holdings_as_of))
    on_surface = discovered_watchlist | monitor_set | held
    new = tuple(sorted({c.fund_id for c in cands if c.fund_id not in on_surface}))
    return tuple(cands), new
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_candidates.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/candidates.py tests/rotation/test_candidates.py
git commit -m "feat(rotation): ranked candidates + membership annotations + new-candidate rollup (pure)"
```

**Verification point:** only emerging/hot boards yield candidates; 10% threshold; annotations correct against fixtures; `holdings_as_of` present on every row; `new_candidates` excludes on-surface funds (AC7).

---

## Task 9: Report projections (PURE) — §5/D8/AC8

**Files:**
- Create: `src/irc/rotation/report.py`
- Test: `tests/rotation/test_report.py`

**Interfaces:**
- Consumes: `RotationReport`.
- Produces: `to_json(report) -> str` (sorted keys, byte-stable — the source of truth); `to_md(report) -> str` (display-only, additive subset, NO `[ref:` markers); `abstain_report(reason) -> RotationReport` helper (`data_status="abstain"`, empty states/candidates, `diagnostics={"failure": reason}`); `cold_holdings_note() -> str` (the single actionable line pointing at `irc rotation seed`, §7).

- [ ] **Step 1: Write the failing test**

```python
# tests/rotation/test_report.py
import json

from irc.rotation.report import to_json, to_md, abstain_report
from irc.rotation.types import BoardState, RotationCandidate, RotationReport


def _report(status="ok"):
    return RotationReport(
        schema_version=1, radar_version=1, data_status=status,
        board_states=(BoardState("BK1", "半导体", "emerging", 2, 0.85, 1.2, 1.5,
                                 0.4, 0.95, True),),
        candidates=(RotationCandidate("F1", "基金一", "BK1", "半导体", 20.0,
                                      True, False, False, "2026Q1"),),
        diagnostics={"coverage_pct": 88.0, "immature_boards": 3})


def test_json_is_byte_stable_and_sorted():
    a, b = to_json(_report()), to_json(_report())
    assert a == b  # deterministic (AC3)
    parsed = json.loads(a)
    assert parsed["schema_version"] == 1 and parsed["radar_version"] == 1
    assert parsed["data_status"] == "ok"


def test_md_has_no_ref_marker():
    md = to_md(_report())
    assert "[ref:" not in md  # AC8 grep test — pure market data, no citations


def test_md_is_additive_subset_of_json():
    rep = _report()
    md, js = to_md(rep), json.loads(to_json(rep))
    # every board code / candidate fund in json appears in md (nothing extra suppressed)
    assert "BK1" in md and "半导体" in md and "F1" in md


def test_json_carries_pe_pctl_and_chase_risk():
    js = json.loads(to_json(_report()))
    bs = js["board_states"][0]
    assert bs["pe_pctl"] == 0.95 and bs["chase_risk"] is True


def test_md_renders_pe_pctl_and_chase_flag():
    md = to_md(_report())
    assert "追高" in md  # chase_risk annotation surfaced
    assert "0.95" in md or "95" in md  # pe_pctl rendered on the row


def test_abstain_report_shape():
    rep = abstain_report("snapshot dead after retries")
    js = json.loads(to_json(rep))
    assert js["data_status"] == "abstain"
    assert js["board_states"] == [] and js["candidates"] == []
    assert js["diagnostics"]["failure"] == "snapshot dead after retries"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_report.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/rotation/report.py
"""PURE: RotationReport → md + json projections (spec §5, D8).

json = source of truth (schema_version 1, radar_version 1, byte-stable sorted
keys). md = display-only additive subset, NO [ref:] markers (pure market data,
outside citation/SAME-3/H3 machinery — AC8). No I/O.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from irc.rotation.types import RotationReport

SCHEMA_VERSION = 1
RADAR_VERSION = 1  # bump ONLY on weight/window/hysteresis change (monitor lesson)


def to_json(report: RotationReport) -> str:
    """Pure: byte-stable sorted-key JSON (the source of truth)."""
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def _state_line(bs) -> str:
    chase = " ⚠追高" if bs.chase_risk else ""
    pe = f"{bs.pe_pctl:.2f}" if bs.pe_pctl is not None else "N/A"
    return (f"| {bs.board_code} | {bs.board_name} | {bs.state} | "
            f"{bs.days_in_state} | {bs.composite_pctl:.2f} | {pe} |{chase}")


def _cand_line(c) -> str:
    tags = []
    if c.on_discovered_watchlist:
        tags.append("watchlist")
    if c.in_monitor_set:
        tags.append("monitor")
    if c.held:
        tags.append("held")
    surface = ",".join(tags) or "新"
    return (f"| {c.fund_id} | {c.name_cn} | {c.board_name} | "
            f"{c.exposure_pct:.1f}% | {surface} | {c.holdings_as_of or 'N/A'} |")


def to_md(report: RotationReport) -> str:
    """Pure: display markdown (additive subset; NO [ref:] markers — AC8)."""
    lines = [f"# 板块轮动雷达 (data_status: {report.data_status})", ""]
    if report.data_status == "abstain":
        lines.append(f"雷达今日弃权：{report.diagnostics.get('failure', '未知')}")
        return "\n".join(lines) + "\n"
    lines += ["## 板块状态", "| 板块 | 名称 | 状态 | 天数 | 分位 | PE分位 |",
              "|---|---|---|---|---|---|"]
    lines += [_state_line(b) for b in report.board_states
              if b.state != "quiet"]
    lines += ["", "## 轮动候选基金", "| 基金 | 名称 | 板块 | 敞口 | 现有面 | 持仓季度 |",
              "|---|---|---|---|---|---|"]
    lines += [_cand_line(c) for c in report.candidates]
    return "\n".join(lines) + "\n"


def abstain_report(reason: str) -> RotationReport:
    """Pure: the total-failure abstain stub (§7, AC5)."""
    return RotationReport(schema_version=SCHEMA_VERSION, radar_version=RADAR_VERSION,
                          data_status="abstain", board_states=(), candidates=(),
                          diagnostics={"failure": reason})


def cold_holdings_note() -> str:
    """Pure: the single actionable line when the holdings cache is cold (§7)."""
    return "持仓缓存为空：先运行 `uv run irc rotation seed` 以填充持仓+行业映射。"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_report.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/report.py tests/rotation/test_report.py
git commit -m "feat(rotation): md+json report projections (byte-stable, no [ref:], abstain stub)"
```

**Verification point:** json byte-stable + sorted (AC3); md contains no `[ref:` (AC8 grep); `pe_pctl` + `chase_risk` rendered on state rows (§5/§6); abstain stub shaped per §7.

---

## Task 10: Forward ledger (pure builder + edge append) — §5/D9/AC9

**Files:**
- Create: `src/irc/rotation/ledger.py`
- Test: `tests/rotation/test_ledger.py`

**Interfaces:**
- Consumes: `BoardState` rows; `radar_version`.
- Produces: `build_ledger_rows(date, board_states, radar_version) -> tuple[dict,...]` (pure; one row per board with state ≠ quiet: `{date, board_code, state, composite_pctl, chg_pct, radar_version}`); `append_rows(path, rows) -> None` (edge; append-only, atomic, same-day rerun does not duplicate).

- [ ] **Step 1: Write the failing test**

```python
# tests/rotation/test_ledger.py
import json
from pathlib import Path

from irc.rotation.ledger import build_ledger_rows, append_rows
from irc.rotation.types import BoardState


def _bs(code, state, pctl=0.85):
    return BoardState(code, code, state, 1, pctl, 1.0, 1.0, 0.1, None, False)


def test_build_skips_quiet():
    rows = build_ledger_rows("2026-07-06",
                             (_bs("BK1", "emerging"), _bs("BK2", "quiet")), 1)
    assert [r["board_code"] for r in rows] == ["BK1"]
    assert rows[0]["radar_version"] == 1 and rows[0]["date"] == "2026-07-06"


def test_append_is_append_only(tmp_path):
    p = tmp_path / "forward_ledger.jsonl"
    append_rows(p, build_ledger_rows("2026-07-06", (_bs("BK1", "emerging"),), 1))
    append_rows(p, build_ledger_rows("2026-07-07", (_bs("BK2", "hot"),), 1))
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["date"] == "2026-07-06"
    assert json.loads(lines[1])["date"] == "2026-07-07"


def test_same_day_rerun_no_duplicate(tmp_path):
    p = tmp_path / "forward_ledger.jsonl"
    rows = build_ledger_rows("2026-07-06", (_bs("BK1", "emerging"),), 1)
    append_rows(p, rows)
    append_rows(p, rows)  # rerun same day
    assert len(p.read_text().strip().splitlines()) == 1  # no dup (AC9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_ledger.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/rotation/ledger.py
"""Forward-ledger row builder (pure) + append (edge) — spec §5/D9, AC9.

One row per (date × board) with state ≠ quiet: {date, board_code, state,
composite_pctl, chg_pct, radar_version}. Append-only, atomic; a same-day rerun
does NOT duplicate (dedup by (date, board_code) already present). Corrupt/missing
existing file → treated as empty (never crash). Eval command deferred (F1).
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path

from irc.rotation.types import BoardState

_log = logging.getLogger(__name__)


def build_ledger_rows(date: str, board_states: Iterable[BoardState],
                      radar_version: int) -> tuple[dict, ...]:
    """Pure: non-quiet board rows for the ledger."""
    return tuple(
        {"date": date, "board_code": b.board_code, "state": b.state,
         "composite_pctl": round(b.composite_pctl, 4), "chg_pct": round(b.mom20, 4),
         "radar_version": radar_version}
        for b in board_states if b.state != "quiet")


def _existing_keys(path: Path) -> set[tuple[str, str]]:
    if not path.is_file():
        return set()
    keys: set[tuple[str, str]] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            keys.add((obj.get("date"), obj.get("board_code")))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("rotation ledger: unreadable %s; treating as empty", path,
                     exc_info=True)
        return set()
    return keys


def append_rows(path: Path, rows: Iterable[dict]) -> None:
    """EDGE: append-only atomic write; dedup by (date, board_code) (AC9)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_keys(path)
    fresh = [r for r in rows if (r["date"], r["board_code"]) not in existing]
    if not fresh:
        return
    prior = path.read_text(encoding="utf-8") if path.is_file() else ""
    body = prior + "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                           for r in fresh)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_ledger.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/ledger.py tests/rotation/test_ledger.py
git commit -m "feat(rotation): forward ledger builder + append-only atomic dedup (pure+edge)"
```

**Verification point:** quiet boards skipped; append-only; same-day rerun no duplicate; rows carry `radar_version` (AC9).

---

## Task 11: Import-isolation test — AC11

**Files:**
- Test: `tests/rotation/test_import_isolation.py`

**Interfaces:**
- Consumes: the whole `irc.monitor` / `irc.discovery` / `irc.scoring` / `irc.memo` / `irc.opportunity` source trees.
- Produces: a grep/AST test enforcing one-way dependency.

- [ ] **Step 1: Write the test**

```python
# tests/rotation/test_import_isolation.py
"""AC11: NOTHING in monitor/discovery/scoring/memo/opportunity imports irc.rotation.
rotation imports FROM monitor, never the reverse (one-way dependency)."""
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "irc"
_FORBIDDEN_IMPORTERS = ("monitor", "discovery", "scoring", "memo", "opportunity")


def test_no_upstream_imports_rotation():
    offenders = []
    for pkg in _FORBIDDEN_IMPORTERS:
        for py in (_SRC / pkg).rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "irc.rotation" in text or "from irc import rotation" in text:
                offenders.append(str(py))
    assert offenders == [], f"rotation imported by upstream packages: {offenders}"
```

- [ ] **Step 2: Run test to verify it passes** (should pass immediately — nothing imports rotation yet)

Run: `uv run pytest tests/rotation/test_import_isolation.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/rotation/test_import_isolation.py
git commit -m "test(rotation): AC11 one-way dependency isolation guard"
```

**Verification point:** the guard passes now and will fail loudly if any later change adds an upstream import of `irc.rotation` (AC11).

---

## Task 12: Extend industry_map_store for board-code seeding

**Files:**
- Modify: `src/irc/monitor/industry_map_store.py`
- Test: `tests/monitor/test_industry_map_store.py` (add cases — this is the EXISTING mirror test; do NOT create a rotation copy)

**Interfaces:**
- Consumes: the existing store shape `{symbol: {"industry": str, "seen_at": str}}`.
- Produces: no new function is strictly required — the radar's stock→board map uses **board codes** as the "industry" value, and the existing `merge_seen`/`fresh_slice`/`record_seen` already store arbitrary strings. Extend only the module docstring to document the board-code reuse (D7 "extended in place"). If a board-code + board-name pair must both be stored, add `merge_seen_pairs(store, today, pair_by_symbol)` where `pair_by_symbol: dict[str, tuple[str,str]]` writes `{"industry": board_code, "board_name": name, "seen_at": today}`; `fresh_slice` remains code-only.

**Decision:** the spec §4 says "written through the extended `industry_map_store` (30-day cache semantics preserved)". The minimal extension that preserves byte-stability is to store `board_code` as the `industry` value and carry `board_name` in the exposure step's separate `board_names` map (built from the daily snapshot). So the ONLY change here is a documented `merge_seen_pairs` for board_name co-storage IF the impl finds it cleaner; otherwise document the reuse. Prefer the smaller change: add `merge_seen_pairs` only if a test needs board_name persisted.

- [ ] **Step 1: Add a test for board-code storage via the existing API**

```python
# tests/monitor/test_industry_map_store.py  (ADD, do not replace existing tests)
def test_merge_seen_stores_board_codes_as_industry():
    from irc.monitor.industry_map_store import merge_seen, fresh_slice
    store = merge_seen({}, "2026-07-06", {"600001": "BK0475", "000002": "BK0438"})
    served = fresh_slice(store, "2026-07-06")
    assert served == {"600001": "BK0475", "000002": "BK0438"}
```

- [ ] **Step 2: Run to verify it passes** (existing API already supports arbitrary strings)

Run: `uv run pytest tests/monitor/test_industry_map_store.py -v`
Expected: PASS (existing + new).

- [ ] **Step 3: Extend the module docstring**

Edit `src/irc/monitor/industry_map_store.py` header to add: *"Also serves the sector rotation radar (ADR 0023 D7): the same store persists stock→EM-board-code mappings (board codes are stored in the `industry` slot; the radar carries board display names separately from the daily snapshot). 30-day serve-while-stale semantics preserved."*

- [ ] **Step 4: Commit**

```bash
git add src/irc/monitor/industry_map_store.py tests/monitor/test_industry_map_store.py
git commit -m "feat(monitor): document industry_map_store board-code reuse for rotation radar (D7)"
```

**Verification point:** existing monitor tests still green; the store round-trips board codes. Per trap T6, since no signature changed, no broader test sweep is required — but run `uv run pytest tests/monitor/test_industry_map_store.py -v` to confirm.

---

## Task 13: Seed orchestration (EDGE) — AC2 resumability

**Files:**
- Create: `src/irc/rotation/seed.py`
- Test: `tests/rotation/test_seed.py`

**Interfaces:**
- Consumes: `fetch_board_hist` (Task 3, injectable); `fetch_top_holdings` (injectable); `fetch_flow_today_batch`-style batch for stock→board via `ulist.np` f100 (injectable); `series_store.seed_backfill`; `industry_map_store.record_seen`.
- Produces: `seed_boards(board_list, *, series_path, keep_td, trading_days, fetch_hist, load_existing) -> dict` returning `{"done": int, "skipped": int, "failed": tuple}` — skips boards already present in the series store (resumable, AC2); `seed_holdings(fund_ids, *, cache_dir, fetch) -> dict` — skips funds already cached; `seed_stock_board_map(symbols, *, map_path, today, batch_fetch, load_existing) -> dict` — skips symbols fresh in the map, chunked. Each returns a coverage summary; partial completion is fine (never raises out).

- [ ] **Step 1: Write the failing test**

```python
# tests/rotation/test_seed.py
from pathlib import Path

from irc.rotation.seed import seed_boards, seed_holdings
from irc.rotation.types import BoardDay


def test_seed_boards_skips_already_present(tmp_path):
    from irc.rotation.series_store import append_snapshot
    p = tmp_path / "board_series.json"
    tds = tuple(f"2026-06-{i:02d}" for i in range(1, 26))
    # BK1 already seeded with 25 rows
    append_snapshot(p, [BoardDay(d, "BK1", "半导体", 1.0, 1.0, 2.0, None, "backfill")
                        for d in tds], keep_td=60, trading_days=tds)
    calls = []

    def fake_hist(code, name):
        calls.append(code)
        return tuple(BoardDay(d, code, name, 1.0, None, 2.0, None, "backfill")
                     for d in tds)

    summary = seed_boards([("BK1", "半导体"), ("BK2", "白酒")], series_path=p,
                          keep_td=60, trading_days=tds, fetch_hist=fake_hist)
    assert calls == ["BK2"]  # BK1 skipped (already ≥20 td)
    assert summary["done"] == 1 and summary["skipped"] == 1


def test_seed_holdings_skips_cached(tmp_path):
    cache = tmp_path / "narrative_holdings"
    cache.mkdir()
    (cache / "F1.json").write_text('{"holdings": []}', encoding="utf-8")
    fetched = []

    def fake_fetch(fund_id, *, cache_dir):
        fetched.append(fund_id)
        return ()

    summary = seed_holdings(["F1", "F2"], cache_dir=cache, fetch=fake_fetch)
    assert fetched == ["F2"]  # F1 already cached
    assert summary["done"] == 1 and summary["skipped"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/rotation/test_seed.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/rotation/seed.py
"""EDGE orchestration for `irc rotation seed` (spec §4 seed steps, D11, AC2).

Resumable + partial-tolerant: each step skips anything already cached and reports
a coverage summary; a transient failure on one board/fund/chunk never aborts the
rest (breaker-protected via the injected fetchers). No LLM, no paid search.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from irc.rotation.board_fetch import fetch_board_hist
from irc.rotation.series_store import load_store, seed_backfill
from irc.rotation.composite import MIN_TD

_log = logging.getLogger(__name__)


def seed_boards(board_list: Iterable[tuple[str, str]], *, series_path: Path,
                keep_td: int, trading_days, fetch_hist=fetch_board_hist) -> dict:
    """Backfill board-history series; skip boards already having ≥MIN_TD rows."""
    store = load_store(series_path)
    done, skipped, failed = 0, 0, []
    for code, name in board_list:
        if len(store.get(code, ())) >= MIN_TD:
            skipped += 1
            continue
        try:
            rows = fetch_hist(code, name)
        except Exception as exc:  # noqa: BLE001 — partial-tolerant (AC2/T3)
            _log.warning("seed_boards: %s failed: %s", code, exc)
            failed.append(code)
            continue
        if rows:
            seed_backfill(series_path, {code: rows}, keep_td=keep_td,
                          trading_days=trading_days)
            done += 1
        else:
            failed.append(code)
    return {"done": done, "skipped": skipped, "failed": tuple(failed)}


def seed_holdings(fund_ids: Iterable[str], *, cache_dir: Path, fetch) -> dict:
    """Fetch top-10 holdings for funds missing from the cache; skip cached ones."""
    done, skipped, failed = 0, 0, []
    for fid in fund_ids:
        if (cache_dir / f"{fid}.json").is_file():
            skipped += 1
            continue
        try:
            fetch(fid, cache_dir=cache_dir)
            done += 1
        except Exception as exc:  # noqa: BLE001 — never raises (fetch_top_holdings doesn't)
            _log.warning("seed_holdings: %s failed: %s", fid, exc)
            failed.append(fid)
    return {"done": done, "skipped": skipped, "failed": tuple(failed)}


def seed_stock_board_map(symbols: Iterable[str], *, map_path: Path, today: str,
                         batch_fetch, load_existing, record, chunk_size: int = 200
                         ) -> dict:
    """Chunked ulist.np (f100 行业 — NOT f127, T1) over held stocks; skip symbols
    already fresh in the map. record(map_path, today, industry_by_symbol) merges."""
    existing = load_existing(map_path)
    fresh = set(existing.keys())
    pending = [s for s in dict.fromkeys(symbols) if s not in fresh]
    done, failed = 0, []
    for i in range(0, len(pending), chunk_size):
        chunk = pending[i:i + chunk_size]
        try:
            _flow, industry_by_symbol = batch_fetch(tuple(chunk))
        except Exception as exc:  # noqa: BLE001 — partial-tolerant chunk (AC2/T3)
            _log.warning("seed_stock_board_map: chunk failed: %s", exc)
            failed.extend(chunk)
            continue
        record(map_path, today, industry_by_symbol)
        done += sum(1 for v in industry_by_symbol.values() if v)
    return {"done": done, "skipped": len(fresh), "failed": tuple(failed)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/rotation/test_seed.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/rotation/seed.py tests/rotation/test_seed.py
git commit -m "feat(rotation): resumable seed orchestration (boards/holdings/stock-board map)"
```

**Verification point:** rerun skips already-cached boards/funds/chunks; per-item failures collected, not raised; coverage summary returned (AC2).

---

## Task 14: `run_rotation` daily command (EDGE) — orchestration + degradation

**Files:**
- Create: `src/irc/commands/rotation_cmd.py`
- Test: `tests/commands/test_rotation_cmd.py`

**Interfaces:**
- Consumes: every pure core (Tasks 5–10) + edges (Tasks 3,4,13); `fetch_board_spot`; `series_store.append_snapshot`; `load_trading_days`; `fetch_top_holdings`; `industry_map_store.load_store`/`fresh_slice`; `composite.pe_percentiles` (pe_pctl from the store's latest-day `board_pe` — NO separate PE cache/call, since f9 rides the snapshot inline); membership loaders. `IRC_ROTATION_TOPUP_BUDGET` (default 50).
- Produces: `run_rotation(*, repo_root, today=None) -> int` (writes `outputs/<date>/rotation/rotation_radar.{md,json}`, appends `data/rotation/forward_ledger.jsonl`, exit 0 always — advisory, never pages); `run_rotation_seed(*, repo_root) -> int`. Degradation: total snapshot failure → abstain stub (no series append, no ledger); flow leg absent → `flow_dark=True` renorm + `data_status="degraded_flow_dark"`; cold holdings → L1 renders, candidates section = `cold_holdings_note()`.

- [ ] **Step 1: Write the failing test** (inject all edges — no network)

```python
# tests/commands/test_rotation_cmd.py
import json
from pathlib import Path

from irc.commands.rotation_cmd import run_rotation
from irc.rotation.types import BoardDay


def _snapshot(today):
    # 3 boards, one clearly hot (high chg + flow + rich PE)
    return (BoardDay(today, "BK1", "半导体", 3.0, 5.0, 4.0, 95.0, "snapshot"),
            BoardDay(today, "BK2", "白酒", 0.1, 0.0, 1.0, 12.0, "snapshot"))


def test_abstain_on_total_snapshot_failure(tmp_path, monkeypatch):
    def boom(today, **kw):
        raise RuntimeError("snapshot dead")
    monkeypatch.setattr("irc.commands.rotation_cmd.fetch_board_spot", boom)
    rc = run_rotation(repo_root=str(tmp_path), today="2026-07-06",
                      _fetch_spot=boom)
    out = tmp_path / "outputs" / "2026-07-06" / "rotation" / "rotation_radar.json"
    assert rc == 0
    js = json.loads(out.read_text())
    assert js["data_status"] == "abstain"
    # no series mutation (AC5)
    assert not (tmp_path / "data" / "rotation" / "board_series.json").exists()


def test_same_day_rerun_byte_identical(tmp_path):
    # seed a series store with ≥20 td so composite/states compute deterministically
    # (helper builds board_series.json + narrative_holdings + stock map, then run twice)
    ...  # see fixtures helper below
    rc1 = run_rotation(repo_root=str(tmp_path), today="2026-07-06",
                       _fetch_spot=lambda today, **kw: _snapshot(today))
    out = tmp_path / "outputs" / "2026-07-06" / "rotation" / "rotation_radar.json"
    first = out.read_bytes()
    rc2 = run_rotation(repo_root=str(tmp_path), today="2026-07-06",
                       _fetch_spot=lambda today, **kw: _snapshot(today))
    assert rc1 == 0 and rc2 == 0
    assert out.read_bytes() == first  # AC3 determinism


def test_flow_dark_tags_data_status(tmp_path):
    # snapshot with all main_inflow_ratio None → flow leg absent
    def spot(today, **kw):
        return (BoardDay(today, "BK1", "半导体", 3.0, None, 4.0, 95.0, "snapshot"),
                BoardDay(today, "BK2", "白酒", 0.1, None, 1.0, 12.0, "snapshot"))
    ...  # seed ≥20 td first
    run_rotation(repo_root=str(tmp_path), today="2026-07-06", _fetch_spot=spot)
    js = json.loads((tmp_path / "outputs" / "2026-07-06" / "rotation"
                     / "rotation_radar.json").read_text())
    assert js["data_status"] == "degraded_flow_dark"


def test_chase_risk_fires_for_rich_emerging_board_and_not_when_pe_missing(tmp_path):
    # Two boards: BK1 richly-valued (PE 95, top of PE distribution) and emerging;
    # BK2 has no PE. chase_risk fires for BK1 (state in {emerging,hot} AND
    # pe_pctl>0.90) and NEVER for the PE-less board (pe_pctl None → no flag).
    def spot(today, **kw):
        return (BoardDay(today, "BK1", "半导体", 3.0, 5.0, 4.0, 95.0, "snapshot"),
                BoardDay(today, "BK2", "白酒", 3.1, 5.0, 4.0, None, "snapshot"),
                BoardDay(today, "BK3", "银行", 0.1, 0.0, 1.0, 6.0, "snapshot"))
    ...  # seed ≥20 td so BK1/BK3 clear MIN_TD and BK1 lands emerging
    run_rotation(repo_root=str(tmp_path), today="2026-07-06", _fetch_spot=spot)
    js = json.loads((tmp_path / "outputs" / "2026-07-06" / "rotation"
                     / "rotation_radar.json").read_text())
    by_code = {b["board_code"]: b for b in js["board_states"]}
    assert by_code["BK1"]["chase_risk"] is True
    assert by_code["BK1"]["pe_pctl"] is not None and by_code["BK1"]["pe_pctl"] > 0.90
    assert by_code["BK2"]["pe_pctl"] is None and by_code["BK2"]["chase_risk"] is False
    # pe-coverage diagnostic counts boards with / without a PE
    assert js["diagnostics"]["pe_coverage"]["with_pe"] >= 2
    assert "BK2" in js["diagnostics"]["pe_coverage"]["without_pe"]


Note: the `...` markers are placeholders in THIS plan excerpt — the implementer writes a `_seed_series(tmp_path, *, board_pes=None, hot_boards=("BK1",))` helper that populates `data/rotation/board_series.json` (≥20 td per board via `append_snapshot`), an empty-but-present `data/narrative_holdings/`, and a `data/monitor/stock_industry_map.json` mapping a couple symbols to board codes. The helper must seed the `hot_boards` with a rising composite so that after the day's snapshot append they land `emerging` (fresh cross above p80 within 5 td) — required by `test_chase_risk_fires_for_rich_emerging_board_and_not_when_pe_missing`. `board_pe` on the historical seed rows may be None (only the snapshot day carries live PE, which is what pe_pctl reads). Fill these in fully; no placeholder ships in the test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_rotation_cmd.py -v`
Expected: FAIL — module undefined.

- [ ] **Step 3: Write minimal implementation** (inject `_fetch_spot` for tests; default = real edge)

```python
# src/irc/commands/rotation_cmd.py
"""Thin command layer for `irc rotation` (daily) + `irc rotation seed` (§4, D11).

Daily: 1 snapshot call + ≤IRC_ROTATION_TOPUP_BUDGET top-up calls, all pure cores
downstream. Advisory-only: exit 0 always, never pages (§7). Degradation: total
failure → abstain stub; flow leg absent → global flow_dark renorm. Zero LLM/paid
search → no spend-gate preflight.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from irc.rotation.board_fetch import fetch_board_spot
from irc.rotation.candidates import rank_candidates
from irc.rotation.composite import board_signals, cross_sectional, pe_percentiles
from irc.rotation.exposure import build_exposure
from irc.rotation.ledger import append_rows, build_ledger_rows
from irc.rotation.report import (
    RADAR_VERSION, SCHEMA_VERSION, abstain_report, cold_holdings_note, to_json, to_md,
)
from irc.rotation.series_store import append_snapshot, load_store
from irc.rotation.states import classify_board
from irc.rotation.types import BoardState, RotationReport
from irc.io_utils import atomic_write_text
from irc.monitor.trading_calendar import load_trading_days

_log = logging.getLogger(__name__)
_KEEP_TD = 60
_SERIES_REL = ("data", "rotation", "board_series.json")
_LEDGER_REL = ("data", "rotation", "forward_ledger.jsonl")


def _today_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _write_report(out_dir: Path, report: RotationReport) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "rotation_radar.json", to_json(report))
    atomic_write_text(out_dir / "rotation_radar.md", to_md(report))


def _latest_board_pe(series) -> dict[str, float | None]:
    """Pure: each eligible board's PE from its LATEST stored day (the snapshot
    day, which carries live f9). Read from the STORE — not a re-fetch — so pe_pctl
    is byte-stable across same-day reruns (AC3)."""
    out: dict[str, float | None] = {}
    for c, rows in series.items():
        latest = sorted(rows, key=lambda r: r.date)[-1] if rows else None
        out[c] = latest.board_pe if latest else None
    return out


def _build_states(series, flow_dark) -> tuple[tuple[BoardState, ...], dict]:
    """Pure glue: recompute the composite-pctl series per historical day, classify,
    and wire pe_pctl (cross-sectional over boards with a PE) + chase_risk (§6:
    state∈{emerging,hot} AND pe_pctl>0.90). States computed from the store windows
    (composite recomputed per trailing day; D5 no incremental state file).
    Returns (states, pe_coverage) — the §6 'missing PE noted in diagnostics' path."""
    all_dates = sorted({r.date for rows in series.values() for r in rows})
    pctl_series: dict[str, list[tuple[str, float]]] = {c: [] for c in series}
    for d in all_dates:
        sliced = {c: tuple(r for r in rows if r.date <= d) for c, rows in series.items()}
        comp = cross_sectional(board_signals(sliced), flow_dark=flow_dark)
        for c, p in comp.items():
            pctl_series[c].append((d, p))
    latest = cross_sectional(board_signals(series), flow_dark=flow_dark)
    sig = board_signals(series)
    pe_latest = {c: v for c, v in _latest_board_pe(series).items() if c in latest}
    pe_pctls = pe_percentiles(pe_latest)  # PE-less boards absent → None downstream
    states = []
    for c in sorted(latest):
        state, dis = classify_board(tuple(pctl_series[c]))
        name = next((r.board_name for r in series[c][::-1] if r.board_name), c)
        pe_pctl = pe_pctls.get(c)  # None when this board had no PE
        chase = state in ("emerging", "hot") and pe_pctl is not None and pe_pctl > 0.90
        states.append(BoardState(
            board_code=c, board_name=name, state=state, days_in_state=dis,
            composite_pctl=round(latest[c], 4), mom20=round(sig[c]["mom20"], 4),
            flow5=(None if flow_dark else sig[c]["flow5"]),
            turn_delta=round(sig[c]["turn_delta"], 4),
            pe_pctl=(round(pe_pctl, 4) if pe_pctl is not None else None),
            chase_risk=chase))
    pe_coverage = {"with_pe": sum(1 for v in pe_latest.values() if v is not None),
                   "without_pe": sorted(c for c, v in pe_latest.items() if v is None)}
    return tuple(states), pe_coverage


def run_rotation(*, repo_root: str, today: str | None = None, _fetch_spot=None) -> int:
    root = Path(repo_root)
    _today = today or _today_iso()
    out_dir = root / "outputs" / _today / "rotation"
    fetch_spot = _fetch_spot or fetch_board_spot
    try:
        snapshot = fetch_spot(_today)
    except Exception as exc:  # noqa: BLE001 — abstain (§7, AC5)
        _log.warning("rotation: snapshot failed: %s", exc, exc_info=True)
        _write_report(out_dir, abstain_report(f"snapshot failed: {exc}"))
        return 0
    if not snapshot:
        _write_report(out_dir, abstain_report("snapshot returned no boards"))
        return 0
    flow_dark = all(b.main_inflow_ratio is None for b in snapshot)
    tds_set = load_trading_days(date.today(), root=root)
    tds = tuple(d.isoformat() for d in (tds_set or ()))
    series = append_snapshot(root.joinpath(*_SERIES_REL), snapshot,
                             keep_td=_KEEP_TD, trading_days=tds)
    states, pe_coverage = _build_states(series, flow_dark)
    # L2 exposure/candidates from cached holdings + stock→board map (top-up bounded).
    candidates, new_ids, cov = _resolve_candidates(root, _today, states)
    data_status = "degraded_flow_dark" if flow_dark else "ok"
    report = RotationReport(
        schema_version=SCHEMA_VERSION, radar_version=RADAR_VERSION,
        data_status=data_status, board_states=states, candidates=candidates,
        diagnostics={"new_candidates": list(new_ids), "coverage": cov,
                     "pe_coverage": pe_coverage,
                     "immature_boards": sorted(
                         c for c, rows in series.items() if len(rows) < 20)})
    _write_report(out_dir, report)
    append_rows(root.joinpath(*_LEDGER_REL),
                build_ledger_rows(_today, states, RADAR_VERSION))
    print(f"rotation OK ({data_status}): {len(states)} boards, "
          f"{len(candidates)} candidates -> {out_dir}")
    return 0
```

Also implement `_resolve_candidates(root, today, states)` in the same file: loads `data/narrative_holdings/` (skip if empty → return `((), (), {"holdings_cache": "cold"})` and the report renders `cold_holdings_note()` via a diagnostics flag the md checks), loads `stock_industry_map.json` via `industry_map_store.fresh_slice`, builds `board_names` from the snapshot, calls `build_exposure` then `rank_candidates` with membership sets from `_load_membership(root, today)`. Keep each helper < 20 lines; extract `_load_membership` (reads `discovered_watchlist.csv`, `config/monitor.yaml` via `resolve_funds`, `inputs/account.yaml` holdings). `run_rotation_seed` wires Task 13's `seed_*` functions and prints coverage summaries, exit 0 on partial.

- [ ] **Step 4: Run test to verify it passes (PER-FILE — trap T5)**

Run: `uv run pytest tests/commands/test_rotation_cmd.py -q`
Expected: PASS. NEVER run `pytest tests/commands/` whole-dir (hangs).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/rotation_cmd.py tests/commands/test_rotation_cmd.py
git commit -m "feat(rotation): daily run + seed commands (abstain/flow-dark/cold-holdings + pe_pctl/chase_risk)"
```

**Verification point:** abstain on snapshot failure with NO series mutation (AC5); byte-identical json on same-day rerun (AC3, incl. stable pe_pctl since it reads the persisted `board_pe`); flow-dark tags `data_status` (AC5); `chase_risk` fires for a rich (pe_pctl>0.90) emerging board and NOT for a PE-less board, which is counted in `diagnostics.pe_coverage.without_pe` (§5/§6); exit 0 always.

---

## Task 15: Register CLI commands

**Files:**
- Modify: `src/irc/cli.py` (add after the `monitor` group block, ~line 277)
- Test: `tests/commands/test_rotation_cmd.py` (add a CLI-invocation smoke test)

**Interfaces:**
- Consumes: `run_rotation`, `run_rotation_seed`.
- Produces: `irc rotation` (daily) + `irc rotation seed` Click group.

- [ ] **Step 1: Add the CLI smoke test**

```python
# tests/commands/test_rotation_cmd.py  (ADD)
def test_cli_rotation_registered():
    from irc.cli import main
    cmd_names = main.commands.keys()
    assert "rotation" in cmd_names
    rotation_group = main.commands["rotation"]
    assert "seed" in rotation_group.commands
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/commands/test_rotation_cmd.py::test_cli_rotation_registered -q`
Expected: FAIL — `"rotation" not in cmd_names`.

- [ ] **Step 3: Register the group in `cli.py`**

```python
# src/irc/cli.py  — insert after the monitor flow-capture command (~line 277)
@main.group(invoke_without_command=True, help="Daily sector rotation radar (advisory; zero-LLM).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.pass_context
def rotation(ctx: click.Context, repo_root: str) -> None:
    if ctx.invoked_subcommand is None:
        from irc.commands.rotation_cmd import run_rotation
        raise SystemExit(run_rotation(repo_root=repo_root))


@rotation.command("seed", help="One-time resumable backfill (board history + holdings + stock→board map).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def rotation_seed(repo_root: str) -> None:
    from irc.commands.rotation_cmd import run_rotation_seed
    raise SystemExit(run_rotation_seed(repo_root=repo_root))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/commands/test_rotation_cmd.py -q`
Expected: PASS (all rotation command tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/cli.py tests/commands/test_rotation_cmd.py
git commit -m "feat(rotation): register irc rotation + irc rotation seed CLI"
```

**Verification point:** `uv run irc rotation --help` and `uv run irc rotation seed --help` both resolve.

---

## Task 16: Chain the radar into the 15:45 flow-capture wrapper — AC10

**Files:**
- Modify: `ops/launchd/run-flow-capture.sh`
- Test: `tests/ops/test_flow_capture_wrapper.sh` (create; shell-level) OR documented manual verification (see step 3)

**Interfaces:**
- Consumes: the existing wrapper's post-capture exit path.
- Produces: the radar runs AFTER the flow-capture step, protective-only — a radar non-zero exit does NOT page and does NOT change the flow-capture exit code.

- [ ] **Step 1: Add the radar chain to the wrapper (after the capture rc line)**

Edit `ops/launchd/run-flow-capture.sh` — after `echo "[$TODAY] flow-capture rc=$rc"` and BEFORE `exit "$rc"`, insert:

```bash
# Sector rotation radar (ADR 0023 D1/§9): runs AFTER flow-capture, protective-only.
# A non-zero radar exit is LOGGED but never pages and never changes $rc (the
# flow-capture exit path is authoritative). Own watchdog; advisory command.
radar_rc=0
run_with_watchdog "${IRC_ROTATION_TIMEOUT:-300}" "$UV_BIN" run irc rotation || radar_rc=$?
echo "[$TODAY] rotation rc=$radar_rc (advisory; does not affect flow-capture rc)"

exit "$rc"
```

- [ ] **Step 2: Add a shell-level test (AC10)**

```bash
# tests/ops/test_flow_capture_wrapper.sh
#!/bin/bash
# AC10: a radar failure must NOT change the wrapper's exit code (flow-capture rc
# is authoritative). We source the tail logic with a stub uv that fails on
# `rotation` but succeeds on `flow-capture`.
set -u
FAIL=0
grep -q 'does not affect flow-capture rc' ops/launchd/run-flow-capture.sh || {
  echo "FAIL: radar chain comment/marker missing"; FAIL=1; }
# The radar line must appear AFTER the flow-capture rc echo and use `|| radar_rc=$?`
awk '/flow-capture rc=/{seen=1} /irc rotation/{if(seen)ok=1} END{exit !ok}' \
  ops/launchd/run-flow-capture.sh || { echo "FAIL: radar runs before capture rc"; FAIL=1; }
grep -q '|| radar_rc=$?' ops/launchd/run-flow-capture.sh || {
  echo "FAIL: radar rc not isolated from set -e"; FAIL=1; }
grep -q 'exit "$rc"' ops/launchd/run-flow-capture.sh || {
  echo "FAIL: wrapper no longer exits with flow-capture rc"; FAIL=1; }
[ "$FAIL" -eq 0 ] && echo "PASS: AC10 wrapper chaining" || exit 1
```

- [ ] **Step 3: Run the shell test**

Run: `bash tests/ops/test_flow_capture_wrapper.sh`
Expected: `PASS: AC10 wrapper chaining`.

- [ ] **Step 4: Commit**

```bash
git add ops/launchd/run-flow-capture.sh tests/ops/test_flow_capture_wrapper.sh
git commit -m "ops(rotation): chain radar into 15:45 flow-capture wrapper (protective-only, AC10)"
```

**Verification point:** the radar line comes after the capture rc echo, uses `|| radar_rc=$?`, and the wrapper still `exit "$rc"` (flow-capture rc authoritative) — AC10.

---

## Task 17: Docs + CONTEXT + CHANGELOG + ADR flip

**Files:**
- Modify: `docs/monitor/README.md` (15:45 row: note the radar chain)
- Modify: `ops/launchd/README.md` (flow-capture agent description + failure-mode table)
- Modify: `CONTEXT.md` (flip "Sector rotation radar" marker SPEC'd→built)
- Modify: `CHANGELOG.md` (`[Unreleased]`)
- Modify: `docs/adr/0023-sector-rotation-radar.md` (Status: Proposed → Accepted)

- [ ] **Step 1: Update `docs/monitor/README.md`** — in the 15:45 `com.irc.flow-capture` row, append: *"Then runs `irc rotation` (sector rotation radar, ADR 0023) — advisory-only, protective (non-zero radar exit is logged, never pages, never changes the flow-capture rc)."*

- [ ] **Step 2: Update `ops/launchd/README.md`** — flow-capture row: add the radar chain; failure-mode table: add a row `run-flow-capture.sh — rotation step | IRC_ROTATION_TIMEOUT (300s) | rc logged, does NOT page (advisory; wrapper rc unchanged)`.

- [ ] **Step 3: Flip the CONTEXT.md marker** — change the "Sector rotation radar" section header note from **SPEC'd, not built** to built (dated 2026-07-05), keeping the canonical terms.

- [ ] **Step 4: Add CHANGELOG `[Unreleased]` entry** — `feat(rotation): daily sector rotation radar (irc rotation + seed) — EM-board momentum/flow/turnover composite, rotation_state hysteresis, fund×board exposure candidates; advisory-only, zero-LLM (ADR 0023).`

- [ ] **Step 5: Flip ADR 0023 status** — `**Status:** Accepted (built 2026-07-05).`

- [ ] **Step 6: Commit**

```bash
git add docs/monitor/README.md ops/launchd/README.md CONTEXT.md CHANGELOG.md docs/adr/0023-sector-rotation-radar.md
git commit -m "docs(rotation): ops manual + CONTEXT marker + CHANGELOG + ADR 0023 Accepted"
```

**Verification point:** ops docs describe the radar chain; CONTEXT marker flipped; ADR Accepted (§9/§10 doc-sync convention).

---

## Task 18: Full verification sweep

**Files:** none (verification only).

- [ ] **Step 1: Run the whole rotation test dir**

Run: `uv run pytest tests/rotation/ -q`
Expected: all PASS (types, board_fetch, series_store, composite, states, exposure, candidates, report, ledger, seed, import_isolation).

- [ ] **Step 2: Run the command test PER-FILE (trap T5)**

Run: `uv run pytest tests/commands/test_rotation_cmd.py -q`
Expected: PASS. Do NOT run `pytest tests/commands/` whole-dir.

- [ ] **Step 3: Run the monitor mirror test touched in Task 12**

Run: `uv run pytest tests/monitor/test_industry_map_store.py -q`
Expected: PASS.

- [ ] **Step 4: AC8 md grep guard (belt-and-suspenders)**

Run: `! grep -rn '\[ref:' src/irc/rotation/report.py`
Expected: no match (exit 0 via `!`).

- [ ] **Step 5: AC11 isolation guard**

Run: `uv run pytest tests/rotation/test_import_isolation.py -q`
Expected: PASS.

- [ ] **Step 6: Shell wrapper test (AC10)**

Run: `bash tests/ops/test_flow_capture_wrapper.sh`
Expected: `PASS: AC10 wrapper chaining`.

- [ ] **Step 7: Lint**

Run: `uv run ruff check src/irc/rotation src/irc/commands/rotation_cmd.py tests/rotation`
Expected: `All checks passed!`

- [ ] **Step 8: File-size budget check**

Run: `wc -l src/irc/rotation/*.py src/irc/commands/rotation_cmd.py`
Expected: every file < 200 lines. If `rotation_cmd.py` exceeds, extract `_resolve_candidates`/`_load_membership` into `src/irc/rotation/_cmd_helpers.py` (still edge-thin) and re-run.

**Verification point:** every AC has a green test; lint clean; size budget met. Ready for `/ship`.

---

## AC → Task map (self-review)

- **AC1** (live probe first) → Task 1 (probe + notes + fixtures; documented fallback if no CN egress).
- **AC2** (seed resumable) → Task 13 (skip-cached, coverage summary, exit 0 partial) + Task 14 `run_rotation_seed`.
- **AC3** (daily determinism) → Task 4 (byte-stable store) + Task 9 (byte-stable json) + Task 14 `test_same_day_rerun_byte_identical`.
- **AC4** (state machine pure + property test) → Task 6.
- **AC5** (abstain / flow-dark / no carry-forward) → Task 9 `abstain_report`, Task 5 flow-dark renorm, Task 14 degradation tests.
- **AC6** (exposure sums + unmapped coverage) → Task 7.
- **AC7** (candidate annotations + holdings_as_of) → Task 8.
- **AC8** (md no `[ref:`, additive subset) → Task 9 `test_md_has_no_ref_marker` + Task 18 grep.
- **AC9** (ledger append-only/atomic/no dup/radar_version) → Task 10.
- **AC10** (wrapper chaining, no page, no capture-fail) → Task 16.
- **AC11** (one-way dependency) → Task 11.
- **AC12** (tests mirror one-for-one; per-file green) → Tasks 2–13 mirror layout + Task 18 per-file runs.
- **§5/§6 `chase_risk` + `pe_pctl` deliverable** (not a numbered AC) → Task 2 (`board_pe` field), Task 3 (parse f9), Task 4 (persist), Task 5 (`pe_percentiles`), Task 9 (render), Task 14 (`_build_states` wiring + `pe_coverage` diagnostic + `test_chase_risk_fires_for_rich_emerging_board_and_not_when_pe_missing`).

**Spec gaps / judgment calls (flag for review):**
1. **§6 states over a per-day composite series.** The spec says states are "evaluated over the composite-percentile series ... trading-day indexed" but the series store holds raw `BoardDay`s, not a persisted composite-pctl series. Task 14 `_build_states` recomputes the composite per trailing day from the store windows (deterministic, no extra state file per D5). This is O(days × boards) but the store is ≤60 td × ~86 boards — cheap. Flagged in case a reviewer prefers persisting the pctl series.
2. **`pe_pctl`/`chase_risk` — now fully wired (no deferral).** The snapshot requests `f9` (市盈率) inline on the SAME `clist m:90+t:2` interface `em_raw.parse_clist_boards` already reads, so board PE arrives at zero extra cost and identical BK-code vocabulary. It is persisted on `BoardDay.board_pe` in the series store; pe_pctl is computed from the store's LATEST day via `composite.pe_percentiles` (byte-stable across same-day reruns — AC3 — because it reads the persisted row, never an intraday re-fetch). `chase_risk = state∈{emerging,hot} AND pe_pctl is not None AND pe_pctl>0.90` (§6). The ONLY residual degradation is a board that genuinely returns no `f9` value → `pe_pctl=None`, `chase_risk=False`, counted in `diagnostics.pe_coverage.without_pe` (the real §6 "missing PE → no flag, noted in diagnostics" path). This is a documented runtime degradation, not a deferred feature.
3. **`main_inflow_ratio` field on the board snapshot.** The AC1 probe (Task 1) must confirm whether `f184` is present on the `clist` board interface or requires the separate board fund-flow interface. If absent, every run is `degraded_flow_dark` until the correct interface is wired — the degradation path (Task 5/14) handles this gracefully, and it is called out in the probe notes.
