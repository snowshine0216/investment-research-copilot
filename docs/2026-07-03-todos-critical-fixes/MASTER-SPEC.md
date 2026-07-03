# MASTER-SPEC — TODOS.md critical fixes

Mode: **backlog** (4 distinct items from TODOS.md, user asked to "pick up the critical items to fix")
Date: 2026-07-03
Base: `main` @ 221a34e4
Feature branch: `autodev/todos-critical-fixes-feature` (synthesized — no merge-to-main opt-in this turn)

## Scope classification

Every item below was selected from TODOS.md open items as *critical* — correctness or
crash-class bugs actionable today without live repro, SMEs, or credentials.

### IN

| id | Title | TODOS.md line | Class |
|----|-------|---------------|-------|
| 001 | `attribution_strength` unhashable shape escapes macro schema-retry loop | 15 | crash-class (daily monitor path), P2 |
| 002 | `ActiveFundSnapshot` thesis path lacks dual-leg coverage check | 51 | correctness (false `intact` → `core_dca`) |
| 003 | Opportunity venue filtering not wired (`venue_compatible` always True) | 70 | correctness (venue-incompatible → `core_dca`) |
| 004 | Mixed-fund stale-cache with empty `fund_level_evidence` not force-retried | 21 | reliability (7-day cache poisoning) |

Item details (verbatim intent from TODOS.md + invocation):

**001** — `src/irc/monitor/narrative_macro.py:120`: a non-hashable `attribution_strength`
(e.g. a list) from the macro LLM raises `TypeError` at the `strength not in _VALID_STRENGTH`
check, escaping the inner schema-retry loop; the call-site guard then degrades the WHOLE
macro block (honest absence, logged) instead of retrying/dropping that one theme.
Fix: isinstance hardening so a non-str strength is an invalid-schema retry, not a TypeError.

**002** — `src/irc/opportunity/states.py::derive_thesis_from_evidence` sets
`thesis_state="intact"` for an `ActiveFundSnapshot` whenever flattened constituent evidence
is non-empty, WITHOUT requiring both a `data` leg and an `information` leg (the dual-leg
gate exists only on the `FundLevelSnapshot` branch). Data-only (e.g. filing-only) evidence
can reach `intact` → and with cheap valuation + cold heat + acceptable quality → `core_dca`.
Extend the dual-leg check to the `ActiveFundSnapshot` branch. CONTEXT.md "dual-coverage
gate" is the terminology source; `thesis_state` is set ONLY by `derive_thesis_from_evidence`
(never Policy B).

**003** — `OpportunityInput.venue_compatible` is always `True`; wire it from
`bundle.account.venues` so venue-incompatible instruments are routed to `small_watch`
instead of `core_dca`.

**004** — when `_fetch_active_fund_level_evidence` returns `()` (e.g. NAV fetch failed once)
and the fund's CN constituents satisfy `_active_snapshot_has_required_data_leg_gap`, the
snapshot is cached with empty evidence; next runs reuse it and rule 2.5 emits
`foreign_heavy_fund_level_evidence_missing` for up to `IRC_CACHE_FRESHNESS_DAYS` (7).
Fix per TODO: freshness probe — if `fund_level_evidence == ()` AND
`_compute_foreign_listed_share(...) >= FOREIGN_HEAVY_THRESHOLD`: force refetch.

### OUT

None — all four selected items are IN. (Other TODOS.md open items were not selected for
this run: they are polish / observability / test-strengthening / diagnosis-blocked —
notably the memo "exit-0-zero-writes" ghost, which is UNSOLVED and requires a live
occurrence with captured stdout.)

## Repo constraints (binding on every item)

- TDD: failing test first; tests mirror `src/irc/` one-for-one.
- Pure functions / effects at edges; files < 200 lines; functions < 20 lines ideal.
- Do NOT bump VERSION; accumulate under CHANGELOG `[Unreleased]`.
- On signature changes, run every test dir that exercises the function (grep callers in
  `tests/`); `tests/commands/` MUST be run per-file (whole-dir hangs).
- Full pytest ~61 min, NOT green on main (24 known pre-existing failures) — replay failing
  ids on main to diff-scope before assuming a regression.
- Update TODOS.md marking each item `**Resolved 2026-07-03:**` with the standard annotation.
