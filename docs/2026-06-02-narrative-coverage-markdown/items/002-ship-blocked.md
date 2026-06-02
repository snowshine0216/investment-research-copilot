# 002 — /ship pre-landing review findings (pre-push)

Source: /ship steps 8+9 (pr-review-toolkit:code-reviewer + silent-failure-hunter + adversarial).

## Adversarial P0 — REFUTED (verified against code, not fixed)
The adversarial reviewer claimed a `cn_etf` row with `instr=None` (routine for holdings-look-through shortlists) resolves to `broad_index`/empty `provider_symbol` → `snapshot=None` → false-positive `intact` thesis verdict.
**Refuted by code:** in the table-fallback (`states.py:552-559`), `thesis_gaps = ("missing_constituent_snapshot", "news_stage_skipped"[, "constituent_missing"])`. `EXPECTED_OMISSION_CODES = {"constituent_not_applicable"}` only, so those gaps are NOT filtered → `evidence_gaps` is non-empty → `derive_position_risk_level` (risk.py:60) returns `"insufficient"`. The narrative verdict is correctly insufficient. This path is pre-existing and unchanged by item 002 (analyze_fund passed `None` for passive pre-002 too). No fix needed; recorded for provenance.

## P0/P1 to fix before push
1. **Layer inversion (code-reviewer P0).** `src/irc/narrative/analyze.py` imports `_load_latest_nav_cached` from `src/irc/commands/opportunity_cmd.py` — a domain stage package importing from the commands/ I-O layer (inverts dependency; CLAUDE.md: stage cores stay pure, I/O utils live at the edges). FIX: move `_load_latest_nav_cached` to `src/irc/fundamentals/snapshot_cache.py` (alongside `load_active_fund_cache`/`load_nav_cache`); update importers in `opportunity_cmd.py`, `narrative_autobuild.py`, `analyze.py`. Run an import-cycle check after.
2. **`_QDII_KINDS` duplicated (code-reviewer P1).** Defined verbatim in both `narrative_autobuild.py` and `analyze.py` — divergence hazard. FIX: define once (in `src/irc/opportunity/lookthrough.py`, which already owns the QDII key logic, exporting a `QDII_KINDS` constant) and import in both.
3. **Silent degrade — no log (silent-failure P0/P1).**
   - `_build_and_cache_fund_level_one`: bare `return` when `build_snapshot` yields a non-`FundLevelSnapshot` — add `_log.warning` naming the actual type + symbol.
   - `_load_snapshot_for_row` (analyze.py): returns `None` with no log when a row HAS a `provider_symbol` but no cache — add `_log.debug`/`_log.warning` so a disk/permission read error (which `load_nav_cache` swallows to `None`) is distinguishable from a legitimate cache miss.
4. **Missing test.** Add a unit test for `_load_snapshot_for_row` returning `None` when `target.provider_symbol` is absent (the silent-miss → insufficient branch).

## Noted, intentionally NOT changed
- Dead-ish `except FetchBudgetExceeded: raise` guard in `_build_and_cache_fund_level_one`: kept for SYMMETRY with `_build_and_cache_one` (active, item 001) + as defensive code; add a one-line comment that budget enforcement is pre-flight only.
- `con` forwarded-but-unused param: documented signature-parity choice (grill RD); leave.
- narrative_autobuild.py 251 lines: accepted soft-overage (drift NOTE); functions all <20 lines; cohesive.
