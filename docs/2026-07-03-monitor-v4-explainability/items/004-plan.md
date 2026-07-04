# Item 004 — WS-4 Industry Fill (P7 batch-first 行业 + P8 board-PE staleness): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the two dead industry surfaces in the daily monitor brief: 行业 names go batch-first (`f127` rides the ONE existing `ulist.np` call into a new cross-day store; per-symbol `stock/get` demoted to fallback-only), and board PE gains fetch-first ordering + three-state serve-while-stale (FRESH / STALE-N ≤3 td feeds factor math / DARK) with an honest reader-facing age tag.

**Architecture:** Two new small modules own the new behavior — `industry_map_store.py` (cross-day `{symbol: {industry, seen_at}}` store, refresh-on-seen, ≤30 **calendar**-day serve-while-stale) and `board_pe_staleness.py` (board-PE day-file I/O + pure trading-day age math + the non-empty stale scan). `flow_batch_fetch.parse_ulist` widens to `(f184, f127)` tuples; `fetch_industry_pe` returns `(table, BoardPeFreshness)`; `monitor_cmd` reorders the board-PE fetch to run-level before the per-fund loop and threads `(table, freshness)` + the serving map through `_process_fund` → `_build_full_basket_metrics`. Dual-track valuation math (`_dual_track.py`, weights, clamp) is untouched — this item changes what data reaches it and how honestly its age is labelled.

**Tech Stack:** Python 3.12, pytest, frozen dataclasses, pure renderers, injectable fetches. No new dependencies (stdlib + existing pandas/requests only).

**Spec:** `docs/2026-07-03-monitor-v4-explainability/items/004-spec.md` (18 ACs; RD-1…RD-9 in `## Resolved decisions` govern; corrected lines govern over strike-throughs). Grill: `items/004-grill.md`. ADR 0020 addendum + CONTEXT.md terms (*Board-PE freshness state*, *Stock-industry map (cross-day store)*) were already written at the grill — Task 10 only verifies + syncs the ops manual/diagram/CHANGELOG.

## Global Constraints

- **Branch:** you are on `claude/monitor-v4-explainability-004` (already cut from `autodev/monitor-v4-explainability-feature`). Commit per task; do NOT push.
- **Schema stays `"7"`** — `trace.SCHEMA_VERSION` unchanged; `board_pe_freshness` is additive under it (pin test required, AC-11). The `trace.py:14-17` comment block already anticipates this — extend it, don't bump.
- **`_ENGINE_VERSION = "4"` untouched** (`src/irc/commands/monitor_cmd.py:83`); no weight/band/threshold change anywhere (AC-16).
- **`KNOWN_NA_REASONS` untouched** (`src/irc/monitor/factors.py:30`) — `industry_no_data` remains a per-stock HoldingMetric reason covering DARK; no new NA vocabulary (AC-16). No new DARK render string.
- **`VERSION` file NOT bumped**; CHANGELOG entry under `[Unreleased]` (Task 10).
- **Locked copy (verbatim, no variants):** age tag `板块PE 引用 <date> · N个交易日前`; panel reasons `board_pe FRESH` / `board_pe STALE-N (as_of <date>)` / `board_pe DARK`.
- **Purity:** `merge_seen` / `fresh_slice` / `trading_day_age` / freshness decision / tag rendering are pure (no clock, no I/O, no argument mutation). New store I/O lives in `industry_map_store.py` edges + `monitor_cmd`; the staleness scan I/O in `board_pe_staleness.py`'s thin edge.
- **NO live network in any test** — `http_get` / `fetch` / `sleep` stay injectable; fixtures only. AC-15's live spot-check is a SHIP-PHASE gate run by the orchestrator (see final section), never a unit test.
- **Degrade, never crash the brief:** every new edge path (store read/write, staleness scan, board-PE fallback, capture-job board-PE) catches, logs WARNING, degrades (empty map / DARK / no tag).
- **Byte-stability:** store writes sorted-key + `atomic_write_text`; same inputs → identical bytes.
- **`flow_reconciliation` byte-identity:** NO edit to `eval/structural.flow_reconciliation` or any f184 value path; `_coerce` untouched; the AC-1 flow-identity test is the parse-level unit guard.
- **Test hazards:** `tests/commands/` must be run PER-FILE (whole-dir hangs, pre-existing). `tests/monitor/golden/report.html` is byte-compared — this plan adds NO report CSS and only a trailing-defaulted `FundView` field, so the golden file must NOT change (verified in Task 6).
- **Size budgets:** new modules < 200 lines; `src/irc/monitor/industry_valuation.py` must NOT grow past its current 207 lines (Task 4 moves its day-file JSON helpers into `board_pe_staleness.py` to guarantee this); functions < 20 lines ideal.
- **Style:** `uv run ruff check` clean (line-length 100, py312); frozen dataclasses; trailing-defaulted additive params only.
- **Proxy/throttle posture unchanged:** all push2 traffic keeps `resolve_cn_proxy` routing; `cached_fetch` breaker/backoff/pacing constants untouched.

## File Structure

| File | Change |
|---|---|
| `src/irc/monitor/flow_batch_fetch.py` | Modify — `parse_ulist` → `(f184, f127)` tuples; `fetch_flow_today_batch` → two-dict tuple, `fields=f12,f14,f184,f127` (Task 1) |
| `tests/monitor/test_flow_batch_fetch.py` | Rewrite — tuple shape + f127 fixtures + flow-identity guard (Task 1) |
| `src/irc/monitor/industry_map_store.py` | **Create** — cross-day store: `load_store` / `merge_seen` / `fresh_slice` / `record_seen` (Task 2) |
| `tests/monitor/test_industry_map_store.py` | **Create** — mirror tests (Task 2) |
| `src/irc/monitor/board_pe_staleness.py` | **Create** — `BoardPeFreshness`, `freshness_dict`, `trading_day_age`, `read_day_table`/`write_day_table`, `newest_nonempty`, `stale_fallback` (Task 3) |
| `tests/monitor/test_board_pe_staleness.py` | **Create** — mirror tests incl. RD-2 boundary + RD-3 calendar scoping (Task 3) |
| `src/irc/monitor/industry_valuation.py` | Modify — `fetch_industry_pe` → `(table, BoardPeFreshness)`, day-file helpers moved out; MUST end ≤ 207 lines (Task 4) |
| `tests/monitor/test_industry_valuation.py` | Modify — tuple unpack + FRESH/STALE/DARK/Q5 tests (Task 4) |
| `src/irc/monitor/eval/trace.py` | Modify — `build_eval_trace(board_pe_freshness=None)` → run-level key; comment extended (Task 5) |
| `tests/monitor/eval/test_trace.py` | Modify — top-level key set + additive-under-"7" pin + None back-compat (Task 5) |
| `src/irc/monitor/eval/structural.py` | Modify — `valuation_coverage_health(..., board_pe_freshness=None)` + `_board_pe_reason` (Task 5) |
| `tests/monitor/eval/test_structural.py` | Modify — per-state + back-compat + never-gates tests (Task 5) |
| `src/irc/monitor/render_drilldown.py` | Modify — `board_pe_age_note_html` + `drilldown_section_html`/`drilldown_page_html` threading (Task 6) |
| `tests/monitor/test_render_drilldown.py` | Modify — tag text/absence + row[6] threading tests (Task 6) |
| `src/irc/monitor/render_types.py` | Modify — trailing-defaulted `FundView.board_pe_freshness` (Task 6) |
| `src/irc/monitor/render_html.py` | Modify — `_drilldown_block` appends the age note (Task 6) |
| `tests/monitor/test_render_html.py` | Modify — card tag present/absent tests; golden UNCHANGED (Task 6) |
| `src/irc/commands/monitor_cmd.py` | Modify — Tasks 1 (shims), 4 (shim), 7 (batch widen + store + serving map + consume order), 8 (fetch-first threading), 9 (capture) |
| `tests/commands/test_monitor_cmd_industry.py` | **Create** — run-level wiring tests: consume order, store merge, fetch-order recorder, trace/report/panel wiring (Tasks 7, 8) |
| `tests/commands/test_monitor_cmd.py` | Modify — `_batch_flow_industry` rename at 2 sites (Task 7) |
| `tests/commands/test_monitor_cmd_drilldown.py` | Modify — rename at 1 site (Task 7) |
| `tests/commands/test_monitor_constituent.py` | Modify — rename at 1 site (Task 7) |
| `tests/commands/test_monitor_cmd_valuation.py` | Modify — `_patch_common` tuple-returning `fetch_industry_pe` (Task 4) |
| `tests/commands/test_monitor_flow_capture.py` | Rewrite — tuple fetch, secid widening + slice-back, industry merge, P8c (Tasks 1, 9) |
| `docs/monitor/README.md`, `docs/diagrams/monitor-workflow.html`, `CHANGELOG.md` | Modify — doc sync (Task 10) |

**Verified line anchors (re-verify before editing; 001–003 have landed on this branch):** `monitor_cmd.py:83` `_ENGINE_VERSION`, `:212-222` `_provisional_flow_note`, `:315-335` `_build_full_basket_metrics` (board-PE fetch at `:329`), `:565-653` `_compute_gates` (bare `valuation_coverage_health(projection)` at `:638`), `:656-695` `_write_eval_artifacts`, `:850-945` `_process_fund`, `:970-1092` `run_monitor` (`load_trading_days` at `:1028`), `:1098-1112` `_capture_union_symbols`, `:1115-1137` `run_flow_capture` (batch call at `:1127`); `render_html.py:231-240` `_drilldown_block`; `render_drilldown.py:239-268` section/page; `structural.py:223-245` `valuation_coverage_health`; `trace.py:14-17` schema comment, `:203-224` `build_eval_trace`.

---

### Task 1: `flow_batch_fetch` — f127 rides the batch (AC-1, AC-2)

**Files:**
- Modify: `src/irc/monitor/flow_batch_fetch.py`
- Modify (keep-green shims): `src/irc/commands/monitor_cmd.py:219` (`_provisional_flow_note` body), `src/irc/commands/monitor_cmd.py:1127` (`run_flow_capture` unpack)
- Test: `tests/monitor/test_flow_batch_fetch.py` (rewrite), `tests/commands/test_monitor_flow_capture.py` (stub shapes)

**Interfaces:**
- Produces: `parse_ulist(payload) -> dict[str, tuple[float | None, str | None]]` (per f12-symbol `(f184_flow, f127_industry)`); `fetch_flow_today_batch(symbols, *, http_get=None) -> tuple[dict[str, float | None], dict[str, str | None]]` — every requested symbol present in BOTH maps; still exactly ONE HTTP GET via `resolve_cn_proxy`, `fields=f12,f14,f184,f127`.
- Consumed by: Tasks 7 (12:15 site) and 9 (15:45 site).

- [ ] **Step 1: Rewrite the test file (failing)**

Replace the full contents of `tests/monitor/test_flow_batch_fetch.py` with:

```python
from __future__ import annotations

from irc.monitor.flow_batch_fetch import (
    build_secids, fetch_flow_today_batch, parse_ulist,
)


def test_parse_ulist_percent_point_boundaries_with_f127():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 1.0, "f127": "酿酒行业"},
        {"f12": "000651", "f184": 3.0, "f127": "家电行业"},
        {"f12": "300750", "f184": 0.01, "f127": "电池"},
        {"f12": "600690", "f184": 0.03, "f127": "家电行业"},
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": (1.0, "酿酒行业"), "000651": (3.0, "家电行业"),
                   "300750": (0.01, "电池"), "600690": (0.03, "家电行业")}


def test_parse_ulist_f127_absent_blank_dash_whitespace_are_none():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 1.0},                      # f127 missing
        {"f12": "000651", "f184": 2.0, "f127": ""},          # blank
        {"f12": "300750", "f184": 3.0, "f127": "-"},         # dash sentinel
        {"f12": "600690", "f184": 4.0, "f127": "   "},       # whitespace-only
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": (1.0, None), "000651": (2.0, None),
                   "300750": (3.0, None), "600690": (4.0, None)}


def test_parse_ulist_f127_stripped_and_nonstring_is_none():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 1.0, "f127": " 酿酒行业 "},
        {"f12": "000651", "f184": 2.0, "f127": 42},          # never fabricated
    ]}}
    out = parse_ulist(payload)
    assert out == {"600519": (1.0, "酿酒行业"), "000651": (2.0, None)}


def test_parse_ulist_blank_and_dash_f184_are_none():
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": "-"}, {"f12": "000651", "f184": ""},
        {"f12": "300750", "f184": None},
    ]}}
    assert parse_ulist(payload) == {"600519": (None, None), "000651": (None, None),
                                    "300750": (None, None)}


def test_parse_ulist_data_null_is_empty():
    assert parse_ulist({"data": None}) == {}
    assert parse_ulist({}) == {}


def test_parse_ulist_dict_diff_shape_tolerated():
    payload = {"data": {"diff": {"0": {"f12": "600519", "f184": 4.86, "f127": "酿酒行业"}}}}
    assert parse_ulist(payload) == {"600519": (4.86, "酿酒行业")}


def test_parse_ulist_flow_half_identity_with_pre_change_parser():
    """AC-1 flow-identity guard: for any fixture payload, the flow halves equal
    the PRE-CHANGE parse_ulist output exactly (guards the flow_reconciliation
    byte-identity contract at the parse level — the f184 coercion path is
    untouched by the f127 widening)."""
    payload = {"data": {"diff": [
        {"f12": "600519", "f184": 4.86, "f127": "酿酒行业"},
        {"f12": "000651", "f184": "-", "f127": "家电行业"},
        {"f12": "300750", "f184": 0.01},
        {"f12": "600690", "f184": None, "f127": ""},
    ]}}
    pre_change = {"600519": 4.86, "000651": None, "300750": 0.01, "600690": None}
    assert {sym: pair[0] for sym, pair in parse_ulist(payload).items()} == pre_change


def test_build_secids_prefixes():
    assert build_secids(("600519", "000651", "300750")) == "1.600519,0.000651,0.300750"


def test_fetch_flow_today_batch_one_call_two_maps_via_proxy(monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "1.2.3.4:9")
    calls = {"n": 0}

    def http_get(url, *, params, headers, timeout, proxies=None):
        calls["n"] += 1
        assert proxies == {"http": "http://1.2.3.4:9", "https": "http://1.2.3.4:9"}
        assert params["secids"] == "1.600519,0.000651"
        assert params["fields"] == "f12,f14,f184,f127"     # AC-2: ONE call, +f127
        return {"data": {"diff": [{"f12": "600519", "f184": 4.86, "f127": "酿酒行业"},
                                  {"f12": "000651", "f184": 7.42}]}}

    flow, industry = fetch_flow_today_batch(("600519", "000651"), http_get=http_get)
    assert calls["n"] == 1                       # ONE batch call, not per-symbol
    assert flow == {"600519": 4.86, "000651": 7.42}
    assert industry == {"600519": "酿酒行业", "000651": None}


def test_fetch_flow_today_batch_blank_body_all_none():
    flow, industry = fetch_flow_today_batch(
        ("600519",), http_get=lambda *a, **k: {"data": None})
    assert flow == {"600519": None}              # never fabricated
    assert industry == {"600519": None}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_flow_batch_fetch.py -q`
