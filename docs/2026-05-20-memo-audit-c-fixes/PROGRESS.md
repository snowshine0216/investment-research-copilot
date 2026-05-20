# Progress

Feature branch: `feat/memo-audit-c-fixes` → squash-merged to `main` as `9743c8d` via PR #53.

| # | Subject | Tests | Impl | Lint | Commit | Note |
|---|---|---|---|---|---|---|
| C4 | Soften macro_summary string | ✅ | ✅ | ✅ | ✅ | `3480328` — `_MACRO_SUMMARY` constant, 4 new tests; clears audit P1 |
| C6 | Execution-line triggers w/ comparator+threshold | ✅ | ✅ | ✅ | ✅ | `819bb23` — `_format_threshold` + `_format_trigger`, 5 new tests; clears audit P4 |
| C7 | Picks-table methodology footnote | ✅ | ✅ | ✅ | ✅ | `283dc6b` — `_SCORING_FOOTNOTE`, 3 new tests; clears audit P5 |
| C5+C8 | Synthesizer guardrails (no prediction / explicit gaps / QDII premium) | ✅ | ✅ | ✅ | ✅ | `4a46d82` — `_GUARDRAILS` block + `_capture_user_prompt` test helper, 3 new tests; clears audit P2+P3+P6 |

## Final stage

| Step | Status |
|---|---|
| All commits on branch | ✅ 5 (4 feature + 1 review-fix) |
| Focused suite green | ✅ 96/96 (`tests/memo/` + `tests/commands/test_memo_cmd.py`) |
| Full suite | ✅ 1474 passed, 17 skipped, 2 pre-existing failures (same baseline as PR #51 / #52) |
| Branch pushed | ✅ |
| PR opened | ✅ #53 |
| QA subagent | ✅ PASS (95 tests, ruff clean, all acceptance checks green) |
| Review subagent | ✅ PASS-WITH-NITS → 2 latent bugs + 2 nits → fixed in `2fa8d80` → re-review PASS |
| Triage / fixes | ✅ `2fa8d80` — None-threshold → `（未设阈值）`, empty-table header invariant, macro spacing nit, docstring nit |
| Tracker updated | ✅ `outputs/2026-05-20/AUDIT_FIXES_TRACKER.md` — C4–C8 marked Done, run linked |
| Merged | ✅ #53 squashed to main as `9743c8d` |

Legend: ⏳ pending • 🔄 in progress • ✅ done • ⚠️ blocked

## Cross-branch validation

Compared `main` (pre-PR) vs `feat/memo-audit-c-fixes`:
- `main` (pre-PR): 2 failures (`test_no_all_evidence_insufficient_valuation`, `test_eval_single_stage_data`) — documented as pre-existing in tracker.
- `feat/...`: same 2 failures + 17 net new passing tests for this feature.
- **No regressions introduced.**

## Review findings + dispositions

| Finding | Severity | Action |
|---|---|---|
| `_format_threshold(None)` returns literal "None" → would surface in published memo | Latent | **Fixed** in `2fa8d80` — explicit `None` guard returns `（未设阈值）` + new regression test |
| `test_render_picks_table_footnote_emitted_even_when_no_rows` asserts only the disclaimer, not the table-header invariant | Latent | **Fixed** in `2fa8d80` — test now also pins `代码`, `名称`, and `\|---\|` |
| Spurious ASCII space in `_MACRO_SUMMARY` between sentences (inherited from prior hardcoded string) | Nit | **Fixed** in `2fa8d80` |
| `_format_threshold` docstring said "repr" but uses `f"{n}"` formatting | Nit | **Fixed** in `2fa8d80` — docstring tightened |
| `_capture_user_prompt` underscore convention | Nit (already correct) | **No action** — reviewer confirmed |
| `_GUARDRAILS` rule 4 (内部自洽 estimates) is not covered by a test | Risk note | Shipped — rule 4 is a soft prompt guideline; load-bearing rules 1/2/3 are pinned by tests |

## Post-merge follow-up (not in this PR)

- User runs `.venv/bin/irc memo --repo-root .` to verify audit gate passes on real data.
- E3 (QDII premium/discount ingest) and E6 (A-share valuation percentile ingest) remain manual environment work — the new C5 guardrail will explicitly flag the missing data in §6 rather than fabricate qualitative levels, which is the right behavior pre-ingest.
