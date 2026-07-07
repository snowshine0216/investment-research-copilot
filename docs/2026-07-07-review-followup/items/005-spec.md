# Item 005 — Rotation seed skip-set freshness (review R-4)

Spec for autodev run `review-followup`. Ground truth: `docs/2026-07-07-workflow-review.md`
§2.1 R-4 + §3 Tier-1 #5 + §5. Locked scope: `BACKLOG.md` "Item 005". Effort: S. Kind: code
(bug fix). Ordered AFTER item 004 (already merged); the current post-004 code is the baseline.

## Goal

The `irc rotation seed` stock→board map builder skips **all** symbols already present in
`data/monitor/stock_industry_map.json`, ignoring their `seen_at` age
(`src/irc/rotation/seed.py:86-88`, current post-004 code):

```python
existing = load_existing(map_path)
fresh = set(existing.keys())        # BUG: every key, regardless of seen_at age
pending = [s for s in dict.fromkeys(symbols) if s not in fresh]
```

The variable is even named `fresh`, but it is the ALL-keys set. Meanwhile the daily
rotation join reads only the **fresh** slice — rows with `seen_at` within ≤30 calendar days
(`_cmd_helpers.resolve_candidates:122` → `industry_map_store.fresh_slice` /
`_within`, `industry_map_store.py:77-93`). This creates a **heal gap**: only the ~60 Monitor
symbols get their `seen_at` refreshed daily (via `irc monitor`'s `record_seen`); the other
~640 seeded mappings are never re-touched, so around **2026-08-05** they cross the 30-day
line and drop out of `fresh_slice`. Exposure coverage silently collapses, and because seed's
skip-set contains *every* key, **re-seeding skips the now-stale symbols forever** — the store
can only recover by being deleted. This is the exact "serve-while-stale then can-never-heal"
trap the review flags for ~2026-08-05.

**Fix (one line + tests):** seed's skip-set becomes the keys of `fresh_slice(existing,
today)` instead of all existing map keys. Stale (`seen_at` > 30 calendar days) entries fall
out of the skip-set and are re-fetched — which, via `record_seen`'s REFRESH-ON-SEEN
(`merge_seen`, `industry_map_store.py:65-74`), bumps their `seen_at` back to `today`. Fresh
entries stay skipped, so resumability / partial-tolerance is preserved. Board scoring, store
shape, and all version numbers are untouched.

## Acceptance criteria

- **AC1 — the one-line fix.** In `seed_stock_board_map` (`src/irc/rotation/seed.py`), the
  skip-set derives from `fresh_slice(existing, today)` (its keys), not `existing.keys()`.
  `fresh_slice` is called with its **default** `max_age_days` (=`MAX_AGE_DAYS`=30) so seed
  and the join stay in lockstep on one freshness window — no new age parameter is introduced
  on `seed_stock_board_map`. The `today` argument already present on the function is the
  freshness anchor. `summary["skipped"]` now counts genuinely-fresh skips (`len(fresh)` where
  `fresh` is the fresh-slice key set) — a stale entry is no longer reported as skipped.
- **AC2 — stale re-fetched, fresh still skipped (TDD, red-first).** A new test in
  `tests/rotation/test_seed.py` drives a **production-shaped** store — 行业 **names** in the
  `industry` slot, `{sym: {"industry": "<name>", "seen_at": "<date>"}}` (e.g.
  `"家电行业"`, `"酿酒行业"`; NOT `"BK1"`-in-industry, the 004-masking shape) — with one
  entry **stale** (`seen_at` > 30 calendar days before `today`) and one entry **fresh**
  (`seen_at` ≤ 30 days). It asserts the stale symbol IS re-fetched (appears in the symbols
  passed to `batch_fetch`) while the fresh symbol is NOT (skipped). It also asserts the
  pre-fix behavior — where the stale symbol would be skipped — so the freshness distinction
  is a permanent regression guard. This test **fails** against the current
  `set(existing.keys())` code (the stale symbol is wrongly skipped) and **passes** after AC1.
- **AC3 — a seed run refreshes `seen_at` on re-fetched entries (integration-shaped).** A
  second new test in `tests/rotation/test_seed.py` exercises the **real** store round-trip
  (`load_store`/`record_seen`/`merge_seen`, NOT fakes) against a tmp_path map file: pre-seed
  a stale entry (`record_seen(map_path, <stale_date>, {...})`) and a fresh entry, run
  `seed_stock_board_map(..., today=<today>, load_existing=load_store, record=record_seen,
  batch_fetch=<fake returning the 行业 name for the stale symbol>)`, then assert
  `load_store(map_path)[<stale_sym>]["seen_at"] == today` (refreshed) while the fresh
  symbol's `seen_at` is untouched. This proves the heal loop end-to-end: stale → re-fetched →
  `seen_at` bumped → back inside the join's fresh window.
- **AC4 — docstring truthful.** `seed_stock_board_map`'s docstring
  (`src/irc/rotation/seed.py:83-85`) no longer says "skip symbols already present in the
  map". Rewritten to: skip symbols still **FRESH** (`seen_at` ≤ 30 calendar days,
  `fresh_slice`) in the map; **STALE** entries fall out of the skip-set and are re-fetched so
  exposure coverage self-heals. (The 004 lesson: a false docstring is a defect.)
- **AC5 — no version bump.** No `radar_version` / `schema_version` change
  (`src/irc/rotation/types.py`); no `VERSION` bump. Board scoring, hysteresis states,
  composite, and the store file format are untouched (F7 / item-004 availability-class
  precedent — this is an L2 seed-side bug fix).
- **AC6 — TDD + budgets + per-file pytest.** Red → green → refactor: AC2 and AC3 fail before
  the fix and pass after (paste the red-then-green per-file output into the item verify
  notes as runtime proof). `seed.py` stays < 200 lines and the changed function ≤ ~20 lines.
  Tests run **per file** — `uv run pytest tests/rotation/test_seed.py` — **never** the whole
  `tests/commands/` directory (documented hang, FACTS.md). The existing seed / industry-map
  suites (`tests/rotation/test_seed.py`, `tests/monitor/test_industry_map_store.py`) stay
  green.

## Non-goals

- **No change to `fresh_slice` / `_within` / `MAX_AGE_DAYS`** — the 30-calendar-day window is
  the monitor-owned contract (`industry_map_store.py`); seed only *consumes* it. This item
  does not fork or parameterize the window.
- **No store-side change.** The store stays monitor-owned and 行业-name-based (item 004's
  locked decision); `record_seen`/`merge_seen`/`load_store` are unchanged.
- **No pruning of orphaned stale rows (R-6).** A stale entry for a symbol that has left every
  fund's holdings is not fetched (it's not in the seed's symbol input) and is not deleted; it
  simply falls out of `fresh_slice` at the join and is inert. Store pruning / snapshot-absent
  cleanup is R-6, a separate finding with its own `radar_version` decision.
- **No seed pacing / backoff / breaker (R-5), no pagination fix (R-3), no flow warm-up gate
  (R-2), no empty-holdings-cache fix (R-9).** Each is a distinct review finding, out of scope.
- **No new counter or richer summary shape.** `summary` keeps `{done, skipped, failed}`;
  `skipped` simply now means fresh-skipped. No separate "stale re-fetched" tally (YAGNI).
- **No candidates-join change (R-1).** That was item 004 (already merged); this item touches
  only the seed skip-set.
- **No `radar_version` / `schema_version` / `VERSION` bump.**

## Constraints (incl. locked decisions)

- **LOCKED — the fix:** seed's skip-set = `fresh_slice(existing, today)` keys, so stale
  (`seen_at` > 30 calendar days) entries are re-fetched while fresh entries are still skipped
  (resumability preserved).
- **LOCKED — acceptance MUST include:** (1) a test that a stale entry (> 30d `seen_at`) IS
  re-fetched by seed while a fresh entry is still skipped (AC2); (2) a test that a seed run
  refreshes `seen_at` on re-fetched entries (AC3); (3) per-file pytest only; production-shaped
  fixtures — 行业 names in the `industry` slot (the 004 lesson).
- **LOCKED — scope: one-line fix + tests.** Resist scope growth; anything adjacent (R-2/R-3/
  R-5/R-6/R-9) goes to Non-goals.
- **LOCKED — no `radar_version` bump; no `VERSION` bump.**
- **`fresh_slice` import site:** function-local import inside `seed_stock_board_map`
  (`from irc.monitor.industry_map_store import fresh_slice`), matching the sibling
  `_cmd_helpers.resolve_candidates` pattern that already imports from this store. Avoids any
  import-time coupling of the rotation package to the monitor store at module load.
  `fresh_slice` is a pure function, so this does not add an effect to the seed core; the
  effectful dependencies (`load_existing`, `batch_fetch`, `record`) remain injected.
- **Functional / immutable / effects-at-edges** per CLAUDE.md; the change is a pure
  substitution of the skip-set expression. Worker dispatches carry the literal line
  **"Calling the Agent tool is FORBIDDEN"**. CHANGELOG `[Unreleased]` accumulation, no VERSION
  bump.
- **Failure clock (context, encode in the plan's "why"):** ~60 Monitor symbols refresh
  daily; ~640 others expire ≈2026-08-05; exposure coverage then collapses and re-seeding
  skips them all forever (recovery impossible without deleting the store). This fix restores
  self-healing.

## Open questions resolved during brainstorming (auto-accepted; rationale recorded)

No user in the loop (autodev). Every recommendation below was auto-accepted and is recorded
here. The USER-LOCKED items (the one-line fix; the two required tests; per-file pytest;
production-shaped fixtures; no version bump) were not re-litigated — only their mechanics.

- **Q1 — How is `fresh_slice` reached from `seed.py`: module-top import, function-local
  import, or inject a new callable param?** → **Function-local import** inside
  `seed_stock_board_map`. Matches the existing `_cmd_helpers.resolve_candidates` convention
  (it already does `from irc.monitor.industry_map_store import fresh_slice, load_store`
  function-locally), keeps the rotation package from importing the monitor store at module
  load, and avoids adding a param for a pure deterministic function (no test value; more
  signature surface). Rejected: injecting a `fresh_keys` callable — over-engineering for a
  pure fn.
- **Q2 — Should seed take its own age window, or reuse the join's 30-day window?** →
  **Reuse, via `fresh_slice`'s default `max_age_days`.** Calling `fresh_slice(existing,
  today)` with no `max_age_days` guarantees seed and the daily join move together if the
  monitor ever retunes `MAX_AGE_DAYS`. A seed-local window would let the two drift and
  re-open a heal gap. No new parameter on `seed_stock_board_map`.
- **Q3 — Which store rows actually heal — all stale, or only stale-and-requested?** → **Only
  symbols present in the seed's `symbols` input AND stale** re-enter `pending`. That is
  correct: seed fetches only symbols it is asked about (the ~700 held symbols from
  `_held_symbols`). A stale row for a symbol no longer in any holding stays stale but is inert
  (dropped by `fresh_slice` at the join). Pruning such orphans is R-6 → Non-goal.
- **Q4 — Do the two required tests overlap; can they be one?** → **Keep them separate**, as
  the locked acceptance lists two. AC2 (skip-set membership) uses recording fakes to assert
  *which* symbols are re-fetched vs skipped; AC3 (integration) uses the **real**
  `load_store`/`record_seen` round-trip to assert `seen_at` is bumped on disk. Different
  surfaces, different failure modes — both warranted.
- **Q5 — Fate of the existing `test_seed_stock_board_map_skips_fresh_and_chunks` fixture,
  which puts `"BK1"` in the `industry` slot?** → **Align its `industry` value to a 行业 name**
  (e.g. `"半导体"`) as a zero-risk drive-by in the same file we are already editing. It still
  passes under the fix (its entry is `seen_at`=today → fresh → skipped), but `"BK1"`-in-slot
  is the exact 004-masking anti-pattern; leaving it while adding production-shaped tests next
  to it is inconsistent. Minor, string-only, no behavior change.
- **Q6 — Does `summary["skipped"]` semantics need a migration note?** → **No.** `skipped`
  keeps meaning "not fetched because already good"; after the fix "already good" = fresh
  rather than merely present. No consumer asserts the old all-keys count as a contract (the
  command-layer only prints the summary). No new field.
