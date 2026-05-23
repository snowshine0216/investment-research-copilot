PR: https://github.com/snowshine0216/investment-research-copilot/pull/58
Mode: A
Branch: autodev/thesis-evidence-004-live-verify-fund-announcement-em
Base: autodev/thesis-cards-evidence-gap
Title: test(fundamentals): Q4 pivot — live-verify the 3 topic-specific fund-announcement endpoints (004)

## Source
/ship invocation (manual orchestrator-driven, test-only sub-PR):
- Step 0: platform=GitHub, base=autodev/thesis-cards-evidence-gap (autodev override, not main)
- Step 1: preflight OK (15 commits, ~3100 insertions, 19 files, zero src/ changes)
- Step 2: skipped (no new binary)
- Step 3: base already up to date
- Step 5: full suite ran; 7 pre-existing failures match base (1644 passed, 28 skipped including the 11 live tests)
- Step 6: test-only diff — no coverage audit needed
- Step 7: drift verdict PASS-WITH-NOTES (items/004-drift.md)
- Steps 8+9: 2 parallel reviewers (code-reviewer + adversarial). Code-reviewer: LAND with 4 cosmetic P1s. Adversarial: RISKS with 3 P1/P2 findings — 2 addressed in commit f76137f (docstring/README dual-gate clarification), 1 deferred (NaN row P2). No P0s.
- Steps 10-12: skipped (test-only sub-PR into feature branch; no version/changelog bump)
- Step 13: tree clean
- Step 14: pushed
- Step 15: PR #58 created

## Q4 status
- ORIGINAL: ak.fund_announcement_em missing → FAIL surfaced 2026-05-23
- PIVOT: user-authorized option (a) → 3 topic-specific endpoints
- POST-PIVOT VERIFY: PASS (9/9 cells covered, all 3 symbols × 3 endpoints non-empty)
- DOWNSTREAM: item 005's information-leg design must compose the 3 endpoints; uses 报告ID as opaque citation key (no URL column available)

## Pivot rationale
ak.fund_announcement_em does not exist in AkShare 1.18.63. AkShare exposes 3 topic-specific variants (dividend/report/personnel). User chose option (a) (adapt to topic-specific endpoints) over (b) (theme reports w/ promoted scope) and (c) (exclude gold + cn_bond_fund from V1). Pivot is documented in items/004-spec.md §"Pivot — Q4 option (a)" and items/004-verify.md.

## Test-only invariant
Confirmed via `git diff --name-only autodev/thesis-cards-evidence-gap...HEAD | grep ^src/` → empty.
