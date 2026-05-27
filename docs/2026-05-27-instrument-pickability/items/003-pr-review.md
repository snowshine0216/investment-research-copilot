Verdict: PASS-WITH-NITS

Source: /code-review (second-pass, high effort, 7 angles)
PR: https://github.com/snowshine0216/investment-research-copilot/pull/78
Review comment: https://github.com/snowshine0216/investment-research-copilot/pull/78#issuecomment-4552318570
Date: 2026-05-27

## Prior review fixes confirmed

Commit `b509385` fixes verified in-scope:
- P0: hardcoded `cwd="/Users/snow/..."` in AC13 test — fixed, `Path(__file__).resolve().parents[2]`
- P1: nan/inf bypass in `_coerce_premium` — fixed with `math.isfinite` guard
- P1: nan/inf bypass in `_coerce_optional_float` — fixed with `math.isfinite` guard
- P1: missing 5.0% / 5.001% boundary regression locks — added

## Findings (this pass)

### Finding 1 — PLAUSIBLE P1 (missed nan-guard site)

**File:** `src/irc/commands/memo_cmd.py` lines 619–622 (`_decision_status_for_pick`)

The prior review fixed nan/inf at `_coerce_premium` and `_coerce_optional_float` but did not
address this third coercion site. `float(nan)` returns `nan`, not `None`. With `premium_value = nan`:

- `qdii_premium_unknown = False` (nan is not None)
- `qdii_premium_too_high = False` (nan > 0.05 evaluates False)

Both blocking flags are silently skipped. A QDII buy candidate with a NaN upstream premium
receives `decision_status = "actionable_buy"` instead of `"blocked"`. The `_coerce_optional_float`
fix at line 782 guards `PickRow.qdii_premium_pct` but does not feed back into the `_decision_status_for_pick`
call at line 751, which reads the raw `sc` dict directly.

This function predates PR #78 (introduced in commit `affce1f`, PR #74), but the PR applied the
isfinite fix to two parallel sites while leaving this one. This is an inconsistency surfaced by
the second-pass sweep.

**Fix:** at line 621, replace bare `float(raw_premium)` coercion with `_coerce_optional_float(raw_premium)`.

### Finding 2 — Nit (cleanup)

**File:** `src/irc/memo/qdii_premium_lines.py` line 85, `src/irc/commands/memo_cmd.py` line 347

`import math` placed inside function bodies. `math` is stdlib — move to module-level imports.

### Finding 3 — Nit (documentation)

**File:** `src/irc/memo/picks_table.py` line 50

Footnote wording `（正值=溢价/折价为负）` is ambiguous; slash looks like AND/OR.
Intended meaning is likely `（正值=溢价，负值=折价）`.

## Verdict rationale

- 1 PLAUSIBLE P1 (missed fix site — pre-existing function, inconsistent with the stated P1 fix)
- 2 Nits (cleanup)
- No new P0 found
- All other paths verified clean: H3/SAME-3 invariants, citation IDs, §7 double-prefix
  impossibility, backward-compat (new kwargs keyword-only with None defaults), atomic write
  pattern, synthesizer marker lock, callers of modified functions

PASS-WITH-NITS: no merge blocker; P1 is a hardening improvement on a pre-existing gap.
