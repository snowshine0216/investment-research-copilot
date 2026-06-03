Verdict: PASS-WITH-NITS
Source: /ship steps 8+9 (pr-review-toolkit:code-reviewer + silent-failure-hunter + adversarial), with a pre-push fix round + re-review

## Summary
Initial pre-landing review surfaced 1 adversarial "P0" (REFUTED on inspection), a real layer-inversion P0, a _QDII_KINDS duplication, silent-degrade observability gaps, and a missing test. The refuted item needed no change; the rest were fixed before push (commits c98be90, d97b3e3). Re-review: P0 none, all 4 prior findings verified resolved, no circular import. Two cosmetic nits remain. Zero blockers, zero latent bugs.

## Findings → resolution
- **Adversarial "P0" — REFUTED (not a bug).** Claim: instr-absent `cn_etf` → `snapshot=None` → false `intact` verdict. Verified against code: table-fallback (states.py:552-559) stamps `missing_constituent_snapshot`/`news_stage_skipped`, which are NOT in `EXPECTED_OMISSION_CODES` → `evidence_gaps` non-empty → `derive_position_risk_level` returns `insufficient`. Correct verdict. Pre-existing path, unchanged by item 002. See items/002-ship-blocked.md.
- **P0 layer inversion (fixed, c98be90)** — `narrative/analyze.py` imported `_load_latest_nav_cached` from `commands/opportunity_cmd.py` (domain→commands inversion). Moved to `fundamentals/snapshot_cache.py` as `load_latest_nav_cached`; all importers repointed; `narrative/` now imports nothing from `commands/` (verified by grep). Bonus: removed the pre-existing `commands↔narrative` import cycle.
- **P1 _QDII_KINDS duplication (fixed, c98be90)** — centralized as `QDII_KINDS` in `opportunity/lookthrough.py`; both call sites import it.
- **P1 silent degrade (fixed, d97b3e3)** — `_log.warning` on non-FundLevelSnapshot build return; `_log.debug` on provider_symbol cache miss in `_load_snapshot_for_row`.
- **Missing test (fixed, d97b3e3)** — `test_load_snapshot_for_row_returns_none_when_no_provider_symbol`.

## Remaining nits (non-blocking)
- `_fund_level_eligible_target(con: object)` is accepted for documented signature parity but unused — clarity nit (control flow unaffected; grill RD-documented).
- New test imports placed mid-file with `# noqa: E402` (recurring style nit; ruff-clean). Cosmetic.

## Verification
- `uv run pytest tests/narrative tests/opportunity` → 588 passed, 4 skipped (pre-existing).
- import-cycle runtime check → OK; `dag_acyclic_check` False on BOTH base and branch (pre-existing cycle, NOT introduced by 002 — item 002 removed one cycle).
- `uv run ruff check` (touched files) → All checks passed.
- Re-review: code-reviewer P0=none.
