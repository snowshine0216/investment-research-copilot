# Progress tracker

| id  | title | spec | grill | plan | branch | impl | drift | ship | verify | pr-review | fix | merge |
|-----|-------|------|-------|------|--------|------|-------|------|--------|-----------|-----|-------|
| 001 | contributing-dimensions | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏭️ | ✅ |
| 002 | citation-data-model | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 003 | active-fund-constituent-layer | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 004 | live-verify-fund-announcement-em | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 005 | per-asset-class-citation-coverage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 006 | failure-mode-and-policy-b | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 007 | memo-and-discipline-renderers | ✅ | ✅ | ✅ | ✅ | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 008 | integration-test-sweep | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 009 | citation-gate-block-mode | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 010 | duckdb-fund-holdings-ingest | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

Legend: ⏳ = pending, 🔄 = in progress, ✅ = done, ⏭️ = skipped (mode / not applicable), ⚠️ = blocked.

## Run status: item 007 impl complete; ready for drift phase

Item 007 (memo + discipline renderers + alias-builder) impl phase verified green:
- 14 plan tasks committed (one per task per plan §"Task index").
- 2 additional commits during Task 15 verification:
  - `d01077f refactor(opportunity)`: relocated `citation_selector` from `irc.memo` to `irc.opportunity` to break a cycle (`opportunity → memo` via `report.py` calling `select_citations`, combined with pre-existing `memo → opportunity` edges via `picks_table` / `aliases`). Old import path preserved as a one-line re-export shim. ADR 0001 §3 amended to name the new canonical location.
  - `fab3b08 style(tests)`: 14 ruff cleanups (E402 mid-file imports, E741 ambiguous `l`, F401 unused imports, F841 unused locals) on the item-007 test additions. Pre-existing `tests/memo/test_evidence_pool.py:86` E741 left untouched (out of scope).
- Item 007 test scope (`tests/memo/`, `tests/opportunity/`, `tests/fundamentals/`, `tests/commands/test_memo_cmd.py`, `tests/commands/test_memo_cmd_aliases.py`, `tests/commands/test_opportunity_cmd.py`): 738 passed, 12 skipped, 0 failed.
- `tests/evals/test_architecture.py::test_dag_acyclic_check_*`: PASS after the cycle fix.
- Broader pytest sweep against the feature branch shows 5 pre-existing failures (integration + e2e tests requiring AkShare/manifest state); verified identical on the baseline branch — NOT regressions from item 007.
- Sub-branch `autodev/thesis-evidence-007-memo-and-discipline-renderers` is 16 commits ahead of `autodev/thesis-cards-evidence-gap`, not pushed.

Next phase: drift check, then ship.

## Notes on the `verify` column

This project is a non-web Python CLI. Each item's post-ship verification uses `/verify` (entry-point smoke + acceptance walkthrough), NOT `/qa` (which requires a browser-driven web app). The verdict file is `items/<id>-verify.md`.

## Notes on the `review` column

Per `/ship`'s steps 8+9, the in-flow review verdict is captured inline by `/ship` and lands in `items/<id>-review.md`. There is no separate review subagent dispatch. The `pr-review` column captures `/code-review` on the open PR (a distinct surface from `/ship`'s inline review).

## Outcome

(populated at run close-out — feature branch left open for user to review/merge into `main`)

## Per-item merge log