Expected: FAILs (tuple shape mismatches / `fields` assertion / unpack errors).

- [ ] **Step 3: Implement**

In `src/irc/monitor/flow_batch_fetch.py`, replace `parse_ulist` and `fetch_flow_today_batch` (keep `_UT`/`_HEADERS`/`_ULIST_URL`/`_secid`/`build_secids`/`_coerce`/`_default_http_get` exactly as-is), and add `_coerce_industry` directly after `_coerce`:

```python
def _coerce_industry(value: object) -> str | None:
    """Pure: f127 → stripped non-empty industry string, else None (missing key /
    '-' / '' / whitespace / non-string → None — never fabricated)."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text and text != "-" else None


def parse_ulist(payload: dict) -> dict[str, tuple[float | None, str | None]]:
    """Pure: {f12 → (f184 percent-points NO /100, f127 行业 | None)}. Tolerant of
    list/dict diff shape. Blank/missing data → {} (→ all None upstream, never
    fabricated)."""
    diff = (payload.get("data") or {}).get("diff") if isinstance(payload, dict) else None
    rows = list(diff.values()) if isinstance(diff, dict) else (list(diff) if isinstance(diff, list) else [])
    return {str(r.get("f12")): (_coerce(r.get("f184")), _coerce_industry(r.get("f127")))
            for r in rows}
```

```python
def fetch_flow_today_batch(
    symbols, *, http_get=None,
) -> tuple[dict[str, float | None], dict[str, str | None]]:
    """EDGE: ONE ulist.np call for all symbols via the CN proxy → (flow_by_symbol,
    industry_by_symbol). Every requested symbol is present in BOTH maps (None when
    the endpoint returned no row/field). Non-A-share lines never enter secids
    (uncovered, as today). No new call, no pagination (AC-2)."""
    get = http_get or _default_http_get
    proxy = resolve_cn_proxy()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    params = {"ut": _UT, "fltt": "2", "invt": "2", "np": "1", "dect": "1",
              "secids": build_secids(symbols), "fields": "f12,f14,f184,f127"}
    payload = get(_ULIST_URL, params=params, headers=_HEADERS, timeout=20,
                  proxies=proxies)
    by_symbol = parse_ulist(payload)
    flow: dict[str, float | None] = {}
    industry: dict[str, str | None] = {}
    for s in dict.fromkeys(symbols):
        f184, f127 = by_symbol.get(s, (None, None))
        flow[s], industry[s] = f184, f127
    return flow, industry
```

Update the module docstring's first line mention of fields from `f12,f14,f184` to `f12,f14,f184,f127` and note "returns (flow, industry) maps; f127 batch-first per ADR 0020 addendum 2026-07-03".

- [ ] **Step 4: Keep-green shims at the two production call sites**

In `src/irc/commands/monitor_cmd.py`, `_provisional_flow_note` (line ~219) — change ONLY the `try` body:

```python
    try:
        flow, _industry = fetch_flow_today_batch(tuple(symbols))
        return flow
```

In `run_flow_capture` (line ~1127) — change ONLY the unpack line:

```python
        by_symbol, _industry = fetch_flow_today_batch(symbols)
```

(Both sites are fully restructured in Tasks 7/9; these shims keep every commit green.)

- [ ] **Step 5: Update the flow-capture test stubs to the new shape**

In `tests/commands/test_monitor_flow_capture.py`:
- line 18-19: `monkeypatch.setattr(mc, "fetch_flow_today_batch", lambda symbols: ({"600519": 4.0, "000651": 7.0}, {"600519": None, "000651": None}))`
- line 31-32: `monkeypatch.setattr(mc, "fetch_flow_today_batch", lambda symbols: ({"600519": 11.78}, {"600519": None}))` and change the assertion to `assert note == {"600519": 11.78}` (unchanged — `_provisional_flow_note` still returns the flow half).

- [ ] **Step 6: Run to verify green**

Run: `uv run pytest tests/monitor/test_flow_batch_fetch.py tests/commands/test_monitor_flow_capture.py -q`
Expected: all PASS.

Run: `uv run pytest tests/scripts/test_phase0_flow_batch_spike.py -q`
Expected: PASS unchanged (Q11 — the spike has its own private `_parse_ulist`; NO edit there).

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check src/irc/monitor/flow_batch_fetch.py src/irc/commands/monitor_cmd.py tests/monitor/test_flow_batch_fetch.py tests/commands/test_monitor_flow_capture.py
git add -A && git commit -m "feat(monitor): f127 industry rides the ulist.np batch — parse_ulist (flow,industry) tuples, two-map fetch (004 AC-1/AC-2)"
```

---

### Task 2: New `industry_map_store.py` — cross-day 行业 store (AC-4)

**Files:**
- Create: `src/irc/monitor/industry_map_store.py`
- Test: `tests/monitor/test_industry_map_store.py`

**Interfaces (produced, consumed by Tasks 7/9):**
- `load_store(path: Path) -> dict[str, dict]` — missing/corrupt/malformed rows → `{}`/dropped with WARNING.
- `merge_seen(store, today: str, industry_by_symbol) -> dict` — PURE, new dict; upserts non-None non-blank with `seen_at=today` (refresh-on-seen); None/blank skipped.
- `fresh_slice(store, today: str, max_age_days: int = 30) -> dict[str, str]` — PURE; ≤30 **calendar** days (Q4); unparseable `seen_at` dropped.
- `record_seen(path, today, industry_by_symbol) -> dict` — EDGE load→merge→atomic write; a no-op merge writes NOTHING (RD-4 `{sym: None}`-writes-nothing).

- [ ] **Step 1: Write the failing tests**

Create `tests/monitor/test_industry_map_store.py`:

```python
from __future__ import annotations

import json
import logging
from pathlib import Path

from irc.monitor.industry_map_store import fresh_slice, load_store, merge_seen, record_seen


def test_load_store_missing_file_is_empty(tmp_path: Path):
    assert load_store(tmp_path / "stock_industry_map.json") == {}


def test_load_store_corrupt_file_degrades_to_empty(tmp_path: Path, caplog):
    p = tmp_path / "stock_industry_map.json"
    p.write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert load_store(p) == {}
    assert any("unreadable" in r.message for r in caplog.records)


def test_load_store_malformed_rows_dropped_not_crash(tmp_path: Path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "600519": {"industry": "酿酒行业", "seen_at": "2026-07-03"},
        "000651": {"industry": None, "seen_at": "2026-07-03"},
        "300750": "just-a-string",
    }, ensure_ascii=False), encoding="utf-8")
    assert load_store(p) == {"600519": {"industry": "酿酒行业", "seen_at": "2026-07-03"}}


def test_merge_seen_upserts_and_refreshes_seen_at_even_when_unchanged():
    store = {"600519": {"industry": "酿酒行业", "seen_at": "2026-06-01"}}
    merged = merge_seen(store, "2026-07-03", {"600519": "酿酒行业", "000651": "家电行业"})
    # refresh-on-seen: seen_at refreshed even though the industry string is unchanged
    assert merged["600519"] == {"industry": "酿酒行业", "seen_at": "2026-07-03"}
    assert merged["000651"] == {"industry": "家电行业", "seen_at": "2026-07-03"}


def test_merge_seen_skips_none_and_blank_and_never_mutates():
    store = {"600519": {"industry": "酿酒行业", "seen_at": "2026-06-01"}}
    before = {k: dict(v) for k, v in store.items()}
    merged = merge_seen(store, "2026-07-03", {"000651": None, "300750": "", "600690": "  "})
    assert set(merged) == {"600519"}         # absence ≠ evidence: nothing written
    assert store == before                   # pure: argument not mutated
    assert merged is not store


def test_fresh_slice_serves_within_30_calendar_days_only():
    store = {
        "600519": {"industry": "酿酒行业", "seen_at": "2026-06-03"},   # exactly 30 d → served
        "000651": {"industry": "家电行业", "seen_at": "2026-06-02"},   # 31 d → dropped
        "300750": {"industry": "电池", "seen_at": "2026-07-03"},       # today → served
    }
    assert fresh_slice(store, "2026-07-03") == {"600519": "酿酒行业", "300750": "电池"}


def test_fresh_slice_unparseable_seen_at_dropped_not_served():
    store = {"600519": {"industry": "酿酒行业", "seen_at": "not-a-date"}}
    assert fresh_slice(store, "2026-07-03") == {}


def test_record_seen_roundtrip_and_byte_stable(tmp_path: Path):
    p = tmp_path / "stock_industry_map.json"
    record_seen(p, "2026-07-02", {"600519": "酿酒行业"})
    record_seen(p, "2026-07-03", {"000651": "家电行业"})
    assert load_store(p) == {
        "600519": {"industry": "酿酒行业", "seen_at": "2026-07-02"},
        "000651": {"industry": "家电行业", "seen_at": "2026-07-03"},
    }
    a = p.read_bytes()
    record_seen(p, "2026-07-03", {"000651": "家电行业"})   # same-day no-op merge
    assert p.read_bytes() == a                              # byte-stable


def test_record_seen_all_none_input_writes_nothing(tmp_path: Path):
    p = tmp_path / "stock_industry_map.json"
    record_seen(p, "2026-07-03", {"600519": None})
    assert not p.exists()                    # RD-4: a no-op merge never creates the file
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_industry_map_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.industry_map_store'`.

- [ ] **Step 3: Implement**

Create `src/irc/monitor/industry_map_store.py`:

```python
"""EDGE + pure merge: cross-day stock→东财行业 store (ADR 0020 addendum 2026-07-03).

data/monitor/stock_industry_map.json = {symbol: {"industry": str, "seen_at":
"YYYY-MM-DD"}}. Filled batch-first from the f127 field riding the ONE daily
ulist.np call (both call sites: 12:15 brief + 15:45 capture); per-symbol
fallback results merge too (Q3). Refresh-on-seen; serve-while-stale ≤ 30
CALENDAR days — deliberately NOT trading days (industry membership is
quasi-static; see CONTEXT.md 'Stock-industry map (cross-day store)').
Absence ≠ evidence: None/blank never written (RD-4 — a throttle classifies
TRANSIENT upstream and can never reach here as a string). Corrupt/missing →
{} (never crash the brief). Byte-stable atomic writes; a no-op merge writes
nothing. Patterned on flow_series_store.py.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from irc.io_utils import atomic_write_text

_log = logging.getLogger(__name__)
MAX_AGE_DAYS = 30


def _valid_row(row: object) -> bool:
    return (isinstance(row, dict) and isinstance(row.get("industry"), str)
            and isinstance(row.get("seen_at"), str))


def load_store(path: Path) -> dict[str, dict]:
    """Load the store; missing/corrupt file → {} with a WARNING; malformed rows
    dropped, never served (same degrade posture as flow_series_store.load_store)."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("industry_map_store: unreadable store %s; degrading", path,
                     exc_info=True)
        return {}
    if not isinstance(raw, dict):
        _log.warning("industry_map_store: non-dict store %s; degrading", path)
        return {}
    out: dict[str, dict] = {}
    for sym, row in raw.items():
        if _valid_row(row):
            out[str(sym)] = {"industry": row["industry"], "seen_at": row["seen_at"]}
        else:
            _log.warning("industry_map_store: malformed row for %s; dropped", sym)
    return out


def merge_seen(store: dict, today: str, industry_by_symbol: dict) -> dict[str, dict]:
    """Pure (NEW dict, no mutation): upsert every non-None, non-blank industry as
    {industry, seen_at: today}. REFRESH-ON-SEEN: seen_at refreshes even when the
    industry string is unchanged. None/blank skipped (absence ≠ evidence)."""
    fresh = {
        str(sym): {"industry": ind.strip(), "seen_at": today}
        for sym, ind in industry_by_symbol.items()
        if isinstance(ind, str) and ind.strip()
    }
    return {**store, **fresh}


def _within(seen_at: str, today: str, max_age_days: int) -> bool:
    try:
        return (date.fromisoformat(today) - date.fromisoformat(seen_at)).days <= max_age_days
    except ValueError:
        return False   # unparseable seen_at → dropped, not served


def fresh_slice(store: dict, today: str, max_age_days: int = MAX_AGE_DAYS) -> dict[str, str]:
    """Pure: {symbol: industry} for rows seen within ≤ max_age_days CALENDAR days
    of today (Q4 — quasi-static attribute, NOT a market-data freshness window)."""
    return {sym: row["industry"] for sym, row in store.items()
            if _within(row.get("seen_at", ""), today, max_age_days)}


def record_seen(path: Path, today: str, industry_by_symbol: dict) -> dict[str, dict]:
    """EDGE: load → merge → byte-stable atomic write → merged store. A no-op merge
    (e.g. an all-None fallback result) writes NOTHING — the file is not even
    created (RD-4)."""
    store = load_store(path)
    merged = merge_seen(store, today, industry_by_symbol)
    if merged != store:
        atomic_write_text(path, json.dumps(merged, ensure_ascii=False, indent=2,
                                           sort_keys=True))
    return merged
```

- [ ] **Step 4: Run to verify green**

Run: `uv run pytest tests/monitor/test_industry_map_store.py -q`
Expected: 9 passed.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/monitor/industry_map_store.py tests/monitor/test_industry_map_store.py
git add -A && git commit -m "feat(monitor): cross-day stock-industry map store — refresh-on-seen, <=30d fresh_slice, byte-stable (004 AC-4)"
```

---

### Task 3: New `board_pe_staleness.py` — freshness states + non-empty stale scan (AC-9 scan/age, AC-10)

**Files:**
- Create: `src/irc/monitor/board_pe_staleness.py`
- Test: `tests/monitor/test_board_pe_staleness.py`

**Interfaces (produced):**
- `BoardPeFreshness` frozen dataclass: `state: str` (`"FRESH" | "STALE" | "DARK"`), `as_of: str | None`, `age_td: int | None`.
- `freshness_dict(f: BoardPeFreshness | None) -> dict | None` — `{"state","as_of","age_td"}` trace/panel projection.
- `trading_day_age(as_of: str, today: str, trading_days) -> int | None` — PURE, AC-10: `N = |{trading days d : as_of < d ≤ today}|`.
- `read_day_table(cache_dir: Path, day: str) -> dict | None` / `write_day_table(cache_dir, day, table)` — day-file JSON I/O (moved here from `industry_valuation.py` in Task 4 to hold its 207-line budget; same semantics: unreadable → None + WARNING; byte-stable `.tmp.{pid} → os.replace`).
- `newest_nonempty(cache_dir: Path, today: str) -> tuple[str, dict] | None` — EDGE scan, newest→older, skips empty `{}` and unreadable files (RD-2).
- `stale_fallback(cache_dir: Path, today: str, trading_days) -> tuple[dict, BoardPeFreshness]` — the stale branch: STALE ≤3 td serves the table; calendar None/empty → DARK (RD-3, stale branch only); never raises.

- [ ] **Step 1: Write the failing tests**

Create `tests/monitor/test_board_pe_staleness.py`:

```python
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from irc.monitor.board_pe_staleness import (
    BoardPeFreshness, freshness_dict, newest_nonempty, read_day_table,
    stale_fallback, trading_day_age, write_day_table,
)

