Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (3 parallel reviewers: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, adversarial general-purpose). Two rounds of review + fix; all P0s closed before PR open.

## Reviewers
- pr-review-toolkit:code-reviewer (round 2 verdict: branch ready, all 5 round-1 P0s verified CLOSED)
- pr-review-toolkit:silent-failure-hunter (round 2: all 5 round-1 P1s verified CLOSED; new findings → P1-level)
- adversarial general-purpose (round 2 verdict: RISKS, not BREAKS)

## Round 1 findings (closed)
- BLOCKER: fundamentals→opportunity import cycle (tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports failed in-branch, passed on base). Root cause: snapshot.py and snapshot_cache.py imported ConstituentAnalysis/ThesisEvidence/LookthroughTarget from irc.opportunity.types while opportunity/thesis_evidence.py and opportunity/states.py already imported from irc.fundamentals.types.
  - Resolution: commit 57dc0b3 relocated the 4 types to fundamentals/types.py; opportunity/types.py re-exports for backward compat. No call-site changes; cycle broken; arch test passes.
- BLOCKER: --limit / --rebuild-fundamentals declared in cli.py but not threaded through run_opportunity → _build_rows. Spec acceptance criteria 17–19, 23 would have failed at integration level.
  - Resolution: commit 9701913 wired the params end-to-end; 3 new acceptance tests cover the canonical/non-canonical paths.

## Round 2 findings (P0 — all CLOSED)
- P0-1 (budget gate UNWIRED): FetchPlan / FetchBudgetExceeded / compute_plan_hash defined and unit-tested, but _build_rows / run_opportunity never called them. Spec AC 16 (exit code 3 on over-budget) unsatisfied end-to-end.
  - Resolution: commit c35267a; _classify_active_fund_scores pre-scans, FetchBudgetExceeded raised at _build_rows entry, run_opportunity maps to exit 3, no .tmp written. Test: test_budget_exceeded_exits_code_3_before_any_fetch.
- P0-2 (lock UNWIRED): acquire_fetch_lock / FetchLockBusy defined and unit-tested but never called from _build_rows. Spec AC 21 (concurrent run → exit 4) unsatisfied.
  - Resolution: commit c35267a; acquire after budget gate, FetchLockBusy → exit 4 in run_opportunity, release in finally:. Test: test_concurrent_run_exits_code_4.
- P0-3 (state file UNWIRED): load_fetch_state / write_fetch_state defined but never called. Spec AC 19/20 (resume + stale-hash discard) unsatisfied.
  - Resolution: commit c35267a; load at entry, completed_ids skip, write per-fund, delete on clean completion. Tests: test_resumable_state_skips_completed_funds, test_stale_plan_hash_discarded.
- P0-4 (validate_cli_args default-path bypass): output_dir=None defaulted to canonical outputs/<today>/ but validate_cli_args returned early at line 254. --limit silently honored on production paths.
  - Resolution: commit c35267a; default resolved to canonical, Path.resolve() added (closes symlink bypass). Tests: test_limit_rejected_on_default_canonical_path, test_limit_rejected_via_symlink_to_canonical.
- P0-5 (empty source_report_quarter cache path collapse): "2024年半年度" → regex miss → empty quarter → cache written at data/fundamentals//active_fund/fund_X.json → resolves to wrong depth → never re-found → infinite re-fetch.
  - Resolution: commit c35267a; _build_active_fund_snapshot stamps holdings_quarter_parse_failed:{fund_id} when quarter is empty; _build_rows skips write_active_fund_cache in that case. Test: test_empty_source_report_quarter_no_cache_written_stamps_failure_reason.

## Round 3 findings (P1 hardening — all CLOSED)
- Stale-hash discard logged to stderr violated spec AC 20 ("silently ignored"). Resolution: commit 7496e94 removed the stderr block.
- holdings_quarter_parse_failed not fired when quarter column was absent (only when regex failed on non-empty rows). Resolution: 7496e94 emits constituents with empty quarter when column is missing too, so the existing stamp path covers both.
- cache_write_failed:{fund_id}:{ExcType} was stderr-only, invisible to item 006's gap stamping. Resolution: 7496e94 also appends to ActiveFundSnapshot.fund_level_failure_reasons via dataclasses.replace.
- Budget gate over-counted resumed runs because misses were classified before consulting state. Resolution: 7496e94 loads state first; _classify_active_fund_scores excludes completed_ids from both miss and stale counts. Test: test_budget_gate_credits_completed_ids.

## Adversarial verdict
RISKS (round 2). No data-loss or crash case found. Residual concerns are edge-case hardening (PID-recycle, clock-skew, lock release fragility, holdings_quarter_parse_failed downstream item-006 prefix table coverage). Deferred — see "P1 deferred" below.

## Invariant checks (verified by reading actual code post-fix)
- citation_id hash preimage unchanged (ADR 0001 §2): fundamentals/types.py:86-91 — preimage is owner_instrument_id : scope : constituent_key : type : canonical_id : date; holding_weight_pct appended after citation_id and NOT in the hash. PASS.
- Disclosure-quarter cache key (ADR 0002 §1): snapshot_cache.py:128, 213 — path uses source_report_quarter (provider-declared), never date.today(). PASS.
- Fail-closed freshness probe (ADR 0002 §2): opportunity_cmd.py:212-220 — exception or empty quarter → schedule full refetch. PASS.
- Preflight budget gate (ADR 0002 §3): opportunity_cmd.py:524-541 — FetchPlan computed before any adapter call; .tmp guard verified. PASS.
- Forbidden adapter pairs (ADR 0002 §4): snapshot.py:251-283 — HK branch only calls fetch_hk_* adapters; CN-only adapters explicitly excluded. PASS.

## P1 deferred (post-merge — surface to items 006/008 follow-up)
- Adapter-exception type distinction inside fetch_cn_etf_holdings (currently collapses all errors to empty HoldingsResult). Larger refactor surface; tracked.
- _parse_exchange Strategy-1-miss vs Strategy-2-miss distinction (currently both stamp generic exchange_unknown). Cosmetic; no routing correctness impact.
- fcntl.flock Windows fallback hole (no-op + stderr warning at module load). Windows is not a supported deployment surface per CLAUDE.md and ADR 0002 §Negative consequences.
- Lock file (.fetch_lock_<hash>.lock) cleanup on clean exit. Disk cruft; harmless.
- PID-tmp recycle collision (mid-write crash + same-PID reuse) — extremely rare; would require crash-on-write + immediate PID recycle. tmp.replace remains atomic for completed writes.
- Future cache_probed_at handling (clock skew) — _is_stale now clamps negative days to "stale", which is safer but may force unnecessary probes on small skews. Acceptable.

## Drift retrospective
The in-flow drift verdict (items/003-drift.md) classified the implementation as PASS after the Task 22 wiring fix. It missed the "defined-but-not-called" pattern for FetchPlan/acquire_fetch_lock/load_fetch_state because it verified file presence and structural correctness, not call-path integration. /ship's adversarial review (round 2) caught it. Future drift dispatches should grep for ≥1 call site of every new exported symbol in the execution entry point (`_build_rows`, `run_opportunity`, equivalent).
