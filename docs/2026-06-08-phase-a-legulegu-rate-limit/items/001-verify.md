Verdict: PASS

Subagent: sonnet
Source: Fallback used: manual offline checks (criteria 1–5 via Bash + Read tools)
Entry point exercised: `uv run irc --help` (exit 0, 20 commands listed); `uv run python -c "from irc.fundamentals.legulegu_fetch import fetch_legulegu_frame, LeguleguCooldownExhausted, _is_throttle_signature, _is_network_transient; print('ok')"` (exit 0, printed "ok")

Observed behavior:
  - **Criterion 1 — CLI imports cleanly:** `uv run irc --help` → exit 0, lists all 20 commands including `ingest`, `fundamentals`, `run` — no import errors from the new module.
  - **Criterion 2 — New module public surface:** `from irc.fundamentals.legulegu_fetch import fetch_legulegu_frame, LeguleguCooldownExhausted, _is_throttle_signature, _is_network_transient` → exit 0, printed "ok".
  - **Criterion 3 — Targeted offline test suites:** `uv run pytest tests/fundamentals/test_legulegu_fetch.py tests/fundamentals/test_akshare_index_valuation.py tests/fundamentals/test_provider.py tests/data/test_index_valuation_ingestor.py tests/commands/test_ingest_index_valuation_wiring.py tests/fundamentals/test_index_valuation_live.py -q` → **88 passed, 5 skipped** in 0.46 s. The 5 skips are the live-gated tests (CORRECT — requires `IRC_RUN_LIVE_AKSHARE=1` + `IRC_RUN_LEGULEGU_SPECULATIVE=1`; no network touched).
  - **Criterion 4 — ruff clean on changed files:** `uv run ruff check <9 changed .py files>` → "All checks passed!" (exit 0). Changed files: `src/irc/data/index_valuation_ingestor.py`, `src/irc/fundamentals/akshare_index_valuation.py`, `src/irc/fundamentals/legulegu_fetch.py`, and 6 test files.
  - **Criterion 5 — Behavioral spot-checks (via passing tests as evidence):**
    - **Paced dual-policy retry:** `test_network_success_on_third_attempt` asserts sleeps `[4.0, 3.0, 4.0, 6.0, 4.0]` (GAP before every attempt + exponential backoff); `test_throttle_success_on_retry` asserts sleeps `[4.0, 30.0, 4.0]` (GAP + cooldown + GAP). Both PASSED.
    - **Raise/catch asymmetry (`_history` propagates, `fetch_cn_index_valuation` catches → None):** grep on `akshare_index_valuation.py` confirms `fetch_cn_index_valuation_history` (line 161) calls `fetch_legulegu_frame` and does NOT catch `LeguleguCooldownExhausted`; `fetch_cn_index_valuation` (line 246) wraps in `try/except LeguleguCooldownExhausted` → returns None. Confirmed by `test_ingest_wiring` (propagation path) and `test_provider.py` (never-raises contract) — all PASSED.
    - **Both-axes PB-wipe guard:** `test_replace_keys_skips_key_when_fetch_lacks_pe_ttm` (PB-only → 0 rows, cache untouched) and `test_replace_keys_skips_key_when_fetch_lacks_pb` (PE-only → 0 rows, cache untouched) — both PASSED.
    - **Sweep suspension:** `test_cooldown_exhausted_suspends_sweep_and_writes_what_landed` confirms `fetched == ["csi1000", "csi300"]` (stops at trip key; csi500/sse50 never fetched), `written == 1` (csi1000 still persisted) — PASSED.
    - **Tested WARNING contracts:** `test_cooldown_suspension_logs_trip_key_and_skipped_keys` asserts `"suspending broad-leg sweep"` + trip key (`csi300`) + skipped keys (`csi500`, `sse50`) + `"cache preserved"`. `test_replace_skip_missing_axis_logs_warning` asserts `"replace skipped"` + key + missing axis (`pe`) + `"cache preserved"` — both PASSED.
    - **Throttle exhaust raises:** `test_throttle_exhausts_raises` confirms `pytest.raises(LeguleguCooldownExhausted)` after exactly 2 attempts, sleeps `[4.0, 30.0, 4.0]`, no second cooldown retry — PASSED.
    - **Gate-1 wiring repair (D8):** `test_ingest_index_valuation_wiring.py` now asserts `_LEGULEGU_INDEX_SYMBOL` + `replace_keys=True` (replaced the previously-red `_BROAD_INDEX_KEYS` assertions) — 4 wiring tests PASSED.

Deferred to operator (live network): gates #3/#4/#5 — deep cooldown is active; do NOT run until limiter recovers.
  - Gate #4 (cold window): `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/fundamentals/test_index_valuation_live.py -v -s -x`
  - Gate #3 (cold window after gate #4): `uv run irc run --from ingest` then `python count_grounded.py outputs/<date>/opportunity_report.json`
  - Gate #5 (cold window after gate #3): see `docs/2026-06-05-phase-a-broad-grounding/before-after.md` steps 1–5.
  - Speculative sweep (separate cold window): `IRC_RUN_LIVE_AKSHARE=1 IRC_RUN_LEGULEGU_SPECULATIVE=1 uv run pytest -m live_akshare tests/fundamentals/test_index_valuation_live.py -v -s`

Failures: none
