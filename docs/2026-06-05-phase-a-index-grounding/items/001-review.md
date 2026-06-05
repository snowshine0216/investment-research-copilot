Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pr-review-toolkit:code-reviewer + silent-failure-hunter + general-purpose adversarial), diff base `claude/stupefied-banach-f1f037`. Raw findings: [`001-ship-blocked.md`](001-ship-blocked.md).

## Blocker / latent bugs: 0 remaining (1 found, fixed pre-push)

- **[FIXED] Latent — `replace_keys` cache-wipe (D8 hole)** — `src/irc/data/index_valuation_ingestor.py`. A legulegu frame carrying `市净率` (PB) but no usable `滚动市盈率` (PE-TTM) produced a non-empty history with `pe_ttm=None` for every row; it slipped past the `not hist.rows` guard, so `replace_keys=True` would DELETE good cached PE rows AND (because the table has `PRIMARY KEY (index_key, date)`) `INSERT OR REPLACE`-overwrite overlapping dates with `pe_ttm=None` — silently degrading grounding to NAV. Directly violated D8 ("a non-empty fetch is required before delete, so transient provider failures never wipe good cache").
  **Resolution:** commit `39dbf7f`. Guard added (scoped strictly to `replace_keys=True`, before both the DELETE-key list and the params emit): `if replace_keys and not any(p.pe_ttm is not None for p in hist.rows): continue`. TDD regression test `test_replace_keys_skips_key_when_fetch_lacks_pe_ttm` (red confirmed, then green). Sector append path (`replace_keys=False`) untouched.

## Should-fixes: addressed (commit `39dbf7f`)

- **Silent `_fetch_frame` swallow** — `akshare_index_valuation.py` `except Exception: return None` had no logging; a network blip was indistinguishable from "index not found". Added module logger + `_log.warning(..., exc_info=True)` before the `None` return (I/O-edge wrapper; behavior unchanged).
- **Dead speculative sweep (gate #4 graduation discovery)** — `tests/fundamentals/test_index_valuation_live.py` informational sweep called `fetch_cn_index_valuation(slug)`, which gates on the allowlist → always `None` for speculative slugs. Rewrote it to probe legulegu DIRECTLY (`_fetch_frame` + `_extract_latest_value` on `_SPECULATIVE_LEGULEGU_SYMBOL[slug]`), so the landing table is real. Still informational + double-gated; default run skips.

## Nits

- **[cleaned]** Unexercised spy in `tests/commands/test_ingest_cmd.py::test_broad_leg_iterates_allowlist_with_replace_keys` (monkeypatched but `run_ingest` never called) — removed the dead scaffolding; kept the literal allowlist assertion with a note that `replace_keys=True` wiring is verified by the drift check + live/integration path.
- **[note, no action]** `replace_keys` path has no nested-`BEGIN` guard — current callers autocommit, so no live trigger (P2).
- **[note, no action]** On a sector-leg exception `ak_counts["index_valuation_history"]` is not reset — informational count only, cosmetic (P2).

## Post-fix verification (this orchestrator)
- Guard inspected at `src/irc/data/index_valuation_ingestor.py` (before both destructive paths, scoped to replace mode).
- `uv run pytest tests/data/test_index_valuation_ingestor.py tests/fundamentals/test_akshare_index_valuation.py tests/fundamentals/test_index_valuation_live.py tests/commands/test_ingest_cmd.py -q` → exit 0, no failures (live tests skipped). ruff clean (per fix subagent).
