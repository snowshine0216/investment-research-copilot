# Cross-branch validation — `claude/trust-check-fixes-2026-05-19`

## Acceptance check against the trust-check priority list

Source: `outputs/2026-05-19/adversarial_review_trust_check.md`.

| # | Priority item                                                  | Status | Evidence                                                                     |
|---|----------------------------------------------------------------|--------|------------------------------------------------------------------------------|
| 1 | "Today's only action" headline                                 | ✅     | Line 3 of regenerated `decision_report.md` — empty-state visible             |
| 2 | Memo_audit P1 in Verdict                                       | ✅     | Line 13: `🛑 合规审核未达标 / Memo compliance audit failed: …条件通过…P1…10条` |
| 3 | Execution drift banner                                         | ✅     | Line 11: `⚠️ 执行漂移提醒 / Execution drift: 现金残余权重 15% > 目标 5%`      |
| 4 | Refuse QDII `actionable` until premium known                   | ✅     | Gate in `gates.py` (`qdii_premium_unknown`); 6 unit tests; behind pipeline_halted in this run |
| 5 | Reconcile English `score_action` with Chinese label            | ✅     | Every row reads `english_label / 中文标签` + `Name` column                  |
| 6 | Collapse venue-blocked list to one remediation line            | ✅     | Line 136: `_✓ Role already met for gold: cmb_paper_gold (20% target_weight)_` |
| 7 | Beginner glossary                                              | ✅     | Line 143: `## 术语速查 (Glossary)` with 11 explained terms                  |

## Test suite

Full pytest run on the feature branch:

```
1411 passed, 2 failed, 17 skipped
```

The 2 failures (`test_no_all_evidence_insufficient_valuation` and
`test_eval_single_stage_data`) are **pre-existing on `main`** and
unrelated to this branch — verified by checking out main's `src/` +
`tests/` and re-running. The prior 2026-05-19-adversarial-fixes
run-dir also documents them as "2 pre-existing e2e failures unrelated
to this branch."

Focused suite for the modified surface area:
```
tests/decision/ + tests/memo/ + tests/commands/ = 325 passed
```

## Manual end-to-end check

Ran `uv run irc decision` on the existing 2026-05-19 outputs:

- Exits 0 (CLI prints `decision blocked -> outputs/2026-05-19/decision_report.md`)
- Output starts with the "Today's only action" headline (not the
  Verdict line)
- Drift banner appears under Verdict
- Audit P1 banner appears under drift
- Bilingual `score_action / 中文` cells visible in every table
- Gold-blocked group shows the "Role already met" remediation line
- Glossary appears at the end

## Files touched

- `src/irc/commands/decision_cmd.py` (+ `_load_audit_summary`,
  `_names_from_bundle`, `_names_from_watchlist_csv`, name+audit
  plumbing)
- `src/irc/decision/gates.py` (+ `_QDII_ASSET_CLASSES`, the QDII
  premium gate, `target_weight` + `role` kwargs)
- `src/irc/decision/models.py` (+ `instrument_name`, `target_weight`,
  `role` fields on `DecisionRow`)
- `src/irc/decision/report.py` (+ `_todays_only_action_section`,
  `_execution_drift_banner`, `_audit_summary_banner`,
  `_proxy_coverage_banners`, `_glossary_section`, `_score_action_cell`,
  `_name_cell`, `_build_proxy_coverage`, `_execution_drift`, the
  `audit_summary` / `execution_drift` / `proxy_coverage` /
  `target_weight` / `role` plumbing)
- `src/irc/memo/auditor.py` (+ `extract_audit_summary` with broader
  P1 detection)
- Tests: `tests/decision/test_three_section_markdown.py`,
  `tests/decision/test_gates.py`, `tests/decision/test_report.py`,
  `tests/memo/test_audit_summary.py`, `tests/commands/test_decision_cmd.py`
- Run dir: `2026-05-19-trust-check-fixes/MASTER-*.md`, `PROGRESS.md`,
  `SKIPPED.md`, `items/00{1..7}-spec.md`

## Items skipped — see SKIPPED.md

- Strategy Sanity Check S1–S7 (mostly already shipped in v0.8.5.1).
- A3 "completeness: 1.00" deeper fix (partial mitigation via glossary).
- B5 pipeline state visibility (already addressed by the pre-existing
  `pipeline_halted` Verdict line).

## Net effect

A non-finance reader opening today's `decision_report.md` now sees, in order:

1. What to do today (or that nothing is buyable)
2. Whether 5pp+ of NAV has drifted to cash
3. Whether the memo flunked compliance audit
4. Why the system is blocked (if any)
5. Actionable buys
6. Blocked rows grouped by reason, with proxy-coverage remediation
   where applicable
7. Watch rows collapsed by reason
8. A glossary explaining every cryptic term

That delivers the trust-check doc's stated outcome:

> If the user safely acts only on what survives all gates, they buy
> only what is genuinely actionable.
