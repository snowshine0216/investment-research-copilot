# Rotation candidates join fix (item 004) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate 行业 name → EM board code at the sector-rotation radar's L2 candidates join so `ExposureRow.board_code` carries a BK code the active-board filter can match — turning the always-empty `candidates` list into real rows built from data already on disk.

**Architecture:** The monitor-owned store (`data/monitor/stock_industry_map.json`) holds 东财行业 **names** (f100) in its `industry` slot. The radar's `resolve_candidates` currently feeds that name-valued slice straight into `build_exposure` as if it were board codes, so every `ExposureRow.board_code` is a name and `rank_candidates`'s code-keyed `active` filter matches nothing. The fix builds a `{board_name: board_code}` map from the run's `BoardState` list and translates name → code *before* `build_exposure`, keeping `build_exposure` a pure `{symbol: board_code}` aggregator (its never-used `board_names` param is dropped). The store stays name-based; translation lives only at the radar join.

**Tech Stack:** Python 3.12+, uv, pytest, DuckDB/pandas (not touched here), frozen dataclasses. Pure-logic + edge-glue change; no fetch, LLM, or network path.

## Global Constraints

- **TDD is law** (repo CLAUDE.md): red → run-to-fail → green → commit. Test file mirrors source; never write impl without a failing test first.
- **Functional / immutable / effects-at-edges**: pure dict comprehensions, no argument mutation, no new module state. Translation is a pure comprehension.
- **Size budgets**: files < 200 lines, changed functions ≤ ~20 lines ideal. `resolve_candidates` gains ~3 lines; `build_exposure` loses a param.
- **pytest per-FILE only**: e.g. `uv run pytest tests/rotation/test_exposure.py`. **NEVER** run the whole `tests/commands/` directory (documented hang, FACTS.md / MEMORY.md).
- **`uv run …` for everything** — never bare `python`/`pip`/`pytest`.
- **No version bumps**: `RotationReport.radar_version` and `schema_version` stay `1` (`src/irc/rotation/report.py:14-15`); the `VERSION` file stays `0.9.3`. CHANGELOG `[Unreleased]` accumulation only.
- **Store shape is off-limits**: `data/monitor/stock_industry_map.json`, `seed.py`, `series_store.py`, and all monitor code are untouched. R-4 seed skip-set freshness (`seed.py:87-88`) is **item 005**, not this item — do not touch it.
- **Stay on branch `autodev/review-followup-feature`.** Do NOT switch branches, do NOT push.
- **Calling the Agent tool is FORBIDDEN.** Do all work yourself.
- **No committed heavy fixture**: never commit the real 2.9 MB `board_series.json` as a test fixture. The committed regression coverage is a small production-*shaped* synthetic map; the real-data check is a documented, re-runnable offline replay (Task 5).

---

### Task 1: `build_exposure` — drop the dead `board_names` param (AC2, AC5)

Remove the never-used third positional param so `build_exposure` keeps its single job — `{symbol: board_code}` → fund×board exposure rows + coverage diagnostics — with no taxonomy knowledge. Update its unit tests to the 2-arg contract and update the sole caller so every commit stays coherent (the name-vs-code bug still persists after this task; it is fixed in Task 2).

**Files:**
- Modify: `src/irc/rotation/exposure.py:17-21` (function signature)
- Modify: `src/irc/rotation/_cmd_helpers.py:100-103` (sole caller — keep it coherent)
- Test: `tests/rotation/test_exposure.py:13,24,33` (3 call sites → 2-arg)

**Interfaces:**
- Produces: `build_exposure(funds: Iterable[Fund], stock_to_board: Mapping[str, str]) -> tuple[tuple[ExposureRow, ...], dict]`. `Fund = tuple[str, str, tuple[Holding, ...], str | None]`. The diag dict keys are unchanged: `total_holding_syms`, `mapped_syms`, `unmapped_syms` (sorted tuple), `coverage_pct`.

- [ ] **Step 1: Update `test_exposure.py` to the 2-arg contract**

