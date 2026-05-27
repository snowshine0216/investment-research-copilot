Verdict: PASS

Source: /ship steps 8+9
PR: https://github.com/snowshine0216/investment-research-copilot/pull/77

## Step 8 — pre-landing parallel review

### Subagent 1: pr-review-toolkit:code-reviewer

Findings (0 P0, 3 P1):

1. **P1 — Non-deterministic set iteration in `weighted_overlap_pct`** (`src/irc/memo/concentration.py:71`)
   - `shared = top_a.keys() & top_b.keys()` produces a set; iteration order is PYTHONHASHSEED-dependent. IEEE 754 float addition is non-commutative — empirically deterministic with current 1dp weight data but fragile.
   - **Fixed in commit `60d5469`**: `sorted(top_a.keys() & top_b.keys())` pins order; function determinism is now provable rather than empirical.
2. **P1 — Missing boundary test at exactly 5 shared symbols** (`tests/memo/test_concentration.py`)
   - Test for n=6 ellipsis exists; n=5 (no ellipsis) boundary not exercised.
   - **Fixed in commit `60d5469`**: added `test_compose_concentration_lines_exactly_5_shared_symbols_no_ellipsis`.
3. **P1 — Redundant 3rd call to `_reconstruct_opportunity_rows`** (`memo_cmd.py:886`)
   - Same input traversed three times in `run_memo`. Correct but inefficient.
   - **Accepted as P2 — deferred**: refactor to memoize the result on a `MemoCmdState` would be its own task; cost-benefit not worth it for ≤80 rows.

### Subagent 2: pr-review-toolkit:silent-failure-hunter

Findings (0 P0, 2 P1, 4 P2/Notes):

1. **P1 — `_reconstruct_opportunity_rows` drops gapped rows from concentration analysis**
   - Rows with non-empty `evidence_gaps` are skipped at line 483; same dict feeds concentration at line 886, hiding eligible pairs whose member has any gap.
   - **Accepted as designed**: AC6 says only publishable rows participate. Gapped picks already get a §6 absence-block from `_format_gap_sub_block`. Mixing gap-handling and concentration-handling would conflate row-level and pair-level signals (ADR 0005 principle).
2. **P1 — Empty `constituent_analyses` silently excludes a pick** (`_eligible_rows`)
   - No log when a fund's holdings fetch failed upstream; pair disappears from analysis.
   - **Accepted as designed**: failure_reason already in `failure_reasons_by_symbol`; the omission is the correct fail-closed behavior (don't synthesize concentration from absent data).
3. **P2 — FP boundary instability on threshold comparison** (`compute_concentration_pairs:162`)
   - Same finding as adversarial; fixed (see step 9 fix).
4. **P2 (notes)** — marker lock is prompt-only (codebase-wide pattern), instrument_id lookup miss silently dropped (specced), empty result indistinguishable from missing-data result (same as item 001's pattern). All accepted as documented.

## Step 9 — adversarial review

Initial verdict: BREAKS (1 P0 + 2 P1 + 1 P2 + 1 false-positive)

1. **P0 — Duplicate symbol within one fund silently understates overlap** (`concentration.py:69`)
   - `{c.symbol: c.weight_pct for c in _top_n_by_weight(a)}` — if `_top_n_by_weight` returns the same symbol twice (rare malformed AkShare row), the dict keeps only the LAST iteration (lower weight after DESC sort). A pair that should be ≥30% silently drops below threshold → false negative concentration suppression. Operator buys two identical-thesis funds without warning.
   - **Fixed in commit `60d5469`**: `_top_n_by_weight` now dedupe-sums duplicate symbols BEFORE topN selection, with a clear docstring noting the defense. New test `test_weighted_overlap_pct_dedupes_duplicate_symbol_within_fund` verifies.
2. **P1 — `_reconstruct_opportunity_rows` divergence scenario** (`memo_cmd.py:886`)
   - Triple-call same input; if anything mutates `rebuilt_op_rows` between calls, concentration silently loses picks.
   - **Accepted**: rebuilt_op_rows is treated as immutable downstream. AC6/AC7 spec acceptance: "tolerates missing op rows" (tested).
3. **P1 (false positive) — Missing 5-pair display cap**
   - Adversarial misread the spec: AC7 caps shared SYMBOLS per bullet at 5, not pairs. The cap is implemented at `_format_concentration_bullet:48`. Confirmed by reading the code-reviewer's analysis. No fix needed.
4. **P2 — `sum()` returns `int 0` for empty intersection**
   - Cosmetic; `< 30.0` works correctly regardless of int vs float. Accepted.

Final verdict: PASS after in-branch fix of the duplicate-symbol P0 and the determinism + FP-boundary P1s.

## Final verdict rationale

- P0 fixed (commit `60d5469`)
- 2 P1 fixed (commit `60d5469`)
- 2 P1 accepted as designed
- All P2 accepted

Per autodev exit contract: PASS — zero blocker bugs, zero latent bugs surface unaddressed.
