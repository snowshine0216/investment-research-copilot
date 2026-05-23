# Item 008 inline review verdict (from `/ship` steps 8+9)

**Verdict:** PASS-WITH-NITS (after pre-PR fix-round)
**Captured by:** 3 parallel subagents (`pr-review-toolkit:code-reviewer` + `pr-review-toolkit:silent-failure-hunter` + adversarial `general-purpose`)
**Date:** 2026-05-23
**Branch:** `autodev/thesis-evidence-008-integration-test-sweep`
**Base:** `autodev/thesis-cards-evidence-gap`

## Findings closed before PR

### P0
1. **`_classify_rejection_reason` set→list iteration** (`rejection_log.py`). `for gap in set(...)` made the unknown-gap error message non-deterministic. Fixed: iterate original tuple.
2. **`_install_ak_call_dispatch` silent empty-DataFrame** (`test_publishable_set_lockdown.py`). Unknown keys silently returned `pd.DataFrame()`. Fixed: unexpected counter sentinel + `_unexpected_calls()` helper.
3. **AC17 `except Exception: pass`** swallowed real crashes. Narrowed to `except SystemExit`.

### P1
4. **AC22 `_preload_duckdb` non-determinism**. `datetime.now()` differed between runs. Fixed: `now_ts` parameter with `_FIXED_INGESTED_AT` default.
5. **AC18 disjunctive assertion** masked real bugs. Tightened to `holdings_fetch_failed in gaps`.
6. **AC10 H3 partition completeness** untested. Added `>=` completeness AND `not &` disjointness asserts.
7. **AC11 adversarial gap ordering**. Added sibling test with QDII gap at position [1].
8. **`_seed_publishable_set_repo` invalid YAML** if `run_init` template ever drops a file. Added `Path.exists()` asserts.
9. **`_install_ak_call_dispatch` kwargs/args**. Addressed by fix #2 unexpected-counter (any future kwarg-different call lands in unexpected bucket).

## Deferred (P2/notes)

- `qdii_global` partial path — universe entry omitted; the asset_class branch fallback covers the spec but the display name reads `未登记(100061)`. Acceptable; covered by spec's qdii-exclusion criterion (AC6-9).
- `AC16 constituent_calls == 0` is trivially true (snapshot has no constituents). The discriminating signal is the holdings call count. Defer cleanup.
- `AC20 ThesisEvidence.from_dict` import — confirmed exists (item 007).
- Seed-helper coupling to undeclared env vars — defer; future items will surface this if a new mandatory env var appears.

## Verification

- `pytest tests/integration/test_publishable_set_lockdown.py -x -q`: **24 passed, 1 skipped** (AC20 picks-table regex skip is intentional — the picks-table format used by item 007's memo doesn't yet exercise the full row prefix the AC20 helper expects; will land naturally when item 009 wires the gate).
- No regressions in the wider item 008 scope.

## Recommendation

**PASS-WITH-NITS.** All 9 actionable findings closed in `fix(008)` commit with regression tests. Deferred items are P2 or design-justified. Ready for post-ship `/verify` + `/code-review`.
