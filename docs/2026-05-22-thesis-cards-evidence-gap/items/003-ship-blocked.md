# /ship halted — pre-landing review surfaced multiple P0s (item 003)

`/ship` step 8+9 reviews (code-reviewer + silent-failure-hunter + adversarial) converged on a major drift that the in-flow drift verdict missed: significant ADR 0002 §3 functionality (preflight budget gate, resumable state, advisory lock) is **defined and unit-tested but never wired into the actual execution path**. Plus two related guard-bypass bugs. Per `ship.md` §"/ship review can demand fixes before push", routing through triage-fix and re-invoking `/ship`.

## Prior round (resolved)

`tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports` was failing in-branch due to a `fundamentals → opportunity` import cycle introduced by item 003. Fixed in commit `57dc0b3` by relocating `LookthroughTarget` / `LookthroughKind` / `ThesisEvidence` / `ConstituentAnalysis` to `fundamentals/types.py` with `opportunity/types.py` re-exporting them.

## Round 2 findings — P0 blockers

### P0-1. Preflight budget gate + resumable state + advisory lock are unwired

`src/irc/commands/opportunity_cmd.py:61-167` defines `FetchPlan`, `FetchBudgetExceeded`, `compute_plan_hash`, `load_fetch_state`, `write_fetch_state`, `acquire_fetch_lock`, `FetchLockBusy`, `_fetch_budget()`. All have unit tests in `tests/commands/test_opportunity_cmd.py`. **But `_build_rows` / `run_opportunity` never call any of them.** 

ADR 0002 §3 ("preflight budget gate, not mid-loop check; abort exits code 3 with per-category breakdown; no `.tmp` files written before the gate") is unenforced end-to-end. Spec acceptance criteria 16 (`IRC_FETCH_BUDGET=10` + 5 cold rows → exit 3), 19 (mid-run interrupt → resume on next run), 20 (stale plan_hash discard), 21 (concurrent run → exit 4) all FAIL at integration level despite unit tests passing.

Production impact: a buggy universe expansion silently makes thousands of AkShare calls and triggers rate-limit bans; two concurrent `irc opportunity` runs both write to the same `fund_*.json.tmp` and race on `tmp.replace(path)`.

### P0-2. `validate_cli_args` misses the default canonical path

`opportunity_cmd.py:243-263`'s canonical-path rejection runs only when `output_dir is not None`. When the user runs `irc opportunity --limit 5` with no `--output-dir`, `run_opportunity` defaults `out_dir = root/outputs/today` (the canonical path) but `validate_cli_args(output_dir=None, ...)` returns early at line 254 and `--limit` is silently honored on production output. Spec criterion 18 promised exit code 2 on canonical paths — defeated.

### P0-3. Empty `source_report_quarter` collapses cache path depth

When the provider returns `"2024年半年度"` (semi-annual, not quarterly), `_QUARTER_RE = r"(\d{4})年(\d)季度"` doesn't match → `_parse_quarter_column` returns `("", "")` → `ActiveFundSnapshot(source_report_quarter="", ...)`. `write_active_fund_cache` is still called and writes to `data/fundamentals//active_fund/fund_X.json` which resolves to `data/fundamentals/active_fund/fund_X.json` (one level shallower than expected). `_load_latest_active_fund_cached` uses `base.glob("*/active_fund/fund_X.json")` requiring two levels — the file is never found again. Result: infinite re-fetch on every subsequent run; budget consumed every time.

## Round 2 findings — P1 (must address before merge but can land in fix-round 2)

