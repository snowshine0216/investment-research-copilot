# Monitor CN-egress data-plane light-up — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Light up the three degraded monitor data legs (flow, industry-valuation, per-stock PE/PB) by routing the EastMoney data plane through `IRC_CN_PROXY`, un-shelving the B2 batch-first flow (one `ulist.np` call/run into a persisted daily series + a 15:45 capture job), and re-transporting the industry leg on raw EastMoney JSON — all with `_ENGINE_VERSION` untouched.

**Architecture:** A single `proxy_env()` context manager + `resolve_cn_proxy()` in `src/irc/http_proxy.py` becomes the one source of truth for CN-egress. New raw-JSON fetchers (`em_raw.py`) slot into the existing injectable `fetch` hooks of `industry_valuation` and per-stock valuation without touching their pure parsers or 3-outcome caches. Flow moves from ~30 per-symbol calls to one `ulist.np` batch (`flow_batch_fetch.py`) accumulated in a completed-day-only series store (`flow_series_store.py`); `monitor_cmd` consumes the store; a new `irc monitor flow-capture` launchd job appends the post-close final value. Effects stay at edges; parsers stay pure; one eval-trace `_SCHEMA_VERSION` bump.

**Tech Stack:** Python 3.12, uv, Click, DuckDB, pandas, akshare (fund plane only), raw `urllib`/`requests` EastMoney JSON (data plane), pytest, launchd/bash.

## Global Constraints

- **TDD.** Red → green → refactor. Failing test first for every behavior. Test file mirrors source (`foo.py` → `tests/.../test_foo.py`).
- **Functional, immutable.** Pure functions; `const`-by-default; never mutate arguments; frozen dataclasses + `dataclasses.replace` / `{**d}` spreads; no shared mutable module state; pass deps through signatures.
- **Effects at edges.** I/O (filesystem, network, akshare, LLM) only in thin wrappers and the `commands/` layer. Stage cores pure and unit-testable without mocks.
- **Size budget.** Files < 200 lines, functions < 20 lines (ideal). Extract helpers rather than nest > 3 levels.
- **Secrets in `.env` only.** YAML/code reference env var names; never inline keys.
- **NO VERSION bump.** Accumulate under CHANGELOG `[Unreleased]` at the static VERSION; `/ship` owns CHANGELOG/VERSION later. This plan writes a `[Unreleased]` CHANGELOG entry (Task 15) but never touches VERSION.
- **`_ENGINE_VERSION` in `src/irc/commands/monitor_cmd.py` MUST remain `"3"`** (D4/D5). Any change is a plan bug.
- **Exactly ONE eval-trace `_SCHEMA_VERSION` bump** (`"4"` → `"5"`, Task 14, D9). No other schema bump.
- **`tests/monitor/test_industry_valuation.py` stays green UNTOUCHED** except ADDING one new default-fetch identity test (contract-preservation proof, spec §6). Do not edit or delete any existing test in that file.
- **`pytest tests/commands/` whole-dir HANGS** — every verification command for that dir MUST be per-file.
- **`em_raw.py` parses raw EastMoney JSON itself — NO akshare wrappers for the industry leg.** Any akshare re-introduction there is a regression. Fixtures MUST include the `dlmkts`/`dsc` drift keys, `data:null`, and missing-`f127` cases (spec slice 2 / F4 / F5).
- **`fetch_industry_pe` must NOT cache an empty parse** (`{}` returned but NOT written — D3).
- **The flow store append API accepts only COMPLETED days.** The 12:15 brief path has NO write access to the store; provisional (pre-close) `f184` is render-only annotation, never persisted (D6, trap §8).
- **Fund plane stays DIRECT** (`fund_purchase_em` heat, NAV history) — never routed through `IRC_CN_PROXY` (D2).
- **Live EastMoney probes: python `requests`/`urllib` only** (curl false-fails through the proxy — F3). **Breaker stop-after-5 on EVERY path including the D7 seed helper. Never retry an EastMoney endpoint while a block is active** (ADR 0019, trap §8).

---

## Slice-0 branch decision (recorded per orchestrator directive)

**Chosen branch: GATE-1 live-now (already executed during plan authoring) + GATE-2 4dp equivalence DEFERRED-DOCUMENTED as a post-merge ops step.**

Rationale and evidence:

- **GATE-1 (reachability) — PASS, executed live 2026-07-02 ~12:05 CST during plan authoring.** All three raw transports verified from the monitor host:
  - `ulist.np` `f184` batch → `000651=7.42, 600519=4.86, 600690=5.4` (3/3 numeric, one call).
  - `clist/get` `fs=m:90+t:2 fields=f12,f14,f9` board PE **through `IRC_CN_PROXY`** → 100 boards page 1, sane values (航空机场 30.45, 铁路公路 15.73, 电力 19.68, 水泥 98.47) — the **D4 f9 range-sanity check** (plausible CN sector PEs; matches EastMoney web UI ranges).
  - `stock/get` `secid=1.600690 fields=f57,f58,f127` **through `IRC_CN_PROXY`** → `600690 海尔智家 → 白色家电` (exactly spec F1).
- **GATE-2 (4dp same-day `f184 ≈ daykline.净占比` equivalence) — CANNOT complete this session.** It requires a post-close (≥15:15 CST) `f184` capture compared against the *same completed day's* daykline row (a next-day / same-evening diff). Plan authoring is at ~12:05 CST (before close). Per the orchestrator directive this is made an **EXPLICIT post-merge ops step** (Task 15 README ops row + Task 15 "Tier-0 findings" spec appendix with status **OPEN** and the D-B3 engine-bump escalation path spelled out). If the *implementation* session reaches post-close it MAY attempt the same-evening equivalence run via the Task 1 spike extension and record the result into the appendix; otherwise it stays OPEN. Shipping the multi-day portion deferred-but-documented is acceptable per the directive; silently dropping it is not.
- The D-B3 no-engine-bump claim therefore **remains gated on GATE-2**. Until GATE-2 passes post-merge, the code ships with `_ENGINE_VERSION="3"` unchanged (the leg never emitted a value → data-availability-returning class, ADR 0019/0020 addenda), and the appendix documents: *if GATE-2 shows a material (>4dp) gap → escalate to an `_ENGINE_VERSION` bump + ADR 0019 addendum before trusting the flow factor's forward metrics.*

## Judgment calls made (no user in loop, per AUTONOMY OVERRIDE)

1. **Proxy value format in `.env` is bare `host:port`** (verified: `IRC_CN_PROXY=<host>:<port>`, IP-whitelist auth, no scheme, no credentials). `resolve_cn_proxy()` normalizes bare `host:port` → `http://host:port` (spec D1). (spec §3 D1)
2. **`IRC_CN_PROXY_MODE` default is `on` when the URL is present** (spec §9.3 / D1). Unset URL → `None` regardless of mode. `mode=off` → `None` even when URL present.
3. **`clist/get` board fetch uses `fs=m:90+t:2` fields `f12,f14,f9`** and maps `f14`→`板块名称`, `f9`→`市盈率` so the existing pure `parse_industry_pe` consumes it unchanged (spec F6; verified live). Pagination stops when a page returns `< pz` rows or the running board set stops growing, capped at ≤10 pages with the existing 0.3s pacing (D3).
4. **`stock/get` stock→industry uses `secid` built via `flow_fetch._market_of`-style prefix** (`6*`→`1.`, `0*/3*`→`0.`, `8*/4*`→`0.`) fields `f57,f58,f127`, mapped into the existing `(item,value)` frame shape (`item="行业"`, `value=f127`) so `parse_stock_industry`/`_is_blank_info_frame`/3-outcome are unchanged (D3).
5. **`flow_source` marker values** are `"batch_today"` | `"per_symbol_seed"` (spec D9). Stored on the eval trace `holding_metrics` block; `per_symbol_seed` denotes a row whose series came from the D7 daykline seed rather than a live `ulist.np` append.
6. **`f184` sign/units**: percent-points, NO `/100` (matches `flow_fetch._coerce` and B2 §5.B). `parse_ulist` returns `{f12 → f184}` percent-points.

---

## File Structure (created / modified)

**Create:**
- `src/irc/monitor/em_raw.py` — raw EastMoney JSON fetchers (board PE, stock→industry) as injectable `fetch` hooks. Pure parsers + edge fetchers with injected `http_get`.
- `src/irc/monitor/flow_batch_fetch.py` — `ulist.np` batch edge + pure `parse_ulist` + secid build (B2 §5.B).
- `src/irc/monitor/flow_series_store.py` — persisted completed-day-only daily series store + D7 seed helpers (B2 §5.C).
- `tests/test_http_proxy.py` — proxy resolution + `proxy_env` context manager.
- `tests/monitor/test_em_raw.py` — raw parsers + edge fetchers (incl. drift-key fixtures).
- `tests/monitor/test_flow_batch_fetch.py` — parse_ulist boundaries + batch edge 3-outcome.
- `tests/monitor/test_flow_series_store.py` — append/prune/idempotency/corrupt-degrade + seed.
- `ops/launchd/run-flow-capture.sh` — 15:45 capture wrapper.
- `ops/launchd/com.irc.flow-capture.plist` — 15:45 launchd job.

**Modify:**
- `src/irc/http_proxy.py` — add `resolve_cn_proxy()` + `proxy_env()` (single source of truth).
- `src/irc/data/akshare_client.py` — dedupe `_proxy_env` to import the shared `proxy_env`.
- `src/irc/monitor/industry_valuation.py` — default-fetch swap to em_raw; empty-parse-not-cached.
- `src/irc/fundamentals/akshare_stock_valuation.py` — wrap `_fetch_frame` in `proxy_env` when enabled.
- `src/irc/commands/monitor_cmd.py` — store-consumption swap (D10); provisional annotation; `run_flow_capture`.
- `src/irc/cli.py` — `irc monitor flow-capture` subcommand.
- `src/irc/monitor/eval/trace.py` — `_SCHEMA_VERSION` `"4"`→`"5"`; `flow_source` marker in holding_metrics block.
- `src/irc/monitor/eval/structural.py` — warm-up (rows-per-symbol) curve + `flow_source` in `flow_coverage_health`.
- `scripts/phase0_flow_batch_spike.py` — `IRC_CN_PROXY` support.
- `ops/launchd/install.sh` — template + bootstrap the flow-capture job.
- `tests/monitor/test_industry_valuation.py` — ADD one default-fetch identity test only.
- `tests/monitor/eval/test_trace.py` — schema `"4"`→`"5"` assert.
- `tests/commands/test_monitor_cmd_drilldown.py` / `test_monitor_cmd_valuation.py` — store-fed path.
- `tests/ops/test_launchd_monitor.py` — flow-capture plist/wrapper assertions.
- `tests/monitor/eval/test_structural.py` — warm-up + flow_source coverage assertions.
- `CONTEXT.md`, `docs/adr/0019-*.md`, `docs/adr/0020-*.md`, `README.md`, `CHANGELOG.md`, the design spec — docs.

