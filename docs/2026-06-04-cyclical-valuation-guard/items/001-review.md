Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (orchestrator-driven inline review)
Reviewers (model=sonnet):
  - pr-review-toolkit:code-reviewer (step 8 subagent 1)
  - pr-review-toolkit:silent-failure-hunter (step 8 subagent 2)
  - general-purpose adversarial reviewer (step 9) — verdict: RISKS (one P1, one P2; no P0/BREAKS)
Scoped test gate (step 5): 216 passed (touched files), 1.87s.

## P0 / blockers
None. Adversarial verdict was RISKS (P1), not BREAKS.

## Findings + triage

1. **`narrative/risk.py:34-41` — new `evidence_insufficient` driver fires for ALL evidence_insufficient valuations, not only the commodity-cyclical guard** (flagged by code-reviewer P1 + adversarial P1 — most-corroborated).
   - Reality confirmed in code: `classify_valuation` has TWO paths to `evidence_insufficient` — the new §1 metals guard (`states.py:259`) and the pre-existing missing-data path (`states.py:274-275`, `if pct is None`). `_state_drivers` runs only on publishable rows (empty `evidence_gaps` short-circuits to `insufficient` first, `risk.py:68`), so a non-metals fund with neither a PE anchor nor NAV history CAN reach the new driver.
   - **Classification: NOT a bug — spec-intended.** Spec §4's explicit intent is to "surface a withheld valuation so it isn't silently dropped"; that intent applies to ANY unassessable valuation, not just metals. The rationale string "valuation withheld — no fundamental anchor" is *accurate for both paths* (neither has a fundamental anchor; both are withheld). Bumping an unassessable-valuation fund low→moderate is the conservative, correct behavior — the prior `low` ("no elevated risk drivers") was the silently-benign outcome the spec set out to close. The driver tuple string is specified VERBATIM in spec §4. Narrowing to metals-only would (a) contradict spec intent and (b) deviate from the spec's literal driver string. The behavior is locked by `test_evidence_insufficient_valuation_surfaces_driver_non_blocking` (level==moderate) and broke no existing test (216 green). → keep as-is; documented.

2. **`tests/opportunity/test_inputs_loader.py` `_seed_sector_instrument_with_prices` seeds `'metals'` into the `asset_class` column** (code-reviewer P1).
   - Behaviorally harmless (`populate_inputs` never reads `asset_class` from the instruments table; the test passes the correct `asset_class="cn_etf"` on the `OpportunityInput` skeleton). → **NIT** (fixture hygiene). Documented follow-up; not blocking.

3. **`_csindex_pe_ttm_map` / sector fetch path has no observability when a non-empty csindex frame yields zero usable PE** (silent-failure-hunter P1; the genuine column-drift concern).
   - A future csindex column rename (`市盈率1` → other) or a string-coded PE (`"—"`) silently degrades to None → the accumulate-forward series never activates and no log signals why. → **ENHANCEMENT / follow-up.** Deliberately NOT added pre-push: `_csindex_pe_ttm_map` is a pure helper and the project's FP rule forbids logging in pure functions; the right fix is a thin log at the I/O edge, best done holistically with the pre-existing `_fetch_frame` silent-degrade (item 4) in a focused follow-up. The current behavior is correct per the degrade-to-None contract; the §1 guard makes the missing PE safe.

4. **`akshare_index_valuation.py` `_fetch_frame` bare `except Exception: return None` swallows adapter errors without logging** (silent-failure-hunter labeled P0).
   - **Downgraded: pre-existing shared infrastructure, OUT of scope.** `_fetch_frame` is not introduced by this diff; it is shared with the broad-index legulegu fetchers, and its silent-degrade is the established, documented best-effort contract. Touching it has broad blast radius (broad-index ingest). The new sector leg's `try/except` in `ingest_cmd.py` does log on exception (`exc_info=True`). → documented follow-up (improve fetch-layer observability holistically), not a blocker for this PR.

5. **P2 — all-NaN csindex frame returns a non-None `IndexValuationHistory` with all-None PE rows** (adversarial P2). Downstream-safe: `pe=None` → latest-null guard blocks percentile; `_pe_series_is_mature.dropna()` → 0 valid → gate fails. → accept.

6. **P2 — duplicate dates in a csindex frame: dict-keying silently keeps the last row** (adversarial P2). csindex is authoritative and single-row-per-date; unlikely. → accept.

## Net code quality
- Net ruff delta −2 vs feature base (no lint regression); production source ruff-clean.
- Test coverage for all new behavior (symmetric guard, min-history gate, csindex column isolation incl. the legulegu-rejection test, slug resolution, sector ingest leg, risk driver) is comprehensive and TDD-ordered.
- All five load-bearing invariants confirmed by the drift pass + these reviews.

Exit-contract status: zero blockers, zero latent bugs → PASS-WITH-NITS. Nits (2) + accepted follow-ups (3,4,5,6) documented; none block merge.
