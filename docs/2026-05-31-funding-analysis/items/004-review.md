Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial), orchestrator-inline
PR: https://github.com/snowshine0216/investment-research-copilot/pull/86
Supersedes: items/004-ship-blocked.md (pre-push findings; all 3 fixed before push)

## Reviewers
- pr-review-toolkit:code-reviewer (sonnet) — no P0; 2× P1
- pr-review-toolkit:silent-failure-hunter (sonnet) — 1× P0 (inf), 2× P1
- adversarial general-purpose (sonnet) → verdict RISKS (inf P1 + truncation P2)

## Findings

### FIXED pre-push (commit d185648)
1. **`_finite` screened NaN but not ±inf** — a derived `gross_margin = 1 - cost/revenue` could overflow to ±inf and render `毛利inf%`. Fixed: `_finite` now uses `math.isfinite` (blocks NaN + ±inf). Tests added.
2. **ROE percent-vs-ratio unit risk** (live-data display correctness) — if AkShare returns `18.5` (percent) not `0.18` (ratio), the fragment would show `ROE 1850%`. Fixed: `compute_ratios` degrades implausible `roe` (`abs > 1.5`) to None (degrade-to-none, ADR 0009 family). Tests added (0.18 pass-through; 1.85/-1.6 → None). Unit-verification follow-up → TODOS.
3. **`[:60]` cap mid-truncated the fragment** leaving an orphaned `（` — Fixed: `_one_line_view` appends the fragment only if the candidate fits whole within the cap (cap value unchanged, AC11); empty/base-only rows stay byte-identical. Tests added.

### Nits → TODOS (not blocking)
- Verify AkShare ROE unit via the double-gated live test (consider `/100` if percent-scale).
- `盈利能力`-section schema drift silently yields `roe=None` with no failure_reason/log (matches existing `_common_metric` convention; observability follow-up, same family as item-001's broad-except TODO).

### Adversarial — CLEAN on invariants
- `_evidence_for_constituent` 2→3-tuple ripple complete (sole prod caller `snapshot.py:554` + all 5 test call-sites); reason-only posture intact (no change to valuation_state / thesis_state / Policy B / core_dca / opportunity partition / citation set); determinism holds; all-None / equity=0 / negative-roe handled. The only real gap (inf) was fixed.

## Test notes
- tests/fundamentals + tests/opportunity: 729 passed / 13 skipped (post-fix).
- Full suite: 2559 passed / 32 skipped / 8 failed — the 8 are the documented pre-existing failures (identical to base per items/001-ship.md); 0 new.
- ruff: clean on all item-004 files.