---

# Slice 0 — Spike re-run (gate for slices 3–5)

### Task 1: Extend `phase0_flow_batch_spike.py` with `IRC_CN_PROXY` support

**Files:**
- Modify: `scripts/phase0_flow_batch_spike.py`
- Test: `tests/scripts/test_phase0_flow_batch_spike.py` (create)

**Interfaces:**
- Produces: `_resolve_cn_proxy_for_spike() -> str | None` (bare-host:port normalization); an `_opener(proxy)` that injects the proxy into `urllib` when set. `capture(...)` / `equiv(...)` gain a `proxy: str | None` param threaded from a new `--use-cn-proxy` flag (default: read `IRC_CN_PROXY` from env / `.env`).

- [ ] **Step 1: Write the failing test for the spike's pure proxy normalizer**

Create `tests/scripts/test_phase0_flow_batch_spike.py`:

```python
from __future__ import annotations

from scripts.phase0_flow_batch_spike import _normalize_proxy, _parse_ulist


def test_normalize_bare_host_port_gets_http_scheme():
    assert _normalize_proxy("42.51.40.10:16816") == "http://42.51.40.10:16816"


def test_normalize_already_schemed_is_unchanged():
    assert _normalize_proxy("http://h:1") == "http://h:1"


def test_normalize_blank_is_none():
    assert _normalize_proxy("") is None
    assert _normalize_proxy("   ") is None
    assert _normalize_proxy(None) is None


def test_parse_ulist_still_extracts_f12_to_f184():
    payload = {"data": {"diff": [{"f12": "600519", "f184": 4.86}]}}
    assert _parse_ulist(payload) == {"600519": 4.86}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/scripts/test_phase0_flow_batch_spike.py -v`
Expected: FAIL — `ImportError: cannot import name '_normalize_proxy'`.

- [ ] **Step 3: Add `_normalize_proxy` + proxy-aware opener to the spike**

In `scripts/phase0_flow_batch_spike.py`, add after `_coerce` (pure section):

```python
def _normalize_proxy(raw: object) -> str | None:
    """Bare host:port or URL → http://host:port, or None for blank/unset."""
    text = (str(raw).strip() if raw is not None else "")
    if not text:
        return None
    return text if "://" in text else "http://" + text
```

Add a proxy-aware opener helper near the network section:

```python
def _opener(proxy: str | None):
    """urllib opener that routes through the CN proxy when set, else direct."""
    if proxy is None:
        return urllib.request.build_opener()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
```

Thread `proxy` into `capture(...)` and `equiv(...)`: change their signatures to
`def capture(symbols, out_path, *, proxy=None) -> int:` and
`def equiv(prior_path, n, *, proxy=None) -> int:`, and replace the raw
`urllib.request.urlopen(req, ...)` call in `capture` with
`_opener(proxy).open(req, timeout=20)`. In `equiv`, when `proxy` is set, wrap the
akshare `stock_individual_fund_flow` call in the shared `proxy_env` (import lazily:
`from irc.http_proxy import proxy_env`) — but keep the single-call / abort-on-block
posture (never retry). Record `proxy_used = proxy is not None` in the GATE-1 record dict.

- [ ] **Step 4: Add the `--use-cn-proxy` CLI wiring in `main()`**

In `main()`, add:

```python
    ap.add_argument("--use-cn-proxy", action="store_true",
                    help="route EastMoney through IRC_CN_PROXY (.env / env)")
```

and resolve the proxy after `args = ap.parse_args()`:

```python
    import os
    proxy = None
    if args.use_cn_proxy:
        raw = os.environ.get("IRC_CN_PROXY", "")
        if not raw and Path(".env").is_file():
            for ln in Path(".env").read_text(encoding="utf-8").splitlines():
                if ln.startswith("IRC_CN_PROXY="):
                    raw = ln.split("=", 1)[1].strip()
                    break
        proxy = _normalize_proxy(raw)
        if proxy is None:
            print("--use-cn-proxy set but IRC_CN_PROXY is empty/unset"); return 2
```

Pass `proxy=proxy` to `equiv(...)` and `capture(...)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/scripts/test_phase0_flow_batch_spike.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/phase0_flow_batch_spike.py tests/scripts/test_phase0_flow_batch_spike.py
git commit -m "feat(monitor): phase0 spike gains IRC_CN_PROXY support (slice 0)"
```

### Task 2: GATE-1 live reachability + D4 f9 range-sanity (single live execution)

> **Orchestrator amendment (2026-07-02):** executed AFTER Task 3 — the spike's `--use-cn-proxy` path lazily imports `irc.http_proxy.proxy_env`, which Task 3 delivers. Pure execution-order swap; no content change.

**Files:** none (execution + evidence capture only).

- [ ] **Step 1: Run GATE-1 through the proxy (small volume, breaker/abort-on-block, runnable at any hour)**

Run (from the monitor host, single clean call, never retry):

```bash
uv run python -m scripts.phase0_flow_batch_spike --use-cn-proxy \
  --symbols 000651,600519,600690 \
  --out data/monitor/phase0_flow_spike/$(TZ=Asia/Shanghai date +%Y-%m-%d).json
```

Expected: `rc ok, rows=3  numeric f184=3/3  missing(no row)=[]` and three numeric `f184` values printed. (If it FAILS with a connection drop: DO NOT retry — record the failure and follow the Slice-0 deferral rule below.)

- [ ] **Step 2: D4 f9 board-PE range sanity through the proxy (one call)**

Run:

```bash
uv run python -c "
import json,os,urllib.parse,urllib.request
raw=os.environ.get('IRC_CN_PROXY','') or [l for l in open('.env') if l.startswith('IRC_CN_PROXY=')][0].split('=',1)[1].strip()
p='http://'+raw if '://' not in raw else raw
o=urllib.request.build_opener(urllib.request.ProxyHandler({'http':p,'https':p}))
q={'ut':'fa5fd1943c7b386f172d6893dbfba10b','fltt':'2','invt':'2','np':'1','pz':'100','pn':'1','po':'1','fs':'m:90+t:2','fields':'f12,f14,f9'}
u='https://push2.eastmoney.com/api/qt/clist/get?'+urllib.parse.urlencode(q)
r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
d=json.loads(o.open(r,timeout=20).read()); rows=(d.get('data') or {}).get('diff') or []
rows=list(rows.values()) if isinstance(rows,dict) else rows
print('boards',len(rows)); [print(x.get('f14'),x.get('f9')) for x in rows[:6]]
"
```

Expected: 100 boards, plausible CN sector PEs (e.g. 电力 ~15–25, 白酒/水泥 higher). Hand-check ~3 boards against the EastMoney web UI industry-board list; record in the spec appendix (Task 15).

- [ ] **Step 3: Record GATE-1 outcome**

If both steps passed: note "GATE-1 PASS + D4 sanity OK via proxy, <date> <time> CST" for the Task-15 spec appendix. If either failed (network/permission): record the failure verbatim and mark GATE-1 **DEFERRED** in the appendix (do NOT fake) — the same explicit-deferral rule as GATE-2. (Authoring-session evidence already shows PASS at 12:05 CST; the implementation session re-confirms through the proxy.)

*(GATE-2 4dp equivalence is deferred-documented — see the Slice-0 branch decision above and Task 15.)*

---

# Slice 1 — `http_proxy` (CN egress single source of truth)

### Task 3: `resolve_cn_proxy()` + `proxy_env()` in `http_proxy.py`; dedupe akshare_client

**Files:**
- Modify: `src/irc/http_proxy.py`
- Modify: `src/irc/data/akshare_client.py`
- Test: `tests/test_http_proxy.py` (create)

**Interfaces:**
- Produces: `resolve_cn_proxy() -> str | None`; `proxy_env(proxy_url: str) -> ContextManager[None]` (temporarily sets `HTTP_PROXY`/`HTTPS_PROXY`/lower-case, restores on exit).
- Consumes: `akshare_client._proxy_env` becomes `from irc.http_proxy import proxy_env as _proxy_env`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_http_proxy.py`:

```python
from __future__ import annotations

import os

import pytest

from irc.http_proxy import proxy_env, resolve_cn_proxy

_URL = "IRC_CN_PROXY"
_MODE = "IRC_CN_PROXY_MODE"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(_URL, raising=False)
    monkeypatch.delenv(_MODE, raising=False)


def test_unset_is_none():
    assert resolve_cn_proxy() is None


def test_bare_host_port_gets_http_scheme(monkeypatch):
    monkeypatch.setenv(_URL, "42.51.40.10:16816")
    assert resolve_cn_proxy() == "http://42.51.40.10:16816"


def test_already_schemed_url_unchanged(monkeypatch):
    monkeypatch.setenv(_URL, "http://h:1")
    assert resolve_cn_proxy() == "http://h:1"


def test_blank_is_none(monkeypatch):
    monkeypatch.setenv(_URL, "   ")
    assert resolve_cn_proxy() is None


def test_mode_off_disables_even_when_url_present(monkeypatch):
    monkeypatch.setenv(_URL, "h:1")
    monkeypatch.setenv(_MODE, "off")
    assert resolve_cn_proxy() is None


def test_mode_on_is_default(monkeypatch):
    monkeypatch.setenv(_URL, "h:1")
    assert resolve_cn_proxy() == "http://h:1"


def test_proxy_env_sets_and_restores(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "orig")
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    with proxy_env("http://p:9"):
        assert os.environ["HTTP_PROXY"] == "http://p:9"
        assert os.environ["HTTPS_PROXY"] == "http://p:9"
        assert os.environ["http_proxy"] == "http://p:9"
    assert os.environ["HTTPS_PROXY"] == "orig"       # restored
    assert "HTTP_PROXY" not in os.environ            # restored to absent
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_http_proxy.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_cn_proxy'`.

- [ ] **Step 3: Implement in `src/irc/http_proxy.py`**

Append to `src/irc/http_proxy.py` (after `resolve_proxy`):