In `tests/rotation/test_exposure.py`, drop the dead third arg from all three `build_exposure(...)` calls. The `s2b` values are already BK codes — that is the correct post-refactor contract, so no shape change is needed.

Replace line 13:
```python
    rows, diag = build_exposure(funds, s2b, {"BK1": "半导体"})
```
with:
```python
    rows, diag = build_exposure(funds, s2b)
```

Replace line 24:
```python
    rows, diag = build_exposure(funds, s2b, {"BK1": "半导体"})
```
with:
```python
    rows, diag = build_exposure(funds, s2b)
```

Replace line 33:
```python
    rows, _ = build_exposure(funds, s2b, {"BK1": "半导体", "BK2": "白酒"})
```
with:
```python
    rows, _ = build_exposure(funds, s2b)
```

- [ ] **Step 2: Run the exposure test to verify it fails**

Run: `uv run pytest tests/rotation/test_exposure.py -v`
Expected: FAIL — 3 errors, `TypeError: build_exposure() missing 1 required positional argument: 'board_names'`.

- [ ] **Step 3: Drop the param from `build_exposure`**

In `src/irc/rotation/exposure.py`, replace the signature (lines 17-21):
```python
def build_exposure(
    funds: Iterable[Fund],
    stock_to_board: Mapping[str, str],
    board_names: Mapping[str, str],
) -> tuple[tuple[ExposureRow, ...], dict]:
```
with:
```python
def build_exposure(
    funds: Iterable[Fund],
    stock_to_board: Mapping[str, str],
) -> tuple[tuple[ExposureRow, ...], dict]:
```
(Leave the `Mapping`/`Iterable` imports — both are still used. The function body is unchanged.)

- [ ] **Step 4: Update the sole caller to stay coherent**

In `src/irc/rotation/_cmd_helpers.py`, replace this block (lines 101-103):
```python
    stock_to_board = fresh_slice(load_store(map_path), today)
    board_names = {b.board_code: b.board_name for b in states}
    rows, exp_diag = build_exposure(funds, stock_to_board, board_names)
```
with:
```python
    stock_to_board = fresh_slice(load_store(map_path), today)
    rows, exp_diag = build_exposure(funds, stock_to_board)
```
(This removes the orphaned `board_names` local and the dead third arg. `stock_to_board` still carries **names** here — the bug is not yet fixed, candidates stay empty as before — but the code is coherent and crash-free. Task 2 adds the translation.)

- [ ] **Step 5: Run tests + lint to verify green**

Run: `uv run pytest tests/rotation/test_exposure.py tests/rotation/test_candidates.py -v`
Expected: PASS — all tests pass.

Run: `uv run ruff check src/irc/rotation/exposure.py src/irc/rotation/_cmd_helpers.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/rotation/exposure.py src/irc/rotation/_cmd_helpers.py tests/rotation/test_exposure.py
git commit -m "refactor(rotation): drop dead board_names param from build_exposure"
```

---

### Task 2: `resolve_candidates` — translate 行业 name → BK code at the join (AC1, AC4)

The core fix. Build a `{board_name: board_code}` map from the run's `states` and translate the fresh stock→行业-name slice into a stock→**board-code** map *before* `build_exposure`, so `ExposureRow.board_code` carries a BK code matching `rank_candidates`'s code-keyed `active` set. A new production-shaped integration test (行业 **names** in the `industry` slot, copied from the real store) drives `record_seen`/`load_store` → `fresh_slice` → `resolve_candidates` and asserts non-empty, code-keyed candidates — plus a pre-fix regression that names-fed-as-codes yield 0.

**Files:**
- Create: `tests/rotation/test_resolve_candidates.py` (new integration test)
- Modify: `src/irc/rotation/_cmd_helpers.py:100-103` (add translation)

