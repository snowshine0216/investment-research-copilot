Verdict: PASS

Subagent: sonnet

## Source

- Branch confirmed: `claude/review-followup-005` (`git branch --show-current`).
- Spec: `docs/2026-07-07-review-followup/items/005-spec.md` (AC1–AC6 + Resolved decisions Q1–Q7).
- Implementation: `src/irc/rotation/seed.py::seed_stock_board_map` (lines 73–112), commits
  `a7bfeeed` (core fix), `66856c7a` (fixture align), `77426054` (ship-review hardenings:
  chunk_size=0 guard + unresolved-symbol warning).
- Store contract: `src/irc/monitor/industry_map_store.py` (`load_store`, `record_seen`,
  `merge_seen`, `fresh_slice`, `MAX_AGE_DAYS = 30`) — unchanged by this item.

## Entry point exercised

Per dispatch instructions, network is unavailable and the real data file must not be
touched, so the REQUIRED entry point is a from-scratch scratchpad script
(`/private/tmp/.../scratchpad/verify_005.py`, ~150 lines, written this dispatch) that calls
the **real** public functions directly — `record_seen`, `load_store` (from
`irc.monitor.industry_map_store`) and `seed_stock_board_map` (from `irc.rotation.seed`) — with
a tmp-dir map file. The only faked boundary is `batch_fetch`, which in production wraps the
AkShare `ulist.np` network call; that is the one true external I/O edge and stubbing it is
consistent with "effects at edges" (CLAUDE.md). This is not an isolated unit-test-style
import-and-call of one function — it is the real `record_seen → seed_stock_board_map →
load_store` round trip across two modules, matching how `rotation_cmd.py` wires them in
production (`load_existing=load_store, record=record_seen`).

Full script output is reproduced below (captured verbatim from this dispatch's run,
`uv run python .../verify_005.py`):

```
========== 2a: seed store via real record_seen (production shape: 行业 names) ==========
pre-seed store: {'000651': {'industry': '家电行业', 'seen_at': '2026-05-02'}, '300750': {'industry': '电池行业', 'seen_at': '2026-07-05'}, '600519': {'industry': '酿酒行业', 'seen_at': '2026-07-02'}, '601318': {'industry': '保险行业', 'seen_at': '2026-04-08'}}

========== 2b: run real seed_stock_board_map against it ==========
requested symbols: ['000002', '000651', '601318']
summary: {'done': 3, 'skipped': 2, 'failed': ()}

========== 2c: assertions — stale+never-seen requested, fresh not, seen_at bumped, counts truthful ==========
[PASS] stale 000651 (66d) IS requested
[PASS] stale 601318 (90d) IS requested
[PASS] never-seen 000002 IS requested
[PASS] fresh 600519 (5d) NOT requested
[PASS] fresh 300750 (2d) NOT requested
post-seed store: {'000002': {'industry': '测试行业', 'seen_at': '2026-07-07'}, '000651': {'industry': '测试行业', 'seen_at': '2026-07-07'}, '300750': {'industry': '电池行业', 'seen_at': '2026-07-05'}, '600519': {'industry': '酿酒行业', 'seen_at': '2026-07-02'}, '601318': {'industry': '测试行业', 'seen_at': '2026-07-07'}}
[PASS] 000651 seen_at bumped to today
[PASS] 601318 seen_at bumped to today
[PASS] 000002 seen_at written as today
[PASS] 600519 (fresh) seen_at UNCHANGED
[PASS] 300750 (fresh) seen_at UNCHANGED
[PASS] summary['skipped']==2 (got 2)
[PASS] summary['done']==3 (got 3)
[PASS] summary['failed']==() (got ())

========== 2d-i: chunk_size=0 does not crash; degrades to 1-symbol chunks ==========
chunk_size=0 chunks: [('A1',), ('A2',), ('A3',)] summary: {'done': 3, 'skipped': 0, 'failed': ()}
[PASS] chunk_size=0 degrades to three 1-symbol chunks
[PASS] chunk_size=0 run: all 3 done

========== 2d-ii: blank industry in a chunk -> exactly one 'unresolved' warning log line ==========
captured warning records: ["seed_stock_board_map: 1 symbol(s) unresolved after batch_fetch (missing/blank industry); sample=['B2']"]
summary3: {'done': 2, 'skipped': 0, 'failed': ()}
[PASS] exactly one 'unresolved' warning line (got 1)
[PASS] warning message names the blank symbol B2
[PASS] summary3 done==2 (B1, B3 resolved; B2 unresolved)

========== RESULT ==========
ALL CHECKS PASSED
```

The real `data/monitor/stock_industry_map.json` was verified untouched before and after
(`git status --porcelain data/monitor/stock_industry_map.json` → empty; `git diff --stat` →
empty) — only the tmp-dir copy created by the script was written.

## Observed behavior per acceptance criterion

- **AC1 — the one-line fix.** Read `src/irc/rotation/seed.py:89-93`:
  `from irc.monitor.industry_map_store import fresh_slice` (function-local, line 89),
  `fresh = set(fresh_slice(existing, today))` (line 92, default `max_age_days` — no new
  parameter added to `seed_stock_board_map`'s signature, confirmed by reading the full
  signature at lines 73-82). `summary["skipped"] == len(fresh)` at line 112. My round-trip
  §2c confirms `summary['skipped']==2` matches exactly the two genuinely-fresh entries
  (600519, 300750), not the 4 originally-present entries. **PASS.**
