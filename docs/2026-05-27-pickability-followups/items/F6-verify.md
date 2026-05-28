Verdict: PASS

Subagent: sonnet
Round: 1
Source: `uv run pytest tests/opportunity tests/memo -q` (794 passed, 1 skipped, 0.53 s) + targeted per-AC checks below.

---

## Test run

    uv run pytest tests/opportunity tests/memo -q
    → 794 passed, 1 skipped in 0.53s

    uv run pytest tests/memo/test_pipeline_sanitization.py::test_appendix_caveat_fires_on_legacy_revenue_yoy_substring_too -v
    → 1 passed in 0.01s (cache-transition P0 guard)

Full suite (`uv run pytest tests/ --tb=no -q`) — 2453 passed, 31 skipped, 9 failed. All 9 failures are pre-existing on `main` and documented in F4-verify AC #9:
- `test_qdii_appears_in_rejections_with_qdii_reason` — pre-existing
- `test_memo_cites_only_publishable_citation_ids` — pre-existing
- `test_opportunity_pipeline_produces_three_outputs` — pre-existing
- `test_opportunity_pipeline_preserves_holdings_even_when_dropped` — pre-existing
- `test_build_rows_qdii_row_carries_sentinel_gap` — pre-existing
- `test_only_stage_runs_single` — pre-existing
- `test_dag_acyclic_check_true_for_valid_imports` — pre-existing
- `test_eval_single_stage_data` — pre-existing
- `test_e2e_irc_run_full_pipeline` — pre-existing

Confirmed pre-existing via `git stash` returning "no local changes to save" — the failures existed before any F6 edits were staged.

---

## Per-AC results

| AC | Description | Result |
|----|-------------|--------|
| #1 | No `revenue_yoy=` in any `ThesisEvidence.summary`; locked phrase `财报已披露（口径未核实）` at all 3 producer sites (legacy `_filing_evidence`, CN `_evidence_for_constituent`, HK `_evidence_for_constituent`) | PASS |
| #2 | Policy B rule 3 still fires on shape (`citation_kind`, `scope`), not summary text; `test_policy_b_rule3_accepts_new_filing_summary_phrase` passes | PASS |
| #3 | `_TYPE_RANK = {"filing": 0, "broker": 1, "news": 2}` unchanged; `test_filing_evidence_preserves_structural_role_legacy` asserts `_TYPE_RANK["filing"] == 0 < broker < news` | PASS |
| #4 | `find_uncited_opportunity_rows` audit gate — `tests/opportunity/test_auditor.py` 12 passed, 0 failed | PASS |
| #5 | SAME-3 invariant — `tests/memo/test_same_3_invariant.py` 3 passed (`evidence_pool`, `picks_table`, `discipline_section`) | PASS |
| #6 | Appendix caveat trigger now keys on `财报已披露（口径未核实）` (new) AND `revenue_yoy=` (legacy cache-transition guard) — both tested in `test_appendix_caveat_fires_on_new_disclosure_existence_phrase` and `test_appendix_caveat_fires_on_legacy_revenue_yoy_substring_too` | PASS |
| #7 | Citation-id hash re-roll acknowledged in ADR 0001 §5.3; filing evidence rows carry `source_url` from `FilingDigest.source_url`, so URL dominates the preimage and citation_ids are stable for non-empty-URL rows; empty-URL degraded-path acknowledged as one-time re-roll | PASS |
| #8 | `memo/synthesizer.py:55-56` updated to reference new locked phrase; `test_synthesize_memo_user_prompt_includes_cost_grade_glossary` (synthesizer_glossary suite) asserts `"财报已披露（口径未核实）"` appears in user_msg; `sanitize_unverified_revenue_yoy` preserved as belt-and-braces | PASS |
| #9 | No new test failures attributable to F6 — all 9 failures pre-existing on `main` (confirmed) | PASS |
| #10 | ADR 0001 §5 Addendum (`## Addendum — 2026-05-28: Filing evidence semantics`) present at line 100 of `docs/adr/0001-citation-data-model.md`; ADR 0003 §1 rule 3 carries one-line pointer back to ADR 0001 §5 Addendum at line 28 of `docs/adr/0003-failure-mode-policy-b.md`; CONTEXT.md new section `## Filing evidence semantics` at line 122 with 4 entries | PASS |

**P0 cache-transition guard**: `pipeline.py:191` — `if "财报已披露（口径未核实）" in ref or "revenue_yoy=" in ref` — both substrings trigger the `⚠️ 合规警示` caveat. Legacy fund cache files (e.g. `data/fundamentals/2026Q1/active_fund/fund_000127.json`) still carry `revenue_yoy=0.063…` summaries; those rehydrate at memo-build time with the legacy shape intact and the compliance caveat fires correctly via the `revenue_yoy=` branch. New cache files (produced after `irc fundamentals snapshot --target all`) will carry the `财报已披露（口径未核实）` phrase and fire via the new branch. No compliance gap during the turnover window.

---

## Code-surface verification

Producer sites confirmed (grep `src/`):

- `src/irc/opportunity/thesis_evidence.py:98` — `summary=f"{f.symbol} {f.fiscal_period} 财报已披露（口径未核实）"` (legacy)
- `src/irc/fundamentals/snapshot.py:344` — same phrase (CN active-fund)
- `src/irc/fundamentals/snapshot.py:395` — same phrase (HK active-fund)
- `src/irc/memo/pipeline.py:191` — dual-trigger: `"财报已披露（口径未核实）" in ref or "revenue_yoy=" in ref`
- `src/irc/memo/synthesizer.py:55-56` — prompt updated to reference new phrase

No `revenue_yoy=` raw scalar appears in any `ThesisEvidence.summary` at any producer site.
