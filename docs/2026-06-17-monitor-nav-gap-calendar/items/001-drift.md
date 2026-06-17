Verdict: PASS

Subagent: sonnet
Plan checklist items: 8
Verified present in diff: 8
Drift findings:
  - Task 3 (walrus operator) — vague plan note resolved by implementation
    Evidence: trace.py:69 — `dates = [p for d, _ in recent if (p := _parse(d)) is not None]`
    The plan body notes the `d` shadowing issue and immediately corrects itself to specify
    `(p := _parse(d))`. The implementation uses the corrected `p` form exactly as instructed.
    Action: accepted (implementation matches the corrected plan text)

  - Task 6 Step 8 (extra `_patch_edges` network-stub additions) — incidental, authorized
    Evidence: tests/commands/test_monitor_cmd.py lines 52-53, 179-180, 211-212, 283-284 —
    four `monkeypatch.setattr(mc, "load_trading_days", lambda today, root: None)` blocks
    added inside `_patch_edges` and three inline test functions.
    Plan Task 6 Step 8 explicitly authorizes: "add a default `monkeypatch.setattr(monitor_cmd,
    'load_trading_days', lambda today, root: None)` inside the shared `_patch` helper".
    The impl applies the same degrade-to-None pattern across all four sites in
    `test_monitor_cmd.py` that call `run_monitor` without override. Consistent with intent.
    Action: accepted (authorized by plan Task 6 Step 8)

  - commit 126cefb (test_gate_flip_m1.py fix) — incidental, authorized
    Evidence: tests/monitor/eval/test_gate_flip_m1.py lines 412-422 — three
    `_compute_gates(...)` call sites updated to pass `trading_days=None` after the
    function signature gained that required kwarg in Task 6.
    This is a mandatory mechanical fix for pre-existing tests that call the newly-extended
    `_compute_gates` signature; the plan's Task 6 Step 8 commentary acknowledges that
    pre-existing tests may need updating when the real edge runs. The commit message
    explicitly flags it as "beyond plan scope".
    Action: accepted (signature propagation fix; incidental, no functional scope creep)

Per-task verification summary:
  Task 1: fetch_trade_calendar — PRESENT. src/irc/data/akshare_client.py +15 lines:
    `_ak_call("tool_trade_date_hist_sina")`, `pd.to_datetime(df["trade_date"]).dt.date`,
    `tuple(sorted(parsed))`. `from datetime import date` added. Tests: two mocked tests
    (date-objects + ISO-strings) + double-gated live test with `@pytest.mark.live_akshare`
    + `skipif IRC_RUN_LIVE_AKSHARE != "1"`. All match plan spec exactly.

  Task 2: trading_calendar.load_trading_days — PRESENT. New file
    src/irc/monitor/trading_calendar.py (57 lines). Cache key `fetched_on < today`
    (not `<= today`): cache is fresh when `fetched_on >= today`. `_read_cache` returns
    None on stale/missing/corrupt; `_fetch_and_persist` sorts + persists via
    `atomic_write_text`. `load_trading_days` wraps with `except Exception` returning None
    on failure. Five edge tests in tests/monitor/test_trading_calendar.py:
    hit/stale/missing/failure/corrupt — all match plan spec exactly.

  Task 3: _missing_trading_days — PRESENT. trace.py:56-81. Signature matches plan:
    `(series, trading_days, *, window=_RECENT_GAP_WINDOW) -> int | None`. Walrus uses
    `p` (not `d`) as plan correction specified. Returns None when `trading_days is None`,
    0 when `< 2` dates, `max(sum(...))` over consecutive pairs. Five unit tests
    (none/few-obs/holiday/real-miss/window) all match plan spec.

  Task 4: trading_days threading + schema_version bump — PRESENT. `_SCHEMA_VERSION = "2"`
    (trace.py:12). `_nav` gains `trading_days` param (trace.py:83). `_fund_entry` gains
    `trading_days` param (trace.py:124) and passes it to `_nav`. `build_eval_trace` gains
    `trading_days: frozenset[date] | None = None` default kwarg (trace.py:146) and passes
    to `_fund_entry`. Tests: nav-key-set updated (+`missing_trading_days`), three new tests
    (threaded-from-calendar/none-without-calendar/schema_version_is_2) all match plan.

  Task 5: nav_quality gate branch — PRESENT. structural.py: `_MISSING_TRADING_WARN = 2`
    added after `_WARN_GAP_DAYS` (lines 15-19) with plan comment text. `nav_quality` branch:
    `missing = nav.get("missing_trading_days")` → if not None: WARN when `>= 2`, else PASS;
    fallback `gap > _WARN_GAP_DAYS` unchanged. Five new tests in test_structural.py
    (warn@2/pass@1/pass@0-holiday/fallback-warn/fallback-pass) all match plan spec. The two
    pre-existing fallback tests unchanged (they omit `missing_trading_days` key → `get`
    returns None → exercise fallback path correctly).

  Task 6: monitor_cmd threading — PRESENT. Import: `from irc.monitor.trading_calendar import
    load_trading_days` (line 51). `_compute_gates` gains `trading_days: frozenset[date] | None`
    kwarg and passes to `build_eval_trace` call. `_write_eval_artifacts` gains same kwarg and
    passes to its `build_eval_trace` call. `run_monitor` calls
    `load_trading_days(date.today(), root=root)` once (line 623) before `_compute_gates` and
    `_write_eval_artifacts`. Both call sites receive `trading_days`. Test
    `test_trace_carries_missing_trading_days_from_calendar` added to test_acceptance_eval.py;
    `_patch` default set to `load_trading_days=None`. All match plan spec.

  Task 7: §6 acceptance test — PRESENT. `test_acceptance_spring_festival_run_day_after_holiday_validates`
    in tests/monitor/test_acceptance_eval.py (lines 616-652). Spring-Festival fixture with
    closed={2026-02-16..20} + weekends; calendar = `frozenset(date(2026,2,d) for d in range(2,24))
    - closed - weekends`; NAV series = trading days only; run dated 2026-02-23.
    Assertions: `missing_trading_days == 0`, `max_gap_days > 8`,
    `nav_quality(...).status == "PASS"`. Matches plan spec exactly.

  Task 8: ADR 0018 D3 update — PRESENT. docs/adr/0018-monitor-scoring-rationale-and-governance.md
    +16 lines appended to the D3 bullet. Text matches plan §8 supersession note verbatim:
    mentions `_MISSING_TRADING_WARN = 2`, `schema_version "1"→"2"`, spec pointer. Committed
    as `ae5628c`.