# Mon 06-29 … Fri 07-03, all trading days
_TDS = frozenset({date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1),
                  date(2026, 7, 2), date(2026, 7, 3)})


def _day(cache_dir: Path, day: str, table: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{day}.json").write_text(
        json.dumps(table, ensure_ascii=False), encoding="utf-8")


# ---- trading_day_age (AC-10) ----


def test_age_counts_trading_days_after_as_of_up_to_today():
    assert trading_day_age("2026-07-01", "2026-07-03", _TDS) == 2


def test_age_weekend_holiday_gap_counts_zero():
    # as_of Friday, today Sunday: no trading day in (07-03, 07-05] → N = 0
    assert trading_day_age("2026-07-03", "2026-07-05", _TDS) == 0


def test_age_unparseable_dates_is_none():
    assert trading_day_age("garbage", "2026-07-03", _TDS) is None


# ---- day-file I/O (moved from industry_valuation in Task 4) ----


def test_day_table_write_read_roundtrip_byte_stable(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    write_day_table(cache, "2026-07-03", {"银行": 6.5, "白酒": 30.2})
    assert read_day_table(cache, "2026-07-03") == {"银行": 6.5, "白酒": 30.2}
    a = (cache / "2026-07-03.json").read_bytes()
    write_day_table(cache, "2026-07-03", {"白酒": 30.2, "银行": 6.5})   # same content
    assert (cache / "2026-07-03.json").read_bytes() == a                # sorted keys


def test_day_table_missing_or_unreadable_is_none(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    assert read_day_table(cache, "2026-07-03") is None
    cache.mkdir(parents=True)
    (cache / "2026-07-02.json").write_text("{corrupt", encoding="utf-8")
    assert read_day_table(cache, "2026-07-02") is None


# ---- newest_nonempty scan (RD-2) ----


def test_scan_skips_empty_and_unreadable_continues_older(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-06-30", {"银行": 6.5})
    _day(cache, "2026-07-01", {})                              # pre-light-up {} landmine
    (cache / "2026-07-02.json").write_text("{corrupt", encoding="utf-8")
    assert newest_nonempty(cache, "2026-07-03") == ("2026-06-30", {"银行": 6.5})


def test_scan_ignores_today_and_future_files(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-03", {"银行": 6.5})                    # today: FRESH's business
    _day(cache, "2026-07-04", {"白酒": 30.0})                   # future: never
    assert newest_nonempty(cache, "2026-07-03") is None


def test_scan_missing_dir_is_none(tmp_path: Path):
    assert newest_nonempty(tmp_path / "nope", "2026-07-03") is None


# ---- stale_fallback (AC-9 stale branch + RD-3 calendar scoping) ----


def test_stale_within_3td_serves_table_and_names_date(tmp_path: Path):
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-01", {"银行": 6.5})
    table, f = stale_fallback(cache, "2026-07-03", _TDS)
    assert table == {"银行": 6.5}
    assert f == BoardPeFreshness("STALE", "2026-07-01", 2)


def test_stale_boundary_n3_serves_n4_darkens(tmp_path: Path):
    cache3 = tmp_path / "ip3"
    _day(cache3, "2026-06-30", {"银行": 6.5})                   # N=3 (07-01, 02, 03)
    table, f = stale_fallback(cache3, "2026-07-03", _TDS)
    assert table == {"银行": 6.5}
    assert (f.state, f.age_td) == ("STALE", 3)

    cache4 = tmp_path / "ip4"
    _day(cache4, "2026-06-29", {"银行": 6.5})                   # N=4 (06-30 … 07-03)
    table, f = stale_fallback(cache4, "2026-07-03", _TDS)
    assert table == {}
    assert f == BoardPeFreshness("DARK", "2026-06-29", 4)


def test_empty_1td_file_skipped_nonempty_3td_serves(tmp_path: Path):
    """RD-2 boundary test verbatim: an empty {} day file 1 td old + a non-empty
    file 3 td old → the 3-td table serves as STALE-3, never the empty one."""
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-02", {})
    _day(cache, "2026-06-30", {"银行": 6.5})
    table, f = stale_fallback(cache, "2026-07-03", _TDS)
    assert table == {"银行": 6.5}
    assert (f.state, f.as_of, f.age_td) == ("STALE", "2026-06-30", 3)


def test_calendar_unavailable_darkens_stale_branch_only(tmp_path: Path):
    """Q5/RD-3: no calendar → an honest N is uncomputable → DARK; as_of still
    names the newest non-empty cached day. (FRESH is calendar-independent —
    covered in test_industry_valuation.py.)"""
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-02", {"银行": 6.5})
    for dead in (None, frozenset()):
        table, f = stale_fallback(cache, "2026-07-03", dead)
        assert table == {}
        assert f == BoardPeFreshness("DARK", "2026-07-02", None)


def test_nothing_cached_is_dark_none(tmp_path: Path):
    table, f = stale_fallback(tmp_path / "industry_pe", "2026-07-03", _TDS)
    assert table == {}
    assert f == BoardPeFreshness("DARK", None, None)


def test_nontrading_day_rerun_yields_stale_0(tmp_path: Path):
    # Q6: a Sunday rerun serving Friday's table → STALE with N = 0 (date named).
    cache = tmp_path / "industry_pe"
    _day(cache, "2026-07-03", {"银行": 6.5})
    table, f = stale_fallback(cache, "2026-07-05", _TDS)
    assert table == {"银行": 6.5}
    assert (f.state, f.age_td, f.as_of) == ("STALE", 0, "2026-07-03")


def test_freshness_dict_projection():
    assert freshness_dict(None) is None
    assert freshness_dict(BoardPeFreshness("STALE", "2026-07-01", 2)) == {
        "state": "STALE", "as_of": "2026-07-01", "age_td": 2}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_board_pe_staleness.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.board_pe_staleness'`.

- [ ] **Step 3: Implement**

Create `src/irc/monitor/board_pe_staleness.py`:

```python
"""Board-PE serve-while-stale + freshness states (ADR 0020 addendum 2026-07-03, OD-1).

Pure age/state math + a thin day-file scan edge, extracted so
industry_valuation.py (207 lines) stays inside its size budget (Q9). States:
FRESH (as_of == today — a date-string equality, calendar-INDEPENDENT per RD-3),
STALE (today's fetch failed; the newest NON-EMPTY cached table N ≤ 3 trading
days old — it FEEDS factor math, rendered with an explicit age tag), DARK
(nothing non-empty ≤ 3 td, or the trading calendar is unavailable on the
STALE BRANCH ONLY → per-stock industry_no_data, val_score == self_score).
RD-2: empty {} day files (the pre-light-up 2026-06-29/30 caches) are skipped by
the scan, never served under an age tag. Never raises.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_log = logging.getLogger(__name__)
MAX_STALE_TRADING_DAYS = 3
_DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


@dataclass(frozen=True)
class BoardPeFreshness:
    state: str            # "FRESH" | "STALE" | "DARK"
    as_of: str | None     # source table date (named even for DARK when known)
    age_td: int | None    # trading-day age N; None when uncomputable


def freshness_dict(f: BoardPeFreshness | None) -> dict | None:
    """Pure: the {"state","as_of","age_td"} trace/panel projection (AC-11/AC-12)."""
    if f is None:
        return None
    return {"state": f.state, "as_of": f.as_of, "age_td": f.age_td}


def trading_day_age(as_of: str, today: str, trading_days) -> int | None:
    """Pure (AC-10): N = |{trading days d : as_of < d ≤ today}|. Weekend/holiday
    gaps count 0. None when either date is unparseable."""
    try:
        a, t = date.fromisoformat(as_of), date.fromisoformat(today)
    except (ValueError, TypeError):
        return None
    return sum(1 for d in trading_days if a < d <= t)


def read_day_table(cache_dir: Path, day: str) -> dict | None:
    """EDGE: parsed day file, or None (missing/unreadable → caller refetches)."""
    path = cache_dir / f"{day}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("board_pe_staleness: unreadable cache %s; skipping", path,
                     exc_info=True)
        return None


def write_day_table(cache_dir: Path, day: str, table: dict) -> None:
    """EDGE: byte-stable atomic day-file write (sorted keys, .tmp.{pid} → os.replace)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(table, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = (cache_dir / f"{day}.json").with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, cache_dir / f"{day}.json")


def _nonempty_floats(table: object, path: Path) -> dict | None:
    if not isinstance(table, dict) or not table:
        return None
    try:
        return {str(k): float(v) for k, v in table.items()}
    except (TypeError, ValueError):
        _log.warning("board_pe_staleness: malformed table %s; skipping", path)
        return None


def newest_nonempty(cache_dir: Path, today: str) -> tuple[str, dict] | None:
    """EDGE (RD-2): newest readable NON-EMPTY YYYY-MM-DD.json strictly before
    today; empty {} and unreadable files are SKIPPED and the scan continues to
    older files. None when nothing qualifies."""
    if not cache_dir.is_dir():
        return None
    days = sorted((p for p in cache_dir.iterdir()
                   if _DAY_FILE.match(p.name) and p.stem < today), reverse=True)
    for p in days:
        table = _nonempty_floats(read_day_table(cache_dir, p.stem), p)
        if table is not None:
            return p.stem, table
    return None


def stale_fallback(cache_dir: Path, today: str, trading_days) -> tuple[dict, BoardPeFreshness]:
    """EDGE: today's fetch failed/empty → serve the newest non-empty cached table
    when its trading-day age N ≤ 3 (STALE — FEEDS factor math per OD-1). Calendar
    None/empty disables ONLY this branch (RD-3) → DARK with as_of named, age None.
    Nothing non-empty on disk → DARK(None, None). Never raises."""
    found = newest_nonempty(cache_dir, today)
    if found is None:
        return {}, BoardPeFreshness("DARK", None, None)
    as_of, table = found
    if not trading_days:                       # None or empty → honest N uncomputable
        return {}, BoardPeFreshness("DARK", as_of, None)
    age = trading_day_age(as_of, today, trading_days)
    if age is None or age > MAX_STALE_TRADING_DAYS:
        return {}, BoardPeFreshness("DARK", as_of, age)
    return table, BoardPeFreshness("STALE", as_of, age)
```

- [ ] **Step 4: Run to verify green**

Run: `uv run pytest tests/monitor/test_board_pe_staleness.py -q`
Expected: 15 passed. (Doc note: an earlier draft said "14 passed" — the
verbatim Step 1 test code above always had 15 `def test_...` functions; this
is a doc miscount fixed during 004-drift review, not a code divergence.)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/monitor/board_pe_staleness.py tests/monitor/test_board_pe_staleness.py
git add -A && git commit -m "feat(monitor): board_pe_staleness module — FRESH/STALE/DARK, trading-day age, non-empty stale scan (004 AC-9/AC-10)"
```

---

### Task 4: `fetch_industry_pe` → `(table, BoardPeFreshness)` (AC-9)

**Files:**
- Modify: `src/irc/monitor/industry_valuation.py` (MUST end ≤ 207 lines — verify)
- Modify (keep-green shim): `src/irc/commands/monitor_cmd.py` `_build_full_basket_metrics` (line ~329)
- Test: `tests/monitor/test_industry_valuation.py`, `tests/commands/test_monitor_cmd_valuation.py`

**Interfaces:**
- Produces: `fetch_industry_pe(*, cache_dir, today, fetch=None, sleep=time.sleep, trading_days=None) -> tuple[dict[str, float], BoardPeFreshness]`. Fetch/cache semantics unchanged when `trading_days` not supplied (per-day cache, D3 no-empty-cache, never raises); freshness degrades per Q5 (FRESH still computable; stale branch → DARK). RD-7: this return-shape change breaks every caller — ALL are updated in-item (`_build_full_basket_metrics` here as a shim; run-level + capture sites in Tasks 8/9).
- `fetch_stock_industry_map` UNTOUCHED (per-day cache + `cached_fetch` 3-outcome/breaker semantics preserved, AC-6).

- [ ] **Step 1: Update + add tests (failing)**

In `tests/monitor/test_industry_valuation.py`, add imports at the top:

```python
from datetime import date

from irc.monitor.board_pe_staleness import BoardPeFreshness
```

Replace `test_fetch_industry_pe_caches_and_round_trips` with:

```python
def test_fetch_industry_pe_caches_and_round_trips(tmp_path: Path):
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        return pd.DataFrame({"板块名称": ["银行"], "市盈率": ["6.5"]})

    cache_dir = tmp_path / "industry_pe"
    out1, f1 = fetch_industry_pe(cache_dir=cache_dir, today="2026-06-21",
                                 fetch=fake_fetch, sleep=lambda _s: None)
    out2, f2 = fetch_industry_pe(cache_dir=cache_dir, today="2026-06-21",
                                 fetch=fake_fetch, sleep=lambda _s: None)
    assert out1 == out2 == {"银行": 6.5}
    assert f1 == f2 == BoardPeFreshness("FRESH", "2026-06-21", 0)
    assert calls["n"] == 1  # second call served from cache
    payload = json.loads((cache_dir / "2026-06-21.json").read_text(encoding="utf-8"))
    assert payload == {"银行": 6.5}
```

Replace `test_fetch_industry_pe_never_raises_returns_empty` with:

```python
def test_fetch_industry_pe_never_raises_returns_empty_dark(tmp_path: Path):
    def boom():
        raise RuntimeError("network down")

    out, f = fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-06-21",
                               fetch=boom, sleep=lambda _s: None)
    assert out == {}
    assert f == BoardPeFreshness("DARK", None, None)   # nothing cached anywhere
```

Update `test_default_fetch_uses_em_raw_board_frame` — change the last two lines to:

```python
    out, f = iv.fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-07-02",
                                  sleep=lambda _s: None)
    assert out == {"电力": 19.68}
    assert f.state == "FRESH"
```

Update `test_empty_parse_is_returned_but_not_cached` — change the body after the monkeypatch to:

```python
    out, f = iv.fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-07-02",
                                  sleep=lambda _s: None)
    assert out == {}
    assert f.state == "DARK"
    assert not (tmp_path / "ip" / "2026-07-02.json").is_file()  # NOT cached
```

Append these NEW tests at the end of the file:

```python
_TDS = frozenset({date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)})


