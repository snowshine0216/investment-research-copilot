# Item 005 — delete production-dead `src/irc/monitor/narrative.py` (user-directed)

Run: todos-critical-fixes · Date: 2026-07-03 · Source: user instruction mid-run (verbatim intent below) + orchestrator investigation.
Spec authorship: USER (in-turn, with explicit decision procedure) — spec/grill dispatches ⏭️ pre-completed.

## Goal

`src/irc/monitor/narrative.py` carries the same unguarded `strength not in _VALID_STRENGTH`
membership test that item 001 fixed in `narrative_macro.py` (`_parse_claims`, ~line 40:
unhashable LLM shape → TypeError escaping `gather_narrative`'s retry loop). The user directed:
if the module is confirmed fully dead in production, DELETE it and its now-unnecessary tests
(precedent: the "Delete dead `_read_prior_signal`" TODOS.md pattern); only if still reachable,
apply the isinstance hardening instead.

**Investigation verdict (orchestrator, 2026-07-03): DEAD — take the deletion path.**

Evidence:
- `grep -rn "gather_narrative" src/` → only its own `def` at `narrative.py:74`. No
  `from irc.monitor.narrative import` anywhere under `src/`.
- Shared dataclasses (`NarrativeDoc`, `Claim`, `EvidenceItem`) live in
  `src/irc/monitor/types.py`, NOT in narrative.py — render/dump/production code imports them
  from types.py. `NarrativeResult` (defined in narrative.py) has no src/ consumer.
- Production constructs the per-fund empty doc directly:
  `monitor_cmd.py:923  empty_narr = NarrativeDoc(fund.id, (), (), (), "empty_pool")` — the
  report-v3 comment at monitor_cmd.py:848 records "the per-fund LLM narrative call is GONE".
- `tests/commands/test_monitor_cmd.py:420-425` (report v3 spec §5) asserts
  `not hasattr(mc, "gather_narrative")` — the DROP is contractual, not accidental.

## Acceptance criteria

- AC1: `src/irc/monitor/narrative.py` deleted.
- AC2: `tests/monitor/test_narrative.py` deleted (mirror tests of the dead module only).
- AC3: `tests/commands/test_monitor_cmd_theme_consolidation.py` no longer imports
  `irc.monitor.narrative` (line ~150 `from irc.monitor.narrative import NarrativeResult`)
  and no longer monkeypatches `mc.gather_narrative` (lines ~172-176, the `raising=False`
  stale scaffolding); the test file's remaining tests still pass unchanged.
- AC4: `grep -rn "monitor.narrative\b\|from irc.monitor.narrative" src/ tests/` → zero hits
  (narrative_macro references excluded by the word boundary).
- AC5: `uv run pytest tests/monitor/ -q` passes; `uv run pytest
  tests/commands/test_monitor_cmd_theme_consolidation.py -q` and
  `uv run pytest tests/commands/test_monitor_cmd.py -q` pass PER-FILE (whole-dir hangs).
  In particular `test_run_monitor_never_calls_gather_narrative_per_fund` still passes
  (it asserts on monitor_cmd's namespace, unaffected by module deletion).
- AC6: CHANGELOG.md [Unreleased] gets a "Removed" entry naming the module, the reason
  (production-dead since report v3; latent unguarded-membership TypeError twin of the
  item-001 fix), and the test cleanup. VERSION not bumped.
- AC7: TODOS.md: no entry exists for this (it was flagged in item-001's spec Non-goals);
  no TODOS edit required beyond none — do NOT add a new open item for it.

## Non-goals

- Do NOT touch `src/irc/monitor/types.py` (NarrativeDoc/Claim stay — production render path).
- Do NOT touch `narrative_macro.py` (item 001, already merged).
- Do NOT refactor `test_monitor_cmd_theme_consolidation.py` beyond removing the stale lines.
- Do NOT delete `_read_prior_signal` here (separate TODOS item, separate scope).

## Constraints

- Repo conventions: effects at edges, files <200 lines (deletion only helps), no VERSION bump.
- TDD note: this is a pure deletion; the "test" is the surviving suite passing + the greps
  in AC4. No new tests required (deleting dead code needs no regression test; the
  namespace-drop contract test already exists in test_monitor_cmd.py).
- tests/commands/ per-file execution discipline applies.

## Resolved decisions

- Q: Delete vs harden? A: Delete — user's decision procedure, branch (1), evidence above.
- Q: Does anything import NarrativeResult? A: Only the stale theme-consolidation test line —
  removed by AC3.
- Q: Keep test_narrative.py as documentation? A: No — it tests only the deleted module's
  internals; keeping it would keep the module alive.
