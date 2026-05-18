# Memo-Audit Cleanup — Progress Tracker

Updated after every step. ⏳ pending · 🔄 in progress · ✅ done · ⚠️ blocked · ⏭️ skipped

| # | Item | spec | plan | branch | impl | PR | QA | review | fix | merge |
|---|---|---|---|---|---|---|---|---|---|---|
| 001 | trigger key mismatch | ✅ | ✅ | ✅ | ✅ | ✅ (#29) | ✅ | ✅ (inline) | — | ✅ (d769bc2) |
| 002 | bond required-metric drop | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 003 | name_cn backfill | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 004 | rename valuation_cost in evidence pool | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 005 | evidence-cutoff date in memo | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 006 | numeric-prose sanity validator | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 007 | tag watch_only with reason | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 008 | derive venue_status (drop unknown default) | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 009 | deterministic Section 7 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 010 | gold paper-gold proxy without index match | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |
| 011 | collapse decision-report markdown | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | ⏳ |

## Notes & deviations

- 2026-05-18: scaffold committed. Beginning loop with Item 001.
- 2026-05-18: Item 001 merged (PR #29 → d769bc2). Inline self-review used instead of subagent dispatch (1-line config-key alignment with full TDD coverage — overhead would have exceeded value). 2 pre-existing unrelated test failures noted: `tests/integration/test_thesis_coverage.py::test_no_all_evidence_insufficient_valuation` and `tests/test_e2e_full_pipeline.py::test_eval_single_stage_data`. Both reproduce on `main` without item 001 and are out of scope for this run.
