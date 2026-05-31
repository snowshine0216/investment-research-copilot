# 002 — /ship steps 8+9 review findings (pre-push)

Captured before the PR is opened (ship.md "review can demand fixes before push" path). Routed through a fix subagent; this file is superseded by `items/002-review.md` once the PR opens clean.

## Reviewers
- `pr-review-toolkit:code-reviewer` (sonnet)
- `pr-review-toolkit:silent-failure-hunter` (sonnet)
- adversarial `general-purpose` (sonnet)

## Findings

### BLOCKER / latent — fix before push
1. **Misleading neutral-branch reason string for negative upside** — `src/irc/opportunity/valuation_fundamental.py:67`.
   The `neutral` branch hardcodes `隐含上行空间 {upside_pct}`. For `consensus_upside_pct` in `(-0.10, 0)` (the neutral band), this prints e.g. `隐含上行空间 -5%` ("implied upside -5%") when the value is downside. Factually wrong user-facing memo text. Dormant in prod (consensus_upside is None until item 003) but in the exact code 002 introduces (AC2). **Fix:** branch the neutral phrase on sign — positive → `上行空间 {upside:.0%}`, negative → `下行空间 {abs(upside):.0%}`.

### latent / robustness — fix while in the file
2. **No None-precondition guard in `_fundamental_reason_phrase`** — `valuation_fundamental.py:61`.
   `f"{inp.consensus_upside_pct:.0%}"` would `TypeError` if ever called with `consensus_upside_pct=None`. Safe today (only called under the `if fundamental is not None` guard), but should fail loud. **Fix:** add `assert inp.consensus_upside_pct is not None` documenting the precondition.

### coverage — add with the fix
3. **No test for the neutral branch with negative upside** (the exact range that triggers #1). Add a red→green test.

## Accepted nits (NOT fixed now — recorded, no action)
- **Signal computed twice** (`states.py:240` inside `classify_valuation` + `states.py:563` in `build_opportunity_row`). Deterministic on a frozen `OpportunityInput`; drift PASS validated the single-threading-param design; adversarial confirmed the `core_dca` gate is sound. Refactoring to a shared binding would change `classify_valuation`'s signature (re-opening drift) for no correctness gain. Note only.
- **`_NOTCHABLE_VALUATION_STATES` includes `"cheap"`** (no-op arm) — naming/docs only; the notch does real work only on `reasonable_low`.
- **NaN/inf in pe/pb/upside** → cosmetic `nan%`/`inf%` in reason string; pydantic permits them but data sources won't emit them. P2 cosmetic, accept.
- **Adversarial verdict: CLEAN** — gate logic sound; no partition/citation/Policy-B/thesis_state change (H3/SAME-3 hold); empty-dims for signal-conflict `small_watch` is pre-existing, not a regression.
