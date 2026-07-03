# Item 005 — Delete Production-Dead `src/irc/monitor/narrative.py`: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the production-dead per-fund narrative module `src/irc/monitor/narrative.py` (112 lines; carries the same latent unhashable-`attribution_strength` `TypeError` that item 001 fixed in `narrative_macro.py`), its mirror test file `tests/monitor/test_narrative.py` (154 lines, 10 tests), and the two stale scaffolding references in `tests/commands/test_monitor_cmd_theme_consolidation.py` — with a CHANGELOG "Removed" entry and nothing else.

**Architecture:** Pure deletion — `git rm` two files, remove 2 stale import lines + 1 inert `raising=False` monkeypatch (with its 4-line comment) from one surviving test, add one CHANGELOG subsection. No source file is modified; production already constructs `NarrativeDoc(fund.id, (), (), (), "empty_pool")` directly (`monitor_cmd.py:923`) and the namespace drop is contractual (`tests/commands/test_monitor_cmd.py:420-425` asserts `not hasattr(mc, "gather_narrative")`).

**Tech Stack:** Python 3.12+, uv, pytest, ruff, git. All commands run from the repo root `/Users/snow/Documents/Repository/investment-research-copilot`.

## Global Constraints

- Branch is already `claude/todos-critical-fixes-005` (created by the orchestrator). If `git branch --show-current` prints anything else, STOP and report — do NOT create branches, do NOT push, do NOT open a PR; the orchestrator ships.
- **This is a deletion item — write NO new tests** (spec Constraints). The acceptance evidence is: the AC4 greps returning zero hits + the surviving suite passing. The namespace-drop contract test (`test_run_monitor_never_calls_gather_narrative_per_fund`) already exists and must keep passing untouched.
- Do NOT touch: `src/irc/monitor/types.py` (`NarrativeDoc`/`Claim`/`EvidenceItem` are the production render path), `src/irc/monitor/narrative_macro.py` (item 001, already merged), `src/irc/monitor/usage.py` / `src/irc/spend/scope.py` / `evals/monitor_narrative/` (these reference the `monitor_narrative` **LLM task name**, which survives — it is `narrative_macro`'s route, not this module), `VERSION`, `TODOS.md` (AC7: no entry exists for this item and none may be added), `_ENGINE_VERSION`, trace `schema_version`.
- Do NOT refactor `tests/commands/test_monitor_cmd_theme_consolidation.py` beyond removing the exact stale lines shown in Task 1 Step 4 (spec Non-goals).
- NEVER run `tests/commands/` as a whole directory (known suite-ordering hang) — per-file only. `tests/monitor/` as a whole directory is fine.
- Ruff is scoped to the touched file only: repo-wide `uv run ruff check src tests` is NOT clean on this branch's base (118 pre-existing errors, recorded in the item-001 drift amendment). The one file this plan edits is currently clean and must stay clean.
- CHANGELOG: add a `### Removed` subsection under `[Unreleased]`; NO version bump.
- **AC4 grep note (deliberate, do not "fix" back):** the spec writes the grep as
  `grep -rn "monitor.narrative\b\|from irc.monitor.narrative" src/ tests/`. That literal
  command can never reach zero hits: the unescaped `.` matches the surviving
  `monitor_narrative` task-name strings (e.g. `spend/scope.py`, `usage.py`,
  `narrative_macro.py` route calls), and the second alternate is a prefix of every
  `from irc.monitor.narrative_macro import …` line. This plan implements AC4's stated
  intent ("zero references to the deleted module; narrative_macro excluded by the word
  boundary") with the corrected, macOS-BSD-grep-verified commands in Task 1 Steps 2 and 5:
  `grep -rn "monitor\.narrative\b" src/ tests/` (escaped dot excludes the task name; `\b`
  fails before `_` so `narrative_macro` is excluded) plus a word-bounded `NarrativeResult`
  sweep. Both were verified against the current tree during planning: pre-change they hit
  exactly the two stale test lines; post-change they are empty.

---

### Task 1: Delete the dead module + mirror tests, remove the stale scaffolding

**Files:**
- Delete: `src/irc/monitor/narrative.py` (112 lines)
- Delete: `tests/monitor/test_narrative.py` (154 lines, 10 tests)
- Modify: `tests/commands/test_monitor_cmd_theme_consolidation.py:150-151, 172-177` (two removals inside `test_run_monitor_searches_each_theme_exactly_once_across_whole_fund_set`)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: a tree with zero references to `irc.monitor.narrative` (AC1–AC4). Task 2 (CHANGELOG) describes this state and depends on the commit landing first.

- [ ] **Step 1: Confirm you are on the implementation branch**

Run: `git branch --show-current`
Expected output: `claude/todos-critical-fixes-005`
If it prints anything else (e.g. `main` or `autodev/todos-critical-fixes-feature`): STOP and report — do not create a branch yourself.

- [ ] **Step 2: Pre-deletion detector check (the deletion analog of "verify the test fails first")**

Prove the AC4 grep actually detects the module before you delete it — this rules out a
silently-wrong pattern producing a false-clean later.

Run: `grep -rn "monitor\.narrative\b" src/ tests/`
Expected output — exactly these 2 lines (line numbers may drift by a line or two; the two file:import pairs must match):

```
tests/monitor/test_narrative.py:3:from irc.monitor.narrative import gather_narrative, _banned_verb_present
tests/commands/test_monitor_cmd_theme_consolidation.py:150:    from irc.monitor.narrative import NarrativeResult
```

(Note the grep does NOT list `src/irc/monitor/narrative.py` itself — grep matches file
*contents*, and the module never spells its own dotted path. Its deletion is verified by
`git status` in Step 6 and the import-driven test runs in Steps 7–9.)

If the output differs (extra hits): STOP — a new consumer appeared since planning; report it instead of deleting.

- [ ] **Step 3: Delete the module and its mirror test file (AC1, AC2)**

```bash
git rm src/irc/monitor/narrative.py tests/monitor/test_narrative.py
```

Expected: `rm 'src/irc/monitor/narrative.py'` and `rm 'tests/monitor/test_narrative.py'`.

- [ ] **Step 4: Remove the two stale references from `tests/commands/test_monitor_cmd_theme_consolidation.py` (AC3)**

Both edits are inside `test_run_monitor_searches_each_theme_exactly_once_across_whole_fund_set`
(the file's last test). Make exactly these two replacements and nothing else.

**Edit 4a — drop the two imports that only served the removed monkeypatch** (lines 148–152;
`NarrativeResult` is the stale module import; `NarrativeDoc` is used ONLY inside the lambda
removed in Edit 4b, so leaving it would be a dead import — ruff F401 — in this
currently-clean file).

Old (verbatim):

```python
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.impacts import ImpactsResult
    from irc.monitor.narrative import NarrativeResult
    from irc.monitor.types import NarrativeDoc
    from irc.research.search.types import SearchResult, Locale
```

New (verbatim):

```python
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.impacts import ImpactsResult
    from irc.research.search.types import SearchResult, Locale
```

**Edit 4b — drop the inert `raising=False` monkeypatch and its scaffolding comment**
(lines 171–178). This is behavior-neutral: since report v3, `run_monitor` never references
`gather_narrative` (the contract test in `test_monitor_cmd.py:420-425` pins
`not hasattr(mc, "gather_narrative")`), so today the `raising=False` patch merely sets an
inert attribute on the module that pytest teardown removes — the comment itself documents
this "after removal" mode. The test's real assertions (rc == 0; provider called exactly
once per unique theme, `len(calls) == 3`) do not involve it.

Old (verbatim):

```python
    monkeypatch.setattr(mc, "gather_impacts", lambda **k: ImpactsResult(k["fund_id"], (), "empty_pool", ()))
    # raising=False: Phase 3 REMOVES gather_narrative from monitor_cmd's namespace
    # (Step 3.23). With raising=False this monkeypatch stays valid both before the
    # removal (intercepts the real per-fund call) and after it (sets an inert,
    # teardown-removed attribute) — so this Phase-2 test survives Phase 3 unchanged.
    monkeypatch.setattr(mc, "gather_narrative", lambda **k: NarrativeResult(
        NarrativeDoc(k["fund_id"], (), (), (), "empty_pool"), ()), raising=False)
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
```

New (verbatim):

```python
    monkeypatch.setattr(mc, "gather_impacts", lambda **k: ImpactsResult(k["fund_id"], (), "empty_pool", ()))
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
```

- [ ] **Step 5: Run the AC4 greps — zero hits (AC4)**

Run: `grep -rn "monitor\.narrative\b" src/ tests/; echo "exit: $?"`
Expected output: no match lines, then `exit: 1` (grep exits 1 on zero matches — that IS the pass condition).

Run: `grep -rnw "NarrativeResult" src/ tests/; echo "exit: $?"`
Expected output: no match lines, then `exit: 1` (`-w` word-match excludes the surviving `MacroNarrativeResult`).

Any hit in either grep: STOP — a reference was missed; do not proceed to the test runs.

- [ ] **Step 6: Confirm the working tree contains exactly the intended changes**

Run: `git status --short`
Expected output (order may vary):

```
D  src/irc/monitor/narrative.py
D  tests/monitor/test_narrative.py
 M tests/commands/test_monitor_cmd_theme_consolidation.py
```

- [ ] **Step 7: Run the surviving monitor suite — whole dir (AC5 part 1)**

Run: `uv run pytest tests/monitor/ -q`
Expected: `920 passed, 12 skipped` (baseline on this branch was `930 passed, 12 skipped`; the deleted mirror file contributed exactly 10 tests). Zero failures, zero errors — in particular zero collection errors (a collection error here means a leftover import of the deleted module).

- [ ] **Step 8: Run the edited test file — PER-FILE (AC5 part 2; AC3 "remaining tests still pass")**

Run: `uv run pytest tests/commands/test_monitor_cmd_theme_consolidation.py -q`
Expected: `6 passed` (same count as before the edit — the file loses no tests, only scaffolding).

- [ ] **Step 9: Run the contract-test file — PER-FILE (AC5 part 3; slow, ~60s)**

First the targeted contract test:

Run: `uv run pytest "tests/commands/test_monitor_cmd.py::test_run_monitor_never_calls_gather_narrative_per_fund" -q`
Expected: `1 passed` (it asserts on `monitor_cmd`'s namespace, unaffected by the module deletion).

Then the whole file (NEVER the whole `tests/commands/` directory — it hangs):

Run: `uv run pytest tests/commands/test_monitor_cmd.py -q`
Expected: `24 passed` (takes ~60 seconds; baseline count unchanged).

- [ ] **Step 10: Lint the touched file (scoped — see Global Constraints)**

Run: `uv run ruff check tests/commands/test_monitor_cmd_theme_consolidation.py`
Expected output: `All checks passed!`
(The two deleted files need no lint; no `src/` file was edited.)

- [ ] **Step 11: Commit the deletion**

```bash
git add tests/commands/test_monitor_cmd_theme_consolidation.py
git commit -m "chore(monitor): delete production-dead per-fund narrative.py + stale test scaffolding"
```

(`git rm` already staged the two deletions.) Expected: commit created on
`claude/todos-critical-fixes-005` containing exactly 3 files — 2 deleted, 1 modified.
Do NOT push.

---

### Task 2: CHANGELOG "Removed" entry (AC6) — and explicitly nothing else (AC7)

**Files:**
- Modify: `CHANGELOG.md` (insert a `### Removed` subsection directly under `## [Unreleased]`, currently line 8)

**Interfaces:**
- Consumes: the Task 1 commit (the entry describes the deleted state).
- Produces: documentation only — no code.

- [ ] **Step 1: Add the CHANGELOG entry**

In `CHANGELOG.md`, replace this exact text (top of the file body — `## [Unreleased]` plus the
current first subsection heading):

```markdown
## [Unreleased]

### Fixed — ActiveFundSnapshot thesis gate: dual-leg (data + information) check extended to the active-fund branch (2026-07-03)
```

with:

```markdown
## [Unreleased]

### Removed — production-dead per-fund narrative module `src/irc/monitor/narrative.py` (2026-07-03)

- **`src/irc/monitor/narrative.py` (per-fund `gather_narrative` + `NarrativeResult`)
  deleted.** Production-dead since report v3 dropped the per-fund LLM narrative call —
  `monitor_cmd.py` constructs the empty per-fund `NarrativeDoc` directly, and
  `tests/commands/test_monitor_cmd.py::test_run_monitor_never_calls_gather_narrative_per_fund`
  pins `not hasattr(monitor_cmd, "gather_narrative")` as a contract. The module also
  carried the unguarded `strength not in _VALID_STRENGTH` membership test — the latent
  unhashable-`attribution_strength` `TypeError` twin of the `narrative_macro.py`
  hardening above — so deletion removes the last copy of that bug class. Mirror tests
  `tests/monitor/test_narrative.py` deleted with it; the stale `NarrativeResult` import
  and inert `raising=False` `gather_narrative` monkeypatch scaffolding removed from
  `tests/commands/test_monitor_cmd_theme_consolidation.py`. Shared dataclasses
  (`NarrativeDoc`, `Claim`, `EvidenceItem`) live in `src/irc/monitor/types.py` and are
  untouched, as is the `monitor_narrative` LLM task (it is the macro narrative's route).
  No VERSION bump.

### Fixed — ActiveFundSnapshot thesis gate: dual-leg (data + information) check extended to the active-fund branch (2026-07-03)
```

Fallback (only if the first `###` heading under `## [Unreleased]` is no longer the
ActiveFundSnapshot one because another item merged first): insert the same
`### Removed …` block — everything between the two `### Fixed — ActiveFundSnapshot…`
lines above, i.e. heading + blank line + the single bullet + trailing blank line —
immediately after the `## [Unreleased]` line and its following blank line, BEFORE
whatever subsection is currently first. Do not reword the entry.

- [ ] **Step 2: Verify the doc edit landed — and that AC7 is honored (NO TODOS.md edit, NO VERSION bump)**

Run: `grep -n "Removed — production-dead per-fund narrative module" CHANGELOG.md`
Expected: exactly 1 match, on a line inside `[Unreleased]` (line number ≈ 10).

Run: `git diff --name-only`
Expected output — exactly one line:

```
CHANGELOG.md
```

If `TODOS.md` or `VERSION` appears: STOP and revert that file — AC7 forbids any TODOS.md
edit for this item (it was flagged only in item-001's spec Non-goals; no open entry exists
and none may be added), and the versioning convention forbids a per-feature VERSION bump.

- [ ] **Step 3: Final sanity re-run (docs must not change test/lint state)**

Run: `uv run pytest tests/commands/test_monitor_cmd_theme_consolidation.py -q`
Expected: `6 passed`

Run: `uv run ruff check tests/commands/test_monitor_cmd_theme_consolidation.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit the bookkeeping**

```bash
git add CHANGELOG.md
git commit -m "docs(monitor): CHANGELOG Removed entry for dead narrative.py deletion"
```

Expected: commit created with exactly 1 file. Do NOT push, do NOT open a PR — the orchestrator ships.

---

## Acceptance-criteria → step map (self-review record)

| Spec AC | Where satisfied |
| --- | --- |
| AC1 module deleted | Task 1 Step 3 (`git rm`), Step 6 (`git status` shows `D src/irc/monitor/narrative.py`) |
| AC2 mirror tests deleted | Task 1 Step 3, Step 6 |
| AC3 stale import + monkeypatch removed; remaining tests pass | Task 1 Step 4 (Edits 4a/4b, verbatim), Step 8 (`6 passed`) |
| AC4 zero-reference greps | Task 1 Step 2 (detector proven pre-deletion), Step 5 (both greps empty, exit 1); corrected-command rationale in Global Constraints |
| AC5 surviving suite passes (per-file discipline) | Task 1 Step 7 (`tests/monitor/` whole dir, 920 passed/12 skipped), Step 8 (theme-consolidation per-file), Step 9 (contract test targeted + `test_monitor_cmd.py` per-file, 24 passed) |
| AC6 CHANGELOG Removed entry, no VERSION bump | Task 2 Steps 1–2 |
| AC7 no TODOS.md edit | Global Constraints + Task 2 Step 2 (`git diff --name-only` = `CHANGELOG.md` only) |
| Spec constraint: deletion item, no new tests | Global Constraints (explicit); no test-writing step exists in this plan |
| Spec Non-goals: types.py / narrative_macro.py / broader refactor untouched | Global Constraints do-not-touch list; Task 1 Step 4 limited to the two verbatim edits |