- **001 contributing-dimensions** — PR [#55](https://github.com/snowshine0216/investment-research-copilot/pull/55) squash-merged 2026-05-22 as `4cb4b9b` on `autodev/thesis-cards-evidence-gap`. Inline review PASS-WITH-NITS, verify PASS (8/8 ACs), pr-review PASS-WITH-NITS. Fix loop skipped (zero blockers, zero latent bugs).
- **002 citation-data-model** — PR [#56](https://github.com/snowshine0216/investment-research-copilot/pull/56) squash-merged 2026-05-22 as `5bc4b95`. 18-task plan; 7 impl commits + 1 fix commit. Drift PASS-WITH-NOTES (27/27 ACs verified), inline review PASS-WITH-NITS, verify PASS-WITH-NOTES (26/27 ACs — AC21 documented as ⚠️), pr-review PASS-WITH-NITS. Fix loop ran once: closed real latent bug (`fetch_types_attempted` schema gap on `OpportunityRow`); inline reviewer's `select_citations` identity-vs-equality flag was refuted by pr-review (mutually-exclusive data/info candidate sets). Includes new ADR `docs/adr/0001-citation-data-model.md`.
- **003 active-fund-constituent-layer** — PR [#57](https://github.com/snowshine0216/investment-research-copilot/pull/57) squash-merged 2026-05-23 as `3fbf50c`. 24-task plan + 4 fix rounds. Drift PASS (after Task 22 wiring amendment). Inline review PASS-WITH-NITS, /verify PASS (31/31 ACs), /code-review PASS-WITH-NITS (after closing 3 latent bugs). New ADR `docs/adr/0002-active-fund-fetch-engine.md` locks the cache/probe/budget/forbidden-pair contracts. Fix rounds closed: (1) `fundamentals→opportunity` import cycle (relocated 4 types to `fundamentals/types.py` with re-exports); (2) `--limit`/`--rebuild-fundamentals` not threaded into `_build_rows`; (3) preflight budget gate + advisory lock + resumable state defined-but-not-called (drift checker missed; surfaced by adversarial review); (4) 3 latent parser bugs from /code-review (all-NaN quarter, `_BJ_TOKENS` `'京'` collision, 5xxx ETF codes routed to UNKNOWN). Spec deviation noted: spec located `LookthroughTarget`/`ConstituentAnalysis`/`ThesisEvidence` in `opportunity/types.py` — ran into an architecture cycle, relocated to `fundamentals/types.py` with re-export preserving documented import path.
- **004 live-verify-fund-announcement-em** — PR [#58](https://github.com/snowshine0216/investment-research-copilot/pull/58) squash-merged 2026-05-23 as `6369601`. **Q4 hard-stop gate** initially FAILED (`ak.fund_announcement_em` missing from AkShare 1.18.63); user authorized fallback option (a) (substitute 3 topic-specific endpoints: `fund_announcement_dividend_em` / `_report_em` / `_personnel_em`). Pivot applied in place. Post-pivot verify PASS (9/9 endpoint × symbol cells covered). Drift PASS-WITH-NOTES (13/13 tasks; 4 cosmetic incidentals; authorized pivot logged). Inline review PASS-WITH-NITS (3 docs nits resolved in commit `f76137f`). /code-review PASS after fixing 2 NaN/NaT latent assertion bugs in commit `6f59c49`. Test-only sub-PR (zero `src/` changes); registered `live_akshare` + `integration` markers with `--strict-markers`; 11 live tests + 7 mocked failure-mode tests + 10 fixture JSONs + run-discipline README. **Downstream impact:** item 005's information-leg design must compose the 3 endpoints; uses `报告ID` as opaque citation key (no URL column available in AkShare 1.18.63).
- **005 per-asset-class-citation-coverage** — PR [#59](https://github.com/snowshine0216/investment-research-copilot/pull/59) squash-merged 2026-05-23 as `96d812d`. 15-task plan + 5 fix commits across 2 fix rounds. Drift FAIL → PASS (1st round: 6 `tests/fundamentals/test_snapshot.py` tests broke because new unconditional QDII sentinel dispatch intercepted `LookthroughTarget("qdii_us", "纳斯达克100")` registry tests — fixed by routing the 6 tests through `kind="broad_index"` to preserve unit-test intent while keeping spec F4 unconditional in production). Inline review (steps 8+9) PASS-WITH-NITS. /verify PASS-WITH-NOTES (19/19 ACs; live AkShare substituted with fixture-mocked integration tests at `test_opportunity_cmd_fund_level_integration.py`). /code-review PASS-WITH-NITS, then 2nd fix round closed 4 actionable findings: (1) `_classify_fund_level_scores` over-counted budget for `cn_etf` rows whose `tracked_index` resolves to QDII (real production bug — `FetchBudgetExceeded` false positives for QQQ/SPY-style ETFs); (2) `_FUND_LEVEL_KINDS` deduped via import from `snapshot.py` (single source of truth); (3) `assert isinstance` → `RuntimeError` for `-O` safety; (4) inverted `derive_thesis_from_evidence` QDII sentinel conditional. New dataclasses `FundNavReport`/`FundAnnouncement`/`FundLevelSnapshot` in `fundamentals/types.py`. F5 invariant locked (`"基金概况"` absent from production code). Cache layout `data/fundamentals/{quarter}/nav/fund_{iid}.json` parallel to item 003's `active_fund/`. Post-Q4-pivot: information leg composes the 3 topic-specific announcement endpoints from item 004 (`fund_announcement_{dividend,report,personnel}_em`); `报告ID` is the opaque citation reference (no URL column in AkShare 1.18.63). Deferred to future hygiene pass: `_ann_from_dict` topic Literal validation, `_ISO_DATE_RE` impossible-date strictness, broad `except Exception` narrowing, `snapshot_cache` dict namespace prefix, `math.isfinite` NaN/inf NAV filter.
- **006 failure-mode-and-policy-b** — PR [#60](https://github.com/snowshine0216/investment-research-copilot/pull/60) squash-merged 2026-05-23 as `3e3047d`. 16-task plan + 1 ruff cleanup + 1 ship-blocked docs + 3 fix-round-1 commits (closed 2 P0s + 1 P1 surfaced during initial /ship steps 8+9) + 3 fix-round-2 commits (closed 1 L1 + 2 nits from /code-review). New ADR `docs/adr/0003-failure-mode-policy-b.md` locks Policy B precedence (1→2→3→4→5) + atomic-write-at-end contract for `rejections.json` + audit_errors field placement + fetch_budget_exhausted raise location. Drift PASS-WITH-NOTES (13/16 OK + 2 accepted divergences — `_GAP_TO_REASON` 3 extra mappings + Task 14 compression). Inline review PASS-WITH-NITS (after fix-round-1: closed silent first-match in `_classify_rejection_reason` + plumbed `plan_hash`/`snapshot_cache_by_instrument` through `run_opportunity` + added 6 legacy gap code mappings). /verify PASS (27/27 ACs; fund-level integration tests as substitute for live AkShare). /code-review PASS-WITH-NITS → PASS after fix-round-2: closed forward-declared `missing_us_news_adapter` Literal/`_GAP_TO_REASON` inconsistency + parametrized mixed-known-unknown ordering test + criterion-18 regex accepts name_cn with spaces. New modules: `opportunity/policy_b.py`, `opportunity/rejection_log.py`, `opportunity/failure_renderer.py`. `_build_rows` now returns 7-tuple `(rows, positions, qualities, roles, pending_verdicts, plan_hash, snapshot_cache_by_instrument)`. `_write_opportunity_outputs` refactored into 5 explicit H3-invariant steps. Deferred latent: `_apply_reduction` (`reduce_same_theme`) ranks rows by quality signals without considering `evidence_gaps` — a clean publishable row sharing a `lookthrough_target.key` with a higher-quality gapped sibling could be silently dropped from both `thesis_cards.yaml` and `rejections.json`. Worth picking up alongside item 007/008's renderer + integration-test work since it touches publish-ability semantics.

## Artifacts (populated as each item completes)

- 001: `items/001-spec.md`, `items/001-grill.md`, `items/001-plan.md`, `items/001-drift.md`, `items/001-ship.md`, `items/001-verify.md`, `items/001-review.md`, `items/001-pr-review.md`
- 002: `items/002-*.md`
- 003–010: same pattern
