# 004 — /ship pre-landing review findings (pre-push)

Source: /ship steps 8+9 (code-reviewer + silent-failure-hunter + adversarial). Verified against code. Code-reviewer P0=none; suppression complete, `.json` intact, refresh line accurate, determinism clean, row identity preserved (all funds still listed). The findings below are the item-003 ↔ item-004 interaction.

## Fix before push
1. **Misleading orphan weak-floor legend (P0/P1, silent-failure + adversarial).** `_has_weak_fund` (report.py, from item 003) injects the weak-floor legend when ANY fund has `product_quality_state == "weak"`. But item 004 now SUPPRESSES the `子状态` line (incl. `质量=weak`) on `position_risk_level == "insufficient"` rows. So a fund that is `weak` AND `insufficient` triggers the legend while its `质量=weak` is hidden → the reader sees a legend warning about a rating no row displays. FIX: scope the legend trigger to funds that actually DISPLAY `质量`, i.e. `product_quality_state == "weak" AND position_risk_level != "insufficient"`. Edge: an all-insufficient report (e.g. robots 8/8) then shows no orphan legend (correct — no `质量` shown). Test: (a) report whose only weak fund is insufficient → NO legend; (b) report with a sufficient weak fund → legend present.
2. **Vacuous item-003 watchdog test (P1, adversarial).** `test_report_md_genuine_weak_shows_real_numbers` splits on `質量=weak` and inspects the rest of that line for the drivers — but item 004 moved `产品驱动` onto its OWN line, so the split now yields `""` and the three `not in ""` assertions pass vacuously. The sufficient-row rendering is still correct (golden test pins it), but this watchdog now covers nothing. FIX: update the test to locate the `产品驱动` line itself (post-004 layout) and assert the real numbers appear there.

## Fix (nit)
3. **Golden docstring inaccuracy (P1, code-reviewer).** `test_sufficient_row_block_byte_identical_golden` docstring says "pre-004 shape", but item 004's Task 1 intentionally split `产品驱动` onto its own line for ALL rows, so the golden pins the POST-004 canonical shape. FIX: correct the docstring wording.

## Noted, NOT changed
- `说明:`/risk_rationale line renders unconditionally before the branch, but for insufficient rows `risk.py:60-61` always returns the fixed `"evidence_gaps present — risk cannot be assessed"` (no verdict tokens), so no leak in production. The forbidden-token test's fixture sanitizes risk_rationale → a theoretical test-surface gap only; production-safe. Leave (optional future test-hardening).
- Sufficient-row `产品驱动` line-split (vs item-003's combined line): intentional, plan-sanctioned (Task 1), drift-accepted; golden test pins the new shape.
- `.md` hides conclusions while `.json` keeps them: intended display-discipline contract (item 003 AC8 + H3).
