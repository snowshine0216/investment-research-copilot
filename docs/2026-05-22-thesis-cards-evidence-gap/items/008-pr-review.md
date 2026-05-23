# Item 008 `/code-review` verdict

**Verdict:** PASS-WITH-NITS (after fix-round-2)
**Tool:** `/code-review --pr 62 effort high` (5 angles × ≤8 candidates → 1-vote verify → sweep)
**Date:** 2026-05-23
**PR:** https://github.com/snowshine0216/investment-research-copilot/pull/62

## Surfaces (5 parallel Sonnet finder subagents)

| Angle | Findings |
|-------|---------:|
| A — line-by-line diff scan | 5 |
| B — removed-behavior auditor | 3 |
| C — cross-file tracer | 4 actionable + 4 pass |
| D — Python pitfall specialist | 5 |
| E — wrapper/proxy + invariant correctness | 6 |

After dedup + verifier convergence: **8 actionable** + ~12 deferred (notes / P2 / theoretical).

## Actionable findings — ALL CLOSED in fix-round-2

1. **`_unexpected_calls` dead helper + wrong docstring** (5/5 angles converged). Sentinel was correctly written but never asserted; docstring's `counter["__unexpected__:*"]` is a string-key lookup that's never stored (silently returns 0). Fix: corrected docstring to canonical `_unexpected_calls(counter)` call; sentinel is now correctly documented.
2. **`broker_frame` wall-clock `日期` breaks AC22 across midnight** (A + D). Date flows into citation_id sha256. Fix: module-level `_BROKER_REPORT_DATE` computed once at import (today−30d), keeping deterministic AND within the 90-day broker-freshness window.
3. **Double `_today_cn()` in 3 tests** (D). Midnight skew between `out_dir` and `today=`. Fix: `today = _today_cn()` captured once per test in AC11 canonical, AC11 adversarial, and AC12.
4. **AC10 missing `failure_idx >= 0` guard** (A + B). Heading rename would silently invert the slice. Fix: parity guard with AC9.
5. **H3 completeness only in AC10** (B + C + E). Universal invariant per CONTEXT.md, but only one test exercised it. Fix: extracted `_assert_h3_partition()` helper and added to QDII discipline-failure test (next-most-likely silent-drop site).
6. **AC21 `same_holding_frame` missing `季度`** (A + D). Cache wrote under `""` quarter key, silently divergent from real AkShare shape. Fix: added `"季度": ["2024年4季度"]`.
7. **Production-fix structural unit-test gap — `qdii` as `_GAP_TO_REASON[0]`** (C + E). New dict-iteration precedence is fragile to reordering. Fix: `test_gap_to_reason_first_key_locks_qdii_precedence` + sibling adversarial test in `tests/opportunity/test_rejection_log.py`.
8. **`fund_announcements_unavailable` no unit-test** (C). Production-fix code path was only covered indirectly. Fix: added parametrized entry.

## Deferred (P2/notes)

- **Q4 contract test for `find_uncited_conclusions` exclusion of rejections** (E F4) — defer to item 009's body implementation (the stub returns `[]` so any contract test is vacuous).
- **`fetch_state_<plan_hash>.json` non-determinism via `fetched_at`** (adversarial F1) — outside the 4 byte-compared artifacts; not a current break.
- **Counter destructuring fragility** (D C5) — safe today; defer.
- **AC16 `constituent_calls == 0` trivially true** — discriminating signal is the holdings count; harmless.
- **`_install_ak_call_dispatch` `args[0]` unreachable** (E F6) — confirmed safe (production passes `symbol=` kwarg).
- **`_side` shared function patched into both modules** (D C7) — intentional, documented.
- **AC22 unmocked `_seed_publishable_set_repo.write_manifest()` timestamp** (E F3) — manifest doesn't flow into compared artifacts; latent only.
- **AC9 unmocked `qdii_global` partial path** (earlier inline review) — already-flagged design choice; defer.

## Verification

- `tests/integration/test_publishable_set_lockdown.py + tests/opportunity/test_rejection_log.py`: **54 passed / 1 skipped / 0 failed**.
- Architecture DAG check: PASS.
- Ruff: clean on item 008 touched files.

## Recommendation

**PASS-WITH-NITS.** All 8 actionable findings closed in `fix(008)` commit with regression tests and helper extraction. Deferred items are P2/theoretical or design-justified. Pre-merge gate satisfied — all 5 verdict files present (drift, ship, verify, review, pr-review). Ready for `gh pr merge`.
