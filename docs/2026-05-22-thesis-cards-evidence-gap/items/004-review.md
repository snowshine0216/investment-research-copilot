Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (2 parallel reviewers: pr-review-toolkit:code-reviewer, adversarial general-purpose). Test-only sub-PR; no production code changes.

## Reviewers
- pr-review-toolkit:code-reviewer: LAND (no P0; 4 P1 cosmetic notes)
- Adversarial general-purpose: RISKS (no BREAKS); 3 findings

## P0
None.

## P1 (addressed in commit f76137f before PR opened)
- Env-var alone triggers live tests under bare `pytest` — documented as project convention (matches `RUN_LIVE_LLM_TESTS`, `RUN_LIVE_INGEST_TESTS`). The docstring/README claim of "dual gate" was overstated. Aligned docs with actual behavior; the marker is for CLI filtering, not a second runtime gate.
- README claimed per-symbol empty cells skip with documented message, but code hard-asserts `len(df) > 0`. Aligned: per-cell failures are diagnostic; the aggregate gate is the orchestrator-readable verdict.
- README mentioned `报告ID` as item 005's citation key — softened to "item 005's spec gets the final say".

## P1 (deferred to post-merge follow-up)
- `COLUMN_EQUIVALENCE` has three identical sub-dicts. Per-endpoint structure is correct for future-proofing but currently redundant. Acceptable.
- "Legacy helpers" block at lines 402-477 of `test_fund_announcement_em_live.py` exists only so the companion file can import them. Could move to a `_helpers.py` shared module. Cosmetic.

## P2 (deferred)
- All-NaN DataFrame rows pass `len(df) > 0` and the aggregate gate. Low probability — AkShare's EastMoney scraper rarely returns NaN-rows; if it does, a downstream item-005 consumer will catch it. Tracked.

## Invariant checks (verified)
- Pytest markers `live_akshare` + `integration` registered with `--strict-markers` (`pyproject.toml`).
- No other unregistered markers in the codebase (audit clean).
- Test isolation: env var unset → tests skip → zero network calls. Verified by running `pytest -q --tb=no` and observing 28 skipped (incl. 11 live tests).
- No `src/` changes (test-only sub-PR).
- Fixture writes are atomic (`tempfile.mkstemp + os.replace`).
- COLUMN_EQUIVALENCE has fallbacks for each logical column name.
- Aggregate gate caches AssertionErrors per-cell so one bad endpoint doesn't short-circuit the matrix.

## Q4 pivot context
Original `fund_announcement_em` target → AkShare 1.18.63 has 3 topic-specific variants instead. User authorized option (a) on 2026-05-23. Pivoted spec + plan + tests. Aggregate gate PASS post-pivot (9/9 cells). Original FAIL verdict preserved in items/004-verify.md "Prior Q4 FAIL" section for historical context.

## Subagent
sonnet (impl + reviewers); orchestrator-recorded verdict.
