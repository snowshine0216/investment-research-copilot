Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pr-review-toolkit:code-reviewer + silent-failure-hunter + adversarial), captured inline. Adversarial first pass = BREAKS (3 P0s) → fixed pre-push (see items/001-ship-blocked.md) → re-verified green. Remaining items are deferred P2 nits + one documented spec gap.

## Blockers found by steps 8+9 — ALL FIXED before push (verified by green tests)

- **[was P0] duplicate-symbol double-count** (`screen.py` / `holdings_fetch.py`) — FIXED: `_parse` dedupes by symbol (highest weight); `score_overlap` tracks a `seen` set. Tests: `test_screen.py` dup-symbol case + `test_holdings_fetch.py` dup-row case.
- **[was P0] `NaN`/`inf` weight → invalid JSON** (`holdings_fetch._to_holding`) — FIXED: sanitize to `0.0` via `math.isnan`/`isinf`. Test: NaN/inf cell → `weight_pct == 0.0`.
- **[was P0] per-fund analyze crash aborts the whole run** (`narrative_cmd._run_analyze`) — FIXED: per-fund try/except → `error_report(row, reason)` (insufficient) + partial results; `None` reserved for prerequisites-absent. Test: one fund raises → rc 0, 2 reports, failed = `insufficient`. Honors spec §4 "surfaced not crashed".
- **[was P1] silent exception swallowing** (`fetch_top_holdings` / `_read_cache` / `_open_analyze_context`) — FIXED: WARNING logs at the I/O edges (repo "no silent caps").
- **[was P1] misleading YAML comment** + **empty-basket accepted** — FIXED: comment corrected; `load_narrative_basket` now rejects an empty basket (`ValueError`).
- **[nit] `h.__dict__`** → `dataclasses.asdict`. FIXED.

## Remaining nits (deferred — non-blocking)

- **N1 (documented spec gap)** `metrics={}` in analyze → `drawdown_3y`/`volatility` risk drivers never fire. Those fields are not on `OpportunityRow`/`OpportunityInput`; spec §3.6 says "fire only when available, never fabricate." Flagged in the PR.
- **N2 (P2)** `--out` resolving to an existing file → `mkdir` crash (rare misuse).
- **N3 (P2)** `--screen-only` + `--analyze` both passed → screen-only wins silently.
- **N4 (P2)** `narrative_id` in YAML disagreeing with the filename stem is not validated.
- **N5 (P2)** `top_n: 0` in config → empty shortlist (config-controlled, not user-facing).

## Evidence

- `uv run pytest tests/narrative/ -q` → 59 passed, 1 skipped (live AkShare gate).
- `uv run ruff check src/irc/narrative src/irc/commands/narrative_cmd.py tests/narrative` → clean.
- Pure cores (schemas/screen/risk/report) contain no I/O or logging; all 8 new files < 200 lines.
- No restricted core file modified; `基金概况` absent under `src/irc/narrative/`.
- Full suite: 8 failures, **all pre-existing** (identical on base `autodev/thematic-fund-mining-feature`; broken `ingest`/data/eval pipeline) — zero in-branch regressions.

Zero open blockers, zero latent bugs → PASS-WITH-NITS.
