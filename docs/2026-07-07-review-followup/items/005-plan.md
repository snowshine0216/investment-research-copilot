# Item 005 — Rotation seed skip-set freshness (review R-4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `irc rotation seed`'s stock→board map builder must skip only symbols still FRESH (`seen_at` ≤ 30 calendar days) in `data/monitor/stock_industry_map.json`, so STALE entries fall back into the re-fetch set and self-heal — instead of the current bug that skips **every** existing key and can never recover once entries age out.

**Architecture:** One-line skip-set substitution in `seed_stock_board_map` (`src/irc/rotation/seed.py`): `set(existing.keys())` → `set(fresh_slice(existing, today))`, reached via a function-local `from irc.monitor.industry_map_store import fresh_slice` (matching the `_cmd_helpers.resolve_candidates` precedent at `_cmd_helpers.py:110`). `fresh_slice` is a pure function called with its **default** `max_age_days` (=`MAX_AGE_DAYS`=30) so seed and the daily join share one freshness window. Two new tests + a docstring rewrite + a legacy-fixture alignment + a CHANGELOG entry. No behavior beyond the skip-set changes; store shape, board scoring, and all version numbers are untouched.

**Tech Stack:** Python 3.12, uv, pytest. Pure/immutable stage core; effects (`load_existing`, `batch_fetch`, `record`) stay injected.

## Global Constraints

Copied verbatim from `005-spec.md` — every task's requirements implicitly include these:

- **Skip-set fix (LOCKED):** seed's skip-set = keys of `fresh_slice(existing, today)`, NOT `existing.keys()`. Call `fresh_slice(existing, today)` with **no** `max_age_days` arg (default 30). Do **not** add an age parameter to `seed_stock_board_map`.
- **Import site (LOCKED):** function-local `from irc.monitor.industry_map_store import fresh_slice` **inside** `seed_stock_board_map` — never a module-top import (avoids import-time coupling of the rotation package to the monitor store). Do **not** inject a `fresh_keys` callable param.
- **No version bump (LOCKED):** do **not** change `radar_version` / `schema_version` (`src/irc/rotation/types.py:58-59`); do **not** bump the root `VERSION` file (currently `0.9.3`). Store file format, hysteresis, composite untouched.
- **`summary` shape unchanged:** keeps `{done, skipped, failed}`. `skipped` stays `len(fresh)` — now the fresh-slice key-set size. No new counter / "stale re-fetched" tally.
- **Production-shaped fixtures (LOCKED):** new-test store rows put **行业 NAMES** in the `industry` slot (`{sym: {"industry": "<行业 name>", "seen_at": "<date>"}}`, e.g. `"酿酒行业"`, `"家电行业"`), NOT `"BK1"`-in-industry (the 004-masking anti-pattern). `batch_fetch` fakes return a **2-tuple** `({}, {sym: "<行业 name>"})`, matching seed's `_flow, industry_by_symbol = batch_fetch(...)` unpack.
- **Per-file pytest ONLY:** run `uv run pytest tests/rotation/test_seed.py`. **NEVER** run the whole `tests/commands/` directory (documented hang, FACTS.md). `uv run` on every command.
- **TDD (LOCKED):** red → run-to-fail → green → commit. AC2 **and** AC3 tests must fail before the fix and pass after; capture both red and green per-file output as runtime proof (goes in `005-verify.md` at ship/verify time).
- **Functional / immutable / effects-at-edges** (CLAUDE.md). `seed.py` stays < 200 lines; the changed function ≤ ~20 body lines.
- **CHANGELOG:** add a `[Unreleased] → Fixed` bullet; do **not** bump VERSION (project convention: accumulate under `[Unreleased]` at static VERSION).
- **Scope discipline:** one-line fix + tests only. R-2/R-3/R-5/R-6/R-9/R-11 are out of scope (Non-goals). No candidates-join change (that was item 004, merged).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/irc/rotation/seed.py` | `seed_stock_board_map` skip-set + docstring | Modify (`:83-88` region) |
| `tests/rotation/test_seed.py` | 2 new tests (AC2 unit, AC3 integration) + 1 legacy-fixture alignment (Q5) | Modify |
| `CHANGELOG.md` | `[Unreleased] → Fixed` R-4 bullet | Modify |

Baseline (post-004, current `main` of the branch) `seed_stock_board_map` — for reference:

```python
def seed_stock_board_map(
    symbols: Iterable[str],
    *,
    map_path: Path,
    today: str,
    batch_fetch,
    load_existing,
    record,
    chunk_size: int = 200,
) -> dict:
    """Chunked ulist.np (f100 行业 — NOT f127, T1) over held stocks; skip symbols
    already present in the map. record(map_path, today, industry_by_symbol) merges
    each chunk through the extended industry_map_store. Partial-tolerant (AC2)."""
    existing = load_existing(map_path)
    fresh = set(existing.keys())
    pending = [s for s in dict.fromkeys(symbols) if s not in fresh]
    done, failed = 0, []
    for i in range(0, len(pending), chunk_size):
        chunk = pending[i:i + chunk_size]
        try:
            _flow, industry_by_symbol = batch_fetch(tuple(chunk))
        except Exception as exc:  # noqa: BLE001 — partial-tolerant chunk (AC2/T3)
            _log.warning("seed_stock_board_map: chunk failed: %s", exc)
            failed.extend(chunk)
            continue
        record(map_path, today, industry_by_symbol)
        done += sum(1 for v in industry_by_symbol.values() if v)
    return {"done": done, "skipped": len(fresh), "failed": tuple(failed)}