**Interfaces:**
- Consumes: `build_exposure(funds, stock_to_board)` (Task 1, 2-arg); `record_seen(path, today, industry_by_symbol) -> dict`, `load_store(path) -> dict`, `fresh_slice(store, today) -> dict[str, str]` from `irc.monitor.industry_map_store`; `rank_candidates(rows, states, *, discovered_watchlist, monitor_set, held)` from `irc.rotation.candidates`; `BoardState`, `ExposureRow` from `irc.rotation.types`; `resolve_candidates(root, states, membership, *, today) -> (candidates, new_ids, diag)` from `irc.rotation._cmd_helpers`.
- Produces (post-fix `resolve_candidates` internals): a `{board_name: board_code}` map named `name_to_code` and a translated `{symbol: board_code}` map named `stock_to_code`, passed to `build_exposure`. External signature/return of `resolve_candidates` is unchanged.

- [ ] **Step 1: Write the failing integration test**

Create `tests/rotation/test_resolve_candidates.py` with exactly this content:

```python
"""Integration: production-shaped (行业-names-in-`industry`-slot) store through
record_seen/load_store -> fresh_slice -> resolve_candidates. Locks the name->code
translation at the radar join (item 004, review R-1). The pre-fix path (names fed
as codes) is asserted to yield 0 candidates — the regression guard for R-1."""
from __future__ import annotations

import json
from pathlib import Path

from irc.monitor.industry_map_store import fresh_slice, load_store, record_seen
from irc.rotation._cmd_helpers import resolve_candidates
from irc.rotation.candidates import rank_candidates
from irc.rotation.exposure import build_exposure
from irc.rotation.types import BoardState

TODAY = "2026-07-06"


def _state(code: str, name: str, state: str) -> BoardState:
    return BoardState(board_code=code, board_name=name, state=state, days_in_state=1,
                      composite_pctl=0.85, mom20=1.0, flow5=1.0, turn_delta=0.1,
                      pe_pctl=None, chase_risk=False)


def _write_holdings(root: Path) -> None:
    cache = root / "data" / "narrative_holdings"
    cache.mkdir(parents=True)
    # 600519 + 000858 sit in the 白酒 board (13.0% >= 10%); 00700 is HK, unmapped.
    body = {"holdings": [
        {"symbol": "600519", "name_cn": "贵州茅台", "weight_pct": 8.0, "sw_industry": ""},
        {"symbol": "000858", "name_cn": "五粮液", "weight_pct": 5.0, "sw_industry": ""},
        {"symbol": "00700", "name_cn": "腾讯控股", "weight_pct": 3.0, "sw_industry": ""},
    ]}
    (cache / "F001.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def _seed_store(root: Path) -> Path:
    # Production shape: 行业 NAMES in the `industry` slot (NOT "BK1"-in-industry).
    map_path = root / "data" / "monitor" / "stock_industry_map.json"
    map_path.parent.mkdir(parents=True)
    record_seen(map_path, TODAY, {"600519": "白酒", "000858": "白酒"})
    return map_path


def test_resolve_candidates_translates_name_to_board_code(tmp_path):
    _write_holdings(tmp_path)
    _seed_store(tmp_path)
    states = (_state("BK0477", "白酒", "hot"), _state("BK0999", "其他", "quiet"))
    membership = (frozenset(), frozenset(), frozenset({"F001"}))  # held

    candidates, new_ids, diag = resolve_candidates(
        tmp_path, states, membership, today=TODAY)

    assert diag["holdings_cache"] == "ok"
    assert len(candidates) >= 1, "translated join must produce candidates"
    assert all(c.board_code.startswith("BK") for c in candidates)
    top = candidates[0]
    assert top.board_code == "BK0477" and top.fund_id == "F001"
    assert top.held is True
    assert "00700" in diag["unmapped_syms"]  # AC7: HK degrades to diagnostics


def test_prefix_names_as_codes_yield_zero_candidates(tmp_path):
    """Regression guard: feeding the 行业-NAME slice straight to build_exposure (the
    pre-fix behavior) makes every ExposureRow.board_code a name, so the code-keyed
    active filter matches nothing and candidates is empty."""
    _write_holdings(tmp_path)
    map_path = _seed_store(tmp_path)
    states = (_state("BK0477", "白酒", "hot"),)
    name_slice = fresh_slice(load_store(map_path), TODAY)  # values are 行业 NAMES
    assert name_slice == {"600519": "白酒", "000858": "白酒"}

    from irc.rotation._cmd_helpers import _load_holdings_cache
    funds = _load_holdings_cache(tmp_path / "data" / "narrative_holdings")
    rows_pre, _ = build_exposure(funds, name_slice)  # names-as-codes (pre-fix)
    cands_pre, _ = rank_candidates(rows_pre, states, discovered_watchlist=frozenset(),
                                   monitor_set=frozenset(), held=frozenset())
    assert len(cands_pre) == 0
```