def _bank_frame():
    return pd.DataFrame({"板块名称": ["银行"], "市盈率": ["6.5"]})


def test_failed_fetch_serves_stale_cached_table_within_3td(tmp_path: Path):
    """OD-1: the ≤3-td stale table is RETURNED AS THE TABLE — the exact value a
    FRESH day feeds factor math with; only the freshness label differs."""
    cache_dir = tmp_path / "ip"
    fetch_industry_pe(cache_dir=cache_dir, today="2026-07-02",
                      fetch=_bank_frame, sleep=lambda _s: None)   # seed yesterday

    def boom():
        raise RuntimeError("down")

    out, f = fetch_industry_pe(cache_dir=cache_dir, today="2026-07-03",
                               fetch=boom, sleep=lambda _s: None, trading_days=_TDS)
    assert out == {"银行": 6.5}
    assert f == BoardPeFreshness("STALE", "2026-07-02", 1)


def test_fresh_is_calendar_independent(tmp_path: Path):
    """RD-3: a calendar outage (trading_days=None) never darkens a today-fresh
    table — FRESH is an as_of == today string equality."""
    out, f = fetch_industry_pe(cache_dir=tmp_path / "ip", today="2026-07-03",
                               fetch=_bank_frame, sleep=lambda _s: None,
                               trading_days=None)
    assert out == {"银行": 6.5}
    assert f == BoardPeFreshness("FRESH", "2026-07-03", 0)


def test_no_calendar_disables_only_the_stale_branch(tmp_path: Path):
    """Q5: failed fetch + stale cache + NO trading_days → DARK (honest N
    uncomputable), as_of still naming the newest non-empty cached day."""
    cache_dir = tmp_path / "ip"
    fetch_industry_pe(cache_dir=cache_dir, today="2026-07-02",
                      fetch=_bank_frame, sleep=lambda _s: None)

    def boom():
        raise RuntimeError("down")

    out, f = fetch_industry_pe(cache_dir=cache_dir, today="2026-07-03",
                               fetch=boom, sleep=lambda _s: None)
    assert out == {}
    assert f == BoardPeFreshness("DARK", "2026-07-02", None)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_industry_valuation.py -q`
Expected: FAIL (tuple unpack of the current dict return).

- [ ] **Step 3: Implement**

In `src/irc/monitor/industry_valuation.py`:

1. DELETE the three helpers `_cache_path`, `_write_json`, `_read_json` (lines ~84-105) — the day-file I/O moved to `board_pe_staleness.py` in Task 3. Then delete the now-unused `import json` and `import os` lines (verify with ruff; `time`, `Path`, `pd` remain used).
2. Add the import (after the `cached_fetch` import):

```python
from irc.monitor.board_pe_staleness import (
    BoardPeFreshness, read_day_table, stale_fallback, write_day_table,
)
```

3. Replace `fetch_industry_pe` with:

```python
def fetch_industry_pe(
    *, cache_dir: Path, today: str, fetch=None, sleep=time.sleep,
    trading_days: frozenset | None = None,
) -> tuple[dict[str, float], BoardPeFreshness]:
    """EDGE: ONE market-wide board PE call/day, cached (D3: empty parse never
    cached). Returns (table, BoardPeFreshness). FRESH iff as_of == today —
    calendar-INDEPENDENT (RD-3); otherwise the board_pe_staleness stale branch
    (STALE ≤3 td FEEDS factor math per OD-1; DARK otherwise or when trading_days
    is None/empty). NEVER raises; fetch injectable (default wraps
    em_raw.fetch_board_pe_frame, raw JSON via IRC_CN_PROXY, D3)."""
    cached = read_day_table(cache_dir, today)
    if cached is not None:
        table = {str(k): float(v) for k, v in cached.items()}
        return table, BoardPeFreshness("FRESH", today, 0)
    if fetch is None:
        fetch = lambda: fetch_board_pe_frame(sleep=sleep)  # noqa: E731 — raw JSON via proxy (D3)
    parsed: dict[str, float] = {}
    try:
        parsed = parse_industry_pe(fetch())
    except Exception:  # noqa: BLE001 — degrade to the stale branch, never crash
        _log.warning("industry_valuation: board PE fetch failed", exc_info=True)
    if parsed:                       # D3: never cache an empty parse (F4 wart)
        write_day_table(cache_dir, today, parsed)
        return parsed, BoardPeFreshness("FRESH", today, 0)
    return stale_fallback(cache_dir, today, trading_days)
```

4. Keep-green shim in `src/irc/commands/monitor_cmd.py` `_build_full_basket_metrics` — replace the `industry_pe = fetch_industry_pe(...)` statement (line ~329) with:

```python
    industry_pe, _board_pe_freshness = fetch_industry_pe(
        cache_dir=root / "data" / "monitor" / "industry_pe", today=today)
```

5. Update `tests/commands/test_monitor_cmd_valuation.py` `_patch_common` — replace the `fetch_industry_pe` monkeypatch with:

```python
    from irc.monitor.board_pe_staleness import BoardPeFreshness
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda cache_dir, today, **kw: ({"酿酒行业": 60.0},
                                                        BoardPeFreshness("FRESH", today, 0)))
```

(The `fetch_stock_industry_map` monkeypatch in `_patch_common` gets `**kw` tolerance NOW so Task 7's kwarg threading doesn't break it: `lambda symbols, cache_dir, today, **kw: {s: "酿酒行业" for s in symbols}`.)

- [ ] **Step 4: Verify green + line budget**

Run: `uv run pytest tests/monitor/test_industry_valuation.py tests/monitor/test_board_pe_staleness.py -q`
Expected: all PASS.

Run: `uv run pytest tests/commands/test_monitor_cmd_valuation.py -q`
Expected: all PASS.

Run: `wc -l src/irc/monitor/industry_valuation.py`
Expected: **≤ 207** (the helper removal offsets the additions). If over, trim the `fetch_industry_pe` docstring — never the guards.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/monitor/industry_valuation.py tests/monitor/test_industry_valuation.py tests/commands/test_monitor_cmd_valuation.py src/irc/commands/monitor_cmd.py
git add -A && git commit -m "feat(monitor): fetch_industry_pe returns (table, BoardPeFreshness) with non-empty serve-while-stale (004 AC-9)"
```

---

### Task 5: Trace marker + panel reason (AC-11, AC-12)

**Files:**
- Modify: `src/irc/monitor/eval/trace.py`
- Modify: `src/irc/monitor/eval/structural.py`
- Test: `tests/monitor/eval/test_trace.py`, `tests/monitor/eval/test_structural.py`

**Interfaces:**
- Produces: `build_eval_trace(..., board_pe_freshness: dict | None = None)` → run-level key `"board_pe_freshness"` (the `freshness_dict` projection or None); `valuation_coverage_health(t, *, board_pe_freshness: dict | None = None)` — appends ONE reason past the empty-metrics early-return; status stays PASS (panel-only, never a gate).
- Consumed by: Task 8 (`monitor_cmd` threads `freshness_dict(...)` to both).

- [ ] **Step 1: Write the failing trace tests**

In `tests/monitor/eval/test_trace.py`, update `test_top_level_keys`'s expected set to:

```python
    assert set(t) == {"schema_version", "engine_version", "run_date", "funds",
                  "macro_narrative", "unmatched_impact_keys", "board_pe_freshness"}
```

Append at the end of the file:

```python
def test_board_pe_freshness_lands_under_unchanged_schema_7():
    """004 AC-11: run-level {"state","as_of","age_td"} marker, additive — NO bump."""
    from irc.monitor.eval.trace import SCHEMA_VERSION
    view = _good_view()
    t = build_eval_trace(((_fund(), view, _stub_gate(view), _bundle()),),
                         engine_version="1", run_date="2026-07-03",
                         board_pe_freshness={"state": "STALE", "as_of": "2026-07-01",
                                             "age_td": 2})
    assert SCHEMA_VERSION == "7"
    assert t["schema_version"] == "7"
    assert t["board_pe_freshness"] == {"state": "STALE", "as_of": "2026-07-01",
                                       "age_td": 2}


def test_board_pe_freshness_defaults_to_none_back_compat():
    """Callers that don't pass one (old paths, _compute_gates projections) → None."""
    view = _good_view()
    t = build_eval_trace(((_fund(), view, _stub_gate(view), _bundle()),),
                         engine_version="1", run_date="2026-07-03")
    assert t["board_pe_freshness"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/eval/test_trace.py -q`
Expected: FAIL (key set mismatch / TypeError unexpected kwarg).

- [ ] **Step 3: Implement trace**

In `src/irc/monitor/eval/trace.py`:

1. Extend the `SCHEMA_VERSION` comment block (lines 14-17) — replace with:

```python
# Public: also consumed by monitor_cmd's Provenance so the report header can
# never drift from the trace (RD-1). Bumped 6->7 by report v4 item 001 (shape
# unchanged — gate.reason just stops being empty); items 002/004 land their
# fields under "7" WITHOUT bumping again (002: mechanism/mechanism_dropped +
# unmatched_impact_keys; 004: run-level board_pe_freshness).
```

2. Add the kwarg + key to `build_eval_trace`:

```python
def build_eval_trace(
    items: tuple[tuple[MonitorFund, FundView, GateDecision, FundTraceBundle], ...],
    *, engine_version: str, run_date: str,
    trading_days: frozenset[date] | None = None,
    macro_narrative=None,
    unmatched_impact_keys: tuple[str, ...] = (),
    board_pe_freshness: dict | None = None,
) -> dict:
```

and in the returned dict, after the `"unmatched_impact_keys"` entry:

```python
        # 004 (AC-11): run-level board-PE freshness marker — the
        # board_pe_staleness.freshness_dict projection {"state","as_of","age_td"},
        # or None when the caller doesn't pass one (additive back-compat under
        # the EXISTING "7", same pattern as macro_narrative).
        "board_pe_freshness": board_pe_freshness,
```

- [ ] **Step 4: Write the failing structural tests**

Append to `tests/monitor/eval/test_structural.py`:

```python
# ---- 004 AC-12: valuation_coverage_health board_pe_freshness reason ----


def _val_cov_trace():
    return {"holding_metrics": {
        "rows": [{"symbol": "600519", "weight_pct": 60.0, "val_score": 0.5,
                  "industry_score": 0.2, "false_cheap": False}],
        "valuation_aggregate": {"value": 0.5, "reason": None,
                                "covered_weight_ratio": 0.6},
    }}


def test_val_cov_board_pe_fresh_reason_appended():
    h = valuation_coverage_health(
        _val_cov_trace(),
        board_pe_freshness={"state": "FRESH", "as_of": "2026-07-03", "age_td": 0})
    assert h.status == "PASS"
    assert "board_pe FRESH" in h.reasons


def test_val_cov_board_pe_stale_reason_names_age_and_date():
    h = valuation_coverage_health(
        _val_cov_trace(),
        board_pe_freshness={"state": "STALE", "as_of": "2026-06-30", "age_td": 2})
    assert "board_pe STALE-2 (as_of 2026-06-30)" in h.reasons


def test_val_cov_board_pe_dark_reason_and_status_stays_pass():
    h = valuation_coverage_health(
        _val_cov_trace(),
        board_pe_freshness={"state": "DARK", "as_of": None, "age_td": None})
    assert "board_pe DARK" in h.reasons
    assert h.status == "PASS"          # panel-only, never a gate


def test_val_cov_no_kwarg_back_compat_no_board_pe_reason():
    h = valuation_coverage_health(_val_cov_trace())
    assert not any(r.startswith("board_pe") for r in h.reasons)


def test_val_cov_malformed_freshness_dict_degrades_to_no_reason():
    h = valuation_coverage_health(_val_cov_trace(), board_pe_freshness={"weird": 1})
    assert not any(r.startswith("board_pe") for r in h.reasons)
```

Run: `uv run pytest tests/monitor/eval/test_structural.py -q` → Expected: new tests FAIL (unexpected kwarg).

- [ ] **Step 5: Implement structural**

In `src/irc/monitor/eval/structural.py`, add before `valuation_coverage_health`:

```python
def _board_pe_reason(f: dict | None) -> tuple[str, ...]:
    """Pure (004 AC-12): ONE panel reason for the run-level board-PE freshness
    marker. Absent/malformed → () (old traces / other callers degrade silently)."""
    if not isinstance(f, dict):
        return ()
    state = f.get("state")
    if state == "STALE":
        return (f"board_pe STALE-{f.get('age_td')} (as_of {f.get('as_of')})",)
    if state in ("FRESH", "DARK"):
        return (f"board_pe {state}",)
    return ()
```

Change `valuation_coverage_health`'s signature to:

```python
def valuation_coverage_health(
    t: dict, *, board_pe_freshness: dict | None = None,
) -> StageHealth:
```

and insert, immediately before its final `return` statement:

```python
    reasons.extend(_board_pe_reason(board_pe_freshness))
```