```

---

## Task 1: Skip-set freshness fix (AC1 + AC2 + AC3 + AC4) — TDD red→green

The core. Two new tests both target the single skip-set behavior change, so they are written and run RED together, then the one-line fix + docstring make both green (the minimal code satisfying both). AC4 docstring rewrite ships in the same commit (a false docstring is a defect — the 004 lesson).

**Files:**
- Modify: `src/irc/rotation/seed.py:83-88` (docstring + skip-set)
- Test: `tests/rotation/test_seed.py` (append 2 tests)

**Interfaces:**
- Consumes: `irc.monitor.industry_map_store.fresh_slice(store, today, max_age_days=MAX_AGE_DAYS) -> dict[str, str]` (pure; keys = fresh symbols); `record_seen(path, today, industry_by_symbol) -> dict` and `load_store(path) -> dict[str, dict]` (real store round-trip, for AC3).
- Produces: unchanged `seed_stock_board_map(...) -> {"done": int, "skipped": int, "failed": tuple}` signature — `skipped` now = fresh-slice key count.

- [ ] **Step 1: Establish baseline green (pre-existing tests pass)**

Run: `uv run pytest tests/rotation/test_seed.py -q`
Expected: `5 passed` (baseline: `test_seed_boards_*` ×2, `test_seed_holdings_skips_cached`, `test_seed_stock_board_map_skips_fresh_and_chunks`, `test_seed_stock_board_map_chunk_failure_is_tolerated`).

- [ ] **Step 2: Write the AC2 test (production-shaped skip-set membership, red-first)**

Append to `tests/rotation/test_seed.py`:

```python
def test_seed_stock_board_map_refetches_stale_skips_fresh(tmp_path):
    # Production-shaped store: 行业 NAMES in the industry slot (NOT "BK1"). One
    # entry STALE (seen_at > 30 calendar days before today), one FRESH (≤ 30 days).
    map_path = tmp_path / "stock_industry_map.json"
    chunks = []

    def fake_batch(symbols):
        chunks.append(tuple(symbols))
        return {}, {s: "半导体" for s in symbols}

    def fake_load(_path):
        return {
            "600519": {"industry": "酿酒行业", "seen_at": "2026-05-01"},  # 66d → STALE
            "000651": {"industry": "家电行业", "seen_at": "2026-07-01"},  # 5d  → FRESH
        }

    summary = seed_stock_board_map(
        ["600519", "000651"],
        map_path=map_path,
        today="2026-07-06",
        batch_fetch=fake_batch,
        load_existing=fake_load,
        record=lambda *a, **k: {},
        chunk_size=200,
    )
    fetched = [s for c in chunks for s in c]
    assert "600519" in fetched       # STALE (>30d) re-fetched — the freshness fix
    assert "000651" not in fetched   # FRESH (≤30d) still skipped — resumability
    assert summary["skipped"] == 1   # only the fresh entry counts as skipped
