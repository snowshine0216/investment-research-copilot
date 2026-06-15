# 001 — Code review verdict (covers review + pr-review gates)

Verdict: **PASS-WITH-NITS** (Approve)

Single `/code-review` (high effort) pass on the `main...autodev/001-monitor-verdict-render`
diff. Because the `/ship` inline review was bypassed by the `gh` fallback (VERSION-bump
convention conflict — see `001-ship.md`), this one review pass is recorded as satisfying
both the in-flow review gate and the PR-review gate (same diff, same surface). See also
`001-pr-review.md`.

## Findings

No critical issues. No correctness / security / performance bugs.

**Verified safe:**
- XSS boundary preserved: every untrusted field (`claim.claim`, `FactorScore.reason`,
  `present_families`, freshness) goes through `html.escape`; numerics through `_num`;
  `[ref:…]` markers are renderer-appended from upstream-validated 16-hex citation ids.
- `_present_row` only sees non-None `c.value` (signal.py `_contributions` filters to present
  factors) → no None-format crash.
- `_ok_clause` only reached when `status == "ok"` (bias guaranteed non-None); `_BAND_PHRASE`
  lookup is None-defensive regardless.
- `factor_table_html` renders all 5 canonical factors because `build_factor_scores`
  (`factors.py:77`) always emits exactly the five FactorScores (eligible or N/A + reason) —
  verified, so "all factors incl. N/A" holds for every analysis_profile.
- `returns_table_html` uses `rt.get(w)` over the fixed window set → safe against the `{}`
  default and `None` values.

**Nits (optional, non-blocking):**
1. `render_factors.py` `_present_row(c, fresh)` — annotate `c: FactorContribution` to match
   the codebase's typed style.
2. `render_cards.py` clauses mix English machine labels into Chinese prose — intentional per
   design decision D2; no action.

Nits left unaddressed (cosmetic). No blocker / latent bug → no fix round required.
