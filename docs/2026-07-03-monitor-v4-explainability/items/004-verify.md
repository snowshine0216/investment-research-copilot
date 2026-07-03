Verdict: PASS

## Subagent

None (Agent tool forbidden for this dispatch, per instructions). All probing done directly in this session.

## Source

- Branch: `claude/monitor-v4-explainability-004` (confirmed via `git branch --show-current`).
- Spec: `docs/2026-07-03-monitor-v4-explainability/items/004-spec.md` (18 ACs, grill strike-throughs corrected — corrected lines RD-1..RD-9 taken as governing).
- No `.claude/skills/verifier-*` exists for this repo; fell back to direct entry-point exercise per the `/verify` skill's fallback path (cold-start, ~15 min timebox not needed — repo structure + existing test harness patterns were legible immediately).
- Implementation commits inspected: `804bec65` (AC-1/2), `d213c0bf` (AC-4), `43bf2fb8` (AC-3/5/6), `d680ef4c`+`24e1a1a0` (AC-9/10), `04e9c753` (AC-11/12), `f3f06084` (AC-13), `19a93785` (AC-8/11/12/13 wiring), `cab1e01a` (AC-3/5/14), `68606f4b` (round-1 fixes: corrupt cache guard, NOT_REQUESTED marker, future seen_at hardening), `4426eaa5` (AC-17 docs).

## Entry points exercised

- `irc.monitor.industry_map_store` (`load_store`, `merge_seen`, `fresh_slice`, `record_seen`) — direct, temp-dir I/O, real module.
- `irc.monitor.board_pe_staleness` (`newest_nonempty`, `stale_fallback`, `trading_day_age`) — direct, against **both** a temp dir and the REAL (read-only) `data/monitor/industry_pe/` directory.
- `irc.monitor.industry_valuation.fetch_industry_pe` — direct, real function, with a stubbed failing `fetch` + corrupt on-disk day files.
- `irc.monitor.render_drilldown` (`board_pe_age_note_html`, `drilldown_section_html`, `drilldown_page_html`) — direct, real render functions, with hand-built real `HoldingMetric`/`FlowAggregate`/`SignalRecord`/`ValuationAggregate` fixtures (not `None` stand-ins).
- `irc.monitor.flow_batch_fetch.parse_ulist` / `fetch_flow_today_batch` — direct, real functions, fixture EastMoney-shaped payloads.
- `irc.commands.monitor_cmd.run_monitor` — **the real 12:15-brief entry point**, driven end-to-end (self-authored fixture: one active fund, 3-symbol basket, pre-seeded cross-day store, monkeypatched true I/O edges only: `load_monitor_config`/network fetchers/DuckDB connect), asserting on the actual written `eval_trace.json` and `stock_industry_map.json` files on disk.
- `irc.commands.monitor_cmd.run_flow_capture` — **the real 15:45-capture entry point**, driven end-to-end, asserting on the actual written `fund_flow_series.json` and `stock_industry_map.json` files on disk.
- `irc.commands.monitor_cmd._industry_map_for` — direct, the AC-6 consume-order helper, with a spy replacing `fetch_stock_industry_map`.
- Existing test suite `tests/commands/test_monitor_cmd_industry.py` (14 tests, itself driving `run_monitor` end-to-end) run as an independent cross-check.

All work offline: no live network, no `uv run irc monitor`. Scratch scripts under `/private/tmp/claude-501/-Users-snow-Documents-Repository-investment-research-copilot/e9f46457-68e8-40b2-b209-50defc4c9c0b/scratchpad/{probe_004.py, probe_004_capture.py, probe_004_run_monitor.py}` (69 self-authored assertions total, all PASS).

## Observed behavior (criterion — evidence)

**AC-1 (parse_ulist carries f127, flow-identity).** Reconstructed a private pre-004 `_old_parse_ulist` (f184-only) from the spec's description and ran it against 6 fixture payloads (present/absent/blank/whitespace-only f127, list-shaped `diff`, blank payload) alongside the current `parse_ulist`. Flow halves matched byte-for-byte in all 6 cases. f127 semantics verified: present→parsed (`{'600690': (1.23, '家用电器')}`), `'-'`→None, `''`→None, whitespace-only→None. — PASS.

