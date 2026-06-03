Verdict: PASS-WITH-NITS
Source: /ship steps 8+9 (code-reviewer + silent-failure-hunter + adversarial), with a pre-push fix round + re-review

## Summary
Code-reviewer P0=none (suppression structurally complete, `.json` intact, refresh line accurate, row identity preserved, determinism clean). Three findings from the item-003 ↔ item-004 interaction were fixed before push (commits a952963, ed4128b). Re-review: P0 none, all 3 verified resolved. One minor test-thoroughness nit remains. Zero blockers, zero latent bugs.

## Findings → resolution
- **Orphan weak-floor legend (P0/P1, fixed a952963)** — item-003's `_has_weak_fund` legend fired on any `weak` fund, but item-004 hides `质量` on insufficient rows → a weak+insufficient fund produced a legend warning about a rating no row displays. Scoped the predicate to `product_quality_state == "weak" AND position_risk_level != "insufficient"`. Two new tests: all-insufficient-weak → NO legend; sufficient weak → legend present. (Edge: robots 8/8-insufficient now shows no orphan legend.)
- **Vacuous item-003 watchdog (P1, fixed ed4128b)** — `test_report_md_genuine_weak_shows_real_numbers` split on `質量=weak ｜ 产品驱动`, but item-004 moved `产品驱动` to its own line → split yielded `""`, assertions vacuous. Rewritten to locate the standalone `产品驱动` line and assert real numbers (would FAIL on regression).
- **Docstring nit (fixed ed4128b)** — golden test docstring "pre-004" → "post-004 canonical shape".

## Remaining nit (non-blocking)
- `_FORBIDDEN_INSUFFICIENT_TOKENS` includes `"evidence_insufficient"`, which the test fixture (`product_quality_state="acceptable"`) never produces — that one token's guard is vacuous against this fixture (the meaningful verdict tokens ARE guarded). Production-safe; conservative list. Left as-is.

## Verification
- `uv run pytest tests/narrative` → 149 passed, 1 skipped.
- `uv run ruff check` (touched files) → All checks passed.
- `git diff …risk.py …states.py` empty (renderer-only); `.json` unchanged (insufficient rows keep conclusions in JSON).
- Re-review: code-reviewer P0=none; legend gate sole-caller + deterministic; suppression branch unchanged.
