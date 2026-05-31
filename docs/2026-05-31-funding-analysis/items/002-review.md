Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial), orchestrator-inline
PR: https://github.com/snowshine0216/investment-research-copilot/pull/85
Supersedes: items/002-ship-blocked.md (pre-push findings; the one blocker fixed before push)

## Reviewers
- pr-review-toolkit:code-reviewer (sonnet)
- pr-review-toolkit:silent-failure-hunter (sonnet)
- adversarial general-purpose (sonnet) → verdict CLEAN

## Findings

### Blocker / latent — FIXED pre-push (commit 3ef0379)
- `src/irc/opportunity/valuation_fundamental.py` neutral branch printed `隐含上行空间 {x}` ("implied upside") for a NEGATIVE `consensus_upside_pct` in the neutral band `(-0.10, 0)` — factually wrong user-facing memo text (AC2). Fixed: branch on sign (`上行空间`/`下行空间` with `abs()` magnitude) + fail-loud `assert consensus_upside_pct is not None` precondition + regression test `test_reason_phrase_neutral_negative_upside_says_downside` (red→green). Zero blockers/latent bugs remain.

### Nits — deferred to TODOS.md (not blocking)
- `valuation_fundamental_signal` computed twice per row (states.py:240 + :563). Deterministic on frozen `OpportunityInput`; drift PASS validated the single-threading-param design. Maintainability note only.
- `_NOTCHABLE_VALUATION_STATES` includes `"cheap"` (no-op arm) — the notch does real work only on `reasonable_low`. Naming/comment cleanup.
- NaN/inf in pe/pb/upside render literal `nan%`/`inf%` cosmetically; no state impact, data sources don't emit them. P2 cosmetic.

### Adversarial — CLEAN
- `core_dca` gate sound across None/neutral/rich × percentile combinations; one-notch never moves toward more-expensive (AC3); no change to citation set / partition / Policy B / `thesis_state` (H3/SAME-3 hold; AC8 structural lock). Empty-dims for signal-conflict `small_watch` is pre-existing, not a regression.

## Test notes
- tests/opportunity/: 458 passed / 1 skipped.
- Full suite: 2517 passed / 32 skipped / 8 failed — the 8 are the documented pre-existing failures (identical to base per items/001-ship.md); 0 new.
- ruff: clean on all item-002 files.