```python
import contextlib
from typing import Generator

_CN_ENV_VAR = "IRC_CN_PROXY"
_CN_MODE_VAR = "IRC_CN_PROXY_MODE"


def resolve_cn_proxy() -> str | None:
    """CN-egress proxy for the EastMoney data plane, or None.

    Opposite direction from ``resolve_proxy`` (IRC_HTTPS_PROXY routes non-CN
    destinations); the two never mix. Accepts a URL or a bare ``host:port``
    (normalized to ``http://host:port``). ``IRC_CN_PROXY_MODE=off`` disables
    even when the URL is set; default mode is ``on`` when the URL is present.
    """
    if os.environ.get(_CN_MODE_VAR, "on").strip().lower() == "off":
        return None
    raw = os.environ.get(_CN_ENV_VAR, "").strip()
    if not raw:
        return None
    return raw if "://" in raw else "http://" + raw


@contextlib.contextmanager
def proxy_env(proxy_url: str) -> Generator[None, None, None]:
    """Temporarily inject HTTP/HTTPS proxy env vars so requests-based libs
    (akshare, urllib) route through the proxy. Restores originals on exit.
    Single source of truth (was duplicated in akshare_client._proxy_env)."""
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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_http_proxy.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Dedupe `akshare_client._proxy_env` to the shared impl**

In `src/irc/data/akshare_client.py`: replace the local `_proxy_env` definition
(the `@contextlib.contextmanager def _proxy_env(...)` block, ~lines 37–52) with:

```python
from irc.http_proxy import proxy_env as _proxy_env  # single source of truth
```

Place the import alongside the existing `from irc.http_proxy import resolve_proxy`.
Delete the now-unused local `_proxy_env` function body (the `keys = (...)` block).
Leave `_AKSHARE_PROXY_LOCK` and the `_fetch_dxy_via_akshare` call sites unchanged
(they still call `_proxy_env(proxy_url)` — now the imported name).

- [ ] **Step 6: Run the akshare_client + dxy tests to prove no regression**

Run: `uv run pytest tests/data/ -k "akshare or dxy or proxy" -v` (per-file if the `-k` set is empty: `uv run pytest tests/data/test_akshare_client.py -v` if it exists).
Expected: all PASS (the DXY proxy path still resolves through the shared context manager).

- [ ] **Step 7: Commit**

```bash
git add src/irc/http_proxy.py src/irc/data/akshare_client.py tests/test_http_proxy.py
git commit -m "feat(monitor): resolve_cn_proxy + proxy_env single source of truth (slice 1)"
```

---

# Slice 2 — Industry light-up (raw EastMoney JSON, contract-preserving)

### Task 4: `em_raw.py` pure parsers (`parse_clist_boards`, `parse_stock_info`)

**Files:**
- Create: `src/irc/monitor/em_raw.py`
- Test: `tests/monitor/test_em_raw.py` (create)

**Interfaces:**
- Produces:
  - `parse_clist_boards(payload: dict) -> pd.DataFrame` — a frame with columns `板块名称` (from `f14`) + `市盈率` (from `f9`) so the existing `parse_industry_pe` consumes it unchanged.
  - `parse_stock_info(payload: dict) -> pd.DataFrame` — an `(item, value)` frame with one `行业` row (from `f127`) so the existing `parse_stock_industry`/`_is_blank_info_frame` consume it unchanged; a `data:null` or missing-`f127` payload → an empty-shaped frame that the existing 3-outcome treats correctly (blank → transient; well-formed-no-行业 → dead).

- [ ] **Step 1: Write failing tests (incl. drift-key + data:null + missing-f127 fixtures)**

Create `tests/monitor/test_em_raw.py`:

```python
from __future__ import annotations

import pandas as pd

from irc.monitor.em_raw import parse_clist_boards, parse_stock_info


def test_parse_clist_boards_maps_f14_and_f9():
    payload = {"data": {"diff": [
        {"f12": "BK0428", "f14": "电力", "f9": 19.68},
        {"f12": "BK0433", "f14": "农林牧渔", "f9": 76.9},
    ]}}
    df = parse_clist_boards(payload)
    assert list(df.columns) == ["板块名称", "市盈率"]
    assert set(df["板块名称"]) == {"电力", "农林牧渔"}
    assert df.set_index("板块名称").loc["电力", "市盈率"] == 19.68


def test_parse_clist_boards_tolerates_dict_diff_shape():
    payload = {"data": {"diff": {"0": {"f14": "电力", "f9": 19.68}}}}
    df = parse_clist_boards(payload)
    assert df.set_index("板块名称").loc["电力", "市盈率"] == 19.68


def test_parse_clist_boards_data_null_is_empty_frame():
    # F4/F5 drift signature: {"data": null}
    df = parse_clist_boards({"data": None})
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_parse_stock_info_reads_f127_industry_with_drift_keys():
    # EastMoney added dlmkts/dsc top-level keys (F5). The raw parser must ignore them.
    payload = {"dlmkts": "x", "dsc": "y",
               "data": {"f57": "600690", "f58": "海尔智家", "f127": "白色家电"}}
    df = parse_stock_info(payload)
    assert set(df.columns) == {"item", "value"}
    row = df[df["item"] == "行业"]
    assert row["value"].iloc[0] == "白色家电"


def test_parse_stock_info_missing_f127_is_wellformed_without_industry_row():
    # well-formed data, no 行业 → DEAD path preserved (item/value cols present, no 行业)
    payload = {"data": {"f57": "600690", "f58": "海尔智家", "f127": None}}
    df = parse_stock_info(payload)
    assert set(df.columns) == {"item", "value"}
    assert (df["item"] == "行业").sum() == 0


def test_parse_stock_info_data_null_is_blank_frame():
    # F5 drift / throttle: {"data": null} → blank frame → TRANSIENT upstream
    df = parse_stock_info({"dlmkts": "x", "data": None})
    assert isinstance(df, pd.DataFrame)
    assert df.empty
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_em_raw.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the pure parsers**

Create `src/irc/monitor/em_raw.py`:

```python
"""EDGE + pure parse: RAW EastMoney JSON fetchers for the monitor industry leg.

Slotted into the existing injectable `fetch` params of industry_valuation
(fetch_board_pe_frame → fetch_industry_pe; fetch_stock_info_frame →
fetch_stock_industry_map) so the pure parsers / per-day 3-outcome caches are
UNCHANGED. em_raw owns its raw-JSON parsing — NO akshare wrappers here — so
upstream response-shape drift (F4 missing 市盈率 column, F5 dlmkts/dsc keys)
can't recur silently. Routed through IRC_CN_PROXY at the edge (D2). Uses python
requests (curl false-fails through the proxy — F3)."""
from __future__ import annotations

import logging
from typing import Callable

import pandas as pd

from irc.http_proxy import proxy_env, resolve_cn_proxy

_log = logging.getLogger(__name__)

_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_STOCK_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_PZ = 100
_MAX_PAGES = 10


def _diff_rows(payload: dict) -> list[dict]:
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
    emitted iff f127 is truthy. data:null / non-dict → empty frame (→ TRANSIENT).
    A well-formed data with no f127 → item/value frame WITHOUT a 行业 row (→ DEAD),
    preserving the existing 3-outcome contract. Ignores dlmkts/dsc drift keys."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return pd.DataFrame()
    items: list[tuple[str, object]] = [("代码", data.get("f57")), ("名称", data.get("f58"))]
    if data.get("f127"):
        items.append(("行业", data.get("f127")))
    return pd.DataFrame({"item": [i for i, _ in items], "value": [v for _, v in items]})
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/monitor/test_em_raw.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/em_raw.py tests/monitor/test_em_raw.py
git commit -m "feat(monitor): em_raw pure parsers for raw EastMoney board/stock JSON (slice 2)"
```

### Task 5: `em_raw` edge fetchers (`fetch_board_pe_frame`, `fetch_stock_info_frame`) with injected `http_get`, proxy, pagination-stop

**Files:**
- Modify: `src/irc/monitor/em_raw.py`
- Test: `tests/monitor/test_em_raw.py`

**Interfaces:**
- Produces:
  - `fetch_board_pe_frame(*, http_get: Callable[..., dict] | None = None) -> pd.DataFrame` — paginated `clist/get` (pz=100, ≤10 pages, 0.3s pacing via injected `sleep`), returns the concatenated `板块名称`/`市盈率` frame. Stops when a page returns `< pz` rows.
  - `fetch_stock_info_frame(symbol: str, *, http_get: Callable[..., dict] | None = None) -> pd.DataFrame` — one `stock/get` call, returns the `(item,value)` frame. `secid` via `_secid`.
  - `_secid(symbol) -> str` (`6*`→`1.`, else `0.`).
  - Default `http_get` records `proxies=` when the CN proxy is set.

- [ ] **Step 1: Write failing tests (pagination stop; injected http_get records proxies)**

Append to `tests/monitor/test_em_raw.py`:

```python
from irc.monitor.em_raw import (  # noqa: E402
    _secid, fetch_board_pe_frame, fetch_stock_info_frame,
)


def test_secid_prefixes():
    assert _secid("600519") == "1.600519"
    assert _secid("000651") == "0.000651"
    assert _secid("300750") == "0.300750"


def test_fetch_board_pe_frame_paginates_and_stops_on_short_page():
    pages: list[dict] = []

    def http_get(url, *, params, headers, timeout):
        pn = int(params["pn"])
        pages.append(url)
        if pn == 1:
            return {"data": {"diff": [{"f14": f"B{i}", "f9": 10.0 + i}
                                      for i in range(100)]}}
        return {"data": {"diff": [{"f14": "LAST", "f9": 5.0}]}}  # short page → stop

    df = fetch_board_pe_frame(http_get=http_get, sleep=lambda _s: None)
    assert len(pages) == 2  # page 1 full (100) → page 2 short → stop
    assert "LAST" in set(df["板块名称"])
    assert len(df) == 101


def test_fetch_board_pe_frame_caps_at_max_pages():
    def http_get(url, *, params, headers, timeout):
        return {"data": {"diff": [{"f14": f"B{params['pn']}_{i}", "f9": 1.0}
                                   for i in range(100)]}}  # always full → never stops

    df = fetch_board_pe_frame(http_get=http_get, sleep=lambda _s: None)
    assert len(df) == 100 * 10  # capped at _MAX_PAGES


def test_fetch_stock_info_frame_one_call_records_proxy(monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "1.2.3.4:9")
    captured = {}

    def http_get(url, *, params, headers, timeout, proxies=None):
        captured["secid"] = params["secid"]
        captured["proxies"] = proxies
        return {"data": {"f57": "600690", "f58": "海尔智家", "f127": "白色家电"}}

    df = fetch_stock_info_frame("600690", http_get=http_get)
    assert captured["secid"] == "1.600690"
    assert captured["proxies"] == {"http": "http://1.2.3.4:9", "https": "http://1.2.3.4:9"}
    assert df[df["item"] == "行业"]["value"].iloc[0] == "白色家电"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_em_raw.py -k "secid or board_pe or stock_info_frame" -v`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement the edge fetchers + default http_get**

Append to `src/irc/monitor/em_raw.py`:

```python
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
```