- [ ] **Step 2: Run the new test to verify it fails (red)**

Run: `uv run pytest tests/rotation/test_resolve_candidates.py -v`
Expected: `test_resolve_candidates_translates_name_to_board_code` FAILS on `assert len(candidates) >= 1` (candidates empty — names still fed as codes). `test_prefix_names_as_codes_yield_zero_candidates` PASSES (it documents the bug and needs no fix).

- [ ] **Step 3: Add the translation to `resolve_candidates`**

In `src/irc/rotation/_cmd_helpers.py`, replace this block (currently lines 100-102 after Task 1):
```python
    map_path = root / "data" / "monitor" / "stock_industry_map.json"
    stock_to_board = fresh_slice(load_store(map_path), today)
    rows, exp_diag = build_exposure(funds, stock_to_board)
```
with:
```python
    map_path = root / "data" / "monitor" / "stock_industry_map.json"
    name_to_code = {b.board_name: b.board_code for b in states}
    stock_to_name = fresh_slice(load_store(map_path), today)
    stock_to_code = {sym: name_to_code[nm] for sym, nm in stock_to_name.items()
                     if nm in name_to_code}
    rows, exp_diag = build_exposure(funds, stock_to_code)
```
(The `if nm in name_to_code` guard drops 行业 names with no board this run — they fall into `build_exposure`'s existing `unmapped`/`coverage_pct` diagnostics, AC7. On the real map all 103 names resolve, so this never fires there.)

- [ ] **Step 4: Run the new test to verify it passes (green)**

Run: `uv run pytest tests/rotation/test_resolve_candidates.py -v`
Expected: PASS — both tests pass.

- [ ] **Step 5: Run the rotation regression + lint**

Run: `uv run pytest tests/rotation/test_exposure.py tests/rotation/test_candidates.py tests/rotation/test_resolve_candidates.py -v`
Expected: PASS — all tests pass.

Run: `uv run ruff check src/irc/rotation/_cmd_helpers.py tests/rotation/test_resolve_candidates.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/rotation/_cmd_helpers.py tests/rotation/test_resolve_candidates.py
git commit -m "fix(rotation): translate 行业 name -> board code at candidates join"
```

---

### Task 3: Correct the false docstring in `industry_map_store.py` (AC3)

The module docstring falsely claims "board codes are stored in the `industry` slot". Rewrite it to state the store holds 行业 **names** (f100) for both monitor and radar consumers, and that the radar translates name → board code at *its* join, never in the store.

**Files:**
- Modify: `src/irc/monitor/industry_map_store.py:16-19` (docstring only — no runtime code)

- [ ] **Step 1: Rewrite the docstring paragraph**

In `src/irc/monitor/industry_map_store.py`, replace this paragraph (lines 16-19):
```python
Also serves the sector rotation radar (ADR 0023 D7): the same store persists
stock→EM-board-code mappings (board codes are stored in the `industry` slot; the
radar carries board display names separately from the daily snapshot). 30-day
serve-while-stale semantics preserved — extended in place, not forked.
```
with:
```python
Also serves the sector rotation radar (ADR 0023 D7): the SAME store holds 东财
行业 NAMES (f100) in the `industry` slot for BOTH consumers (monitor and radar) —
never board codes. The radar translates 行业 name → EM board code at its OWN join
(`rotation.resolve_candidates`, via a `{board_name: board_code}` map built from
that run's `BoardState` list), never in the store, which stays monitor-owned and
name-based. 30-day serve-while-stale semantics preserved — extended in place, not
forked.
```

- [ ] **Step 2: Verify the false claim is gone and the correction landed**

Run: `grep -c "board codes are stored" src/irc/monitor/industry_map_store.py`
Expected: `0`

Run: `grep -c "translates 行业 name" src/irc/monitor/industry_map_store.py`
Expected: `1`

- [ ] **Step 3: Verify the module still imports and its tests pass**

Run: `uv run pytest tests/monitor/test_industry_map_store.py -v`
Expected: PASS — all tests pass (docstring change is behavior-neutral).

Run: `uv run ruff check src/irc/monitor/industry_map_store.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add src/irc/monitor/industry_map_store.py
git commit -m "docs(monitor): industry_map_store slot holds 行业 names, not board codes"
```

---

### Task 4: CHANGELOG `[Unreleased]` — record the user-visible fix (Global Constraints)

The radar now emits candidate rows where it produced none — user-visible output change. Add a `### Fixed` entry under `[Unreleased]`. No `VERSION` bump.

**Files:**
- Modify: `CHANGELOG.md` (insert a `### Fixed` block under `## [Unreleased]`)

- [ ] **Step 1: Insert the Fixed entry**

In `CHANGELOG.md`, replace:
```markdown
## [Unreleased]

### Added — sector rotation radar (2026-07-05)
```
with:
```markdown
## [Unreleased]

### Fixed

- **Sector rotation radar — L2 candidates join (review R-1, P0)**: the stock→board
  store (`data/monitor/stock_industry_map.json`) holds 东财行业 **names** (f100) in
  its `industry` slot, but the radar's candidates join filtered exposure rows against
  BK **board codes**, so `ExposureRow.board_code` (a name) never matched and
  `candidates` was always empty — even on successful runs. `rotation.resolve_candidates`
  now translates 行业 name → EM board code at the join (via a `{board_name: board_code}`
  map from the run's `BoardState` list) before the active-board filter, so the radar
  emits its candidate rows from data already on disk. No `radar_version`/`schema_version`
  bump; board scoring untouched.

### Added — sector rotation radar (2026-07-05)
```

- [ ] **Step 2: Verify the entry landed and no version bumped**

Run: `grep -n "L2 candidates join (review R-1" CHANGELOG.md`
Expected: one match under `[Unreleased]`.

Run: `cat VERSION`
Expected: `0.9.3` (unchanged).

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): record rotation candidates join fix"
```

---

### Task 5: Offline replay runtime proof (AC6, AC7 — documented, NOT a committed test)

Prove the fix end-to-end against the **real** on-disk artifacts (`data/rotation/board_series.json` + `data/monitor/stock_industry_map.json`, EM egress NOT required) through the real `_build_states` → translate → `build_exposure` → `rank_candidates` path. The script gates on **drift-proof invariants** (candidates > 0, cap bites, pre-fix = 0, coverage byte-identical pre/post), NOT on the point-in-time integers — those have already drifted once (review-time 96/34 → 2026-07-07 replay 108–111 raw / 35–38 capped as the holdings cache grew). The script lives in the scratchpad and is **not committed** (never commit the 2.9 MB `board_series.json` as a fixture).

**Files:**
- Create (scratchpad, NOT committed): `<scratchpad>/replay_004.py` where `<scratchpad>` is your session scratchpad directory.

- [ ] **Step 1: Write the replay script**

Write this to `<scratchpad>/replay_004.py`:

```python
"""Item 004 offline runtime proof — real on-disk artifacts, no network.
Gates on drift-proof INVARIANTS, not the point-in-time integers (which drift)."""
from collections import Counter
from pathlib import Path