(The empty-metrics early-return at the top stays FIRST — funds without holding
metrics (gold/QDII) don't carry the reason; the run-level state surfaces on the
active funds' rows, which are the only consumers of the denominator.)

- [ ] **Step 6: Run to verify green**

Run: `uv run pytest tests/monitor/eval/test_structural.py tests/monitor/eval/test_trace.py -q`
Expected: all PASS.

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check src/irc/monitor/eval/trace.py src/irc/monitor/eval/structural.py tests/monitor/eval/test_trace.py tests/monitor/eval/test_structural.py
git add -A && git commit -m "feat(monitor): run-level board_pe_freshness trace key + valuation_coverage panel reason, schema stays 7 (004 AC-11/AC-12)"
```

---

### Task 6: Reader-facing age tag on both surfaces (AC-13)

**Files:**
- Modify: `src/irc/monitor/render_drilldown.py`, `src/irc/monitor/render_types.py`, `src/irc/monitor/render_html.py`
- Test: `tests/monitor/test_render_drilldown.py`, `tests/monitor/test_render_html.py`

**Interfaces:**
- Produces: `board_pe_age_note_html(freshness) -> str` (PURE; duck-typed on `.state/.as_of/.age_td`; `""` for FRESH/DARK/None); `drilldown_section_html(..., val_agg=None, board_pe_freshness=None)`; `drilldown_page_html` rows accept optional `row[6]`; `FundView.board_pe_freshness: BoardPeFreshness | None = None` (trailing-defaulted, precedent `provisional_flow_as_of`).
- NO new CSS anywhere — the note reuses the existing `.na-reason` class (defined in BOTH `render_html._CSS` and `_DRILLDOWN_CSS`), so `tests/monitor/golden/report.html` must stay byte-identical.

- [ ] **Step 1: Write the failing drilldown tests**

In `tests/monitor/test_render_drilldown.py`, FIRST extend the TOP-of-file import block (ruff E402 — never mid-file): add `board_pe_age_note_html` and `drilldown_section_html` to the existing `from irc.monitor.render_drilldown import (...)` list, and add a new top-level line:

```python
from irc.monitor.board_pe_staleness import BoardPeFreshness
```

Then append these tests at the end of the file (`FlowAggregate`, `ValuationAggregate`, `_m`, `_sig` already exist in this file):

```python
# ---- 004 AC-13: 板块PE age tag ----


def test_age_note_exact_text_when_stale():
    html = board_pe_age_note_html(BoardPeFreshness("STALE", "2026-06-30", 2))
    assert "板块PE 引用 2026-06-30 · 2个交易日前" in html
    assert "na-reason" in html     # muted styling via the EXISTING class (no CSS change)


def test_age_note_empty_for_fresh_dark_none():
    assert board_pe_age_note_html(None) == ""
    assert board_pe_age_note_html(BoardPeFreshness("FRESH", "2026-07-03", 0)) == ""
    assert board_pe_age_note_html(BoardPeFreshness("DARK", None, None)) == ""


def test_drilldown_section_places_tag_adjacent_to_board():
    metrics = (_m("600519", 12.0, pe=30.0),)
    agg = FlowAggregate(value=None, reason="flow_no_data", covered_weight_ratio=0.0)
    html = drilldown_section_html(
        "易方达蓝筹", "519069", metrics, agg, _sig(),
        board_pe_freshness=BoardPeFreshness("STALE", "2026-07-01", 1))
    assert "板块PE 引用 2026-07-01 · 1个交易日前" in html
    assert html.index("holdings-board") < html.index("板块PE 引用")


def test_drilldown_page_row7_threads_age_tag():
    metrics = (_m("600519", 12.0, pe=30.0),)
    agg = FlowAggregate(value=None, reason="flow_no_data", covered_weight_ratio=0.0)
    val_agg = ValuationAggregate(value=None, reason="valuation_no_data",
                                 covered_weight_ratio=0.0)
    bpf = BoardPeFreshness("STALE", "2026-07-01", 1)
    html = drilldown_page_html((("519069", "易方达蓝筹", metrics, agg, _sig(),
                                 val_agg, bpf),))
    assert "板块PE 引用 2026-07-01 · 1个交易日前" in html


def test_drilldown_page_5_and_6_tuple_rows_render_without_tag():
    metrics = (_m("600519", 12.0),)
    agg = FlowAggregate(value=None, reason="flow_no_data", covered_weight_ratio=0.0)
    html = drilldown_page_html((("519069", "易方达蓝筹", metrics, agg, _sig()),))
    assert "板块PE 引用" not in html
```

(If `ValuationAggregate` is not yet imported at the top of the file, it IS — line 3. Verify.)

- [ ] **Step 2: Write the failing card tests**

Append to `tests/monitor/test_render_html.py`:

```python
def test_card_drilldown_block_carries_stale_board_pe_age_tag():
    """004 AC-13: the report card (phone-visible surface) renders the tag too."""
    from irc.monitor.board_pe_staleness import BoardPeFreshness
    from irc.monitor.holding_metrics import HoldingMetric
    m = HoldingMetric(symbol="600519", name="茅台", weight_pct=9.0, pe=30.0, pb=8.0,
                      pe_percentile=0.5, valuation_state="fair", valuation_reason=None,
                      flow_pct_5d=None, flow_pct_20d=None, flow_score=None,
                      flow_reason="flow_no_data")
    v = dataclasses.replace(_view(), holding_metrics=(m,),
                            board_pe_freshness=BoardPeFreshness("STALE", "2026-06-30", 2))
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "板块PE 引用 2026-06-30 · 2个交易日前" in html


def test_card_no_age_tag_when_fresh():
    from irc.monitor.board_pe_staleness import BoardPeFreshness
    from irc.monitor.holding_metrics import HoldingMetric
    m = HoldingMetric(symbol="600519", name="茅台", weight_pct=9.0, pe=30.0, pb=8.0,
                      pe_percentile=0.5, valuation_state="fair", valuation_reason=None,
                      flow_pct_5d=None, flow_pct_20d=None, flow_score=None,
                      flow_reason="flow_no_data")
    v = dataclasses.replace(_view(), holding_metrics=(m,),
                            board_pe_freshness=BoardPeFreshness("FRESH", "2026-06-15", 0))
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW, now_dt=_NOW_DT)
    assert "板块PE 引用" not in html
```

Run: `uv run pytest tests/monitor/test_render_drilldown.py tests/monitor/test_render_html.py -q` → Expected: new tests FAIL (no helper / unknown FundView field).

- [ ] **Step 3: Implement**

1. `src/irc/monitor/render_drilldown.py` — add after `provisional_flow_annotation_html`:

```python
def board_pe_age_note_html(freshness) -> str:
    """PURE (004 AC-13): 板块PE age tag for a STALE table — '' for FRESH / DARK /
    None (FRESH needs no noise; DARK already surfaces as industry_no_data + the
    行业覆盖/价值陷阱检测 notes — no new DARK string, KNOWN_NA_REASONS unchanged).
    Duck-typed on BoardPeFreshness(.state/.as_of/.age_td); shared by both
    surfaces so the wording can't drift (Q12)."""
    if freshness is None or getattr(freshness, "state", None) != "STALE":
        return ""
    return (f'<div class="board-pe-age na-reason">板块PE 引用 '
            f'{escape(freshness.as_of or "?")} · {freshness.age_td}个交易日前</div>')
```

2. Same file — replace `drilldown_section_html` and `drilldown_page_html`'s `_section` with:

```python
def drilldown_section_html(
    name_cn: str, fund_id: str, metrics, agg, signal, val_agg=None,
    board_pe_freshness=None,
) -> str:
    """PURE: one fund's board + roll-up section (reused by card + standalone page).
    val_agg: optional ValuationAggregate → appends valuation rollup.
    board_pe_freshness: optional → 板块PE age tag adjacent to the board (AC-13)."""
    val_html = valuation_rollup_html(metrics, val_agg) if val_agg is not None else ""
    age_note = board_pe_age_note_html(board_pe_freshness)
    return (
        f"<section class='drilldown' id='dd-{escape(fund_id)}'>"
        f"<h2>{escape(name_cn)} ({escape(fund_id)})</h2>"
        f"{holdings_board_html(metrics)}{age_note}{flow_rollup_html(metrics, agg, signal)}"
        f"{val_html}</section>"
    )
```

and inside `drilldown_page_html` (docstring: add `... or (fund_id, name_cn, metrics, agg, signal, val_agg, board_pe_freshness).`):

```python
    def _section(row) -> str:
        fund_id, name_cn, metrics, agg, signal = row[:5]
        val_agg = row[5] if len(row) > 5 else None
        bpf = row[6] if len(row) > 6 else None
        return drilldown_section_html(name_cn, fund_id, metrics, agg, signal, val_agg,
                                      board_pe_freshness=bpf)
```

3. `src/irc/monitor/render_types.py` — add import + trailing field:

```python
from irc.monitor.board_pe_staleness import BoardPeFreshness
```

and as the LAST `FundView` field:

```python
    board_pe_freshness: BoardPeFreshness | None = None  # 004: run-global board-PE age (AC-13)
```

4. `src/irc/monitor/render_html.py` — add `board_pe_age_note_html` to the existing `from irc.monitor.render_drilldown import ...` line, then update `_drilldown_block`:

```python
def _drilldown_block(view: FundView) -> str:
    if not view.holding_metrics:
        return ""
    agg = aggregate_flow(view.holding_metrics)
    provisional = provisional_flow_annotation_html(
        symbol_value=view.provisional_flow_pct,
        as_of_hhmm=view.provisional_flow_as_of or "")
    return (holdings_board_html(view.holding_metrics)
            + board_pe_age_note_html(view.board_pe_freshness)
            + flow_rollup_html(view.holding_metrics, agg, view.signal)
            + provisional)
```

- [ ] **Step 4: Run to verify green + golden unchanged**

Run: `uv run pytest tests/monitor/test_render_drilldown.py tests/monitor/test_render_html.py tests/monitor/test_render_types.py tests/monitor/test_report_v2_invariants.py -q`
Expected: all PASS — **including `test_golden_file` untouched** (no CSS change; trailing-defaulted field). If `test_golden_file` fails, you added CSS or changed markup for the default path — fix the code, do NOT regenerate the golden.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/irc/monitor/render_drilldown.py src/irc/monitor/render_types.py src/irc/monitor/render_html.py tests/monitor/test_render_drilldown.py tests/monitor/test_render_html.py
git add -A && git commit -m "feat(monitor): 板块PE age tag on report card + drilldown via shared pure helper (004 AC-13)"
```

---

### Task 7: `monitor_cmd` — full-basket batch, store merge, serving map, consume order (AC-3 helper, AC-5 brief site, AC-6)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Create: `tests/commands/test_monitor_cmd_industry.py`
- Modify: `tests/commands/test_monitor_cmd.py` (rename ×2), `tests/commands/test_monitor_cmd_drilldown.py` (rename ×1), `tests/commands/test_monitor_constituent.py` (rename ×1), `tests/commands/test_monitor_flow_capture.py` (rename ×1)

**Interfaces:**
- Produces: `_full_basket_union_symbols(funds, root) -> tuple` (AC-3); `_batch_flow_industry(root, symbols) -> tuple[dict | None, dict | None]` (renamed/reshaped `_provisional_flow_note`, Q14); `_record_industry_seen(root, today, industry_by_symbol) -> None` (best-effort, AC-5); `_industry_serving_map(root, today) -> dict[str, str]`; `_industry_map_for(full_symbols, *, root, today, serving) -> dict` (AC-6 store→batch→fallback); `_build_full_basket_metrics(..., industry_serving=None)` and `_process_fund(..., industry_serving=None)` threading.
- Consumes: Task 1 fetch tuple, Task 2 store functions, Task 4 tuple-returning `fetch_industry_pe`.

- [ ] **Step 1: Write the failing wiring tests**

Create `tests/commands/test_monitor_cmd_industry.py`:

```python
"""004 run-level wiring: batch-first 行业 (store → batch → fallback) + board-PE
fetch-first. All network edges monkeypatched — offline only."""
from __future__ import annotations

import json
import logging
import textwrap
from datetime import date

import irc.commands.monitor_cmd as mc
from irc.monitor.board_pe_staleness import BoardPeFreshness
from irc.monitor.fetch import NavFetchResult
from irc.monitor.impacts import ImpactsResult
from irc.monitor.valuation import ValuationResolution
from irc.fundamentals.snapshot_cache import write_active_fund_cache
from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis

_YAML_TWO_ACTIVE = textwrap.dedent("""
schema_version: 1
history: { minimum_observations: 10, fetch_calendar_days: 550 }
defaults: { signal_bands: { buy: 0.40, sell: -0.40 }, minimum_confidence: 0.50 }
funds:
  - { id: "110011", name_cn: 蓝筹A, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_monetary], constituent_news: true }
  - { id: "519069", name_cn: 价值B, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_monetary], constituent_news: true }
""")


class _FakeCon:
    def close(self):
        pass


def _snap(fid, holdings):
    return ActiveFundSnapshot(
        fund_id=fid, source_report_date="2026-03-31", source_report_quarter="2026Q1",
        cache_probed_at="2026-07-03T09:00:00",
        constituent_analyses=tuple(
            ConstituentAnalysis(symbol=s, name_cn=n, weight_pct=w,
                                evidence=(), failure_reasons=(), one_line_view="x")
            for s, n, w in holdings),
        failure_reasons_by_symbol={})


def _wire_two_fund_run(tmp_path, monkeypatch, *, batch_industry):
    """Offline two-active-fund run_monitor harness. A fake DuckDB con + empty
    per-code series map keep _build_full_basket_metrics on the REAL industry
    consume path (con=None would early-return before it)."""
    import irc.opportunity.inputs_loader as il
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML_TWO_ACTIVE, encoding="utf-8")
    write_active_fund_cache(_snap("110011", [("600519", "茅台", 60.0)]), tmp_path / "data")
    write_active_fund_cache(_snap("519069", [("000651", "格力", 55.0)]), tmp_path / "data")
    (tmp_path / "data" / "local.duckdb").write_bytes(b"")   # existence gates connect()
    series = tuple((f"2026-{1 + i // 28:02d}-{i % 28 + 1:02d}", 1.0 + 0.01 * i)
                   for i in range(60))
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "connect", lambda p: _FakeCon())
    monkeypatch.setattr(il, "_stock_series_by_code", lambda con, syms: {})
    monkeypatch.setattr(mc, "nav_series_for",
                        lambda fid, **k: NavFetchResult(fid, 2.13, "2026-07-03", series))
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: object())
    monkeypatch.setattr(mc, "load_trading_days",
                        lambda today, root: frozenset({date(2026, 7, 2), date(2026, 7, 3)}))
    monkeypatch.setattr(mc, "_build_theme_results", lambda root, funds: {})
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: ())
    monkeypatch.setattr(mc, "gather_impacts",
                        lambda **k: ImpactsResult(k["fund_id"], (), "ok", ()))
    monkeypatch.setattr(mc, "build_constituent_pool", lambda fid, root: ())
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution(
                            None, False, "valuation_no_anchor", path="lookthrough"))
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    monkeypatch.setattr(mc, "_batch_flow_industry",
                        lambda root, symbols: (None, batch_industry))


# ---- AC-6 consume order (run level) ----


def test_batch_industry_fills_every_row_and_fallback_never_fires(tmp_path, monkeypatch):
    """AC-6 / source-spec §4 bullet 4: batch covers the full basket → 行业 is
    non-None for EVERY holdings row; the per-symbol fetch fake is NEVER invoked."""
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({}, BoardPeFreshness("DARK", None, None)))
    fallback_calls = []
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, **kw: fallback_calls.append(tuple(symbols)) or {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert fallback_calls == []
    trace = json.loads((tmp_path / "outputs" / "2026-07-03" / "monitor" /
                        "eval_trace.json").read_text(encoding="utf-8"))
    rows = [r for fid in ("110011", "519069")
            for r in trace["funds"][fid]["holding_metrics"]["rows"]]
    assert rows and all(r["industry"] is not None for r in rows)


def test_symbol_absent_from_batch_falls_back_only_for_it(tmp_path, monkeypatch):
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业"})   # 000651 absent
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({}, BoardPeFreshness("DARK", None, None)))
    fallback_calls = []
    monkeypatch.setattr(
        mc, "fetch_stock_industry_map",
        lambda symbols, **kw: fallback_calls.append(tuple(symbols))
        or {s: "家电行业" for s in symbols})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert fallback_calls == [("000651",)]      # ONLY the absent symbol reaches fallback


# ---- AC-5: 12:15 batch merge into the cross-day store ----


def test_batch_industry_merges_into_cross_day_store(tmp_path, monkeypatch):
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({}, BoardPeFreshness("DARK", None, None)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    store = json.loads((tmp_path / "data" / "monitor" / "stock_industry_map.json")
                       .read_text(encoding="utf-8"))
    assert store["600519"] == {"industry": "酿酒行业", "seen_at": "2026-07-03"}
    assert store["000651"]["seen_at"] == "2026-07-03"


def test_store_merge_failure_never_crashes_the_brief(tmp_path, monkeypatch, caplog):
    _wire_two_fund_run(tmp_path, monkeypatch, batch_industry={"600519": "酿酒行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({}, BoardPeFreshness("DARK", None, None)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})

    def _boom(path, today, industry_by_symbol):
        raise OSError("disk full")

    monkeypatch.setattr(mc, "record_seen", _boom)
    with caplog.at_level(logging.WARNING):
        rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert any("industry map store merge failed" in r.message for r in caplog.records)


# ---- AC-6 unit level: _industry_map_for ----


def test_fallback_none_result_writes_nothing_to_store(tmp_path, monkeypatch):
    """RD-4: a TRANSIENT/DEAD fallback ({sym: None}) never poisons the store."""
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, **kw: {s: None for s in symbols})
    out = mc._industry_map_for(("600519",), root=tmp_path, today="2026-07-03", serving={})
    assert out == {"600519": None}
    assert not (tmp_path / "data" / "monitor" / "stock_industry_map.json").exists()


def test_fallback_parsed_result_merges_into_store(tmp_path, monkeypatch):
    """Q3: a fallback-served symbol accumulates cross-day (no daily re-fetch)."""
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, **kw: {"600519": "酿酒行业"})
    out = mc._industry_map_for(("600519",), root=tmp_path, today="2026-07-03", serving={})
    assert out == {"600519": "酿酒行业"}
    store = json.loads((tmp_path / "data" / "monitor" / "stock_industry_map.json")
                       .read_text(encoding="utf-8"))
    assert store["600519"]["industry"] == "酿酒行业"


def test_serving_map_covers_all_no_fallback_call(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, **kw: called.append(symbols) or {})
    out = mc._industry_map_for(("600519",), root=tmp_path, today="2026-07-03",
                               serving={"600519": "酿酒行业"})
    assert out == {"600519": "酿酒行业"}
    assert called == []


# ---- AC-3: full-basket union helper ----


def test_full_basket_union_dedup_ordered_and_supersets_top5(tmp_path):
    holdings = [(f"60{i:04d}", f"n{i}", 20.0 - i) for i in range(7)]   # 7 > top-5
    write_active_fund_cache(_snap("110011", holdings), tmp_path / "data")

    class _F:
        id = "110011"
        analysis_profile = "active_cn_equity"

    full = mc._full_basket_union_symbols([_F()], tmp_path)
    top5 = mc._capture_union_symbols([_F()], tmp_path)
    assert len(full) == 7
    assert set(top5) <= set(full)                     # top-5 union ⊆ full-basket union
    assert full == tuple(dict.fromkeys(full))         # dedup-ordered
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/commands/test_monitor_cmd_industry.py -q`
Expected: FAIL — `AttributeError` on `mc._batch_flow_industry` / `mc._industry_map_for` / `mc._full_basket_union_symbols`.

