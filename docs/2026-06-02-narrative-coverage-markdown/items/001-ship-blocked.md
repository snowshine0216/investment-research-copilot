# 001 — /ship pre-landing review surfaced blockers (pre-push)

Source: /ship steps 8+9 (pr-review-toolkit:code-reviewer + silent-failure-hunter + adversarial). All three converged on the same P0.

## P0 (blocker — must fix before push)
- **`FetchBudgetExceeded` propagates uncaught + leaks DuckDB `con`.**
  `src/irc/commands/narrative_cmd.py:95-98` calls `autobuild_active_funds(...)` **before** the `try/finally` (lines 100-120) that closes `con`. When the budget guard raises `FetchBudgetExceeded` (`narrative_autobuild.py:115`), (a) `con` is never closed (resource leak) and (b) the exception propagates through `_run_analyze` → `run_narrative` → CLI with NO handler → raw traceback + Click exit 1, instead of the clean actionable exit `opportunity_cmd` gives (`SystemExit(3)`). Repro: `IRC_FETCH_BUDGET` below `plan.total_calls()` for the eligible-missing count + ≥1 eligible cn_equity_fund missing cache + autobuild on.
  Fix: move the `autobuild_active_funds(...)` call INSIDE the `try` (so `con.close()` always runs in `finally`); catch `FetchBudgetExceeded` in `run_narrative` → actionable stderr (name `IRC_FETCH_BUDGET` / `IRC_NARRATIVE_AUTOBUILD=0`) → `return 3`.

## P1 (fix now — correctness, tightly related)
- **Broad `except Exception` swallows `FetchBudgetExceeded`.** `narrative_autobuild.py:60` — if `build_snapshot` itself raises `FetchBudgetExceeded`, it is degraded to a per-fund warning and the loop continues (each subsequent fund re-trips). Add `except FetchBudgetExceeded: raise` before the broad catch so a budget exhaustion halts the whole autobuild.
- **Cache-write failure bypasses structured logging.** `narrative_autobuild.py:73-77` uses `sys.stderr.write(...)` with colon-delimited machine noise + no message body. Replace with `_log.error("narrative_autobuild: cache write failed for %s — %s", target.provider_symbol, cache_exc)`. Remove the now-unused `import sys` if nothing else uses it.

## P2 (fix — cheap, prevents masking the acceptance gate)
- **cwd-dependent acceptance test.** The `基金概况`-forbidden-indicator test reads `src/irc/commands/narrative_autobuild.py` via a relative path → `FileNotFoundError` from any non-repo-root cwd, silently masking the gate. Anchor the path to the repo root via `Path(__file__).resolve().parents[N]`.
- **`con.close()` bare `except Exception: pass`** (`narrative_cmd.py:117-120`) → `_log.debug("con.close failed", exc_info=True)` (cheap; surfaces under DEBUG).

## Noted, intentionally NOT changed
- Kill-switch matches only `"0"` (`"false"`/`""` leave autobuild on): **spec-compliant** (AC4 mirrors `IRC_OPPORTUNITY_AUTOBUILD`); consistent with codebase convention. Left as-is.
- Duplicate `instrument_id` budget-estimate inflation (P2): curated universe; out of scope to keep the fix tight.
- `_fetch_budget` private cross-module import: spec Q-G8 sanctioned it as a shared seam; left as-is.

## New tests required
- `run_narrative` returns rc==3 (no traceback, actionable message) when `FetchBudgetExceeded` is raised during `--analyze`; `con` is closed.
- `_build_and_cache_one` re-raises `FetchBudgetExceeded` rather than degrading.
