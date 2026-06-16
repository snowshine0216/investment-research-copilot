# MASTER-PLAN — Monitor Eval M2 (Deterministic Rigor)

**Mode:** spec
**Project type:** non-web
**PR shape:** A (per-item PRs; default — no `--rollup` in invocation)
**Feature branch:** `claude/xenodochial-cohen-339150`
**Sub-branch prefix:** `claude/monitor-eval-m2-`
**Final roll-up base:** `main` (Phase 3 opens a feature-branch PR into `main`; opened, not merged)

## Per-mode skill skips (spec mode)

| Phase | Skill | Status in this run |
|-------|-------|--------------------|
| spec (authoring) | `superpowers:brainstorming` | ⏭️ skipped — user authored the spec (verbatim copy at `items/001-spec.md`) |
| grill | `grill-with-docs` | ⏭️ pre-completed — user-grilled (spec is rev 3, adversarial-review folded in). Orchestrator MUST NOT auto-invoke. |
| plan | `superpowers:writing-plans` (Opus) | **runs** — ENTRY phase |
| impl | `superpowers:subagent-driven-development` (Sonnet) | runs |
| drift | in-prompt (Sonnet) | runs |
| ship | `/ship` (captures inline review) | runs |
| post-ship verify | `/verify` (non-web → XOR; **no `/qa`**) | runs |
| pr-review | `/code-review` | runs |
| fix | Sonnet triage subagent | runs if any of the 3 post-ship verdicts FAIL |
| merge | `gh pr merge --squash --delete-branch` (Mode A) | pre-merge gate then merge into feature branch |

## Model contract

- Orchestrator: session default (Opus 4.8) — no override.
- plan subagent: `model="opus"`.
- impl / drift / verify / pr-review / fix subagents: `model="sonnet"`.

## Loop exit contract (item 001)

Merge only when ALL THREE post-ship verdicts are PASS / PASS-WITH-NITS:
1. `/verify` (non-web) → `items/001-verify.md` `^Verdict: PASS`
2. review (inline from `/ship` steps 8+9) → `items/001-review.md` `^Verdict: PASS|PASS-WITH-NITS`
3. `/code-review` → `items/001-pr-review.md` `^Verdict: PASS|PASS-WITH-NITS`

Plus presence: `items/001-spec.md`, `items/001-plan.md`; drift `items/001-drift.md` `^Verdict: PASS`; ship `items/001-ship.md` `PR: https://…`. Grill verdict absence-OK (PROGRESS ⏭️ user-grilled).

## Verification commands (project)

- `uv run pytest` — unit + integration (no network)
- `uv run pytest tests/monitor/ -q` — monitor suite (D1 + D2 land here)
- `uv run ruff check src tests` — lint (line-length 100, py312)
- `uv run irc eval monitor_signal` — confirm M0 oracle still passes (D2 is a superset, must not regress)
- Determinism: hypothesis `derandomize=True` profile loaded in `tests/conftest.py`; suite must stay sub-second and offline.