Note: `_default_http_get` accepts `proxies=` keyword; the test's `http_get` for the
paginating cases omits `proxies` in the signature — update those test doubles to
accept `**_kw` OR add `proxies=None` (they already do for the stock test). If a
board-PE test double lacks `proxies`, add `proxies=None` to its signature. (The
Step-1 board doubles must accept `proxies=None`; adjust if the run errors.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/monitor/test_em_raw.py -v`
Expected: all PASS (9 total). If a board-PE double errors on an unexpected `proxies` kwarg, add `proxies=None` to that double's signature and re-run.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/em_raw.py tests/monitor/test_em_raw.py
git commit -m "feat(monitor): em_raw edge fetchers (paginated board PE + stock industry) via proxy (slice 2)"
```

### Task 6: Wire em_raw into `industry_valuation` default fetch; stop caching empty parse

**Files:**
- Modify: `src/irc/monitor/industry_valuation.py`
- Test: `tests/monitor/test_industry_valuation.py` (ADD one identity test only; do NOT edit existing tests)

**Interfaces:**
- Consumes: `em_raw.fetch_board_pe_frame`, `em_raw.fetch_stock_info_frame`.
- Behavior change: `fetch_industry_pe` default `fetch` becomes a frame-returning wrapper over `em_raw.fetch_board_pe_frame`; `fetch_stock_industry_map` default `fetch` wraps `em_raw.fetch_stock_info_frame`. `fetch_industry_pe` returns `{}` from an empty parse but does NOT write the cache file for it.

- [ ] **Step 1: Add the ONE new default-fetch identity test (contract-preservation proof)**

Append to `tests/monitor/test_industry_valuation.py` (do not touch existing tests):

```python
def test_default_fetch_uses_em_raw_board_frame(tmp_path, monkeypatch):
    """Contract-preservation: with NO fetch injected, fetch_industry_pe pulls the
    board frame from em_raw (raw JSON) and the EXISTING parse_industry_pe yields
    the same {name: pe} mapping — no akshare wrapper involved."""
    import irc.monitor.industry_valuation as iv

    monkeypatch.setattr(
        iv, "fetch_board_pe_frame",
        lambda **_kw: pd.DataFrame({"板块名称": ["电力"], "市盈率": [19.68]}))
    out = iv.fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-07-02",
                               sleep=lambda _s: None)
    assert out == {"电力": 19.68}


def test_empty_parse_is_returned_but_not_cached(tmp_path, monkeypatch):
    """D3: {} from an empty parse is returned but NOT written (kills the
    '{} frozen for the day' wart, F4)."""
    import irc.monitor.industry_valuation as iv

    monkeypatch.setattr(iv, "fetch_board_pe_frame", lambda **_kw: pd.DataFrame())
    out = iv.fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-07-02",
                               sleep=lambda _s: None)
    assert out == {}
    assert not (tmp_path / "ip" / "2026-07-02.json").is_file()  # NOT cached
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -k "default_fetch or empty_parse" -v`
Expected: FAIL — `iv` has no `fetch_board_pe_frame` / empty parse currently caches.

- [ ] **Step 3: Wire em_raw default + empty-not-cached in `industry_valuation.py`**

At the top of `src/irc/monitor/industry_valuation.py`, add the import:

```python
from irc.monitor.em_raw import fetch_board_pe_frame, fetch_stock_info_frame
```

In `fetch_industry_pe`, replace the akshare default-fetch block:

```python
    if fetch is None:
        import akshare as ak  # local import — house pattern
        fetch = ak.stock_board_industry_name_em
    try:
        df = fetch()
    except Exception:  # noqa: BLE001 — degrade to {}, never crash the brief
        _log.warning("industry_valuation: stock_board_industry_name_em failed",
                     exc_info=True)
        return {}
    sleep(_PACING_SECONDS)
    parsed = parse_industry_pe(df)
    _write_json(cache_dir, today, parsed)
    return parsed
```

with:

```python
    if fetch is None:
        fetch = lambda: fetch_board_pe_frame(sleep=sleep)  # raw JSON via proxy (D3)
    try:
        df = fetch()
    except Exception:  # noqa: BLE001 — degrade to {}, never crash the brief
        _log.warning("industry_valuation: board PE fetch failed", exc_info=True)
        return {}
    parsed = parse_industry_pe(df)
    if parsed:                       # D3: never cache an empty parse (F4 wart)
        _write_json(cache_dir, today, parsed)
    return parsed
```

(The `sleep(_PACING_SECONDS)` is now owned by `fetch_board_pe_frame`'s per-page pacing; drop the standalone sleep.)

In `fetch_stock_industry_map`, replace the akshare default-fetch block:

```python
    if fetch is None:
        import akshare as ak  # local import — house pattern
        fetch = ak.stock_individual_info_em
```

with:

```python
    if fetch is None:
        fetch = lambda symbol: fetch_stock_info_frame(symbol)  # raw JSON via proxy (D3)
```

- [ ] **Step 4: Run the new + existing industry tests (existing must stay green)**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -v`
Expected: all PASS — the two new tests plus every pre-existing test (contract preserved; existing tests inject `fetch`, so the em_raw default never fires for them).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/industry_valuation.py tests/monitor/test_industry_valuation.py
git commit -m "feat(monitor): industry leg default-fetch → em_raw; empty parse not cached (slice 2)"
```

### Task 7: Route per-stock PE/PB fetch through `proxy_env`

**Files:**
- Modify: `src/irc/fundamentals/akshare_stock_valuation.py`
- Test: `tests/fundamentals/test_akshare_stock_valuation.py` (add one test; create the file if absent)

**Interfaces:**
- Behavior change: `_fetch_frame` wraps its `stock_value_em` akshare call in `proxy_env(proxy)` when `resolve_cn_proxy()` is set (D2); direct otherwise.

- [ ] **Step 1: Write failing test**

Add to `tests/fundamentals/test_akshare_stock_valuation.py` (create if absent):

```python
from __future__ import annotations

import os

import pandas as pd

import irc.fundamentals.akshare_stock_valuation as asv


def test_fetch_frame_wraps_proxy_env_when_cn_proxy_set(monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "9.9.9.9:1")
    seen = {}

    def fake_ak_call(fn_name, **kwargs):
        seen["https_proxy"] = os.environ.get("HTTPS_PROXY")
        return pd.DataFrame({"数据日期": ["2026-07-01"], "PE(TTM)": [10.0], "市净率": [1.0]})

    monkeypatch.setattr(asv, "_ak_call", fake_ak_call)
    df = asv._fetch_frame("600690")
    assert seen["https_proxy"] == "http://9.9.9.9:1"   # proxy active during the call
    assert "HTTPS_PROXY" not in os.environ or os.environ.get("HTTPS_PROXY") != "http://9.9.9.9:1"
    assert not df.empty


def test_fetch_frame_direct_when_no_cn_proxy(monkeypatch):
    monkeypatch.delenv("IRC_CN_PROXY", raising=False)
    seen = {}

    def fake_ak_call(fn_name, **kwargs):
        seen["https_proxy"] = os.environ.get("HTTPS_PROXY")
        return pd.DataFrame({"数据日期": ["2026-07-01"], "PE(TTM)": [10.0], "市净率": [1.0]})

    monkeypatch.setattr(asv, "_ak_call", fake_ak_call)
    asv._fetch_frame("600690")
    assert seen["https_proxy"] is None   # no proxy injected
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/fundamentals/test_akshare_stock_valuation.py -v`
Expected: FAIL — proxy not injected.

- [ ] **Step 3: Wrap `_fetch_frame` in proxy_env**

In `src/irc/fundamentals/akshare_stock_valuation.py`, add imports:

```python
import contextlib

from irc.http_proxy import proxy_env, resolve_cn_proxy
```

Replace `_fetch_frame`'s `try` around `_ak_call("stock_value_em", ...)`:

```python
def _fetch_frame(symbol: str) -> pd.DataFrame | None:
    proxy = resolve_cn_proxy()
    ctx = proxy_env(proxy) if proxy else contextlib.nullcontext()
    try:
        with ctx:
            df = _ak_call("stock_value_em", symbol=symbol)
    except Exception as exc:
        _log.warning("stock_value_em(%r) failed: %s: %s", symbol, type(exc).__name__, exc)
        return None
    if not isinstance(df, pd.DataFrame):
        _log.warning(
            "stock_value_em(%r) returned unexpected type %s", symbol, type(df).__name__
        )
        return pd.DataFrame()
    return df
```

Update the module docstring line "CN-direct (NOT proxied…)" → "routed through IRC_CN_PROXY when set (D2), else CN-direct."

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/fundamentals/test_akshare_stock_valuation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/akshare_stock_valuation.py tests/fundamentals/test_akshare_stock_valuation.py
git commit -m "feat(monitor): per-stock PE/PB fetch routed through IRC_CN_PROXY (slice 2, D2)"
```

---

# Slice 3 — Flow batch fetch + series store + seed

### Task 8: `flow_batch_fetch.py` — `parse_ulist` + `fetch_flow_today_batch` (B2 §5.B)

**Files:**
- Create: `src/irc/monitor/flow_batch_fetch.py`
- Test: `tests/monitor/test_flow_batch_fetch.py` (create)

**Interfaces:**
- Produces:
  - `parse_ulist(payload: dict) -> dict[str, float | None]` — `{f12 → f184}`, percent-points (NO `/100`), key-tolerant; blank/missing `data` → `{}`.
  - `build_secids(symbols) -> str` — comma-joined secids (`6*`→`1.`, else `0.`).
  - `fetch_flow_today_batch(symbols, *, http_get=None) -> dict[str, float | None]` — ONE `ulist.np` call via the CN proxy; a blank/throttled body → all-None (never fabricated). Non-A-share lines are never in `secids`.

- [ ] **Step 1: Write failing tests (percent-point canary + secid build + blank→None)**

Create `tests/monitor/test_flow_batch_fetch.py`:

```python
from __future__ import annotations

from irc.monitor.flow_batch_fetch import (
    build_secids, fetch_flow_today_batch, parse_ulist,
)


def test_parse_ulist_percent_point_boundaries():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 1.0}, {"f12": "000651", "f184": 3.0},
        {"f12": "300750", "f184": 0.01}, {"f12": "600690", "f184": 0.03},
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": 1.0, "000651": 3.0, "300750": 0.01, "600690": 0.03}


def test_parse_ulist_blank_and_dash_are_none():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": "-"}, {"f12": "000651", "f184": ""},
        {"f12": "300750", "f184": None},
    ]}}
    assert parse_ulist(payload) == {"600519": None, "000651": None, "300750": None}


def test_parse_ulist_data_null_is_empty():
    assert parse_ulist({"data": None}) == {}
    assert parse_ulist({}) == {}


def test_build_secids_prefixes():
    assert build_secids(("600519", "000651", "300750")) == "1.600519,0.000651,0.300750"


