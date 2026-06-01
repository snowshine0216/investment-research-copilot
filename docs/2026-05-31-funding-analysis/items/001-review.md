Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial review)
Subagents: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose (adversarial)

## Findings

### Blocker / latent — 1 (FIXED pre-push)
- `src/irc/fundamentals/consensus.py:22` — adversarial **A1**: the guard
  `latest_close is None or latest_close <= 0` does not catch NaN (NaN compares
  False), and a NaN `target_price` is not None — either poisons the result with
  NaN in a `float | None` field. **Fixed pre-push** (commit `12d5560`): `math.isnan`
  screen on both legs + 2 new tests (`test_latest_close_nan_returns_none`,
  `test_nan_targets_filtered_like_none`). Unreachable today (targets empty until
  Tushare/003) but a real defect in the pure helper.

### Accepted-by-precedent (recorded in TODOS, not blocking)
- `src/irc/fundamentals/akshare_index_valuation.py:78-81` — silent-failure-hunter
  flagged the broad `except Exception: return None` in `_fetch_frame` as masking
  schema drift (renamed legulegu column / retired endpoint → PE/PB silently null
  forever, no log). **Accepted**: matches the established AkShare-fetcher convention
  across the codebase (`akshare_filing.py`, `akshare_fundamentals.py`); the field is
  inert today; the failure mode is *safe degradation* (item 002 would read None →
  `evidence_insufficient`, never wrong data); the double-gated live test is the
  project's drift detector. Recorded in `TODOS.md` → Reliability for a follow-up
  (narrow the catch / add a debug log). Not a wrong-output bug.

### Nits (noted, non-blocking)
- code-reviewer P1: `tests/opportunity/test_inputs_loader.py` — monkeypatch guard
  in the unrecognised-index test is never reached (early-exit before fetch);
  prefer `assert_not_called()`. Plus the gold/bond generator-throw lambda is opaque.
- code-reviewer P1: `_today_iso` not patched in the empty-frames test (inert).
- silent-failure P1: `inputs_loader.py:149` — empty price series → `latest_close=None`
  with no log (handled correctly by `consensus_upside_pct`, no crash).
- adversarial A2 (P2): partial PE/PB fetch stamps `as_of_iso` even when one leg is
  None — cosmetic, fields inert. A5 (P2): `broker_reports` list-vs-tuple annotation.

## Inertness
P0-hunt for downstream classifier mutation: **CLEAN** (all three reviewers
independently confirmed no `src/irc/` classifier reads the new fields;
`test_population_is_inert_classify_valuation_byte_identical` locks it).

## Decision
Zero unresolved blockers or latent correctness bugs in the shipped code (A1 fixed
pre-push). Remaining items are an accepted-by-precedent tech-debt note (TODOS) and
cosmetic nits → **PASS-WITH-NITS**.