- [ ] **Step 3: Implement in `src/irc/commands/monitor_cmd.py`**

1. Add import (near the `flow_series_store` import):

```python
from irc.monitor.industry_map_store import (
    fresh_slice, load_store as load_industry_map_store, record_seen,
)
```

2. Add module constant next to `_FLOW_STORE_REL`:

```python
_INDUSTRY_MAP_REL = ("data", "monitor", "stock_industry_map.json")
```

3. REPLACE `_provisional_flow_note` (lines ~212-222) with:

```python
def _batch_flow_industry(root: Path, symbols) -> tuple[dict | None, dict | None]:
    """EDGE-read only: the ONE 12:15 ulist.np batch — today's intraday f184 (盘中
    提示 annotation, NEVER persisted here: no append_today, D6/trap §8) AND the
    f127 行业 map (merged into the cross-day store by the caller, AC-5). Full-
    basket secids (AC-3). Degrades to (None, None) on any error."""
    if not symbols:
        return None, None
    try:
        return fetch_flow_today_batch(tuple(symbols))
    except Exception:  # noqa: BLE001 — annotation + industry merge are best-effort
        _log.warning("_batch_flow_industry failed", exc_info=True)
        return None, None
```

4. Add the two store edges (directly after `_batch_flow_industry`):

```python
def _record_industry_seen(root: Path, today: str, industry_by_symbol: dict | None) -> None:
    """EDGE: best-effort merge of batch/fallback 行业 into the cross-day store
    (AC-5/Q3). A merge/write failure is logged and never crashes the brief or
    the capture job."""
    if not industry_by_symbol:
        return
    try:
        record_seen(root.joinpath(*_INDUSTRY_MAP_REL), today, industry_by_symbol)
    except Exception:  # noqa: BLE001 — degrade, never crash
        _log.warning("industry map store merge failed", exc_info=True)


def _industry_serving_map(root: Path, today: str) -> dict[str, str]:
    """EDGE-read: fresh_slice (≤30 calendar days) of the cross-day store, built
    AFTER today's batch merge so today's f127 is already in it (AC-6). {} on error."""
    try:
        return fresh_slice(load_industry_map_store(root.joinpath(*_INDUSTRY_MAP_REL)), today)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("industry map store read failed", exc_info=True)
        return {}
```

5. Add `_industry_map_for` + rework `_build_full_basket_metrics` (replace the whole function):

```python
def _industry_map_for(full_symbols, *, root: Path, today: str, serving: dict | None):
    """EDGE (AC-6): store→batch serving map FIRST; the per-symbol stock/get path
    fires ONLY for symbols absent from it (fallback-only, ADR 0020 addendum);
    fallback results merge back into the cross-day store (Q3 — merge_seen's
    None-skip is the poisoning guard, RD-4). serving=None (direct caller) → all
    symbols fall back (pre-004 behaviour)."""
    served = serving or {}
    missing = tuple(s for s in full_symbols if s not in served)
    fallback: dict = {}
    if missing:
        fallback = fetch_stock_industry_map(
            missing, cache_dir=root / "data" / "monitor" / "stock_industry", today=today)
        _record_industry_seen(root, today, fallback)
    return {**{s: served[s] for s in full_symbols if s in served}, **fallback}


def _build_full_basket_metrics(full_holdings, top5, fund_id, *, root, today, con, flow_slice,
                               board_pe=None, industry_serving=None):
    """EDGE: consume flow (top-5, run-level store slice) + 行业 (store→batch
    serving map, per-symbol fallback-only, AC-6) + the run-level board-PE table
    (fetch-first, AC-8) → full-basket HoldingMetrics. A direct caller passing
    neither board_pe nor industry_serving gets the pre-004 lazy-fetch behaviour
    (library robustness — mirrors the flow_slice fallback)."""
    from irc.opportunity.inputs_loader import _stock_series_by_code
    flow_symbols = tuple(h.symbol for h in top5)
    flow_series = {s: flow_slice.get(s) for s in flow_symbols}
    full_symbols = tuple(h.symbol for h in full_holdings)
    if con is None:
        return build_holding_metrics(full_holdings, {}, flow_series)
    series_by_code = _stock_series_by_code(con, full_symbols)
    if board_pe is None:  # direct caller → lazy fetch (freshness half unused here)
        board_pe = fetch_industry_pe(
            cache_dir=root / "data" / "monitor" / "industry_pe", today=today)
    industry_map = _industry_map_for(full_symbols, root=root, today=today,
                                     serving=industry_serving)
    return build_holding_metrics(
        full_holdings, series_by_code, flow_series,
        industry_by_symbol=industry_map, industry_pe_by_industry=board_pe[0])
```

6. Add `_full_basket_union_symbols` directly after `_capture_union_symbols` (line ~1112):

```python
def _full_basket_union_symbols(funds, root: Path) -> tuple:
    """The union of the monitor set's active-fund FULL disclosed baskets (AC-3),
    dedup-ordered. Feeds BOTH ulist.np batch call sites — P7's point is filling
    行业 for the full basket in the same single call. The flow STORE stays
    top-5-scoped via the _capture_union_symbols slice-back (D5). top-5 union ⊆
    full-basket union by construction (top5 = full[:5] per fund, RD-1)."""
    from irc.monitor.profiles import PROFILES
    syms: list[str] = []
    for fund in funds:
        spec = PROFILES.get(fund.analysis_profile)
        if not (spec and spec.lookthrough == "active_fund"):
            continue
        snap = load_latest_active_fund_cached(fund.id, root / "data")
        if snap is None:
            continue
        full = sorted(snap.constituent_analyses, key=lambda c: c.weight_pct, reverse=True)
        syms.extend(h.symbol for h in full)
    return tuple(dict.fromkeys(syms))
```

7. In `run_monitor` (lines ~991-999), replace

```python
    flow_slice = _load_flow_store_slice(root, _capture_union_symbols(funds, root))
    provisional_flow = _provisional_flow_note(root, _capture_union_symbols(funds, root))
```

with (keep the existing `# EDGE clock read` comment + `provisional_flow_as_of` block between the fetch and the merge):

```python
    flow_slice = _load_flow_store_slice(root, _capture_union_symbols(funds, root))
    batch_symbols = _full_basket_union_symbols(funds, root)        # AC-3: full-basket secids
    provisional_flow, batch_industry = _batch_flow_industry(root, batch_symbols)
```

and AFTER the `provisional_flow_as_of = (...)` block insert:

```python
    _record_industry_seen(root, _today, batch_industry)            # AC-5 (12:15 site)
    industry_serving = _industry_serving_map(root, _today)         # AC-6: post-merge slice
```

8. In `run_monitor`'s per-fund loop, add the kwarg to the `_process_fund` call:

```python
                today=_today, flow_slice=flow_slice, theme_results=theme_results,
                provisional_flow=provisional_flow,
                provisional_flow_as_of=provisional_flow_as_of,
                industry_serving=industry_serving,
```

9. In `_process_fund`, add the trailing param `industry_serving: dict | None = None` to the signature and thread it into the `_build_full_basket_metrics` call:

```python
            holding_metrics = _build_full_basket_metrics(
                full_holdings, top5, fund.id, root=root, today=today, con=con,
                flow_slice=(flow_slice if flow_slice is not None
                            else _load_flow_store_slice(
                                root, tuple(h.symbol for h in top5))),
                industry_serving=industry_serving)
```

- [ ] **Step 4: Update the four renamed monkeypatch sites**

- `tests/commands/test_monitor_cmd.py` — in `test_run_monitor_calls_provisional_flow_note_once_per_run` (rename it `test_run_monitor_calls_batch_flow_industry_once_per_run`):

```python
    monkeypatch.setattr(mc, "_batch_flow_industry", lambda root, symbols: (
        calls.append(symbols) or (None, None)
    ))
```

- `tests/commands/test_monitor_cmd.py` — in `test_run_monitor_provisional_flow_note_error_degrades_to_no_annotation`:

```python
    monkeypatch.setattr(mc, "_batch_flow_industry", lambda root, symbols: (None, None))
```

- `tests/commands/test_monitor_cmd_drilldown.py:222` and `tests/commands/test_monitor_constituent.py:495` — replace each `monkeypatch.setattr(mc, "_provisional_flow_note", lambda root, symbols: None)` with:

```python
    monkeypatch.setattr(mc, "_batch_flow_industry", lambda root, symbols: (None, None))
```

- `tests/commands/test_monitor_flow_capture.py` — `test_provisional_note_never_writes_store` becomes:

```python
def test_batch_note_never_writes_store(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "fetch_flow_today_batch",
                        lambda symbols: ({"600519": 11.78}, {"600519": "酿酒行业"}))
    note, industry = mc._batch_flow_industry(tmp_path, ("600519",))
    assert note == {"600519": 11.78}
    assert industry == {"600519": "酿酒行业"}
    # CRITICAL (D6/trap §8): the 12:15 path must NOT create/modify the FLOW store
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()
```

- [ ] **Step 5: Run to verify green**

```bash
uv run pytest tests/commands/test_monitor_cmd_industry.py -q
uv run pytest tests/commands/test_monitor_cmd.py -q
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -q
uv run pytest tests/commands/test_monitor_constituent.py -q
uv run pytest tests/commands/test_monitor_flow_capture.py -q
uv run pytest tests/commands/test_monitor_cmd_valuation.py -q
```
Expected: all PASS (per-file only — never the whole dir).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_industry.py tests/commands/test_monitor_cmd.py tests/commands/test_monitor_cmd_drilldown.py tests/commands/test_monitor_constituent.py tests/commands/test_monitor_flow_capture.py
git add -A && git commit -m "feat(monitor): batch-first 行业 — full-basket secids, cross-day store merge, store->batch->fallback consume order (004 AC-3/5/6)"
```

---

### Task 8: Board-PE fetch-first + freshness threading (AC-8, wiring for AC-11/12/13)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Test: `tests/commands/test_monitor_cmd_industry.py` (append)

**Interfaces:**
- Produces: `_wants_board_pe(funds, con) -> bool`; `_fetch_board_pe(root, today, trading_days) -> tuple[dict, BoardPeFreshness]`; `_process_fund(..., board_pe=None)`; `_make_view(..., board_pe_freshness=None)`; `_compute_gates(..., board_pe_freshness=None)`; `_write_eval_artifacts(..., board_pe_freshness=None)`; `_write_drilldown` rows gain `v.board_pe_freshness` as element 7.
- Consumes: Task 3 `BoardPeFreshness`/`freshness_dict`, Task 4 `fetch_industry_pe`, Task 5 kwargs, Task 6 `FundView` field.

- [ ] **Step 1: Write the failing tests**

Append to `tests/commands/test_monitor_cmd_industry.py`:

```python
# ---- AC-8: fetch-first order + run-level threading ----


def test_board_pe_fetch_first_before_any_per_symbol_fallback(tmp_path, monkeypatch):
    """AC-8 call-order recorder: the board-PE fetch fires ONCE, at run level,
    BEFORE the first per-symbol fallback, across a 2-active-fund run."""
    _wire_two_fund_run(tmp_path, monkeypatch, batch_industry=None)   # nothing batched
    order = []
    monkeypatch.setattr(
        mc, "fetch_industry_pe",
        lambda **kw: order.append("board_pe")
        or ({}, BoardPeFreshness("DARK", None, None)))
    monkeypatch.setattr(
        mc, "fetch_stock_industry_map",
        lambda symbols, **kw: order.append("fallback") or {s: None for s in symbols})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert order.count("board_pe") == 1              # ONE fetch per run, run-level
    assert order.count("fallback") == 2              # one per active fund
    assert order.index("board_pe") < order.index("fallback")