```

- [ ] **Step 3: Write the AC3 test (real-store round-trip refreshes seen_at, red-first)**

Append to `tests/rotation/test_seed.py`. Uses the **real** `load_store` / `record_seen` (function-local imports, matching the file's convention), NOT fakes:

```python
def test_seed_stock_board_map_roundtrip_refreshes_stale_seen_at(tmp_path):
    # Integration: real store round-trip. Pre-seed a STALE + a FRESH entry, run
    # seed, assert stale seen_at bumped to today while fresh is untouched — the
    # heal loop end-to-end (stale → re-fetched → record_seen refresh-on-seen).
    from irc.monitor.industry_map_store import load_store, record_seen

    map_path = tmp_path / "stock_industry_map.json"
    record_seen(map_path, "2026-05-01", {"600519": "酿酒行业"})  # STALE (66d)
    record_seen(map_path, "2026-07-01", {"000651": "家电行业"})  # FRESH (5d)

    chunks = []

    def fake_batch(symbols):
        chunks.append(tuple(symbols))
        return {}, {s: "酿酒行业" for s in symbols}  # 2-tuple; only stale is pending

    summary = seed_stock_board_map(
        ["600519", "000651"],
        map_path=map_path,
        today="2026-07-06",
        batch_fetch=fake_batch,
        load_existing=load_store,
        record=record_seen,
        chunk_size=200,
    )
    store = load_store(map_path)
    assert store["600519"]["seen_at"] == "2026-07-06"   # STALE refreshed to today
    assert store["000651"]["seen_at"] == "2026-07-01"   # FRESH untouched
    assert "000651" not in [s for c in chunks for s in c]  # fresh never re-fetched
    assert summary["done"] == 1
```

- [ ] **Step 4: Run both new tests to verify they FAIL (red proof)**

Run: `uv run pytest tests/rotation/test_seed.py -q -k "refetches_stale or roundtrip_refreshes"`
Expected: `2 failed`. Failure detail:
- `test_seed_stock_board_map_refetches_stale_skips_fresh` → `AssertionError: assert '600519' in []` (pre-fix skips ALL existing keys, so `chunks` is empty).
- `test_seed_stock_board_map_roundtrip_refreshes_stale_seen_at` → `AssertionError: assert '2026-05-01' == '2026-07-06'` (stale never re-fetched, so `seen_at` never bumped).

**Capture this red output for `005-verify.md`.** If either test *passes* here, STOP — the baseline is not what the spec describes; do not proceed.

- [ ] **Step 5: Apply the AC1 one-line skip-set fix + function-local import**

In `src/irc/rotation/seed.py`, replace:

```python
    existing = load_existing(map_path)
    fresh = set(existing.keys())
```

with:

```python
    from irc.monitor.industry_map_store import fresh_slice
    existing = load_existing(map_path)
    fresh = set(fresh_slice(existing, today))
```

(`pending`, the chunk loop, and `return {..., "skipped": len(fresh), ...}` are unchanged — `fresh` is now the fresh-slice key-set, so `len(fresh)` counts genuinely-fresh skips.)

- [ ] **Step 6: Apply the AC4 docstring rewrite (truthful)**

In `src/irc/rotation/seed.py`, replace the `seed_stock_board_map` docstring:

```python
    """Chunked ulist.np (f100 行业 — NOT f127, T1) over held stocks; skip symbols
    already present in the map. record(map_path, today, industry_by_symbol) merges
    each chunk through the extended industry_map_store. Partial-tolerant (AC2)."""
