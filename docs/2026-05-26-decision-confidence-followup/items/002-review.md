Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (initial review found 2 P0 + 4 P1 + 2 P2) → triage-fix round 1 (4 commits) → re-review (PASS)

## Reviewers

- Step 8 code-reviewer: `pr-review-toolkit:code-reviewer` (sonnet) — verdict PASS-WITH-NITS (2 P1s)
- Step 8 silent-failure-hunter: `pr-review-toolkit:silent-failure-hunter` (sonnet) — verdict FAIL (2 P0 + 1 P1)
- Step 9 adversarial: general-purpose (sonnet) — verdict RISKS (2 P1 + 1 P2)
- Post-fix re-review: `pr-review-toolkit:code-reviewer` (sonnet) — verdict PASS

## P0 findings (all fixed before PR opened)

- **P0-1** — `fetch_qdii_premium_pct` silent exception swallow with no logging. Fixed in `5aa6b87`: added `import logging` + module-level `_log`; bare `except Exception:` now logs `_log.warning(..., exc_info=True)` before returning None. Test `test_fetch_qdii_premium_pct_logs_on_exception` asserts the warning via `caplog`.
- **P0-2** — `qdii_premium_resolver` raise propagates through `run_scoring`, silently drops subsequent rows. Fixed in `10b802f`: try/except wraps the resolver call, logs WARNING, sets `premium = None`. Test `test_run_scoring_continues_when_resolver_raises` verifies graceful continuation with all rows returned.

## P1 findings (all fixed in this PR)

- **P1-1** (code-reviewer) — Magic `0.05` literals in `memo_cmd.py` function defaults. Fixed in `d322040`: `QDII_MAX_PREMIUM_DEFAULT` imported at module level; both `_decision_status_for_pick` and `_build_pick_rows` defaults now reference the constant.
- **P1-2** (adversarial) — `qdii_max_premium_pct: 0` silently blocks every QDII buy. Fixed in `b9a930d`: Pydantic constraint tightened from `ge=0` to `gt=0`. Test `test_qdii_max_premium_pct_rejects_zero` asserts ValidationError on 0.0 and -0.01. CONTEXT.md updated.

## P2 findings (deferred to TODOS)

- Synthetic vs measured `0.0` premium distinguishability (display polish — added to TODOS Reliability section).
- `lru_cache` test isolation pattern documented in TODOS as a contributor note.

## Pre-existing test failures (not caused by item 002)

The same 7 pre-existing failures from item 001 still appear on the full pytest run — they are unrelated to QDII premium logic. Not listed here individually; see PROGRESS.md or item 001's review for detail.

## Tests after fix

`311 passed, 1 skipped, 1 warning` on the targeted scope (`tests/data/test_akshare_client.py tests/scoring/ tests/commands/test_memo_cmd.py tests/schemas/test_discovery.py tests/decision/`). Ruff clean on all touched files.
