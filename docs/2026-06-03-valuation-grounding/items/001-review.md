Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial review), orchestrator-dispatched (model=sonnet) — pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose adversarial.

All blocker/latent findings were fixed BEFORE the PR was pushed (ship.md "/ship review can demand fixes before push"). The remaining items are documented nits/deferred-debt, hence PASS-WITH-NITS.

## Findings & resolution

### Blocker (fixed pre-push)
- **P0 — stale fundamental percentile when latest cached row is NULL.**
  `inputs_loader.py::_index_valuation_metrics`: when the latest `index_valuation_history`
  row had a NULL `pe_ttm`/`pb`, `pe`/`pb` was correctly `None` but `pe_pct`/`pb_pct` was
  still computed over prior non-null rows → a stale, non-None `valuation_percentile_fundamental`
  silently drove `classify_valuation`. **Fixed** (commit `0a4f722`): `pe_pct = self_history_percentile(...) if pe is not None else None` (same for pb), with a new TDD test
  (`test_populate_inputs_null_latest_pe_pb_yields_none_percentile`).

### Latent (fixed pre-push)
- **P1 — vacuous AC2 regression lock.** `test_fundamental_none_falls_back_to_nav_byte_for_byte`
  asserted `"PE" not in reason or "PE 百分位" not in reason` — an always-true OR. The single
  most important regression lock (NAV fallback must not leak the fundamental label) was toothless.
  **Fixed** (commit `9de68c1`): strengthened to `"PE 百分位" not in reason`; still passes
  (no real leak).
- **P1 — R3 regression mis-flagged as pre-existing.** Two ADR-0010 migration locks
  (`test_provider_migration.py::test_index_metrics_via_provider_matches_pre_migration`,
  `::test_index_metrics_unknown_key_does_not_call_ak`) PASS on base but FAILED on branch
  (TypeError) because R3 changed `_index_valuation_metrics` from a provider call to a cached
  read. **Fixed** (commit retire-locks): obsolete locks retired; cached-read covered by
  `test_inputs_loader.py`; `provider.fetch_index_valuation` keeps coverage in `test_provider.py`
  (R4). Drift verdict corrected with an honest note.

### Nits / hardening (fixed pre-push)
- **P1 — ingestor missing explicit transaction.** `index_valuation_ingestor.py` now wraps
  `executemany` in `BEGIN/COMMIT/ROLLBACK`, matching `fund_holdings_ingestor.py` (commit `1ced924`).
- **P1 — dead outer try/except + lost traceback.** Removed the redundant outer `try/except` in
  `fetch_cn_index_valuation_history` (it masked programmer errors; `_fetch_frame` already
  degrades); added `exc_info=True` to the best-effort ingest warning in `ingest_cmd.py`
  (commit `118e1c6`).

### Deferred (documented, not fixed — out of Phase-1 scope)
- **P1-C — stale-cache served without an age signal.** Pipeline-wide cached-evidence property
  (prices/nav/holdings/macro all share it), not specific to this table; a per-table expiry here
  would be inconsistent with the architecture. Logged to `TODOS.md` (Reliability section,
  `valuation-grounding-001 ship silent-failure review 2026-06-03`).

## Clean confirmations (from the three reviewers)
- Units correct: `real_yield_10y = cn_10y_yield/100` and `earnings_yield = 1/pe_ttm` both ratios;
  `expected_real_return_positive` dimensionally consistent; `real_yield_10y_tips` never reused (R1).
- Divergence code routes to `advisory_gaps`, never `evidence_gaps` (R2/H3); verified by test and
  by adversarial construction (no input reaches `evidence_gaps`).
- `pe_ttm <= 0` guarded; all-None / `<30`-point series degrade cleanly to NAV fallback (AC2/AC9).
- `f"{...:.0%}"` formats in the divergence note are reachable only when both percentiles are
  non-None (no None-format crash).
- Adversarial verdict: RISKS (no P0 crash / silent-wrong-verdict after fixes).
- risk.py + provider.py byte-identical to base (AC8/AC7/R4).