from irc.commands.rotation_cmd import _build_states
from irc.monitor.industry_map_store import fresh_slice, load_store as load_map
from irc.rotation._cmd_helpers import _load_holdings_cache
from irc.rotation.candidates import CAND_TOP_N, MIN_EXPOSURE_PCT, rank_candidates
from irc.rotation.composite import board_signals, flow_leg_dark, turn_leg_dark
from irc.rotation.exposure import build_exposure
from irc.rotation.series_store import load_store as load_series

root = Path.cwd()
today = "2026-07-07"  # current date; reproduces the git-tracked 07-06 report coverage

series = load_series(root / "data/rotation/board_series.json")
sig = board_signals(series)
flow_dark, turn_dark = flow_leg_dark(sig), turn_leg_dark(sig)
states, _ = _build_states(series, flow_dark=flow_dark, turn_dark=turn_dark)
active = {s.board_code for s in states if s.state in ("emerging", "hot")}

funds = _load_holdings_cache(root / "data/narrative_holdings")
name_slice = fresh_slice(load_map(root / "data/monitor/stock_industry_map.json"), today)
name_to_code = {s.board_name: s.board_code for s in states}
code_slice = {sym: name_to_code[nm] for sym, nm in name_slice.items() if nm in name_to_code}
unresolved = set(name_slice.values()) - set(name_to_code)