**AC-2 (one call, both maps).** `fetch_flow_today_batch` source inspected: single `get(...)` call, `fields=f12,f14,f184,f127`, returns `(flow, industry)` two-dict tuple, every requested symbol present in both (verified via probe `e1`/`e2`/`run_monitor` probe). — PASS.

**AC-3 (secids widen to full-basket union; flow store scope unchanged).** Drove real `run_flow_capture` with a 7-symbol full-basket batch and a 5-symbol top-5 union. Batch call received all 7 symbols (`cap2`); on-disk `fund_flow_series.json` contained exactly the 5 top-5 symbols, disjoint from the 2 tail symbols (`cap4`/`cap4b`). — PASS.

**AC-4 (industry_map_store).** Round-trip probe (a): `record_seen` writes byte-stable sorted JSON; `load_store` returns `{}` on corrupt JSON (`a3`); future `seen_at` excluded from `fresh_slice` (`a4`, the round-1 P2 hardening for clock-skew); 31-day-old row aged out, 30-day-old (boundary) still served (`a5`/`a5b`); all-None/blank input merge writes **no file at all** (`a6`, matches "a no-op merge writes nothing" doc claim exactly). — PASS.

**AC-5 (both call sites merge, best-effort).** Real `run_monitor` (12:15 site, via `_record_industry_seen`) and real `run_flow_capture` (15:45 site) both drove writes to the same store; `run_flow_capture`'s board-PE-raises probe (`cap9`/`cap10`) confirmed a downstream failure never rolls back the already-written flow/industry stores. — PASS.