```

with:

```python
    """Chunked ulist.np (f100 行业 — NOT f127, T1) over held stocks; skip symbols
    still FRESH (seen_at ≤ 30 calendar days per fresh_slice) in the map. STALE
    entries (seen_at > 30 calendar days) fall out of the skip-set and are
    re-fetched, so record(map_path, today, ...)'s REFRESH-ON-SEEN bumps their
    seen_at back to today and exposure coverage self-heals (on re-seed). record
    merges each chunk through the industry_map_store. Partial-tolerant (AC2)."""
```

- [ ] **Step 7: Run the new tests to verify they PASS (green proof)**

Run: `uv run pytest tests/rotation/test_seed.py -q -k "refetches_stale or roundtrip_refreshes"`
Expected: `2 passed`. **Capture this green output for `005-verify.md`.**

- [ ] **Step 8: Run the whole seed file + lint**

Run: `uv run pytest tests/rotation/test_seed.py -q`
Expected: `7 passed` (5 baseline + 2 new; the legacy `test_seed_stock_board_map_skips_fresh_and_chunks` still passes — its `600001` entry is `seen_at`=today → fresh → skipped).

Run: `uv run ruff check src/irc/rotation/seed.py`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add src/irc/rotation/seed.py tests/rotation/test_seed.py
git commit -m "fix(rotation): seed skip-set honors fresh_slice freshness (R-4)"
```

---

## Task 2: Align the legacy seed fixture to production 行业-name shape (Q5)

Zero-risk, string-only drive-by in the file we just edited. The existing `test_seed_stock_board_map_skips_fresh_and_chunks` puts `"BK1"` in the `industry` slot — the exact 004-masking anti-pattern. Leaving it beside the new production-shaped tests is inconsistent. No behavior change (its entry is `seen_at`=today → fresh → skipped either way).

**Files:**
- Test: `tests/rotation/test_seed.py` (`test_seed_stock_board_map_skips_fresh_and_chunks`)

- [ ] **Step 1: Align the store fixture + batch mock to 行业 names**

In `tests/rotation/test_seed.py`, inside `test_seed_stock_board_map_skips_fresh_and_chunks`, replace:

```python
    def fake_batch(symbols):
        chunks.append(tuple(symbols))
        return {}, {s: "BK9" for s in symbols}

    def fake_load(_path):
        return {"600001": {"industry": "BK1", "seen_at": "2026-07-06"}}
```

with:

```python
    def fake_batch(symbols):
        chunks.append(tuple(symbols))
        return {}, {s: "电子元件" for s in symbols}

    def fake_load(_path):
        return {"600001": {"industry": "半导体", "seen_at": "2026-07-06"}}
```

(Both `"BK1"`→`"半导体"` and `"BK9"`→`"电子元件"` are 行业 names. Assertions in that test — chunk shapes `[2, 1]`, `skipped == 1`, `done == 3`, `len(recorded) == 2` — are unchanged.)

- [ ] **Step 2: Run the seed file + the adjacent industry-map-store suite**

Run: `uv run pytest tests/rotation/test_seed.py -q`
Expected: `7 passed`.

Run: `uv run pytest tests/monitor/test_industry_map_store.py -q`
Expected: all pass (adjacent monitor-owned store suite stays green — we changed nothing in `industry_map_store.py`).

- [ ] **Step 3: Commit**

```bash
git add tests/rotation/test_seed.py
git commit -m "test(rotation): align legacy seed fixture to production 行业-name shape (Q5)"
```

---

## Task 3: CHANGELOG entry + no-version-bump verification (AC5)

Document the fix under `[Unreleased] → Fixed`; prove no version numbers moved.

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased] → ### Fixed`)