def test_board_pe_fetch_receives_hoisted_trading_days(tmp_path, monkeypatch):
    """Q10: the hoisted load_trading_days frozenset is threaded to the board-PE
    fetch (and load_trading_days is still called exactly once per run)."""
    _wire_two_fund_run(tmp_path, monkeypatch, batch_industry={"600519": "酿酒行业",
                                                              "000651": "家电行业"})
    tds = frozenset({date(2026, 7, 2), date(2026, 7, 3)})
    calendar_calls = []
    monkeypatch.setattr(mc, "load_trading_days",
                        lambda today, root: calendar_calls.append(1) or tds)
    seen = {}

    def _probe(**kw):
        seen["trading_days"] = kw.get("trading_days")
        return {}, BoardPeFreshness("DARK", None, None)

    monkeypatch.setattr(mc, "fetch_industry_pe", _probe)
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert seen["trading_days"] == tds
    assert len(calendar_calls) == 1                  # hoist is a pure move — one call


def test_trace_carries_run_level_board_pe_freshness(tmp_path, monkeypatch):
    """AC-11 wiring: run_monitor threads the freshness dict into eval_trace.json."""
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({"酿酒行业": 30.0},
                                      BoardPeFreshness("STALE", "2026-07-02", 1)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    trace = json.loads((tmp_path / "outputs" / "2026-07-03" / "monitor" /
                        "eval_trace.json").read_text(encoding="utf-8"))
    assert trace["schema_version"] == "7"            # AC-11: NO second bump
    assert trace["board_pe_freshness"] == {"state": "STALE", "as_of": "2026-07-02",
                                           "age_td": 1}


def test_report_and_drilldown_carry_stale_age_tag_end_to_end(tmp_path, monkeypatch):
    """AC-13 wiring: STALE freshness renders the exact age tag on BOTH surfaces."""
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({"酿酒行业": 30.0},
                                      BoardPeFreshness("STALE", "2026-07-02", 1)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    out = tmp_path / "outputs" / "2026-07-03" / "monitor"
    tag = "板块PE 引用 2026-07-02 · 1个交易日前"
    assert tag in (out / "report.html").read_text(encoding="utf-8")
    assert tag in (out / "drilldown.html").read_text(encoding="utf-8")


def test_panel_reason_carries_board_pe_state(tmp_path, monkeypatch):
    """AC-12 wiring: the valuation_coverage panel row surfaces the run-level state."""
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({"酿酒行业": 30.0},
                                      BoardPeFreshness("STALE", "2026-07-02", 1)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    html = (tmp_path / "outputs" / "2026-07-03" / "monitor" / "report.html").read_text(
        encoding="utf-8")
    assert "board_pe STALE-1 (as_of 2026-07-02)" in html


def test_no_active_funds_or_no_con_skips_board_pe_fetch(tmp_path, monkeypatch):
    """_wants_board_pe: the run-level fetch is skipped when nothing will consume
    the table (con=None here — no data/local.duckdb) — keeps gold-only/offline
    runs network-free; trace key degrades to None (AC-11 back-compat)."""
    _wire_two_fund_run(tmp_path, monkeypatch, batch_industry=None)
    (tmp_path / "data" / "local.duckdb").unlink()     # con stays None
    called = []
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: called.append(1)
                        or ({}, BoardPeFreshness("DARK", None, None)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert called == []
    trace = json.loads((tmp_path / "outputs" / "2026-07-03" / "monitor" /
                        "eval_trace.json").read_text(encoding="utf-8"))
    assert trace["board_pe_freshness"] is None
```

Run: `uv run pytest tests/commands/test_monitor_cmd_industry.py -q` → Expected: the 6 new tests FAIL.

- [ ] **Step 2: Implement in `src/irc/commands/monitor_cmd.py`**

1. Add import:

```python
from irc.monitor.board_pe_staleness import BoardPeFreshness, freshness_dict
```

2. Add the two helpers (after `_industry_serving_map`):

```python
def _wants_board_pe(funds, con) -> bool:
    """Board PE is consumed only inside _build_full_basket_metrics, which is
    con-gated AND active-fund-gated — skip the run-level fetch when nothing will
    read the table (gold-only configs / no DuckDB stay network-free, the same
    effective gating the lazy pre-004 call had). Trace key degrades to None."""
    from irc.monitor.profiles import PROFILES
    if con is None:
        return False
    return any((spec := PROFILES.get(f.analysis_profile)) is not None
               and spec.lookthrough == "active_fund" for f in funds)


def _fetch_board_pe(root: Path, today: str, trading_days) -> tuple[dict, BoardPeFreshness]:
    """EDGE (AC-8 fetch-first): the ONE board-PE fetch per run, at run_monitor
    level BEFORE the per-fund loop (ahead of any per-symbol fallback storm,
    adjacent to the one batch call). Degrades to ({}, DARK) — never crashes."""
    try:
        return fetch_industry_pe(
            cache_dir=root / "data" / "monitor" / "industry_pe", today=today,
            trading_days=trading_days)
    except Exception:  # noqa: BLE001 — fetch_industry_pe never raises; belt+braces
        _log.warning("board PE run-level fetch failed", exc_info=True)
        return {}, BoardPeFreshness("DARK", None, None)
```

3. In `run_monitor`, directly after the `industry_serving = ...` line from Task 7, insert:

```python
    trading_days = load_trading_days(date.today(), root=root)      # hoisted (Q10)
    board_pe = (_fetch_board_pe(root, _today, trading_days)        # AC-8: fetch-first
                if _wants_board_pe(funds, con) else None)
    board_pe_dict = freshness_dict(board_pe[1]) if board_pe is not None else None
```

and DELETE the old `trading_days = load_trading_days(date.today(), root=root)` line (currently after `now_dt = ...`, line ~1028). `now_dt` stays where it is.

4. Thread through the loop call — add to the `_process_fund` call:

```python
                industry_serving=industry_serving, board_pe=board_pe,
```

5. `_process_fund`: add trailing param `board_pe=None`; pass `board_pe=board_pe` into `_build_full_basket_metrics`; change the `_make_view` call to add:

```python
                      board_pe_freshness=(board_pe[1] if board_pe is not None else None))
```

6. `_make_view`: add trailing kwarg `board_pe_freshness=None` and pass `board_pe_freshness=board_pe_freshness` into the `FundView(...)` constructor.

7. `_write_drilldown`: extend the row tuple:

```python
    dd_views = tuple(
        (
            v.fund_id, v.name_cn, v.holding_metrics,
            aggregate_flow(v.holding_metrics), v.signal,
            aggregate_valuation(v.holding_metrics), v.board_pe_freshness,
        )
        for v in views if v.holding_metrics
    )
```

8. `_compute_gates`: add trailing keyword param `board_pe_freshness: dict | None = None`; change the `valuation_coverage_health` call to:

```python
            val_cov_healths[fund.id] = valuation_coverage_health(
                projection, board_pe_freshness=board_pe_freshness)
```

and in `run_monitor` pass `board_pe_freshness=board_pe_dict` to `_compute_gates(...)`.

9. `_write_eval_artifacts`: add trailing keyword param `board_pe_freshness: dict | None = None` and pass `board_pe_freshness=board_pe_freshness` into `build_eval_trace(...)`; in `run_monitor` pass `board_pe_freshness=board_pe_dict` at the call site.

- [ ] **Step 3: Run to verify green**

```bash
uv run pytest tests/commands/test_monitor_cmd_industry.py -q
uv run pytest tests/commands/test_monitor_cmd.py -q
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -q
uv run pytest tests/commands/test_monitor_cmd_trace.py -q
uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q
uv run pytest tests/commands/test_monitor_constituent.py -q
uv run pytest tests/commands/test_monitor_cmd_valuation.py -q
```
Expected: all PASS.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_industry.py
git add -A && git commit -m "feat(monitor): board-PE fetch-first at run level + freshness threading to trace/panel/renderers (004 AC-8/11/12/13 wiring)"
```

---

### Task 9: `run_flow_capture` — widened secids, slice-back, industry merge, P8c (AC-3, AC-5 capture site, AC-14)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (`run_flow_capture` + new `_capture_board_pe`)
- Test: `tests/commands/test_monitor_flow_capture.py` (rewrite)

**Interfaces:**
- Consumes: Task 1 `fetch_flow_today_batch` tuple; Task 7 `_full_basket_union_symbols` / `_record_industry_seen`; Task 4 `fetch_industry_pe`.
- Ordering contract (RD-6, load-bearing): flow `append_today` FIRST, then industry-store merge, then best-effort board-PE — a protective watchdog kill (`IRC_FLOW_CAPTURE_TIMEOUT`, 300 s) can only ever cost the refresh, never the flow row. NO edit to `ops/launchd/run-flow-capture.sh`.

- [ ] **Step 1: Rewrite the test file (failing)**

Replace the full contents of `tests/commands/test_monitor_flow_capture.py` with:

```python
from __future__ import annotations

import json

import irc.commands.monitor_cmd as mc
from irc.monitor.board_pe_staleness import BoardPeFreshness


def _wire_capture(tmp_path, monkeypatch, *, board_pe=None):
    """Offline capture harness: 2 top-5 symbols, 3 full-basket symbols (AC-3)."""
    monkeypatch.setattr(mc, "load_monitor_config", lambda root: object())
    monkeypatch.setattr(mc, "resolve_funds", lambda cfg: [object()])
    monkeypatch.setattr(mc, "_capture_union_symbols",
                        lambda funds, root: ("600519", "000651"))
    monkeypatch.setattr(mc, "_full_basket_union_symbols",
                        lambda funds, root: ("600519", "000651", "600233"))
    monkeypatch.setattr(
        mc, "fetch_flow_today_batch",
        lambda symbols: ({"600519": 4.0, "000651": 7.0, "600233": 9.0},
                         {"600519": "酿酒行业", "000651": None, "600233": "航天航空"}))
    monkeypatch.setattr(mc, "load_trading_days",
                        lambda today, root: frozenset({__import__("datetime").date(2026, 7, 1)}))
    monkeypatch.setattr(
        mc, "fetch_industry_pe",
        board_pe or (lambda **kw: ({}, BoardPeFreshness("DARK", None, None))))


def test_run_flow_capture_appends_completed_day_top5_only(tmp_path, monkeypatch):
    """AC-3: full-basket secids in the ONE batch call, but the flow store is
    sliced back to the top-5 union BEFORE append_today — D5 scope preserved,
    NO non-top-5 symbol ever enters fund_flow_series.json."""
    _wire_capture(tmp_path, monkeypatch)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    store = json.loads((tmp_path / "data" / "monitor" / "fund_flow_series.json").read_text())
    assert store["600519"] == [["2026-07-01", 4.0]]
    assert store["000651"] == [["2026-07-01", 7.0]]
    assert "600233" not in store            # full-basket tail NEVER enters the flow store


def test_capture_merges_batch_industry_into_cross_day_store(tmp_path, monkeypatch):
    """AC-5 (15:45 site): the f127 map — including the non-top-5 tail — lands in
    stock_industry_map.json; None never merges."""
    _wire_capture(tmp_path, monkeypatch)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    imap = json.loads((tmp_path / "data" / "monitor" / "stock_industry_map.json")
                      .read_text(encoding="utf-8"))
    assert imap["600233"]["industry"] == "航天航空"   # basket tail accumulates
    assert imap["600519"]["industry"] == "酿酒行业"
    assert "000651" not in imap                       # None never merges (RD-4)


def test_capture_board_pe_failure_never_fails_capture(tmp_path, monkeypatch):
    """AC-14: a raising board-PE refresh → rc 0, flow store still written."""
    def _boom(**kw):
        raise RuntimeError("board fetch down")

    _wire_capture(tmp_path, monkeypatch, board_pe=_boom)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    store = json.loads((tmp_path / "data" / "monitor" / "fund_flow_series.json").read_text())
    assert store["600519"] == [["2026-07-01", 4.0]]


def test_capture_board_pe_runs_after_flow_append(tmp_path, monkeypatch):
    """RD-6 load-bearing ordering: board PE fires strictly AFTER the flow row is
    durably written (a watchdog kill loses only the refresh, never the row)."""
    seen = {}

    def _probe(**kw):
        seen["flow_store_exists"] = (
            tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()
        seen["cache_dir"], seen["today"] = kw["cache_dir"], kw["today"]
        return {}, BoardPeFreshness("DARK", None, None)

    _wire_capture(tmp_path, monkeypatch, board_pe=_probe)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    assert seen["flow_store_exists"] is True
    assert seen["cache_dir"] == tmp_path / "data" / "monitor" / "industry_pe"
    assert seen["today"] == "2026-07-01"     # capture's own today (P8c)


def test_capture_empty_symbols_early_return(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "load_monitor_config", lambda root: object())
    monkeypatch.setattr(mc, "resolve_funds", lambda cfg: [])
    monkeypatch.setattr(mc, "_full_basket_union_symbols", lambda funds, root: ())
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()


def test_capture_batch_failure_degrades_rc0(tmp_path, monkeypatch):
    _wire_capture(tmp_path, monkeypatch)

    def _boom(symbols):
        raise RuntimeError("ulist down")

    monkeypatch.setattr(mc, "fetch_flow_today_batch", _boom)
    rc = mc.run_flow_capture(repo_root=str(tmp_path), today="2026-07-01")
    assert rc == 0
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()


def test_batch_note_never_writes_store(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "fetch_flow_today_batch",
                        lambda symbols: ({"600519": 11.78}, {"600519": "酿酒行业"}))
    note, industry = mc._batch_flow_industry(tmp_path, ("600519",))
    assert note == {"600519": 11.78}
    assert industry == {"600519": "酿酒行业"}
    # CRITICAL (D6/trap §8): the 12:15 path must NOT create/modify the FLOW store
    assert not (tmp_path / "data" / "monitor" / "fund_flow_series.json").exists()
```

Run: `uv run pytest tests/commands/test_monitor_flow_capture.py -q` → Expected: FAILs (`_full_basket_union_symbols` not used yet / no P8c call / no slice-back).

- [ ] **Step 2: Implement**

Replace `run_flow_capture` in `src/irc/commands/monitor_cmd.py` with:

```python
def run_flow_capture(*, repo_root: str, today: str | None = None) -> int:
    """EDGE (15:45 job, D6): ONE ulist.np batch over the FULL-BASKET union (AC-3)
    → append the now-final f184 to the completed-day store, SLICED BACK to the
    top-5 union (D5 store scope/bytes unchanged) → merge f127 行业 into the
    cross-day store (AC-5) → best-effort board-PE refresh strictly AFTER the
    append (P8c/RD-6 — a watchdog kill loses only the refresh, never the flow
    row). No LLM, no report, no ledger. `today` MUST be a completed CN trading
    day (the wrapper runs it after the 15:00 close)."""
    root = Path(repo_root)
    _today = today or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    funds = resolve_funds(load_monitor_config(root))
    batch_symbols = _full_basket_union_symbols(funds, root)
    if not batch_symbols:
        _log.warning("flow-capture: no active-fund symbols; nothing to capture")
        return 0
    try:
        flow_by_symbol, industry_by_symbol = fetch_flow_today_batch(batch_symbols)
    except Exception:  # noqa: BLE001 — degrade, never crash (breaker/abort posture)
        _log.warning("flow-capture: ulist.np batch failed", exc_info=True)
        return 0
    top5_union = _capture_union_symbols(funds, root)
    store_flow = {s: flow_by_symbol.get(s) for s in top5_union}   # AC-3 slice-back (D5)
    trading_days = load_trading_days(date.today(), root=root)
    tds = tuple(d.isoformat() for d in (trading_days or ()))
    append_today(root / "data" / "monitor" / "fund_flow_series.json", _today,
                 store_flow, keep_td=_FLOW_KEEP_TD, trading_days=tds)
    print(f"flow-capture OK: {_today} appended "
          f"{sum(v is not None for v in store_flow.values())}/{len(top5_union)} symbols")
    _record_industry_seen(root, _today, industry_by_symbol)       # AC-5 (15:45 site)
    _capture_board_pe(root, _today)                               # P8c AFTER append (RD-6)
    return 0


def _capture_board_pe(root: Path, today: str) -> None:
    """EDGE (P8c, AC-14): best-effort board-PE refresh in the proven rested 15:45
    window so next morning's fallback is at worst 1 day old. Runs strictly AFTER
    the flow append (RD-6). Never affects the capture rc; the freshness half is
    ignored. Worst-case added time ≈ 203 s fits the 300 s protective watchdog."""
    try:
        fetch_industry_pe(cache_dir=root / "data" / "monitor" / "industry_pe", today=today)
    except Exception:  # noqa: BLE001 — a board-PE failure never fails capture
        _log.warning("flow-capture: board PE refresh failed", exc_info=True)
```

- [ ] **Step 3: Run to verify green**

Run: `uv run pytest tests/commands/test_monitor_flow_capture.py -q`
Expected: 7 passed.

- [ ] **Step 4: Lint + commit**

```bash
uv run ruff check src/irc/commands/monitor_cmd.py tests/commands/test_monitor_flow_capture.py
git add -A && git commit -m "feat(monitor): flow-capture widens to full-basket secids w/ top-5 slice-back + industry merge + P8c board-PE refresh (004 AC-3/5/14)"
```

---

### Task 10: Docs sync + CHANGELOG (AC-17)

**Files:**
- Verify only (landed at the grill): `docs/adr/0020-monitor-dual-track-valuation.md` addendum "board-PE three-state staleness + fetch-first; industry names batch-first (2026-07-03)"; `CONTEXT.md` terms *Board-PE freshness state* (lines ~19) + *Stock-industry map (cross-day store)* (~20).
- Modify: `docs/monitor/README.md`, `docs/diagrams/monitor-workflow.html`, `CHANGELOG.md`.

- [ ] **Step 1: Verify the grill-landed docs are present (no edit)**

```bash
grep -c "board-PE three-state staleness" docs/adr/0020-monitor-dual-track-valuation.md   # expect 1
grep -c "Stock-industry map (cross-day store)" CONTEXT.md                                 # expect >=1
```

- [ ] **Step 2: Update the ops manual `docs/monitor/README.md`**

1. Line ~44 (the `15:45 daily` row) — replace the description with:

> `irc monitor flow-capture` — one batched EastMoney `ulist.np` call (full-basket secids, `f184`+`f127`) appends today's **completed-day** capital-flow row to `data/monitor/fund_flow_series.json` (top-5-union scope, ~25 trading-day retention), merges the `f127` 行业 names into `data/monitor/stock_industry_map.json`, then best-effort refreshes the board-PE day cache in the rested window (so next morning's stale fallback is at worst 1 day old). The extra duties ride AFTER the flow append and fit the default 300 s watchdog. Best-effort: 5-min watchdog, no page. **Never run manually before the 15:00 close** — the manual path is unguarded.

2. In the "What one 12:15 run does" section (after line ~52), add a bullet:

> - **行业 is batch-first (ADR 0020 addendum 2026-07-03):** the one `ulist.np` batch call carries `f127`; names accumulate cross-day in `data/monitor/stock_industry_map.json` (serve-while-stale ≤ 30 calendar days, refresh-on-seen). The per-symbol `stock/get` path fires only for symbols absent from that map (~never in steady state). Board PE is fetched ONCE at run level before the per-fund loop; on failure the most recent non-empty cached table ≤ 3 trading days old feeds factor math with an explicit `板块PE 引用 <date> · N个交易日前` tag (FRESH / STALE-N / DARK — see CONTEXT.md *Board-PE freshness state*).

3. In the data-files table (~line 225), add rows:

> | `data/monitor/stock_industry_map.json` | Cross-day stock→行业 store (batch-first f127; fallback merges too) |
> | `data/monitor/industry_pe/<date>.json` | Board-PE day cache (non-empty parses only; stale-served ≤ 3 td with an age tag) |

4. In the troubleshooting table (~line 246), add:

> | 行业/行业PE columns dark | Check the panel's `board_pe FRESH/STALE-N/DARK` reason + `stock_industry_map.json` coverage; a DARK board PE ≤ 3 td heals from the 15:45 refresh (P8c) |

- [ ] **Step 3: Update `docs/diagrams/monitor-workflow.html`**

Three text-level edits (keep the SVG structure; these are label/annotation updates — find each by the quoted existing string):

1. Line ~229 (`ulist.np · IRC_CN_PROXY · render-only 盘中提示`) → `ulist.np(f184+f127) · IRC_CN_PROXY · 盘中提示 render-only · f127→industry map store`
2. Line ~258 (`industry PE via IRC_CN_PROXY`) → `board PE fetch-first ×1/run · FRESH/STALE-N≤3td/DARK · 行业 store→batch→fallback`
3. Line ~351 (`ulist.np ×1 post-close · best-effort, no page`) → `ulist.np ×1 full-basket post-close · +f127 store merge · +board-PE refresh · best-effort, no page`

Open the file in a browser (or trust visual inspection of the diff) to confirm no SVG breakage — text-only changes inside existing `<text>` elements.

- [ ] **Step 4: CHANGELOG**

Add under `## [Unreleased]` (above the item-002 block):

```markdown
### Added — monitor industry fill: batch-first 行业 + board-PE serve-while-stale (2026-07-03)

- **行业 names go batch-first** (report-v4 explainability WS-4 / P7, item 004):
  the ONE existing `ulist.np` batch call carries `f127` at both call sites
  (12:15 brief + 15:45 capture, full-basket secids with top-5 flow-store
  slice-back); parsed names accumulate in the new cross-day
  `data/monitor/stock_industry_map.json` (refresh-on-seen, serve-while-stale
  ≤ 30 calendar days, None/blank never written); the per-symbol `stock/get`
  path is fallback-only (~0 calls/day in steady state, ending the ~60-call
  throttle storm). New `monitor/industry_map_store.py`.
- **Board-PE three-state freshness + fetch-first** (P8, OD-1): the paginated
  board-PE fetch runs ONCE at run level before the per-fund loop; on
  empty/failed fetch the newest NON-EMPTY cached table ≤ 3 trading days old
  feeds factor math as STALE-N with an explicit `板块PE 引用 <date> ·
  N个交易日前` tag on the report card + drilldown (> 3 td / no calendar on the
  stale branch → DARK → `industry_no_data`, `val_score == self_score`); the
  15:45 capture job best-effort refreshes board PE after the flow append. New
  `monitor/board_pe_staleness.py`; run-level `board_pe_freshness` trace key
  (additive under schema "7", no bump) + `board_pe FRESH/STALE-N/DARK` panel
  reason. `_ENGINE_VERSION` and `KNOWN_NA_REASONS` unchanged (ADR 0020
  addendum 2026-07-03).
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "docs(monitor): ops manual + workflow diagram + CHANGELOG for batch-first 行业 and board-PE staleness (004 AC-17)"
```

---

### Task 11: Full sweep, hygiene pins, freeze checks (AC-16, AC-18)

- [ ] **Step 1: Signature-change caller sweep (standing lesson)**

```bash
grep -rln "fetch_flow_today_batch\|parse_ulist\|fetch_industry_pe\|_build_full_basket_metrics\|fetch_stock_industry_map\|_provisional_flow_note" tests/
```
Expected files (all already updated; `_provisional_flow_note` must have ZERO remaining hits): `tests/monitor/test_flow_batch_fetch.py`, `tests/monitor/test_flow_fetch.py` (comment only), `tests/monitor/test_industry_valuation.py`, `tests/scripts/test_phase0_flow_batch_spike.py` (private copy), `tests/commands/test_monitor_cmd_valuation.py`, `tests/commands/test_monitor_flow_capture.py`, `tests/commands/test_monitor_constituent.py`, `tests/commands/test_monitor_cmd_industry.py`. If grep reveals ANY other file, run it and fix.

- [ ] **Step 2: Run the mirror suites**

```bash
uv run pytest tests/monitor/ -q
```
Expected: all pass (includes `test_known_na_reasons.py`, golden, eval/).

Then per-file (NEVER the whole `tests/commands/` dir — it hangs):

```bash
uv run pytest tests/commands/test_monitor_cmd.py -q
uv run pytest tests/commands/test_monitor_cmd_industry.py -q
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -q
uv run pytest tests/commands/test_monitor_cmd_valuation.py -q
uv run pytest tests/commands/test_monitor_cmd_trace.py -q
uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q
uv run pytest tests/commands/test_monitor_cmd_heat.py -q
uv run pytest tests/commands/test_monitor_cmd_market_composite.py -q
uv run pytest tests/commands/test_monitor_cmd_nav_history.py -q
uv run pytest tests/commands/test_monitor_cmd_forward_eval.py -q
uv run pytest tests/commands/test_monitor_cmd_predictive_panel.py -q
uv run pytest tests/commands/test_monitor_cmd_theme_consolidation.py -q
uv run pytest tests/commands/test_monitor_cmd_timeline.py -q
uv run pytest tests/commands/test_monitor_constituent.py -q
uv run pytest tests/commands/test_monitor_flow_capture.py -q
uv run pytest tests/commands/test_monitor_snapshot.py -q
uv run pytest tests/scripts/test_phase0_flow_batch_spike.py -q
uv run pytest tests/evals/ -q
```
Expected: all pass.

- [ ] **Step 3: Freeze pins (AC-16)**

```bash
grep -n '_ENGINE_VERSION = "4"' src/irc/commands/monitor_cmd.py        # expect 1 hit, unchanged
grep -n 'SCHEMA_VERSION = "7"' src/irc/monitor/eval/trace.py           # expect 1 hit, unchanged
git diff autodev/monitor-v4-explainability-feature -- src/irc/monitor/factors.py VERSION src/irc/monitor/eval/structural.py
```
Expected: `factors.py` and `VERSION` show NO diff; `structural.py` diff touches ONLY `valuation_coverage_health` + `_board_pe_reason` (NEVER `flow_reconciliation`).

```bash
git diff autodev/monitor-v4-explainability-feature --stat -- src/irc/monitor/eval/structural.py src/irc/monitor/flow_batch_fetch.py
```
Confirm `flow_reconciliation` untouched by inspecting: `git diff autodev/monitor-v4-explainability-feature -- src/irc/monitor/eval/structural.py | grep -c "flow_reconciliation"` → expect `0`.

- [ ] **Step 4: Size budgets**

```bash
wc -l src/irc/monitor/industry_map_store.py src/irc/monitor/board_pe_staleness.py src/irc/monitor/industry_valuation.py
```
Expected: first two < 200; `industry_valuation.py` ≤ 207.

- [ ] **Step 5: Lint everything touched**

```bash
uv run ruff check src tests
```
Expected: clean.

- [ ] **Step 6: Final commit (if any stragglers)**

```bash
git status --short
git add -A && git commit -m "chore(monitor): 004 sweep — caller sweep, freeze pins, size budgets" || true
```

---

## FINAL — Ship-phase note: AC-15 is a MERGE PRECONDITION, not a unit test

**Everything above is offline-green without network.** Before this item merges, the **orchestrator** (not the impl agent, never a committed test) must run ONE live spot-check through `IRC_CN_PROXY` covering BOTH perturbation axes (RD-1):

- **Request A:** the **top-5 union** secids with the OLD field set `f12,f14,f184`.
- **Request B:** the **full-basket union** secids with the NEW field set `f12,f14,f184,f127`.
- **Gate:** f184 over the secid **intersection** must match to **4 dp**.

Use a small throwaway script (extension of `scripts/phase0_flow_batch_spike.py` methodology — do NOT commit it as a live test), e.g.:

```python
# throwaway: uv run python /tmp/spotcheck_004.py  (requires IRC_CN_PROXY set)
import irc.monitor.flow_batch_fetch as fb
from irc.http_proxy import resolve_cn_proxy

TOP5 = [...]        # paste _capture_union_symbols output from a repl
FULL = [...]        # paste _full_basket_union_symbols output

proxy = resolve_cn_proxy()
proxies = {"http": proxy, "https": proxy} if proxy else None


def raw(secids, fields):
    return fb._default_http_get(
        fb._ULIST_URL,
        params={"ut": fb._UT, "fltt": "2", "invt": "2", "np": "1", "dect": "1",
                "secids": fb.build_secids(secids), "fields": fields},
        headers=fb._HEADERS, timeout=20, proxies=proxies)


a = {s: pair[0] for s, pair in fb.parse_ulist(raw(TOP5, "f12,f14,f184")).items()}
b = {s: pair[0] for s, pair in fb.parse_ulist(raw(FULL, "f12,f14,f184,f127")).items()}
common = set(a) & set(b)
bad = {s for s in common
       if (a[s] is None) != (b[s] is None)
       or (a[s] is not None and round(a[s], 4) != round(b[s], 4))}
print(f"intersection={len(common)} mismatches={sorted(bad)}")
assert common and not bad, "AC-15 FAILED — do not merge"
```

(Note: intraday f184 moves — run the two requests back-to-back; a residual mismatch from a tick between calls should be re-run once before being treated as a failure.)

**If live EastMoney endpoints are unreachable at merge time:** this item **pauses at its verify gate as a documented environmental stop** (MASTER-SPEC known risk — items 001–003 land regardless). Never silently skipped, never merged unverified.