- **P1-a. Double-append of `*_fetch_failed` + `*_empty` reason codes** — `snapshot.py:213-217, 227-231, 240-244, 255-258, 273-277`. Exception path sets result to `()`/`None`, appends `*_fetch_failed:X`, then falls into the `if not <result>:` branch and appends `*_empty:X` too. Item 006's prefix-based gap stamping will overcount.
- **P1-b. `_build_active_fund_snapshot` collapses adapter exception into `holdings_fetch_failed:{fund_id}:empty`** — `akshare_fundamentals.py:259-271` returns identical `HoldingsResult((), "", "")` for: AkShare exception, non-DataFrame return, empty df, missing columns, missing quarter column. Cannot distinguish schema change from "fund hasn't disclosed yet".
- **P1-c. `fetch_cn_stock_news` / `fetch_hk_stock_news` swallow exceptions** — adapters catch `Exception` and return `()`; callers' `news_fetch_failed:*:ExcType` branches are dead code; every news fetch failure is mis-classified as `news_empty`.
- **P1-d. Freshness probe success path: `write_active_fund_cache` not wrapped** — `opportunity_cmd.py:200-223`. FS error here crashes the run instead of falling back to re-fetch.
- **P1-e. `_parse_exchange` UNKNOWN routing** — no Strategy-1-miss vs Strategy-2-miss distinction; a future SSE prefix will silently route to UNKNOWN.
- **P1-f. `fcntl.flock` race + Windows fallback hole** — file-delete-between-open-and-flock; Windows fallback returns unlocked FD with only a module-load stderr warning.
- **P1-g. `tmp.replace(path)` collision risk** — same `.tmp` path for every writer; PID/uuid suffix needed.
- **P1-h. Future `cache_probed_at` → permanent cache bypass** — `_is_stale((today - future).days > threshold)` inverts on clock skew or fixture mistake.
- **P1-i. `--limit` symlink bypass** — `validate_cli_args` doesn't call `Path.resolve()`; a symlink to a canonical path bypasses the rejection.
- **P1-j. Semi-annual quarter parse failure → no failure reason emitted** — when `_parse_quarter_column` returns `("", "")` and `holdings.constituents` is non-empty, no `holdings_quarter_parse_failed:{fund_id}` is stamped.

## Why the drift verdict missed this

The drift subagent (`items/003-drift.md`) confirmed:
- All 24 plan tasks present in diff ✅
- All 8 ADR/spec invariants pass at code-level ✅
- Task 22 wiring gap caught and fixed ✅

But it verified files existed and were structurally correct; it did not check that the new symbols were actually called from the execution path. The pattern "implemented + unit-tested + never wired" is invisible to a diff-vs-checklist drift check unless the checker explicitly traces call paths.

Action: enrich the drift verdict's invariant checks in future autodev runs to include "find at least one call site for every new exported symbol in `_build_rows` / `run_opportunity` / the equivalent entry point". For this run, the fix below restores integration coverage.

## Fix scope (single dispatch)

1. **Wire `_fetch_budget()` + `FetchPlan` + `FetchBudgetExceeded` into `_build_rows`** — compute the plan AT ENTRY (before any adapter call); raise `FetchBudgetExceeded` on over-budget; map to exit code 3 in the CLI entry handler; do NOT create any `.tmp` files before the gate passes.
2. **Wire `acquire_fetch_lock` into `_build_rows`** — acquire the lock keyed on `plan_hash` BEFORE the per-instrument loop; raise `FetchLockBusy` on `BlockingIOError`; map to exit code 4 in the CLI entry handler.
3. **Wire `load_fetch_state` / `write_fetch_state` into `_build_rows`** — on entry, load any existing state file matching `plan_hash`; skip items marked `complete`; write `started` / `complete` entries as the loop progresses; atomic write per entry.
4. **Fix `validate_cli_args` default-output-dir bug** — if `output_dir is None`, treat as `outputs/<today>/` (canonical) and apply the same `--limit` rejection rule. Also call `Path.resolve()` on user-provided `output_dir` BEFORE the canonical-suffix check (closes the symlink bypass).
5. **Skip caching when `source_report_quarter == ""`** — don't write a path-collapsed cache. Stamp `holdings_quarter_parse_failed:{fund_id}` into `ActiveFundSnapshot.fund_level_failure_reasons` AND return the snapshot for downstream visibility (item 006 will gap-stamp the row).

P1-a through P1-j: address in a follow-up commit in the SAME fix dispatch where reasonable, but the P0s are non-negotiable.

End-to-end tests required in this fix:
- `irc opportunity --limit 5` (no `--output-dir`) → exits 2 with stderr `"--limit is rejected on canonical output paths"`.
- `IRC_FETCH_BUDGET=10` + 5 cold `cn_equity_fund` rows → exits 3 with per-category breakdown; no `.tmp` files written under `outputs/<today>/`.
- Two concurrent `irc opportunity` runs with same plan_hash → second exits 4 with `"concurrent run detected"`.
- Provider returns `"2024年半年度"` → cache NOT written, `ActiveFundSnapshot.fund_level_failure_reasons` contains `"holdings_quarter_parse_failed:{fund_id}"`.
- `irc opportunity --limit 3 --output-dir /tmp/scratch/` succeeds (non-canonical path) and processes 3 rows.

After fix lands, re-invoke `/ship` (which will re-run tests + parallel reviews + adversarial).
