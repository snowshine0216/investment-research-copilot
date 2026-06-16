# MASTER-PLAN — Monitor Eval M3 backtest

**Mode:** `spec`
**Project type:** non-web
**PR shape:** A (per-item PR; no `--rollup` in invocation)
**Feature branch:** `claude/stupefied-swirles-a9365f` (current worktree branch — non-default, non-protected; sub-branch PRs land here)
**Base for final roll-up:** `main` (roll-up PR opened, NOT merged — left for the user)
**Run dir slug:** `monitor-eval-m3-backtest`
**Sub-branch:** `claude/monitor-eval-m3-backtest-001`

## Per-mode skill skips (spec mode)

| Phase | Skill | This run |
|-------|-------|----------|
| spec (brainstorming) | `superpowers:brainstorming` | **SKIP ⏭️** — user authored the design spec; brainstorming would rewrite intent |
| grill | `grill-with-docs` | **SKIP ⏭️** — user-grilled (9 documented review rounds in the spec appendix); orchestrator must NOT auto-invoke |
| plan | `superpowers:writing-plans` (Opus) | **RUN** — ENTRY phase; authors `items/001-plan.md` from the refined spec |
| impl | `superpowers:subagent-driven-development` (Sonnet) | RUN |
| drift | in-prompt (Sonnet) | RUN |
| ship | `/ship` | RUN — opens PR + docs + inline review |
| post-ship verify | `/verify` (non-web → XOR; NOT `/qa`) | RUN |
| pr-review | `/code-review` | RUN |
| fix | Sonnet triage | RUN if any post-ship verdict FAILs |
| merge | `gh pr merge --squash` (Mode A) | RUN — into the feature branch, after pre-merge gate |

## Workflow rules

- **N=1.** Single IN-scope item; loop runs once. Phase 3 collapses to build/test sanity + doc-sync + `/verify` smoke.
- **TDD enforced** (project CLAUDE.md + global FP guidance): every pure core is test-first.
- **Functional/immutable**, effects at edges (runner + producer + migration are the only EDGE surfaces; stats/baselines/backtest/forward_score/panel are pure).
- **Protected-branch guard:** sub-branch PR base = `claude/stupefied-swirles-a9365f` (non-protected) — allowed. Roll-up PR into `main` is **opened, never auto-merged**.
- **Loop exit:** all three post-ship verdicts (`verify` + inline `review` + `pr-review`) PASS / PASS-WITH-NITS. Environmental stops only — no retry budget.

## Key spec constraints to carry into the plan

- No paid surface (no LLM, no web search) — `monitor_forward` is not `live_gated`, no spend gate / recorder.
- `active, in_all_suite=False` — must stay OUT of the green `--all` suite (`active_suite_stages()`); document the registry category.
- Three-date model (`as_of_date` / `run_date` / `entry_nav_date`) kept strictly separate; entry strictly `>` `run_date`.
- `FORWARD_H=20` has two units (NAV-obs window vs run-date block) — must be documented "H run-date block".
- Retro grid floor sourced from `minimum_observations` (config 251), NOT a new literal.
- WARN-max for statistical weakness; FAIL only for input-contract / scorer-invariant; `bad_nav` = row-level exclusion.