# PRE-FIX: 行业 names fed straight in as codes
rows_pre, diag_pre = build_exposure(funds, name_slice)
cands_pre, _ = rank_candidates(rows_pre, states, discovered_watchlist=frozenset(),
                               monitor_set=frozenset(), held=frozenset())
# POST-FIX: translated to board codes
rows, diag = build_exposure(funds, code_slice)
cands, _ = rank_candidates(rows, states, discovered_watchlist=frozenset(),
                           monitor_set=frozenset(), held=frozenset())
per_board = Counter(r.board_code for r in rows
                    if r.board_code in active and r.exposure_pct >= MIN_EXPOSURE_PCT)
raw_pre_cap = sum(per_board.values())

print(f"active_boards={len(active)} funds={len(funds)} seen_syms={len(name_slice)} "
      f"unresolved_names={len(unresolved)}")
print(f"PRE-FIX  candidates={len(cands_pre)} coverage={diag_pre['coverage_pct']} "
      f"unmapped={len(diag_pre['unmapped_syms'])}")
print(f"POST-FIX candidates={len(cands)} raw_pre_cap={raw_pre_cap} "
      f"coverage={diag['coverage_pct']} unmapped={len(diag['unmapped_syms'])}")
print(f"per_board(raw active >=10%)={dict(per_board.most_common())}")

