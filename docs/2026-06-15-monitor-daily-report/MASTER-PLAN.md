# MASTER-PLAN — `irc monitor` daily brief

Mode: **spec** (N=1)
Project type: **non-web**   <!-- post-ship verifier = /verify (NOT /qa) -->
PR shape: **A** (per-item PR into the feature branch; no `--rollup`)

## Branch strategy

- Default/protected base: `main` (no "merge to main" opt-in given this turn → never auto-merged).
- **Feature branch (synthesized):** `autodev/monitor-daily-report-feature`, cut off `main`. All sub-PRs land here. Left **open** at end of run as a roll-up review surface; the user lands it into `main` themselves.
- Per-item sub-branch: `claude/monitor-daily-report-001` off the feature branch.

## Per-mode skill skips (spec mode)

| Phase | Skill | Status |
|-------|-------|--------|
| spec (brainstorming) | `superpowers:brainstorming` | **SKIPPED** — user authored the spec; brainstorming would rewrite intent |
| grill | `grill-with-docs` | **SKIPPED ⏭️** — already grilled (source §14); orchestrator must NOT auto-invoke |
| plan | `superpowers:writing-plans` (Opus) | **RUNS — ENTRY phase** |
| impl | `superpowers:subagent-driven-development` (Sonnet) | runs |
| drift | in-prompt Sonnet logic | runs |
| ship | `/ship` (PR + docs + inline review) | runs |
| post-ship verify | `/verify` (non-web XOR; **no `/qa`**) | runs |
| pr-review | `/code-review` on open PR | runs |
| fix | Sonnet triage subagent | as needed |
| merge | `gh pr merge --squash --delete-branch` (Mode A) into feature branch | runs |

## Loop exit contract (item 001)

Merge only when ALL on-disk verdicts satisfy:
- `items/001-drift.md` → `^Verdict: PASS`
- `items/001-ship.md` → first line `PR: https://…`
- `items/001-verify.md` → `^Verdict: PASS` (non-web XOR; no qa.md)
- `items/001-review.md` → `^Verdict: PASS|PASS-WITH-NITS` (captured inline by `/ship` steps 8+9)
- `items/001-pr-review.md` → `^Verdict: PASS|PASS-WITH-NITS` (`/code-review`)
- `items/001-spec.md` + `items/001-plan.md` present
- Grill verdict **absence-OK** (PROGRESS shows ⏭️ user-grilled)

## Model contract

| Role | Model |
|------|-------|
| Orchestrator (this session) | session default (no override) |
| plan subagent (writing-plans) | **opus** |
| impl / drift / verify / pr-review / fix subagents | **sonnet** |

## Project conventions enforced (from CLAUDE.md / CONTEXT.md / ADRs)

- **TDD** red→green→refactor; test file mirrors source (`foo.py` → `tests/.../test_foo.py`).
- **Functional, immutable**; effects at edges (`commands/`, thin wrappers); files <200 lines, functions <20 lines ideal.
- Secrets in `.env` only; YAML references env var names.
- Citation ID = 16 hex, regex `\[ref:[0-9a-f]{16}\]`.
- `基金概况` indicator forbidden in production fetch code (acceptance test greps for it).
- ADR 0017 (monitor evidence isolation) + CONTEXT.md monitor terminology are prerequisite docs committed with this run.
