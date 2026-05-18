# Phase 3 — cross-branch validation report

## What this run delivered (Phase 1, 10 items)

| ID | Title | Commit |
|---|---|---|
| 001 | Package `evals/` for installed CLI + regression test | `4210142` |
| 002 | Eval registry with lifecycle classification | `bed0454` |
| 003 | Shared artifact locator | `e537022` |
| 004 | Report-date policy follows source | `7440def` |
| 005 | Discovery runner modernization | `264a679` |
| 006 | Gold_score runner modernization | `170b56b` |
| 007 | Allocation runner modernization | `b368ead` |
| 008 | Trade_plan runner modernization | `b40d5a1` |
| 009 | Memo runner modernization | `9873efc` |
| 010 | Architecture runner modernization | `6980862` |

## Cross-cutting validation

| Check | Result |
|---|---|
| `uv run pytest` (full repo) | 1194 passed, 20 skipped, 0 failed |
| `uv run pytest tests/evals` | 190 passed |
| `uv run irc eval research` | no `ModuleNotFoundError`; reaches runner (FAIL "no input file" — expected when artifacts absent) |
| `uv run irc eval news` | inactive-stage message, rc=2 — no misleading missing-input report |
| `uv run irc eval queries` | inactive-stage message, rc=2 |
| `uv run irc eval --all` | runs 11 active stages only (data, research, discovery, scoring, gold_score, allocation, trade_plan, memo, architecture, opportunity, triggers); excludes news + queries |
| Branch up-to-date with `origin/main` | merged at `449615d` |

## Active suite behavior against an empty worktree

Without producer artifacts in `outputs/`, the active suite reports:

```
PASS data
FAIL research      (no data/research/research_status.json)
FAIL discovery
FAIL scoring
FAIL gold_score
FAIL allocation
FAIL trade_plan
FAIL memo
FAIL architecture  (0/7 producer artifacts in latest outputs/<date>/)
FAIL opportunity
FAIL triggers      (unimplemented — honest signal)
```

Every FAIL is now traceable to a real, current artifact contract. Reruns against an actual pipeline output set will surface only honest signal — Phase 1's acceptance criterion.

## Phase 2 status

Out of scope for this run; see [SKIPPED.md](SKIPPED.md). Each runner's report `notes` lists the metrics deferred for that stage so a future Phase 2 owner can pick them up directly.

## Honest red after rerun

Spec §Risks-and-trade-offs warned:

> Phase 1 will probably still end red. That is success, not failure, if the remaining red is honest.

In this worktree the suite IS red. The red comes from:

- Missing producer artifacts (the worktree never ran `irc discover`, `irc score`, etc.).
- `triggers` intentionally unimplemented.

Neither is a defect in this Phase 1 work.