def test_fetch_flow_today_batch_one_call_via_proxy(monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "1.2.3.4:9")
    calls = {"n": 0}

    def http_get(url, *, params, headers, timeout, proxies=None):
        calls["n"] += 1
        assert proxies == {"http": "http://1.2.3.4:9", "https": "http://1.2.3.4:9"}
        assert params["secids"] == "1.600519,0.000651"
        return {"data": {"diff": [{"f12": "600519", "f184": 4.86},
                                  {"f12": "000651", "f184": 7.42}]}}

    out = fetch_flow_today_batch(("600519", "000651"), http_get=http_get)
    assert calls["n"] == 1                       # ONE batch call, not 53/not per-fund
    assert out == {"600519": 4.86, "000651": 7.42}


def test_fetch_flow_today_batch_blank_body_all_none():
    out = fetch_flow_today_batch(
        ("600519",), http_get=lambda *a, **k: {"data": None})
    assert out == {"600519": None}              # never fabricated
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_flow_batch_fetch.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `flow_batch_fetch.py`**

Create `src/irc/monitor/flow_batch_fetch.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/monitor/test_flow_batch_fetch.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/flow_batch_fetch.py tests/monitor/test_flow_batch_fetch.py
git commit -m "feat(monitor): flow_batch_fetch — one ulist.np call via proxy (slice 3, B2 5.B)"
```

### Task 9: `flow_series_store.py` — completed-day-only append, prune, idempotency, corrupt-degrade, D7 seed

**Files:**
- Create: `src/irc/monitor/flow_series_store.py`
- Test: `tests/monitor/test_flow_series_store.py` (create)

**Interfaces:**
- Consumes: `flow_fetch.FlowSeries` type (`tuple[tuple[str, float], ...]`).
- Produces:
  - `load_store(path) -> dict[str, FlowSeries]` — degrade to `{}` on corrupt/missing.
  - `append_today(path, today, today_by_symbol, *, keep_td, trading_days) -> dict[str, FlowSeries]` — append COMPLETED-day rows only (idempotent same-day: overwrite that day's row, never duplicate), prune to `keep_td` trading days, atomic byte-stable write; returns the per-symbol series for the run.
  - `series_slice(store, symbols) -> dict[str, FlowSeries | None]` — per-symbol slice for the run (missing symbol → None).
  - `seed_from_per_symbol(path, fund_flow_dir, *, keep_td, trading_days) -> dict[str, FlowSeries]` — one-time merge of existing `fund_flow/*.json` `ok` series into the store (D7).

- [ ] **Step 1: Write failing tests**

Create `tests/monitor/test_flow_series_store.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from irc.monitor.flow_series_store import (
    append_today, load_store, seed_from_per_symbol, series_slice,
)

_TD = ("2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02")


def test_append_completed_day_then_slice(tmp_path):
    p = tmp_path / "flow_series.json"
    store = append_today(p, "2026-07-01", {"600519": 4.0, "000651": 7.0},
                         keep_td=25, trading_days=_TD)
    assert store["600519"] == (("2026-07-01", 4.0),)
    assert series_slice(store, ("600519", "999999")) == {
        "600519": (("2026-07-01", 4.0),), "999999": None}


def test_append_is_idempotent_same_day(tmp_path):
    p = tmp_path / "flow_series.json"
    append_today(p, "2026-07-01", {"600519": 4.0}, keep_td=25, trading_days=_TD)
    store = append_today(p, "2026-07-01", {"600519": 9.0}, keep_td=25, trading_days=_TD)
    assert store["600519"] == (("2026-07-01", 9.0),)  # overwrite, not duplicate


def test_append_accumulates_across_days_and_prunes(tmp_path):
    p = tmp_path / "flow_series.json"
    append_today(p, "2026-06-29", {"600519": 1.0}, keep_td=2, trading_days=_TD)
    append_today(p, "2026-06-30", {"600519": 2.0}, keep_td=2, trading_days=_TD)
    store = append_today(p, "2026-07-01", {"600519": 3.0}, keep_td=2, trading_days=_TD)
    # keep_td=2 → only the last 2 trading days survive
    assert store["600519"] == (("2026-06-30", 2.0), ("2026-07-01", 3.0))


def test_append_skips_none_values(tmp_path):
    p = tmp_path / "flow_series.json"
    store = append_today(p, "2026-07-01", {"600519": None, "000651": 7.0},
                         keep_td=25, trading_days=_TD)
    assert "600519" not in store        # None → not appended (no fabricated row)
    assert store["000651"] == (("2026-07-01", 7.0),)


def test_load_store_degrades_on_corrupt(tmp_path):
    p = tmp_path / "flow_series.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert load_store(p) == {}           # degrade, never crash


def test_write_is_byte_stable_sorted(tmp_path):
    p = tmp_path / "flow_series.json"
    append_today(p, "2026-07-01", {"z": 1.23456, "a": 2.0}, keep_td=25, trading_days=_TD)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert list(payload.keys()) == ["a", "z"]           # sorted keys
    assert payload["z"][0][1] == 1.2346                 # 4dp round


def test_seed_from_per_symbol_merges_ok_series(tmp_path):
    fund_flow = tmp_path / "fund_flow"
    fund_flow.mkdir()
    (fund_flow / "2026-07-01.json").write_text(json.dumps({
        "600519": {"status": "ok", "rows": [{"date": "2026-06-30", "main_net_pct": 2.5},
                                            {"date": "2026-07-01", "main_net_pct": 3.5}]},
        "000001": {"status": "miss", "rows": []},
    }), encoding="utf-8")
    p = tmp_path / "flow_series.json"
    store = seed_from_per_symbol(p, fund_flow, keep_td=25, trading_days=_TD)
    assert store["600519"] == (("2026-06-30", 2.5), ("2026-07-01", 3.5))
    assert "000001" not in store          # miss series not seeded
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_flow_series_store.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `flow_series_store.py`**

Create `src/irc/monitor/flow_series_store.py`:

```python
"""EDGE: persisted completed-day-only flow daily-series store (B2 §5.C, D6/D7).

One market-wide file (data/monitor/fund_flow_series.json), scoped to the monitored
union symbols, pruned to ~25 trading days. The append API takes only COMPLETED
days — the 12:15 brief path has NO write access (provisional f184 is render-only,
D6/trap §8). Idempotent same-day (overwrite that day's row). Byte-stable
(.tmp.{pid}→os.replace, sorted keys, 4dp). Corrupt/missing → {} (never crash)."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from irc.monitor.flow_fetch import FlowSeries

_log = logging.getLogger(__name__)
_ROUND_DP = 4


def load_store(path: Path) -> dict[str, FlowSeries]:
    """Load the store; degrade to {} on corrupt/missing (never crash)."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(sym): tuple((str(d), float(v)) for d, v in rows)
                for sym, rows in raw.items()}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        _log.warning("flow_series_store: unreadable store %s; degrading", path,
                     exc_info=True)
        return {}


def series_slice(store: dict[str, FlowSeries], symbols) -> dict[str, FlowSeries | None]:
    """Per-symbol slice for a run: missing symbol → None (uncovered)."""
    return {s: store.get(s) for s in dict.fromkeys(symbols)}


def _prune(rows: FlowSeries, keep_td: int, trading_days) -> FlowSeries:
    keep = set(sorted(d for d in trading_days)[-keep_td:]) if trading_days else None
    kept = [(d, v) for d, v in rows if keep is None or d in keep]
    return tuple(sorted(kept, key=lambda r: r[0]))


def _write(path: Path, store: dict[str, FlowSeries]) -> None:
    payload = {sym: [[d, round(v, _ROUND_DP)] for d, v in rows]
               for sym, rows in sorted(store.items())}
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def append_today(path: Path, today: str, today_by_symbol, *, keep_td, trading_days):
    """Append COMPLETED-day rows (idempotent same-day; None values skipped),
    prune to keep_td trading days, byte-stable write. Returns the pruned store."""
    store = load_store(path)
    for sym, val in today_by_symbol.items():
        if val is None:
            continue
        prior = tuple((d, v) for d, v in store.get(sym, ()) if d != today)
        store[sym] = _prune(prior + ((today, float(val)),), keep_td, trading_days)
    _write(path, store)
    return store


def seed_from_per_symbol(path: Path, fund_flow_dir: Path, *, keep_td, trading_days):
    """D7: one-time merge of existing fund_flow/*.json `ok` series into the store."""
    store = load_store(path)
    if fund_flow_dir.is_dir():
        for f in sorted(fund_flow_dir.glob("*.json")):
            try:
                day = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            for sym, entry in day.items():
                if entry.get("status") != "ok":
                    continue
                rows = tuple((str(r["date"]), float(r["main_net_pct"]))
                             for r in entry.get("rows", []))
                merged = {d: v for d, v in store.get(sym, ())}
                merged.update(dict(rows))
                store[sym] = _prune(tuple(merged.items()), keep_td, trading_days)
    _write(path, store)
    return store
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/monitor/test_flow_series_store.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/flow_series_store.py tests/monitor/test_flow_series_store.py
git commit -m "feat(monitor): flow_series_store — completed-day append/prune/seed (slice 3, B2 5.C)"
```

---

# Slice 4 — Capture job + monitor_cmd swap + launchd

### Task 10: `monitor_cmd` swaps to store-consumption; provisional 12:15 annotation; D10 per-fund fetch removed

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Test: `tests/commands/test_monitor_cmd_valuation.py`, `tests/commands/test_monitor_cmd_drilldown.py` (update the flow-caller stubs — RUN PER-FILE, the dir hangs)

**Interfaces:**
- Consumes: `flow_series_store.load_store`, `flow_series_store.series_slice`; `flow_batch_fetch.fetch_flow_today_batch`.
- Produces: `_build_full_basket_metrics(full_holdings, top5, fund_id, *, root, today, con, flow_slice)` — now takes a per-fund `flow_slice` (from the run-level store) instead of calling `fetch_flow_series` per fund (D10). `run_monitor` reads the store ONCE (its newest completed day), passes each fund its slice.

- [ ] **Step 1: Update the two flow-caller tests to the store-fed path (RED)**

In `tests/commands/test_monitor_cmd_drilldown.py`, replace the monkeypatch of `fetch_flow_series` (lines ~84–85):

```python
    monkeypatch.setattr(mc, "fetch_flow_series",
                        lambda symbols, cache_dir, today: _flow_series_with_coverage())
```

with a store-fed stub — patch the run-level store read so `_process_fund` gets a slice:

```python
    monkeypatch.setattr(mc, "_load_flow_store_slice",
                        lambda root, symbols: _flow_series_with_coverage())
```

In `tests/commands/test_monitor_cmd_valuation.py`, replace both `fetch_flow_series` monkeypatches (lines ~75 and ~213) with:

```python
    monkeypatch.setattr(mc, "_load_flow_store_slice", lambda root, symbols: {})
