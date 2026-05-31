# MASTER-PLAN — Funding analysis enhancements

- **Mode:** backlog
- **Project type:** non-web  (Python CLI `irc`; post-ship verifier = `/verify`, never `/qa`)
- **PR shape:** A  (per-item PRs into the feature branch)
- **Sonnet override:** none  (Opus authoring for spec + grill + plan on all items)
- **Feature branch:** `autodev/funding-analysis-feature`  (sub-branches `claude/funding-analysis-<id>`)
- **Base for sub-PRs:** `autodev/funding-analysis-feature`  (NOT `main` — main is protected; no opt-in given)
- **Item order:** 001, 002, 004, 003, 005  (locked after dependency scan — see `dependency-scan.md`)
- **Soft token ceiling:** lifted by user 2026-05-31 after item 001 ("Continue all 4"); real cost ~700-900K/item, ~2.5-3.5M for items 002/004/003/005. Run to completion, no further cost check-ins unless environmentally blocked.

## Per-mode skill invocations (backlog — no skips)

| Phase | Skill / dispatch | Model |
|-------|------------------|-------|
| spec | `superpowers:brainstorming` | Opus |
| grill | `grill-with-docs` (auto-accept) | Opus |
| plan | `superpowers:writing-plans` | Opus |
| impl | `superpowers:subagent-driven-development` | Sonnet |
| drift | in-prompt diff-vs-plan | Sonnet |
| ship | `/ship` (PR + docs + inline review) | Sonnet |
| verify | `/verify` (non-web XOR — never `/qa`) | Sonnet |
| pr-review | `/code-review` on the open PR | Sonnet |
| fix | triage + fix loop | Sonnet |
| merge | `gh pr merge --squash --delete-branch` (Mode A) | orchestrator |

## Per-item exit contract

Three post-ship verdicts — verify + review (inline from `/ship`) + pr-review — all PASS / PASS-WITH-NITS, plus drift + ship PASS, plus grill PASS. No retry budget; environmental stops only.

## Run-level gates (end of Phase 2)

1. `run-doc-sync` (Sonnet) — CONTEXT.md / `docs/adr/**` / README cover every functional change.
2. `run-final-verify` (Sonnet `/verify`) — smoke the integrated feature branch (`uv run irc …`).

Close-out leaves the feature branch open for the user to land into `main`.

## Standing test/lint commands (every item)

```
uv run pytest                       # unit + integration (no network)
uv run pytest -m integration        # cross-module
uv run ruff check src tests         # lint (line-length 100, py312)
```

Live network tests stay double-gated (`-m live_akshare` + `IRC_RUN_LIVE_AKSHARE=1`; new Tushare marker + its env var).
