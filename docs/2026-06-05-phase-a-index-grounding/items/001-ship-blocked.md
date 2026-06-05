# Ship steps 8+9 review — findings (pre-push)

Source: /ship steps 8+9 — three parallel reviewers (pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose adversarial). Diff base: `claude/stupefied-banach-f1f037`.

## Confirmed correct (no action)
- **D1**: single-candidate `(_LEGULEGU_PE_TTM_COL,)` tuple cannot fall back to 静态市盈率 — absent column → None. ✓
- **D2**: production fetch gates on `_LEGULEGU_INDEX_SYMBOL` (4 keys); speculative map never consulted. ✓
- **D8 ROLLBACK**: DELETE+INSERT inside one BEGIN/COMMIT; executemany failure → ROLLBACK restores rows; outer `except` logs exc_info. ✓
- Index codes 创业板指→399006, 创业板50→399673, 中证红利低波→930740 verified (last preserves a pre-existing code). ✓
- Slug inversion collision-free (14 unique lowercased keys). Seed overrides yield tracked_index=None. ✓

## LATENT BUG (must fix) — partial-column cache wipe (adversarial P1)
`src/irc/data/index_valuation_ingestor.py` replace path. A legulegu frame with `市净率` present but `滚动市盈率` absent/misnamed yields `hist.rows` non-empty with `pe_ttm=None` for every row. The `not hist.rows` guard does NOT skip it → with `replace_keys=True` the key's existing good PE rows are DELETEd (and/or `INSERT OR REPLACE`-overwritten on overlapping dates) with `pe_ttm=None`. Permanently degrades grounding to NAV until the next clean fetch. Directly violates D8's "non-empty fetch required before delete, so transient provider failures never wipe good cache." No test covers it.
**Fix:** in replace mode, treat a fetch lacking the primary PE-TTM leg as a (partial) failure — skip the key entirely so cache survives. Guard: only mark a key for replace AND emit its params when `any(p.pe_ttm is not None for p in hist.rows)`. Scope strictly to `replace_keys=True` (sector append path unchanged). TDD: stale non-None-PE rows + fresh PB-only(None-PE) fetch + replace_keys=True → assert stale rows preserved, written==0.

## SHOULD-FIX #1 — `_fetch_frame` silent swallow (silent-failure-hunter P1)
`src/irc/fundamentals/akshare_index_valuation.py` `_fetch_frame` `except Exception: return None` with no log. A network timeout is indistinguishable from "index not found."
**Fix:** log WARNING with exc_info before `return None` (use/add module logger; this is an I/O-edge wrapper, logging is appropriate observability).

## SHOULD-FIX #2 — dead speculative sweep probe (code-reviewer P1)
`tests/fundamentals/test_index_valuation_live.py::test_speculative_symbol_landing_sweep_informational` calls `fetch_cn_index_valuation(slug)`, which gates on the allowlist → always None for speculative slugs. The gate-#4 graduation-discovery sweep can therefore never "land" a symbol.
**Fix:** probe legulegu DIRECTLY for the speculative Chinese symbol (bypass the allowlist gate) via `_fetch_frame("stock_index_pe_lg"/"stock_index_pb_lg", _SPECULATIVE_LEGULEGU_SYMBOL[slug])` + `_extract_latest_value(..., (_LEGULEGU_PE_TTM_COL,))` so the landing table is real.

## NIT (cleanup) — unexercised spy
`tests/commands/test_ingest_cmd.py::test_broad_leg_iterates_allowlist_with_replace_keys` monkeypatches a spy but never calls `run_ingest`; spy assertions are dead. Trim the dead spy/monkeypatch; keep the literal allowlist assertion with a comment that replace_keys=True wiring is covered by the drift check + live/integration path.

## NOTES (no action this PR)
- Nested-BEGIN: replace path has no guard if `con` already in a transaction; current callers autocommit (P2, no trigger).
- Sector-leg exception does not reset `ak_counts["index_valuation_history"]` (P2 cosmetic).