# DURABLE INVARIANT GATES (drift-proof — NOT the integers):
assert len(cands_pre) == 0, "INV-iii: pre-translation (names as codes) must yield 0"
assert len(cands) > 0, "INV-i: post-fix candidates must be > 0"
assert raw_pre_cap >= len(cands), "INV-ii: raw pre-cap must be >= capped candidates"
assert max(per_board.values()) > CAND_TOP_N, "INV-ii: the CAND_TOP_N=10 cap must bite"
assert diag_pre["coverage_pct"] == diag["coverage_pct"], "AC7/G4: coverage byte-identical pre/post"
assert len(unresolved) == 0, "locked: all seen 行业 names resolve to a board (100% coverage)"
print("ALL INVARIANTS PASS")
```

- [ ] **Step 2: Run the replay against the real artifacts**

Run (from the repo root so `Path.cwd()` resolves the real data):
```bash
uv run python "$(cat <<'EOF'
<scratchpad>/replay_004.py
EOF
)"
```
(Substitute `<scratchpad>` with the actual scratchpad path. Simplest: `uv run python <scratchpad>/replay_004.py` run with the repo root as the working directory.)

Expected output (integers are an **illustrative, drifting** snapshot — the gate is the final line, not the numbers):
```
active_boards=21 funds=446 seen_syms=699 unresolved_names=0
PRE-FIX  candidates=0 coverage=67.8016 unmapped=331
POST-FIX candidates=38 raw_pre_cap=111 coverage=67.8016 unmapped=331
per_board(raw active >=10%)={'BK1036': 69, 'BK0465': 19, 'BK0727': 15, ...}
ALL INVARIANTS PASS
```
The process must exit `0` with `ALL INVARIANTS PASS` printed. If any assert fires, the fix is wrong — stop and diagnose. **Do not** treat a mismatch of the exact integers (e.g. 38 vs 34, or 111 vs 96) as a failure — those drift with the holdings cache; only the asserted invariants gate.

Cross-check (AC7 / G2 / G4): the printed `coverage=67.8016 unmapped=331` is byte-identical pre-fix and post-fix and matches the git-tracked `outputs/2026-07-06/rotation/rotation_radar.json` (`holdings_coverage_pct=67.8016`, 331 unmapped) — the fix moves *candidates* 0 → ~35, never the coverage diagnostic.

- [ ] **Step 3: Record the proof in the run dir**

Append the observed replay output (the four printed lines + `ALL INVARIANTS PASS`) plus a one-line note "integers are a drifting snapshot; the gate is the invariants" to `docs/2026-07-07-review-followup/items/004-notes.md` (create it if absent). Commit that note only — never the scratchpad script or the real artifacts:

```bash
git add docs/2026-07-07-review-followup/items/004-notes.md
git commit -m "docs(004): record offline replay runtime proof"
```

---

### Task 6: Final regression sweep + no-version-bump guard (AC8, AC9)

Confirm the full rotation + monitor-store surface is green, no version numbers moved, and no stray `board_names` references remain.

**Files:** none modified — verification only.

- [ ] **Step 1: Run every touched/adjacent test file (per-file, never the whole `tests/commands/` dir)**

Run: `uv run pytest tests/rotation/test_exposure.py tests/rotation/test_candidates.py tests/rotation/test_resolve_candidates.py tests/rotation/test_seed.py tests/monitor/test_industry_map_store.py -v`
Expected: PASS — all tests pass.

- [ ] **Step 2: Confirm no version bump and no orphan param**

Run: `grep -n "RADAR_VERSION\|SCHEMA_VERSION" src/irc/rotation/report.py`
Expected: `SCHEMA_VERSION = 1` and `RADAR_VERSION = 1` (both unchanged).

Run: `cat VERSION`
Expected: `0.9.3`.

Run: `grep -rn "board_names" src/ tests/`
Expected: no output (the dead param is fully gone).

- [ ] **Step 3: Lint the full change surface**

Run: `uv run ruff check src/irc/rotation tests/rotation src/irc/monitor/industry_map_store.py`
Expected: `All checks passed!`

- [ ] **Step 4: Confirm the git log is clean and on-branch**

Run: `git log --oneline -6 && git branch --show-current`
Expected: the Task 1-5 commits present, on branch `autodev/review-followup-feature`. Do NOT push.

---

## Self-Review

**Spec coverage:**
- AC1 (translate at the join) → Task 2, Step 3.
- AC2 (drop dead param) → Task 1, Step 3.
- AC3 (false docstring corrected) → Task 3.
- AC4 (production-shaped integration test, red-first, incl. pre-fix `==0` guard) → Task 2, Steps 1-4.
- AC5 (`test_exposure.py` calls → 2-arg) → Task 1, Step 1.
- AC6 (offline replay runtime proof, invariant-gated) → Task 5.
- AC7 (unmapped/HK degrade unchanged; coverage byte-identical) → Task 2 test (`00700` unmapped) + Task 5 coverage-equality invariant.
- AC8 (no version bump) → Task 6, Step 2.
- AC9 (TDD + budgets + per-file pytest) → every task's red→green→commit; per-file pytest throughout.
- Non-goals (no store-side translation, R-4 is item 005, no scoring/version change, no committed heavy fixture) → Global Constraints + Task 5's "not committed" note.

**Placeholder scan:** none — every code/test/command block is concrete. The only `<scratchpad>` token is the session-specific path the executor already knows.

**Type consistency:** `build_exposure(funds, stock_to_board)` 2-arg everywhere post-Task-1; `resolve_candidates(root, states, membership, *, today)` signature unchanged; `BoardState` constructed with all 10 fields in both test helpers; `rank_candidates(rows, states, *, discovered_watchlist, monitor_set, held)` keyword args consistent with `candidates.py`.