- [ ] **Step 1: Add the R-4 Fixed bullet**

In `CHANGELOG.md`, find the end of the existing R-1 candidates-join bullet and insert the new bullet after it (still inside `### Fixed`, before `### Added`). Replace:

```
  emits its candidate rows from data already on disk. No `radar_version`/`schema_version`
  bump; board scoring untouched.

### Added — sector rotation radar (2026-07-05)
```

with:

```
  emits its candidate rows from data already on disk. No `radar_version`/`schema_version`
  bump; board scoring untouched.

- **Sector rotation radar — seed skip-set freshness (review R-4, P0)**: `irc rotation
  seed`'s stock→board map builder skipped **every** symbol already present in
  `data/monitor/stock_industry_map.json`, ignoring `seen_at` age, so once the ~640
  seeded non-Monitor mappings crossed the store's 30-calendar-day `fresh_slice`
  window (~2026-08-05) they dropped out of the daily join AND could never be
  re-fetched — the store could only recover by being deleted. `seed_stock_board_map`'s
  skip-set now derives from `fresh_slice(existing, today)` (its keys) instead of
  `existing.keys()`, so STALE entries re-enter the re-fetch set and `record_seen`'s
  refresh-on-seen bumps their `seen_at` back to `today` (coverage self-heals on
  re-seed); FRESH entries stay skipped, preserving resumability. No
  `radar_version`/`schema_version`/`VERSION` bump; store shape and board scoring
  untouched.

### Added — sector rotation radar (2026-07-05)
```

- [ ] **Step 2: Verify NO version bump (AC5)**

Run: `git diff --name-only && echo "---" && grep -n "radar_version\|schema_version" src/irc/rotation/types.py && cat VERSION`
Expected: changed files are only `src/irc/rotation/seed.py`, `tests/rotation/test_seed.py`, `CHANGELOG.md`, `docs/2026-07-07-review-followup/items/005-plan.md` (this plan). `VERSION` prints `0.9.3` (unchanged). `types.py:58-59` still `schema_version` / `radar_version` (unchanged). If `VERSION` or `types.py` appears in the diff, STOP and revert that change.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(rotation): CHANGELOG — seed skip-set freshness fix (R-4)"
```

---

## Final verification (before ship)

Run the full seed suite once more and confirm the freshness fix is intact:

Run: `uv run pytest tests/rotation/test_seed.py -q`
Expected: `7 passed`.

Do **NOT** run `uv run pytest tests/commands/` as a whole directory (documented hang, FACTS.md). If a broader sanity check is wanted, run per-file: `uv run pytest tests/rotation/ -q` and `uv run pytest tests/monitor/test_industry_map_store.py -q`.

---

## Self-Review (author checklist — done)

1. **Spec coverage:** AC1 (skip-set fix) → Task 1 Step 5. AC2 (production-shaped skip-set test, red-first) → Task 1 Steps 2/4/7. AC3 (integration round-trip refreshes `seen_at`) → Task 1 Steps 3/4/7. AC4 (truthful docstring) → Task 1 Step 6. AC5 (no version bump) → Task 3 Step 2 + Global Constraints. AC6 (TDD, per-file pytest, red-then-green proof) → Task 1 Steps 4/7 + every run command. Q5 legacy-fixture alignment → Task 2. CHANGELOG → Task 3. All Non-goals (R-2/R-3/R-5/R-6/R-9/R-11, store-side, candidates-join, richer summary) untouched — no task introduces them.
2. **Placeholder scan:** none — every code and command step is literal.
3. **Type consistency:** `fresh_slice(existing, today)` used with default `max_age_days` everywhere; `seed_stock_board_map` signature unchanged; `{done, skipped, failed}` shape preserved; `record`/`load_existing`/`batch_fetch` injection unchanged; `batch_fetch` fakes all return the 2-tuple `({}, {...})` matching the `_flow, industry_by_symbol` unpack.
