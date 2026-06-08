Verdict: PASS

Subagent: sonnet
Plan checklist items: 8 tasks (Tasks 1–8, each with 2–8 steps)
Verified present in diff: all 8 tasks fully implemented

---

## Verification details

### Task 1 — New `legulegu_fetch.py` primitive

- `src/irc/fundamentals/legulegu_fetch.py` created (124 lines, matches plan spec exactly).
- Constants present at correct values: `_LEGULEGU_GAP_S=4.0`, `_LEGULEGU_NETWORK_ATTEMPTS=3`,
  `_LEGULEGU_BACKOFF_S=3.0`, `_LEGULEGU_COOLDOWN_S=30.0`, `_LEGULEGU_COOLDOWN_RETRIES=1`.
- `LeguleguCooldownExhausted` exception defined.
- `_is_throttle_signature`: checks `AttributeError` carrying BOTH `'NoneType'` AND `'attrs'`;
  checks `isinstance(exc, (json.JSONDecodeError, requests.exceptions.JSONDecodeError))` — the
  documented deviation (plan §Verified facts, judgment call #2) — correctly implemented.
- `_is_network_transient`: delegates to `_is_transient_network_error` then adds
  `requests.exceptions.ConnectionError` / `Timeout` explicitly (plan §Verified facts judgment call #1).
- `fetch_legulegu_frame`: `_sleep` module-level indirection present; `ak_call` injected parameter.
- `tests/fundamentals/test_legulegu_fetch.py` created with all plan-specified tests.
- All 4 sleep-sequence assertions match plan exactly:
  - network-success-on-3rd: `[4.0, 3.0, 4.0, 6.0, 4.0]` ✓
  - network-exhaust → None: `[4.0, 3.0, 4.0, 6.0, 4.0]` ✓
  - throttle-success-on-retry: `[4.0, 30.0, 4.0]` ✓
  - throttle-exhaust → raises: `[4.0, 30.0, 4.0]` then `LeguleguCooldownExhausted` ✓
- Commit: `3373b0b`

### Task 2 — Route 4 legulegu calls through `fetch_legulegu_frame`

- `akshare_index_valuation.py` docstring replaced to scope never-raises to
  `fetch_cn_index_valuation` / sector path; ADR 0014 D3 carve-out for `_history` documented. ✓
- Import of `LeguleguCooldownExhausted`, `fetch_legulegu_frame` added after the
  `index_valuation_types` import block. ✓
- `fetch_cn_index_valuation_history`: both `_fetch_frame` legulegu calls replaced by
  `fetch_legulegu_frame(_ak_call, ...)` with no try/except (propagates). ✓
- `fetch_cn_index_valuation`: both `_fetch_frame` legulegu calls replaced inside a
  `try/except LeguleguCooldownExhausted: return None` block (never-raises seam). ✓
- csindex sector call (`stock_zh_index_value_csindex`) unchanged on `_fetch_frame`. ✓
- `tests/fundamentals/test_akshare_index_valuation.py`: `_no_legulegu_sleep` autouse fixture
  added at top; 5 routing-pin + asymmetry tests appended. ✓
- Commits: `e998fbf` (implementation) — fixture + tests committed together.

### Task 3 — Provider-seam no-sleep fixture

- `tests/fundamentals/test_provider.py`: `import pytest` + `_no_legulegu_sleep` autouse
  fixture inserted after the existing imports block. ✓
- Note: `import pytest` appears after the stdlib/third-party imports (not at top of file) but
  ruff reports clean (`All checks passed`) — accepted as incidental style, no functional impact.
- Commit: `66a3e84`

### Task 4 — Ingestor both-axes guard + sweep suspension

- `src/irc/data/index_valuation_ingestor.py`: `import logging` added; `_log` defined. ✓
- `LeguleguCooldownExhausted` imported from `irc.fundamentals.legulegu_fetch`. ✓
- Loop body replaced with `for i, key in enumerate(index_keys)`: try/except
  `LeguleguCooldownExhausted` → WARNING + `break`. ✓
- WARNING message contains: trip key, `"suspending broad-leg sweep"`, count of skipped,
  skipped-key list (`, ".join(skipped)`), `"cache preserved"`. ✓
- Both-axes guard (`has_pe and has_pb`): replaces the old PE-only guard. ✓
- WARNING on skip contains: `"replace skipped"`, key, `"pe"` or `"pb"` (missing axis),
  `"cache preserved"`. ✓
- 4 new tests added to `tests/data/test_index_valuation_ingestor.py` matching plan spec. ✓
- Commits: `e7b1a5b` (implementation) + `ff4e61d` (orchestrator lint fix — imports hoisted to
  top of test file to satisfy ruff E402/F401; accepted incidental cleanup, noted in PROGRESS.md).

### Task 5 — Repair gate-1 wiring tests

- `tests/commands/test_ingest_index_valuation_wiring.py`: both RED tests repaired. ✓
  - `test_run_ingest_calls_index_valuation_ingestor`: asserts `_LEGULEGU_INDEX_SYMBOL` and
    `replace_keys=True` (not removed `_BROAD_INDEX_KEYS`). ✓
  - `test_ingest_cmd_imports_broad_index_keys_and_ingestor`: asserts `_LEGULEGU_INDEX_SYMBOL`. ✓
- Commit: `42635ee`

### Task 6 — Live-test speculative sweep gating (source edit only)

- `tests/fundamentals/test_index_valuation_live.py`: `_fetch_frame` import removed; `_ak_call`
  and `fetch_legulegu_frame` imports added. ✓
- `test_speculative_symbol_landing_sweep_informational`: `@pytest.mark.skipif` guard added on
  `IRC_RUN_LEGULEGU_SPECULATIVE != "1"`. ✓
- Speculative sweep body uses `fetch_legulegu_frame(_ak_call, ...)` instead of `_fetch_frame`. ✓
- File NOT executed (source edit only, as required). ✓
- Commit: `510dc24`

### Task 7 — CHANGELOG `[Unreleased]` sub-bullet

- `CHANGELOG.md`: `### Added — Phase A legulegu broad-leg rate-limit hardening (2026-06-08)`
  sub-section inserted under `[Unreleased]`, text matches plan spec. ✓
- `VERSION` unchanged at `0.9.3`. ✓
- Commit: `47fd986`

### Task 8 — Full offline verification gate

- PROGRESS.md (commit `9977218`) records: 88 passed / 5 skipped (live-gated), ruff clean on
  changed files, VERSION 0.9.3, raise/catch asymmetry intact. ✓

---

## Drift findings

None. All plan steps are present in the diff and match intent.

Incidental changes (accepted):
- `ff4e61d` — orchestrator hoisted mid-file imports (`import logging`,
  `from irc.fundamentals.legulegu_fetch import LeguleguCooldownExhausted`) to the top of
  `tests/data/test_index_valuation_ingestor.py` to satisfy ruff E402/F401. Not flagged in the
  plan's implementer commit (`e7b1a5b`) but applied as a separate orchestrator lint-fix commit.
  Noted in PROGRESS.md as an accepted cleanup.
- `import pytest` placement in `tests/fundamentals/test_provider.py` is after the third-party
  block rather than at the very top; ruff passes clean so no action required.
- PROGRESS.md status-row update (`9977218`) — bookkeeping, not scope creep.