**AC-6 (consume order: store → batch → per-symbol fallback).** Self-authored `run_monitor` scenario with 3 symbols split three ways — one resolved by today's batch, one only by yesterday's pre-seeded store, one by neither — showed exactly: `600519` industry from batch, `000651` industry preserved from the carried-over store (fallback never invoked for it), `300014` industry from the fallback (fallback called with **only** `("300014",)**, confirmed via spy). Cross-checked against the 14 real tests in `tests/commands/test_monitor_cmd_industry.py`, all passing. The `{sym: None}`-writes-nothing guard independently verified (`cap7`: a batch-unresolved symbol never appears in the persisted store). — PASS.

**AC-7 (no renderer/table shape change for 行业).** Not independently probed beyond reading `holdings_board_html`/`HoldingMetric` — no `industry` field renaming observed; existing `tests/monitor/test_render_drilldown.py` (46 lines touched, all green) covers this. — PASS (by inspection + green existing suite).

**AC-8 (fetch-first reorder).** Ran `tests/commands/test_monitor_cmd_industry.py::test_board_pe_fetch_first_before_any_per_symbol_fallback` (real `run_monitor`, call-order recorder) — green. Independently confirmed via source read of `_fetch_board_pe` (called once, pre-loop) and the hoisted `load_trading_days` call. — PASS.

**AC-9/AC-10 (freshness states + age math, RD-2/RD-3 boundary rules).** Against the **REAL** `data/monitor/industry_pe/` directory (read-only): confirmed on disk exactly the two `{}` files the spec describes (`2026-06-29.json`, `2026-06-30.json`, both literally `{}`); `newest_nonempty` over that real directory correctly returns `None` (skips both, matching "no cache since 2026-06-30" in the spec). Constructed temp-dir fixtures with a fixture Mon-Fri trading calendar: STALE-2 scenario served `age_td=2`, `state=STALE`, table content served (feeds factor math per OD-1); DARK-4td scenario served `age_td=4` (named, not swallowed) with an empty table; RD-2 boundary (empty `{}` file 1 td old + non-empty file 3 td old) correctly skipped the empty file and served the 3-td-old non-empty one as `STALE-3`. — PASS.

**AC-11 (trace marker, no bump).** `grep SCHEMA_VERSION src/irc/monitor/eval/trace.py` → `"7"` (unchanged). Real `run_monitor` end-to-end run's written `eval_trace.json` inspected directly (own probe) — schema stable. — PASS.

**AC-12 (panel freshness state).** Not independently re-derived beyond source read of `valuation_coverage_health`'s optional kwarg and back-compat default; covered by the item's own `tests/monitor/eval/test_structural.py` (56 lines touched, green). — PASS (by inspection + green existing suite).

**AC-13 (reader-facing age tag on both surfaces).** Drove `board_pe_age_note_html` directly: STALE → exact text `板块PE 引用 2026-06-30 · 2个交易日前` present; FRESH/DARK/None → `''`. Drove the full render chain (`drilldown_section_html`, `drilldown_page_html`) with real `HoldingMetric`/`FlowAggregate`/`SignalRecord`/`ValuationAggregate` fixtures I constructed myself: STALE bundle → tag appears, positioned immediately after `holdings-board` in the HTML (index comparison); DARK bundle → no `板块PE 引用` string anywhere in the rendered section; short view-row (no `val_agg`/`board_pe_freshness`, i.e. NOT_REQUESTED/None) → renders cleanly with no age tag, no crash. — PASS.

**AC-14 (capture-job board-PE, P8c, RD-6 ordering).** Real `run_flow_capture`, board-PE fetch spy confirmed invoked exactly once, and (separately) a **raising** board-PE fetch confirmed capture still returns rc 0 with the flow store still written (`cap9`/`cap10` — the AFTER-the-append ordering's safety property directly observed: a downstream failure cannot roll back the already-completed flow write). — PASS.

**AC-15 (live f184 spot-check).** Orchestrator-run merge precondition, out of verify scope (push2 outage per `004-ship.md`: "AC-15 live spot-check: PENDING at ship time... MERGE PRECONDITION — re-run in a rested window"). Not exercised in this dispatch per instructions.

**AC-16 (engine + reason-vocabulary freeze).** Grepped `_ENGINE_VERSION` — untouched by this diff (no hits in the item-004 file set); `KNOWN_NA_REASONS` untouched (not present in the diff stat's touched-file list beyond structural.py's additive kwarg). — PASS (by inspection).

**AC-17 (docs).** Confirmed by direct file read: CONTEXT.md carries both the sharpened *Board-PE freshness state* term (RD-2/RD-3 rules verbatim: "FRESH is calendar-independent... only a non-empty cached table can be served stale") and the new *Stock-industry map (cross-day store)* term (calendar-vs-trading-day distinction, refresh-on-seen, absence≠evidence). ADR 0020 has the 2026-07-03 addendum section with the stale-scan hygiene rule. `docs/monitor/README.md` documents the batch-first 行业 + board-PE stale-serving + capture-job's new duties. `docs/diagrams/monitor-workflow.html` has both the `f127→industry map store` and the board-PE-refresh annotations. — PASS.

**AC-18 (TDD + hygiene + signature-change sweep).** `uv run ruff check` on all 6 touched/new source files: `All checks passed!`. New modules: `industry_map_store.py` 95 lines, `board_pe_staleness.py` 118 lines (both < 200); `industry_valuation.py` 197 lines (stayed under its 207-line pre-item ceiling, per the spec's explicit budget). `uv run pytest tests/monitor/test_industry_map_store.py tests/monitor/test_board_pe_staleness.py tests/monitor/test_flow_batch_fetch.py tests/monitor/test_render_drilldown.py tests/monitor/test_industry_valuation.py` → 82 passed. `tests/commands/test_monitor_cmd_industry.py` run per-file (per the known suite-ordering hang) → 14 passed. — PASS.

## Failures

None. All 69 self-authored probe assertions passed (40 in `probe_004.py` + 22 in `probe_004_capture.py` + 7 in `probe_004_run_monitor.py`); all inspected existing test files for this item's touched modules passed when run per-file; `ruff check` clean; module line-budgets respected.

One probe-authoring artifact worth noting for the record (not a product defect): my first attempt at probe (c) passed `agg=None`/`signal=None` into `drilldown_section_html` and hit an `AttributeError` inside `flow_rollup_html` — this is pre-existing, unrelated-to-004 behavior (that function has never tolerated `None` aggregates; it's not part of this item's diff). Fixed by constructing real `FlowAggregate`/`SignalRecord` fixtures; not counted as a finding against item 004.

## AC-15 note

AC-15 (live f184 spot-check comparing top-5-union+old-fields vs full-basket-union+new-fields secid requests through `IRC_CN_PROXY`) is the orchestrator's job and is currently blocked by a push2 outage (confirmed via `004-ship.md`: "push2 total 502 block — proxied/direct/single-secid all fail this hour"). Per dispatch instructions: **AC-15: orchestrator-run merge precondition, out of verify scope.**
