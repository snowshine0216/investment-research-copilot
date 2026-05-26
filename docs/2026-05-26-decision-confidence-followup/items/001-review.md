Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (initial review found 2 P0 + 4 P1 + 2 P2) → triage-fix round 1 (3 commits) → re-review (PASS)

## Reviewers

- Step 8 code-reviewer: `pr-review-toolkit:code-reviewer` (sonnet)
- Step 8 silent-failure-hunter: `pr-review-toolkit:silent-failure-hunter` (sonnet)
- Step 9 adversarial: general-purpose (sonnet) — verdict RISKS (no P0)
- Post-fix re-review: `pr-review-toolkit:code-reviewer` (sonnet) — verdict PASS

## P0 findings (all fixed before PR opened)

- `FetchPlan.total_calls()` undercount — fixed in `67cea2e`. `per_active = 1 + top_n*3 + 4`. Tests updated 155→175, 165→185.
- Dead outer try/except in `_fetch_active_fund_level_evidence` masking failure type — fixed in `04fcf87`. Both inner fetchers documented "Never raises"; dead wrappers removed.

## P1 findings (latent bug fixed; one architectural risk deferred with rationale)

- Fragile `decision_rule.startswith("foreign-heavy")` discriminator — fixed in `845e86b`. Added `fired_rule: str = ""` to `PolicyBVerdict`; all 6 rule branches populate the literal; `_stamp_fund_level_evidence_from_verdict` now checks `fired_rule == "2.5"`.
- Mixed-fund stale-cache with empty `fund_level_evidence` not force-retried (adversarial review attack 1) — deferred. Fix touches `_active_snapshot_has_required_data_leg_gap` and broader staleness logic; out of scope for item 001 (which is the Policy B rule itself, not cache lifecycle). Noted as followup in `001-ship-blocked.md` and surfaced in PR body Coverage section.
- Double-failure-code recording on raised fetcher (subsumed by P0-2 fix — the dead try/except was the source).

## P2 findings (noted, not fixed)

- `_EXCHANGE_FROM_SYMBOL_PREFIX` missing `"5": "SH"` — conservative under-count only, never causes incorrect publish. Noted in PR body.
- `_ak_call` has no timeout enforcement — pre-existing; item 001 adds +4 calls per active fund × 50 funds ≈ 200 calls of additional exposure. Noted in PR body.

## Pre-existing test failures (not caused by item 001)

7 tests failed on the full pytest run, all of which also fail on `autodev/decision-confidence-followup-feature` (base) without item 001's changes. They are pre-existing failures in the repo and do NOT block this PR:

- `tests/commands/test_opportunity_cmd_fund_level.py::test_build_rows_qdii_row_carries_sentinel_gap`
- `tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports`
- `tests/integration/test_opportunity_pipeline.py::test_opportunity_pipeline_produces_three_outputs`
- `tests/integration/test_opportunity_pipeline.py::test_opportunity_pipeline_preserves_holdings_even_when_dropped`
- `tests/integration/test_publishable_set_lockdown.py::test_qdii_appears_in_rejections_with_qdii_reason`
- `tests/integration/test_publishable_set_lockdown.py::test_memo_cites_only_publishable_citation_ids`
- `tests/test_e2e_full_pipeline.py::test_eval_single_stage_data`

## Tests after fix

`643 passed, 12 skipped` on `tests/opportunity/ tests/fundamentals/ tests/commands/test_opportunity_cmd.py`. Ruff clean on all changed files.
