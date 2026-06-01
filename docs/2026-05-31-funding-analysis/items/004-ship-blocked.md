# 004 — /ship steps 8+9 review findings (pre-push)

Captured before the PR opens (ship.md "review can demand fixes before push"). Routed through a fix subagent; superseded by `items/004-review.md` once the PR opens clean.

## Reviewers
- pr-review-toolkit:code-reviewer (sonnet) — no P0; 2× P1
- pr-review-toolkit:silent-failure-hunter (sonnet) — 1× P0 (inf), 2× P1
- adversarial general-purpose (sonnet) — verdict RISKS (inf P1 + truncation P2)

## Findings to fix pre-push

### FIX A — `_finite` screens NaN but not inf (latent)
`src/irc/fundamentals/ratios.py` `_finite` uses `math.isnan` only. `gross_margin = 1 - (cost/revenue)` (akshare_filing.py:160) is a DERIVED value that can overflow to ±inf, bypassing the guard → `毛利inf%`/`毛利-∞%` in the fragment. The docstring advertises "NaN screened to None" — inf escaping contradicts it. **Fix:** `_finite` returns None unless `math.isfinite(value)` (blocks both nan and inf). Add a test with an inf input.

### FIX B — ROE unit assumption risks a silent 100× display error (latent, live-data)
`_profitability_metric` passes AkShare `净资产收益率` through assuming ratio units (fixture uses 0.18). If the live API returns percent units (18.5), `ratios_reason_fragment` renders `ROE 1850%` — non-None, non-NaN, factually 100× wrong. roe renders on LIVE data today (unlike consensus_upside). **Fix:** degrade implausible roe to None — if `abs(roe) > 1.5` (≈150%, implausible as a ratio for the in-scope universe), treat as a unit error and return None (degrade-to-none, ADR 0009 family). Deterministic; the 0.18 fixture stays valid; a percent-scale value safely shows nothing rather than a wrong figure. Add a test (1.85 → None; 0.18 → 0.18). Record the "verify AkShare ROE unit via the double-gated live test; consider /100 normalization if confirmed percent" follow-up in TODOS.

### FIX C — `[:60]` cap mid-truncates the fragment (cosmetic, orphaned bracket)
`src/irc/fundamentals/snapshot.py` one_line_view appends the ratios fragment then slices `[:60]`, which can cut mid-fragment leaving an unclosed `（ROE 1...`. **Fix:** append the ratios fragment only if the joined result stays within the 60-char cap; otherwise omit it WHOLE. Cap value unchanged (AC11). Empty-fragment rows stay byte-identical. Add a test for the overflow case (fragment omitted, no dangling separator/bracket).

## Accepted / noted (NOT fixed now)
- `盈利能力`-section schema drift → silent `roe=None` with no failure_reason/log. Matches the existing `_common_metric` convention and the spec ("ROE absence never fails the digest"); documented in FilingDigest.roe docstring + test. → TODOS note (observability), consistent with the item-001 broad-except TODOS entry.
- Adversarial CLEAN on: 3-tuple ripple complete (all 6 unpack sites), reason-only invariant (no opportunity/ change, no new [ref:...], partition/Policy-B/thesis_state untouched), determinism, all-None/equity=0/negative-roe handling.