```

and update `test_build_full_basket_metrics_skips_industry_fetch_when_con_none` (line ~227) to pass the new `flow_slice` param:

```python
    result = mc._build_full_basket_metrics(
        full_holdings, top5, "110011",
        root=Path("/tmp"), today="2026-06-21", con=None,
        flow_slice={s.symbol: None for s in full_holdings})
```

- [ ] **Step 2: Run the two test files (per-file — dir hangs) to verify failure**

Run:
```bash
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -v
uv run pytest tests/commands/test_monitor_cmd_valuation.py -v
```
Expected: FAIL — `mc` has no `_load_flow_store_slice`; `_build_full_basket_metrics` has no `flow_slice` kwarg.

- [ ] **Step 3: Implement the swap in `monitor_cmd.py`**

Add imports near the flow import:

```python
from irc.monitor.flow_batch_fetch import fetch_flow_today_batch
from irc.monitor.flow_series_store import load_store, series_slice
```

(Remove the `from irc.monitor.flow_fetch import fetch_flow_series` import — D10 retires it from the run path. `flow_fetch` stays as library code for the seed/spike; it is no longer imported by monitor_cmd.)

Add a store-slice edge helper and a store-path constant near `_TOP_N_HOLDINGS`:

```python
_FLOW_STORE_REL = ("data", "monitor", "fund_flow_series.json")


def _load_flow_store_slice(root: Path, symbols) -> dict:
    """EDGE-read: the persisted completed-day flow store, sliced to `symbols`.
    The 12:15 brief consumes the store (whose newest row is a COMPLETED day); it
    NEVER writes a provisional intraday value (D6/trap §8). Degrades to {} on any
    error — the flow factor then reads all-None (honest N/A)."""
    try:
        store = load_store(root.joinpath(*_FLOW_STORE_REL))
        return series_slice(store, symbols)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("_load_flow_store_slice failed", exc_info=True)
        return {}
```

Change `_build_full_basket_metrics` to accept `flow_slice` and drop the per-fund fetch:

```python
def _build_full_basket_metrics(full_holdings, top5, fund_id, *, root, today, con, flow_slice):
    """EDGE: consume flow (top-5, from the run-level store slice) + fetch industry
    (full basket) → full-basket HoldingMetrics. Flow no longer fetched per fund
    (D10); the store slice is fed in by run_monitor."""
    from irc.opportunity.inputs_loader import _stock_series_by_code
    flow_symbols = tuple(h.symbol for h in top5)
    flow_series = {s: flow_slice.get(s) for s in flow_symbols}
    full_symbols = tuple(h.symbol for h in full_holdings)
    if con is None:
        return build_holding_metrics(full_holdings, {}, flow_series)
    series_by_code = _stock_series_by_code(con, full_symbols)
    industry_pe = fetch_industry_pe(
        cache_dir=root / "data" / "monitor" / "industry_pe", today=today)
    industry_map = fetch_stock_industry_map(
        full_symbols, cache_dir=root / "data" / "monitor" / "stock_industry", today=today)
    return build_holding_metrics(
        full_holdings, series_by_code, flow_series,
        industry_by_symbol=industry_map, industry_pe_by_industry=industry_pe)
```

In `_process_fund`, add a `flow_slice` param (default `None`) and thread it:

```python
def _process_fund(
    fund: MonitorFund, cfg, root: Path, llm_config, *, con=None, purchase_table=None,
    today: str | None = None, flow_slice: dict | None = None,
) -> tuple[FundView, list, FundTraceBundle]:
```

Replace the `_build_full_basket_metrics(...)` call:

```python
        if full_holdings and today is not None:
            holding_metrics = _build_full_basket_metrics(
                full_holdings, top5, fund.id, root=root, today=today, con=con,
                flow_slice=(flow_slice if flow_slice is not None
                            else _load_flow_store_slice(
                                root, tuple(h.symbol for h in top5))))
```

In `run_monitor`, load the store slice once per fund (from the run-level store) and pass it into `_process_fund`:

```python
        for fund in funds:
            top5_syms = ()  # resolved inside _process_fund; pass the store root instead
            view, costs, bundle = _process_fund(
                fund, cfg, root, llm_config, con=con, purchase_table=purchase_table,
                today=_today,
            )
```

(Leave `_process_fund` to call `_load_flow_store_slice` for its own top-5 when `flow_slice is None`; the run path uses the store, not a per-fund network fetch. Tests inject `_load_flow_store_slice`.)

- [ ] **Step 4: Run the two test files (per-file) to verify pass**

Run:
```bash
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -v
uv run pytest tests/commands/test_monitor_cmd_valuation.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_drilldown.py tests/commands/test_monitor_cmd_valuation.py
git commit -m "feat(monitor): monitor_cmd consumes flow store; per-fund flow fetch retired (slice 4, D10)"
```

### Task 11: `irc monitor flow-capture` subcommand + CLI wiring

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Modify: `src/irc/cli.py`
- Test: `tests/commands/test_monitor_flow_capture.py` (create)

**Interfaces:**
- Produces: `run_flow_capture(*, repo_root, today=None) -> int` — ONE `fetch_flow_today_batch` for the monitor-set union top-5 symbols → `append_today` (completed-day). No LLM, no report, no ledger. `today` must be a COMPLETED CN trading day (the caller runs it at 15:45 after close). `irc monitor flow-capture` CLI entry.

- [ ] **Step 1: Write failing test**

Create `tests/commands/test_monitor_flow_capture.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import irc.commands.monitor_cmd as mc


def test_run_flow_capture_appends_completed_day(tmp_path, monkeypatch):
    # Two active funds whose top-5 union symbols get one batch call.
    class _F:
        def __init__(self, fid, syms):
            self.id, self._syms = fid, syms

    monkeypatch.setattr(mc, "load_monitor_config", lambda root: object())
    monkeypatch.setattr(mc, "resolve_funds", lambda cfg: [_F("110011", ("600519",))])
    monkeypatch.setattr(mc, "_capture_union_symbols",
                        lambda funds, root: ("600519", "000651"))
    monkeypatch.setattr(mc, "fetch_flow_today_batch",
                        lambda symbols: {"600519": 4.0, "000651": 7.0})
    monkeypatch.setattr(mc, "load_trading_days",
                        lambda today, root: frozenset({__import__("datetime").date(2026, 7, 1)}))

    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    store = json.loads((tmp_path / "data" / "monitor" / "fund_flow_series.json").read_text())
    assert store["600519"] == [["2026-07-01", 4.0]]
    assert store["000651"] == [["2026-07-01", 7.0]]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/commands/test_monitor_flow_capture.py -v`
Expected: FAIL — `run_flow_capture` not defined.

- [ ] **Step 3: Implement `run_flow_capture` + `_capture_union_symbols`**

Add to `monitor_cmd.py`, importing the store append and batch fetch (already imported in Task 10). Add near `run_monitor`:

```python
from irc.monitor.flow_series_store import append_today  # add to the existing import line

_FLOW_KEEP_TD = 25


def _capture_union_symbols(funds, root: Path) -> tuple:
    """The union of the monitor set's active-fund top-5 look-through symbols."""
    from irc.monitor.profiles import PROFILES
    syms: list[str] = []
    for fund in funds:
        spec = PROFILES.get(fund.analysis_profile)
        if not (spec and spec.lookthrough == "active_fund"):
            continue
        snap = load_latest_active_fund_cached(fund.id, root / "data")
        if snap is None:
            continue
        top = sorted(snap.constituent_analyses, key=lambda c: c.weight_pct,
                     reverse=True)[:_TOP_N_HOLDINGS]
        syms.extend(h.symbol for h in top)
    return tuple(dict.fromkeys(syms))


def run_flow_capture(*, repo_root: str, today: str | None = None) -> int:
    """EDGE (15:45 job, D6): ONE ulist.np batch → append the now-final f184 to the
    completed-day store. No LLM, no report, no ledger. `today` MUST be a completed
    CN trading day (the wrapper runs it after the 15:00 close)."""
    root = Path(repo_root)
    _today = today or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    funds = resolve_funds(load_monitor_config(root))
    symbols = _capture_union_symbols(funds, root)
    if not symbols:
        _log.warning("flow-capture: no active-fund symbols; nothing to capture")
        return 0
    try:
        by_symbol = fetch_flow_today_batch(symbols)
    except Exception:  # noqa: BLE001 — degrade, never crash (breaker/abort posture)
        _log.warning("flow-capture: ulist.np batch failed", exc_info=True)
        return 0
    trading_days = load_trading_days(date.today(), root=root)
    tds = tuple(d.isoformat() for d in (trading_days or ()))
    append_today(root / "data" / "monitor" / "fund_flow_series.json", _today,
                 by_symbol, keep_td=_FLOW_KEEP_TD, trading_days=tds)
    print(f"flow-capture OK: {_today} appended {sum(v is not None for v in by_symbol.values())}"
          f"/{len(symbols)} symbols")
    return 0
