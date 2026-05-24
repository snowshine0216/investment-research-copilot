Verdict: PASS

Subagent: sonnet
Plan tasks: 24
Verified present in diff: 24

Prior finding (resolved):
  - Task 22 — divergent (scope: CLI flag wiring) — RESOLVED by commit 9701913
    Original finding: `run_opportunity` had no `limit`/`rebuild_fundamentals` params and never called
    `validate_cli_args`; `_build_rows` had no `limit`/`rebuild_fundamentals` params; `cli.py` silently
    dropped both flags.
    Fix commit: 9701913 ("fix(opportunity): thread --limit/--rebuild-fundamentals through
    run_opportunity → _build_rows (item 003 drift fix)")
    Files changed: src/irc/cli.py (+7 -2), src/irc/commands/opportunity_cmd.py (+65 -12),
    tests/commands/test_opportunity_cmd_acceptance.py (+197 new lines)
    Verification:
      - `run_opportunity` at `opportunity_cmd.py:622-637` now has signature
        `(repo_root: str, *, output_dir: str | None = None, limit: int | None = None,
        rebuild_fundamentals: bool = False) -> int` and calls `validate_cli_args(...)` at line 632
        before any I/O.
      - `_build_rows` at `opportunity_cmd.py:417-445` accepts `*, limit: int | None = None,
        rebuild_fundamentals: bool = False`; limit caps `cn_equity_fund` rows by sorted
        `instrument_id` at lines 435-445 BEFORE the fetch loop; `rebuild_fundamentals=True` at
        line 473 skips `_load_latest_active_fund_cached` and `_maybe_freshness_probe` entirely,
        going directly to `build_snapshot`.
      - `cli.py:125-130` — Click handler forwards `output_dir`, `limit`, `rebuild_fundamentals`
        to `run_opportunity(...)`.
      - Three new end-to-end tests in `tests/commands/test_opportunity_cmd_acceptance.py:134-241`:
        `test_limit_caps_active_fund_autobuild_rows`, `test_limit_rejected_on_canonical_output_path_via_run_opportunity`,
        `test_rebuild_fundamentals_bypasses_cache` — all 3 passed (0.35 s).

New drift findings: none

Invariant checks (post-fix, HEAD):
  - citation_id preimage unchanged: `src/irc/opportunity/types.py:130-154` — `citation_id: str = ""`
    at line 130; comment at line 132: "Appended AFTER citation_id; NOT part of the hash preimage
    (ADR 0001 §2)."; `holding_weight_pct: float | None = None` at line 133; `__post_init__` at
    line 154 computes hash without `holding_weight_pct`. PASS.
  - active-fund cache path uses provider-declared quarter: `src/irc/fundamentals/snapshot_cache.py:127` —
    `def active_fund_cache_path(fund_id: str, quarter: str, root: Path) -> Path`; line 212 calls it
    as `active_fund_cache_path(snap.fund_id, snap.source_report_quarter, root)` using the
    provider-declared field, not `date.today()` or `calendar_quarter`. PASS.
  - HK forbidden adapter pairs: `src/irc/fundamentals/snapshot.py:253-285` — `elif holding.exchange == "HK":`
    branch calls only `fetch_hk_filing_digest` (line 255) and `fetch_hk_stock_news` (line 274);
    no `fetch_cn_filing_digest`, `fetch_cn_broker_reports`, or `fetch_cn_stock_news` in the HK branch.
    PASS.
  - HK news stub-empty fallback: `src/irc/fundamentals/hkex_client.py:174` — `hk_news_adapter_available()`
    uses `hasattr(ak, "stock_hk_news_em")`; `snapshot.py:269-271` — `if not hk_news_adapter_available():
    failures.append(f"hk_news_unsupported_adapter:{holding.symbol}"); news = ()`. Returns `()` when
    adapter unavailable. PASS.
  - no evidence_gaps stamping: `src/irc/opportunity/thesis_evidence.py:349-350` — comment "Item 003:
    do NOT stamp evidence_gaps yet; item 006 H2 owns that."; `gaps: tuple[str, ...] = ()` always
    for `ActiveFundSnapshot` branch. PASS.
  - default env values: `src/irc/commands/opportunity_cmd.py:55-57` — `TOP_N_DEFAULT = 10`,
    `IRC_FETCH_BUDGET_DEFAULT = 2000`, `IRC_CACHE_FRESHNESS_DAYS_DEFAULT = 7`; line 173
    `IRC_OPPORTUNITY_AUTOBUILD` default `"1"`. PASS.
  - --limit canonical-path rejection: `src/irc/commands/opportunity_cmd.py:243-261` —
    `validate_cli_args` raises `SystemExit(2)` with stderr `"--limit is rejected on canonical output
    paths"` when `output_dir` ends with `outputs/{today}` and `limit is not None`; now called from
    `run_opportunity` at line 632 (previously was unit-only — PARTIAL PASS is now FULL PASS).
    Test `test_limit_rejected_on_canonical_output_path_via_run_opportunity` confirms exit code 2
    via end-to-end path. PASS.
  - fcntl.flock advisory lock: `src/irc/commands/opportunity_cmd.py:97-106` — stdlib `fcntl`
    imported with Windows no-op fallback; line 156 — `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)`.
    No new third-party dependency. PASS.