- **AC2 — stale re-fetched, fresh still skipped (TDD, red-first).**
  `tests/rotation/test_seed.py::test_seed_stock_board_map_refetches_stale_skips_fresh` (lines
  136-164) drives a production-shaped store (`"酿酒行业"`/`"家电行业"` in the `industry`
  slot, not `"BK1"`). I independently reproduced RED: checked out `seed.py` at `a7bfeeed~1`
  (pre-fix) into the working tree, ran
  `uv run pytest tests/rotation/test_seed.py -q -k "refetches_stale or roundtrip_refreshes"`
  → `2 failed` (`AssertionError: assert '2026-05-01' == '2026-07-06'` and the stale-not-in-
  fetched-list assertion), restored the current file (`git status --porcelain` empty after,
  confirming byte-identical restore), then re-ran the same command against current code →
  `2 passed`. My own scratchpad round-trip (§2c) additionally confirms this with fresh
  fixtures of my own construction (two stale + two fresh + one never-seen), not reused from
  the test file. **PASS.**
- **AC3 — a seed run refreshes `seen_at` on re-fetched entries (integration-shaped).**
  `tests/rotation/test_seed.py::test_seed_stock_board_map_roundtrip_refreshes_stale_seen_at`
  (lines 167-196) uses the real `load_store`/`record_seen` round-trip against a `tmp_path`
  file — confirmed passing above. My own script independently reproduces this against a
  *different* tmp store with 4 pre-seeded rows (2 stale, 2 fresh) rather than the test's 2,
  and confirms via the real `load_store(map_path)` after the run: stale rows'
  `seen_at == "2026-07-07"` (today), fresh rows' `seen_at` unchanged at their original dates.
  **PASS.**
- **AC4 — docstring truthful.** `src/irc/rotation/seed.py:83-88` reads: "skip symbols still
  FRESH (seen_at ≤ 30 calendar days per fresh_slice) in the map. STALE entries (seen_at > 30
  calendar days) fall out of the skip-set and are re-fetched, so record(...)'s REFRESH-ON-SEEN
  bumps their seen_at back to today and exposure coverage self-heals (on re-seed)." Grepped
  the file for the old wording ("already present in the map") — zero hits; only the new
  "still FRESH"/"STALE entries" phrasing is present. Matches the store's real semantics
  exactly as exercised in §2c. **PASS.**
- **AC5 — no version bump.** `git diff $(git merge-base main HEAD)..HEAD --stat` (this
  dispatch) shows `src/irc/rotation/types.py` is **not** in the changed-file list; read
  `types.py:58-59` directly — `schema_version: int` / `radar_version: int` fields present,
  unchanged. `VERSION` file reads `0.9.3` and is not in the diff's changed-file list either
  (CHANGELOG accumulates under `[Unreleased]` per the project's locked versioning
  convention). **PASS.**
- **AC6 — TDD + budgets + per-file pytest.** Red→green reproduced independently above (not
  merely trusted from `005-drift.md`). Ran per-file only, never the whole `tests/commands/`
  dir: `uv run pytest tests/rotation/test_seed.py -v` → **9 passed** (all seed tests,
  including the two review-hardening regression tests
  `test_seed_stock_board_map_chunk_size_zero_does_not_crash` and
  `test_seed_stock_board_map_warns_once_on_unresolved_symbols`);
  `uv run pytest tests/monitor/test_industry_map_store.py -q` → **11 passed** (adjacent
  suite, untouched by this item, still green). `uv run ruff check src/irc/rotation/seed.py`
  → `All checks passed!`. File size: `seed.py` is 112 lines (< 200, budget met). Function-size
  note (not a fail): `seed_stock_board_map` is 40 lines end-to-end (73-112) — above the
  CLAUDE.md "ideal ≤20 lines" guideline, but the item-005 core fix itself
  (commit `a7bfeeed`, isolated via `git show`) added only 4 net lines to the body (the
  function-local import + the `fresh_slice` substitution); the extra length comes from the
  two *ship-review-mandated* hardenings (chunk_size guard, unresolved-symbol warning) added
  in `77426054`, both independently re-verified live in §2d of my round-trip. Judged
  acceptable: AC6's line budget is a soft "ideal," not a hard gate, and CLAUDE.md's own
  process explicitly allows review-triggered follow-up commits.
- **Ship-review hardening 1 — chunk_size=0 guard.** `src/irc/rotation/seed.py:90`:
  `effective_chunk_size = max(1, chunk_size)`. My script §2d-i called
  `seed_stock_board_map(..., chunk_size=0)` with 3 symbols — no exception raised; observed
  chunks `[('A1',), ('A2',), ('A3',)]` (three 1-symbol chunks) and `summary2['done']==3`.
  **PASS.**
- **Ship-review hardening 2 — one warning on blank industry.** `src/irc/rotation/seed.py:105-
  111`: `unresolved` list collects requested symbols whose `industry_by_symbol.get(sym)` is
  falsy across *all* chunks, then a single `_log.warning(...)` fires once after the loop (not
  per-chunk). My script §2d-ii used a real `logging.Handler` attached to logger
  `"irc.rotation.seed"` (not `caplog`, to prove it works through the standard logging API,
  not just pytest's fixture) with a fake `batch_fetch` returning a blank string for symbol
  `B2` in a 3-symbol single chunk. Captured exactly **one** record containing "unresolved",
  message: `"seed_stock_board_map: 1 symbol(s) unresolved after batch_fetch (missing/blank
  industry); sample=['B2']"`; `summary3['done']==2` (B1, B3 resolved). **PASS.**

## Failures

None. 0 of 6 spec ACs failed; both ship-review hardenings re-verified live; 20/20 pytest
assertions across two per-file runs passed (9 + 11); my independent round-trip script
recorded 0 failed checks (`ALL CHECKS PASSED`); red→green reproduced myself, not trusted
from prior docs; real data file confirmed untouched throughout.