```

Add the CLI entry to `src/irc/cli.py` under the `monitor` group (after `monitor_snapshot`):

```python
@monitor.command("flow-capture",
                 help="15:45 job: append the completed-day flow batch to the series store.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def monitor_flow_capture(repo_root: str) -> None:
    from irc.commands.monitor_cmd import run_flow_capture
    raise SystemExit(run_flow_capture(repo_root=repo_root))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/commands/test_monitor_flow_capture.py -v`
Expected: PASS.

- [ ] **Step 5: Verify the CLI wiring resolves**

Run: `uv run irc monitor flow-capture --help`
Expected: help text prints (exit 0).

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/monitor_cmd.py src/irc/cli.py tests/commands/test_monitor_flow_capture.py
git commit -m "feat(monitor): irc monitor flow-capture 15:45 job (slice 4, D6)"
```

### Task 12: 12:15 provisional annotation (render-only, never persisted)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Test: `tests/commands/test_monitor_flow_capture.py` (add a no-write assertion)

**Interfaces:**
- Produces: `_provisional_flow_note(root, symbols) -> dict[str, float | None] | None` — an intraday `fetch_flow_today_batch` result used ONLY as a 盘中提示 annotation on the brief; it is returned for render and NEVER passed to `append_today` (the 12:15 path has no store-write access — trap §8). Behind a guard so a fetch failure degrades to `None` (no annotation).

- [ ] **Step 1: Write failing test — the 12:15 brief path never writes the store**

Add to `tests/commands/test_monitor_flow_capture.py`:

```python
def test_provisional_note_never_writes_store(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "fetch_flow_today_batch",
                        lambda symbols: {"600519": 11.78})  # intraday-provisional
    note = mc._provisional_flow_note(tmp_path, ("600519",))
    assert note == {"600519": 11.78}
    # CRITICAL (D6/trap §8): the provisional path must NOT create/modify the store
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/commands/test_monitor_flow_capture.py::test_provisional_note_never_writes_store -v`
Expected: FAIL — `_provisional_flow_note` not defined.

- [ ] **Step 3: Implement the render-only provisional helper**

Add to `monitor_cmd.py`:

```python
def _provisional_flow_note(root: Path, symbols) -> dict | None:
    """EDGE-read only: today's intraday f184 as a 盘中提示 annotation for the 12:15
    brief. NEVER persisted (no append_today here) — the store's newest row stays a
    COMPLETED day (D6/trap §8). Degrades to None on any error (no annotation)."""
    if not symbols:
        return None
    try:
        return fetch_flow_today_batch(tuple(symbols))
    except Exception:  # noqa: BLE001 — annotation is best-effort
        _log.warning("_provisional_flow_note failed", exc_info=True)
        return None
```

(Wiring the annotation into the report HTML is part of the report-v3 readability spec — out of scope here per §4. This task ships the helper + the no-write guarantee; the render surface consumes it later. Do NOT call `append_today` from any 12:15 path.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/commands/test_monitor_flow_capture.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_flow_capture.py
git commit -m "feat(monitor): render-only provisional flow note; store stays completed-day (slice 4, D6)"
```

### Task 13: launchd flow-capture wrapper + plist + install.sh; test assertions

**Files:**
- Create: `ops/launchd/run-flow-capture.sh`
- Create: `ops/launchd/com.irc.flow-capture.plist`
- Modify: `ops/launchd/install.sh`
- Test: `tests/ops/test_launchd_monitor.py` (add flow-capture assertions)

**Interfaces:**
- Produces: a 15:45 Asia/Shanghai LaunchAgent that runs `irc monitor flow-capture` under `acquire_lock` + `run_with_watchdog` (protective; a capture timeout does not page — it is best-effort). Reuses `lib-run.sh`.

- [ ] **Step 1: Write failing test assertions for the new artifacts**

Add to `tests/ops/test_launchd_monitor.py`:

```python
def test_flow_capture_plist_fires_at_1545() -> None:
    text = (_OPS / "com.irc.flow-capture.plist").read_text(encoding="utf-8")
    assert "<string>com.irc.flow-capture</string>" in text
    assert "<integer>15</integer>" in text, "flow-capture plist missing 15:xx Hour"
    assert "<integer>45</integer>" in text, "flow-capture plist missing :45 Minute"


def test_flow_capture_plist_logs_to_devnull() -> None:
    text = (_OPS / "com.irc.flow-capture.plist").read_text(encoding="utf-8")
    assert text.count("<string>/dev/null</string>") >= 2


def test_flow_capture_wrapper_uses_lib_and_calls_flow_capture() -> None:
    text = (_OPS / "run-flow-capture.sh").read_text(encoding="utf-8")
    assert "source ops/launchd/lib-run.sh" in text
    assert "acquire_lock" in text
    assert "run_with_watchdog" in text
    assert "irc monitor flow-capture" in text


def test_install_sh_templates_flow_capture() -> None:
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    assert "com.irc.flow-capture" in text
    assert "run-flow-capture.sh" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -k flow_capture -v`
Expected: FAIL — files missing / install.sh lacks the label.

- [ ] **Step 3: Create `run-flow-capture.sh`**

Create `ops/launchd/run-flow-capture.sh`:

```bash
#!/bin/bash
# 15:45 FLOW-CAPTURE wrapper: append the completed-day flow batch to the series
# store. Protective-only (a timeout does NOT page — capture is best-effort; the
# 12:15 brief already ran). StandardOut/ErrPath are /dev/null; we write our own log.
#
# __UV_BIN__ / __REPO_ROOT__ are substituted by install.sh.
set -euo pipefail

UV_BIN="__UV_BIN__"
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
# shellcheck source=ops/launchd/lib-run.sh
source ops/launchd/lib-run.sh
mkdir -p outputs/_logs

LOG_FILE="outputs/_logs/run-flow-capture.$(TZ='Asia/Shanghai' date '+%Y%m%d-%H%M%S').log"
exec >> "$LOG_FILE" 2>&1
find outputs/_logs -name 'run-flow-capture.*.log' -type f -mtime +14 -delete 2>/dev/null || true

TODAY="$(TZ='Asia/Shanghai' date +%Y-%m-%d)"
DOW="$(TZ='Asia/Shanghai' date +%u)"
HOLIDAYS_FILE="config/cn_market_holidays.yaml"
if [ "$DOW" -ge 6 ]; then
  echo "[$TODAY] weekend — skipping flow-capture."; exit 0
fi
if [ -f "$HOLIDAYS_FILE" ] && grep -Eq "^[-[:space:]]*[\"']?${TODAY}[\"']?[[:space:]]*$" "$HOLIDAYS_FILE"; then
  echo "[$TODAY] CN holiday — skipping flow-capture."; exit 0
fi

# Single-instance lock (separate from the monitor lock).
acquire_lock "outputs/_logs/.flow-capture.lock" || {
  echo "[$TODAY] another flow-capture in progress — skipping."; exit 0
}

# Watchdog: protective. On overrun the group is killed (rc=124) but capture is
# best-effort — no page. `|| rc=$?` keeps set -e from aborting before we exit.
rc=0
run_with_watchdog "${IRC_FLOW_CAPTURE_TIMEOUT:-300}" "$UV_BIN" run irc monitor flow-capture || rc=$?
echo "[$TODAY] flow-capture rc=$rc"
exit "$rc"
```

- [ ] **Step 4: Create `com.irc.flow-capture.plist`**

Create `ops/launchd/com.irc.flow-capture.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.irc.flow-capture</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>__REPO_ROOT__/ops/launchd/run-flow-capture.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>__REPO_ROOT__</string>
  <!-- Daily 15:45 (Asia/Shanghai; machine is UTC+8), AFTER the 15:00 CN close so
       f184 is the completed-day value. The wrapper skips weekends + CN holidays. -->
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>15</integer>
    <key>Minute</key><integer>45</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/dev/null</string>
  <key>StandardErrorPath</key>
  <string>/dev/null</string>
</dict>
</plist>
```

- [ ] **Step 5: Wire install.sh to template + bootstrap the job**

In `ops/launchd/install.sh`, extend the two arrays:

```bash
LABELS=("com.irc.monitor" "com.irc.fundamentals-quarterly" "com.irc.flow-capture")
WRAPPERS=("run-monitor.sh" "run-fundamentals.sh" "run-flow-capture.sh")
```

(The existing wrapper-templating and plist-templating loops iterate these arrays, so the new job is templated + bootstrapped automatically.)

- [ ] **Step 6: Run to verify pass + lint the shell/plist**

Run:
```bash
uv run pytest tests/ops/test_launchd_monitor.py -k flow_capture -v
bash -n ops/launchd/run-flow-capture.sh
plutil -lint ops/launchd/com.irc.flow-capture.plist
```
Expected: tests PASS; `bash -n` silent (syntax OK); plutil "OK".

- [ ] **Step 7: Commit**

```bash
git add ops/launchd/run-flow-capture.sh ops/launchd/com.irc.flow-capture.plist ops/launchd/install.sh tests/ops/test_launchd_monitor.py
git commit -m "feat(monitor): 15:45 flow-capture launchd job (slice 4, D6)"
```

---

# Slice 5 — Eval + docs

### Task 14: Eval-trace `_SCHEMA_VERSION` bump + `flow_source` marker + warm-up curve

**Files:**
- Modify: `src/irc/monitor/eval/trace.py`
- Modify: `src/irc/monitor/eval/structural.py`
- Test: `tests/monitor/eval/test_trace.py`, `tests/monitor/eval/test_structural.py`

**Interfaces:**
- Produces: `_SCHEMA_VERSION = "5"`; the trace `holding_metrics` block gains a `flow_source` field (`"batch_today"` | `"per_symbol_seed"` | `None`); `flow_coverage_health` gains a warm-up (rows-per-symbol) reason + surfaces `flow_source`.
- Consumes: the FundView `holding_metrics` (no new field required on the render type — `flow_source` is derived at trace-build time from whether the run consumed a live batch vs a seeded slice; default `"batch_today"` when flow rows exist, else `None`).

- [ ] **Step 1: Update the schema assertion (RED)**

In `tests/monitor/eval/test_trace.py`, change `test_schema_version_is_4`:

```python
def test_schema_version_is_5():
    ...
    assert t["schema_version"] == "5"
```

Rename the function and update the assert to `"5"`. (Keep the rest of the test body identical.)

- [ ] **Step 2: Add the warm-up + flow_source coverage test (RED)**

Add to `tests/monitor/eval/test_structural.py`:

```python
def test_flow_coverage_surfaces_warmup_and_source():
    t = {"holding_metrics": {
        "rows": [
            {"symbol": "600519", "flow_score": 1.0, "flow_reason": None,
             "pe_percentile": 0.3, "flow_rows": 5},
            {"symbol": "000858", "flow_score": None, "flow_reason": "flow_no_data",
             "pe_percentile": None, "flow_rows": 0},
        ],
        "aggregate": {"covered_weight_ratio": 0.6, "reason": None},
        "flow_source": "batch_today",
    }}
    from irc.monitor.eval.structural import flow_coverage_health
    h = flow_coverage_health(t)
    assert h.status == "PASS"
    joined = " ".join(h.reasons)
    assert "flow_source batch_today" in joined
    assert "flow_rows_min" in joined  # warm-up curve (min rows-per-symbol)
```

- [ ] **Step 3: Run to verify failure (per-file)**

Run:
```bash
uv run pytest tests/monitor/eval/test_trace.py -k schema -v
uv run pytest tests/monitor/eval/test_structural.py -k "warmup or source" -v
```
Expected: FAIL — schema is still `"4"`; `flow_source`/`flow_rows_min` reasons absent.

- [ ] **Step 4: Bump schema + add flow_source to the trace holding_metrics block**

In `src/irc/monitor/eval/trace.py`:

```python
_SCHEMA_VERSION = "5"
```

Locate `_holding_metrics(view)` (the helper that builds the `holding_metrics` block — grep for `"holding_metrics": _holding_metrics(view)` and its definition). Add a `flow_source` key to the returned dict: `"batch_today"` when any row has a non-None `flow_score`, else `None`. If `_holding_metrics` builds per-row dicts, add a per-row `flow_rows` count from the fund's flow series length when available (default 0). If the row count is not reachable at trace-build time, set `flow_rows` to `0` and rely on `flow_coverage_health`'s row-fraction fallback — but prefer wiring the real length via the FundView's `holding_metrics` (add a `flow_rows` field to `HoldingMetric` only if it does not exist; otherwise compute at trace time from `_window`—no: keep it simple and set `flow_rows` from the series the metric carries if present, else 0).

Minimal concrete edit — in the trace's per-row dict builder add:

```python
        "flow_rows": getattr(m, "flow_rows", 0),
```

and in the block builder add after the rows list:

```python
        "flow_source": ("batch_today"
                        if any(r.get("flow_score") is not None for r in rows_list)
                        else None),
```

(Adapt names to the actual `_holding_metrics` locals; the two additions are: a per-row `flow_rows` and a block-level `flow_source`.)

- [ ] **Step 5: Add the warm-up + flow_source reasons to `flow_coverage_health`**

In `src/irc/monitor/eval/structural.py` `flow_coverage_health`, before the final `return`, append:

```python
    flow_rows = [r.get("flow_rows", 0) for r in rows]
    if flow_rows:
        reasons.append(f"flow_rows_min {min(flow_rows)}")  # warm-up curve (D9/B2 5.E)
    source = hm.get("flow_source")
    if source is not None:
        reasons.append(f"flow_source {source}")
```

- [ ] **Step 6: Run to verify pass (per-file)**

Run:
```bash
uv run pytest tests/monitor/eval/test_trace.py -v
uv run pytest tests/monitor/eval/test_structural.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/irc/monitor/eval/trace.py src/irc/monitor/eval/structural.py tests/monitor/eval/test_trace.py tests/monitor/eval/test_structural.py
git commit -m "feat(monitor): eval schema 4→5 + flow_source marker + warm-up curve (slice 5, D9)"
```

### Task 15: Docs — CONTEXT.md Flow-freshness rewrite, ADR addenda, README ops rows, CHANGELOG, Tier-0 findings appendix

**Files:**
- Modify: `CONTEXT.md`
- Modify: `docs/adr/0019-monitor-capital-flow-factor.md`
- Modify: `docs/adr/0020-monitor-dual-track-valuation.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/2026-07-02-monitor-cn-egress-lightup/items/001-spec.md` (append Tier-0 findings)

- [ ] **Step 1: Rewrite CONTEXT.md "Flow freshness state" as-built**

In `CONTEXT.md`, replace the "Flow freshness state" bullet with the as-built states now that the batch/store path ships. Describe: **FRESH** (today's completed-session flow from the `ulist.np` batch store landed and covered top-5 weight ≥ 0.50 → factor renders); **STALE-N** (freshest stored row N≤3 trading days old, rendered `滞后 N 个交易日`; now buildable via the store); **abstain/DARK** (>3 td / never → `资金流数据今日不可用——倾向回退至五因子` banner). Note the store is completed-day-only (no provisional intraday value ever persisted), the 15:45 capture is the sole writer, and the 12:15 brief may show a render-only 盘中提示. Remove the "designed but shelved" / "non-CN egress IP caps coverage" language (superseded). Keep the "no silent stale" contract and the distinction from a coverage N/A.

- [ ] **Step 2: ADR 0019 addendum — mark the pivot BUILT**

Append to `docs/adr/0019-monitor-capital-flow-factor.md` a dated addendum: the 2026-07-02 CN-egress pivot is **BUILT** — batch `ulist.np` via `IRC_CN_PROXY`, completed-day series store, 15:45 capture job (D6), seed-then-organic warm-up (D7); per-symbol path retired from the run path (D10, retained as library code for seed/spot-checks); `_ENGINE_VERSION` unchanged ("3"), gated on the GATE-2 4dp equivalence spike which is **OPEN post-merge** (see the spec Tier-0 appendix); one eval schema bump + `flow_source` marker.

- [ ] **Step 3: ADR 0020 addendum — mark the industry re-transport BUILT**

Append to `docs/adr/0020-monitor-dual-track-valuation.md`: the industry leg is re-transported on raw EastMoney JSON (`em_raw.py`: `clist/get` f9 board PE + `stock/get` f127 stock→industry) via `IRC_CN_PROXY`, slotted into the existing injectable `fetch` hooks (parsers/caches unchanged); `fetch_industry_pe` no longer caches an empty parse; `_ENGINE_VERSION` unchanged (data availability returning); D4 f9 range-sanity hand-verified in Slice 0.

- [ ] **Step 4: README ops-table rows (15:45 capture job + D8 backfill + post-merge order)**

In `README.md`: add `com.irc.flow-capture` (daily 15:45, `irc monitor flow-capture`) to the launchd schedule table; add a monitor command line for `irc monitor flow-capture`; add the **post-merge op order** (§5) verbatim: *install the 15:45 job → run the D7 seed once after close (`uv run irc monitor flow-capture` after seeding, or the seed helper) → `uv run irc fundamentals stock-valuation --force` (D8 valuation backfill) → next 12:15 brief: verify Tier-2*. Add the **GATE-2 post-merge ops step**: run `uv run python -m scripts.phase0_flow_batch_spike --use-cn-proxy` after close to capture, then next day `--use-cn-proxy --equiv-against <capture>` to confirm the 4dp equivalence.

- [ ] **Step 5: CHANGELOG [Unreleased] entry (NO VERSION bump)**

Add under the `[Unreleased]` heading in `CHANGELOG.md` (do NOT touch VERSION):

```markdown
### Added
- Monitor CN-egress data-plane light-up: `IRC_CN_PROXY` egress (`resolve_cn_proxy`/`proxy_env` single source of truth), batch-first flow via one `ulist.np` call into a completed-day series store, a 15:45 `irc monitor flow-capture` launchd job, industry-leg raw EastMoney JSON fetchers (`em_raw.py`), and per-stock PE/PB fetch routed through the proxy. Eval schema 4→5 with a `flow_source` marker + warm-up curve. `_ENGINE_VERSION` unchanged (data availability returning); GATE-2 4dp equivalence gate OPEN post-merge (ADR 0019/0020 addenda).
```

- [ ] **Step 6: Append the Tier-0 findings section to the design spec**

Append a `## Tier-0 findings` section to `docs/2026-07-02-monitor-cn-egress-lightup/items/001-spec.md`:

- **GATE-1 (reachability) — PASS via proxy** (record the implementation-session date/time + the three live results: `ulist.np` f184 batch, `clist/get` f9 board PE 100 boards sane, `stock/get` f127 600690→白色家电). D4 f9 range-sanity hand-check noted.
- **GATE-2 (4dp same-day f184≈daykline equivalence) — OPEN (deferred post-merge).** Reason: requires a post-close capture vs the same completed day's daykline; not completable in the plan/impl session before close. **Escalation path (D-B3):** run the spike post-close, then next day `--equiv-against`; if `max|Δ| ≤ 4dp` → keep `_ENGINE_VERSION="3"` (no bump); if a material (>4dp) gap → escalate to an `_ENGINE_VERSION` bump + a fresh ADR 0019 addendum BEFORE trusting the flow factor's forward metrics.

- [ ] **Step 7: Commit**

```bash
git add CONTEXT.md docs/adr/0019-monitor-capital-flow-factor.md docs/adr/0020-monitor-dual-track-valuation.md README.md CHANGELOG.md docs/2026-07-02-monitor-cn-egress-lightup/items/001-spec.md
git commit -m "docs(monitor): CN-egress light-up — CONTEXT/ADR/README/CHANGELOG + Tier-0 findings (slice 5)"
```

---

# Final verification

### Task 16: Full slice-test sweep + engine/schema invariants

- [ ] **Step 1: Run every touched test module (commands per-file — dir hangs)**

Run:
```bash
uv run pytest tests/test_http_proxy.py tests/monitor/test_em_raw.py \
  tests/monitor/test_industry_valuation.py tests/monitor/test_flow_batch_fetch.py \
  tests/monitor/test_flow_series_store.py tests/monitor/eval/test_trace.py \
  tests/monitor/eval/test_structural.py tests/ops/test_launchd_monitor.py \
  tests/scripts/test_phase0_flow_batch_spike.py \
  tests/fundamentals/test_akshare_stock_valuation.py -v
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -v
uv run pytest tests/commands/test_monitor_cmd_valuation.py -v
uv run pytest tests/commands/test_monitor_flow_capture.py -v
```
Expected: all PASS.

- [ ] **Step 2: Assert engine untouched + exactly one schema bump**

Run:
```bash
grep -n '_ENGINE_VERSION = "3"' src/irc/commands/monitor_cmd.py
grep -rn '_SCHEMA_VERSION = "5"' src/irc/monitor/eval/trace.py
grep -c '_SCHEMA_VERSION = ' src/irc/monitor/eval/trace.py
```
Expected: engine line present (`"3"`); schema `"5"` present; exactly ONE `_SCHEMA_VERSION =` assignment.

- [ ] **Step 3: Assert no akshare re-introduced in the industry leg**

Run:
```bash
grep -n "stock_board_industry_name_em\|stock_individual_info_em" src/irc/monitor/em_raw.py src/irc/monitor/industry_valuation.py || echo "OK: no akshare industry wrappers"
```
Expected: `OK: no akshare industry wrappers` (the default path uses em_raw; existing tests inject `fetch`).

- [ ] **Step 4: Lint**

Run: `uv run ruff check src tests`
Expected: no errors (line-length 100, py312). Fix any lambda-assignment (`E731`) findings by converting `fetch = lambda ...` to a nested `def` if ruff flags them.

- [ ] **Step 5: Final commit if any lint fixes**

```bash
git add -A && git commit -m "chore(monitor): lint + final invariants for CN-egress light-up"
```

---

## Self-review (author checklist — done)

**Spec coverage:** D1/D2 → Task 3, Task 5/8 (proxy at edges), Task 7. D3 → Tasks 4–6 (em_raw + empty-not-cached). D4 f9 sanity → Task 2. D5 (B2 un-shelve) → Tasks 8–10. D6 (hybrid + capture) → Tasks 11–13. D7 (seed) → Task 9 `seed_from_per_symbol` + README op. D8 (valuation backfill) → Task 7 + README. D9 (schema + flow_source + warm-up) → Task 14. D10 (per-symbol retired) → Task 10. Slices 0–5 all mapped. §6 locked tests: trace schema (Task 14), fetch_flow_series callers (Task 10, per-file), industry identity test (Task 6, existing untouched), launchd job (Task 13). §7 exit gates: Tier-0 (Tasks 1–2 + deferred GATE-2 documented Task 15), Tier-1 (Task 16), Tier-2 (README post-merge ops). §8 traps encoded in Global Constraints + per-task notes.

**Placeholder scan:** every code step carries concrete code; the one soft spot (Task 14 `_holding_metrics` locals) gives the exact two additions to make and how to adapt names — an implementer can execute it. No TBD/TODO.

**Type consistency:** `FlowSeries` reused from `flow_fetch`; `flow_slice: dict` threaded consistently Task 10↔11; `_load_flow_store_slice` name identical across monkeypatch + impl; `flow_source` values `"batch_today"`/`"per_symbol_seed"` consistent Task 14; `run_flow_capture` signature identical CLI↔impl↔test.
