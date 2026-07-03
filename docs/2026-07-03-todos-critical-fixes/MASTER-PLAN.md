# MASTER-PLAN — TODOS.md critical fixes

Mode: **backlog**
PR shape: **A** (per-item PRs into the feature branch; no `--rollup` opt-in this turn)
Project type: **non-web** (Python CLI — post-ship verifier is `/verify`, never `/qa`)
Feature branch: `autodev/todos-critical-fixes-feature` (synthesized off `main` @ 221a34e4, pushed)
Branch prefix: `claude/todos-critical-fixes-` (e.g. `claude/todos-critical-fixes-001`)
Run dir: `docs/2026-07-03-todos-critical-fixes/`
Item order: 001, 002, 005, 004 (001/002/004 locked 2026-07-03 after dependency scan;
005 appended mid-run by direct user instruction and slotted after 002 — small, independent
of 002/004, user-requested promptly. 005's spec is user-authored in-turn → spec + grill
dispatches ⏭️ pre-completed for that item only; plan onward runs normally.)

Dependency-scan outcome: no hard cross-item dependencies; ordering is smallest-first with
same-file adjacency (002 before 004 keeps `opportunity_cmd.py` edits from interleaving).
Item 003 RECLASSIFIED OUT during the scan review: the venue wiring already exists on main
(`inputs_build.py` ← `opportunity_cmd.py:1497`), and the small_watch demotion was
deliberately removed by PR #25 (`ae5a7d88`). TODOS.md annotated as resolved (doc-only).

## Per-item pipeline (backlog mode, no shortcuts)

spec (brainstorming) → grill (grill-with-docs auto-accept) → plan (writing-plans)
→ branch → impl (Sonnet subagent-driven-development) → drift (Sonnet)
→ ship (/ship: PR + inline review) → [verify ‖ pr-review] (Sonnet) → fix loop → merge (squash into feature branch)

Model contract: spec/grill/plan subagents omit `model=` (inherit session model);
impl/drift/verify/pr-review/fix subagents use `model="sonnet"`.
Every worker dispatch carries the literal line "Calling the Agent tool is FORBIDDEN"
(repo memory: workers have gone meta and delegated to phantom children).

## Merge policy

- Sub-PRs squash-merge into `autodev/todos-critical-fixes-feature` only after all gates pass
  (drift + ship + verify + review + pr-review + grill).
- The feature branch is NEVER merged to `main` by this run — Phase 3 opens a roll-up PR
  `autodev/todos-critical-fixes-feature → main` and leaves it open for the user.

## Run-level gates (end of Phase 2)

- `run-doc-sync.md` (Sonnet) — CONTEXT.md / ADR / README coverage vs merged diff.
- `run-final-verify.md` (Sonnet `/verify`) — integrated smoke on the feature branch.

## Test discipline (binding)

- `uv run pytest tests/<mirror-dir>` per touched module + grep-caller sweep on signature changes.
- `tests/commands/` per-file only (whole-dir hangs).
- `uv run ruff check src tests` before every ship.
- Never run the full ~61-min suite as a gate; diff-scope any failure against main first.
