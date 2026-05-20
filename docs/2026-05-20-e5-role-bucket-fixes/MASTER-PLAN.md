# Master plan — E5 role-bucket fixes

## Branch strategy

User asked for one PR. We use **one feature branch with multiple commits** rather than the per-item sub-branch pattern. Each item below corresponds to one or two commits.

```
main → feat/e5-role-bucket-fixes
  commit 1: chore(discovery): raise cn_equity_fund DD buffer 1.6 → 1.8 (001)
  commit 2: feat(universe): add US bond QDII feeders for defensive_us_bond (002)
  commit 3: feat(universe): add SOE / real-estate / semiconductor passive proxies (003)
  commit 4: feat(discovery): broaden _is_core_us predicate (004 — TDD: tests first)
  commit 5: feat(discovery): broaden _is_hedge_low_corr predicate (005 — TDD)
  commit 6: docs: E5 close-out + tracker update (006)
```

## Workflow per item

1. Write `items/<id>-plan.md` with exact lines to add/change and exact tests to add.
2. (For code items) TDD: write the failing test first, run it (red), implement the change (green), run it again.
3. (For yaml items) Add the rows, then run focused tests to confirm no schema break.
4. Commit. Update PROGRESS.md.
5. Move to next item.

## Cross-cutting validation (after all commits)

- Run `pytest tests/discovery/ tests/schemas/test_discovery.py tests/memo/test_diagnostics_role_bucket.py` — focused.
- Run `pytest -q` — full suite. Expect the same baseline failures as documented in AUDIT_FIXES_TRACKER (`test_no_all_evidence_insufficient_valuation`, `test_eval_single_stage_data`). No new failures.
- Run `ruff check` on touched files.
- Open one PR with the squashed commits.
- Wait for CI; if clean, squash-merge.
- Update tracker.

## Stop conditions

- If raising the DD buffer to 1.8 causes any existing test to fail (other than a pinned-value test we update), pause and investigate — could indicate a behavioural assumption.
- If the QA subagent finds the buffer raise promotes junk-quality picks in a synthetic eval, fall back to surgical split (out-of-scope expansion) and document.
- Two-retry rule from the autodev-loop applies.

## Subagent usage

This run is small enough (6 items, mostly trivial) to do **inline in the orchestrator** rather than dispatch implementation subagents. Subagents would be overkill and add latency. We will still dispatch:

- **One** QA subagent at the end to do adversarial review of the full diff.
- **One** code-review subagent on the open PR before merge.

This is a deliberate adaptation of the autodev-loop pattern for tightly-coupled, small-scope fixes.
