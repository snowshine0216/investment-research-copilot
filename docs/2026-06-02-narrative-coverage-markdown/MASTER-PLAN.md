# MASTER-PLAN — narrative coverage gap + markdown

**Mode:** backlog
**Project type:** non-web
**PR shape:** A (per-item PRs into the feature branch; no `--rollup`)
**Authoring model:** Full Opus (spec / grill / plan all on Opus — user choice; no Sonnet override)
**Item order:** 001, 002, 003, 004 (locked via dependency scan — coverage-gap items first so markdown renders real enriched evidence; same-file changes adjacent to minimize rebase; 003 → 004 since 004 suppresses fields 003 adds)
**Token ceiling (soft):** ~1.2M tokens for the run; STOP and confirm if approached.

## Branch strategy

- Base / default branch: `main` (**protected** — autodev never auto-merges here; no opt-in given this turn).
- Feature branch (synthesized off `main`): `autodev/narrative-coverage-markdown-feature` — all sub-PRs land here; left open at end of run for the user to review + land.
- Per-item sub-branches: `claude/narrative-coverage-markdown-<id>` (e.g. `claude/narrative-coverage-markdown-001`), PR'd into the feature branch.

## Per-mode skill invocations (backlog — none skipped)

| Phase | Skill / dispatch | Model |
|-------|------------------|-------|
| spec | `superpowers:brainstorming` | Opus |
| grill | `grill-with-docs` (auto-accept) | Opus |
| plan | `superpowers:writing-plans` | Opus |
| impl | `superpowers:subagent-driven-development` | Sonnet |
| drift | in-prompt diff-vs-plan | Sonnet |
| ship | `/ship` (PR + docs + inline review) | Sonnet |
| verify | `/verify` (non-web; XOR with qa) | Sonnet |
| pr-review | `/code-review` on open PR | Sonnet |
| fix | triage loop, re-run failing verifier(s) | Sonnet |

## Run-level gates (end of Phase 2)

- `run-doc-sync.md` — CONTEXT.md / docs/adr / README coverage of all merged functional changes.
- `run-final-verify.md` — `/verify` smoke against the integrated feature branch (CLI entry: `uv run irc narrative ... --analyze`).

## Conventions enforced (from CLAUDE.md / CONTEXT.md / ADRs)

- TDD red→green→refactor; tests mirror source (`foo.py` → `tests/.../test_foo.py`).
- Functional/immutable; effects at edges; files <200 lines, functions <20 lines (ideal).
- Versioning: accumulate under CHANGELOG `[Unreleased]` at static VERSION (0.9.3); do NOT bump VERSION per feature PR (project memory).
- Respect ADR 0001 (citation id), 0003 (Policy B), 0004 (renderer determinism / SAME-3); H3 invariant.
