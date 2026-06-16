# MASTER-PLAN — Monitor Eval M0 + M1

Mode: backlog
Project type: non-web
PR shape: A
Feature branch: monitor-eval
Base for final roll-up PR: main (opened, NOT merged at close-out — protected branch)
Item order: 001, 002    # locked after dependency scan (M1 depends on M0)
Branch prefix: claude/monitor-eval-m0-m1-

## Per-mode skill invocations (backlog)

Every item runs the full pipeline — no shortcuts:

| Phase | Skill / dispatch | Model |
|-------|------------------|-------|
| spec | `superpowers:brainstorming` (faithful extraction of the milestone slice — see MASTER-SPEC rationale) | opus |
| grill | `grill-with-docs` (auto-accept) | opus |
| plan | `superpowers:writing-plans` | opus |
| impl | `superpowers:subagent-driven-development` | sonnet |
| drift | in-prompt diff-vs-plan | sonnet |
| ship | `/ship` (PR + docs + inline review) | sonnet (dispatch) |
| post-ship verify | `/verify` (non-web — QA is N/A) | sonnet |
| pr-review | `/code-review` on the open PR | sonnet |
| fix | triage + fix loop | sonnet |
| merge | `gh pr merge --squash --delete-branch` into `monitor-eval` | — |

No `Sonnet override:` (N=2 < 5; full Opus authoring).

## Post-ship XOR

Project type is **non-web** → exactly `/verify` per item (`items/<id>-verify.md`).
`/qa` is NOT run; the QA column in PROGRESS.md is pre-filled ⏭️.

## Run-level gates (end of Phase 2)

- `run-doc-sync` (Sonnet) — CONTEXT.md / docs/adr/** / README.md coverage for all merged items.
  Relevant docs: CONTEXT.md "Monitor set" section; ADR 0017 (monitor evidence isolation).
- `run-final-verify` (Sonnet `/verify`) — end-to-end `irc monitor` smoke on the integrated
  feature branch (must emit `eval_trace.json` + ledger + panel) and `irc eval monitor_signal`.

## Per-item exit contract

drift PASS + ship PASS + `/verify` PASS + review (inline from /ship) PASS|PASS-WITH-NITS +
pr-review PASS|PASS-WITH-NITS + grill PASS. No retry budget — environmental stops only.

## Protected-branch guard

`monitor-eval` is non-protected → sub-PRs merge into it. `main` is protected and the default
branch → autodev never merges into it; close-out opens the roll-up PR and leaves it for the user.
