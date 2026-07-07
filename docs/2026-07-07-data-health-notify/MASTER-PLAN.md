# MASTER-PLAN — data-health-notify

- **Mode:** spec — brainstorming ⏭️ (user-provided spec), grill ⏭️ (user-grilled 2026-07-07, §9 grill log). writing-plans RUNS (Opus). Everything downstream runs unchanged.
- **Project type:** non-web (Python CLI `irc`) → post-ship verifier is **/verify**, never /qa.
- **PR shape:** A (per-item PRs; no `--rollup` in the invocation).
- **Feature branch:** `autodev/data-health-notify-feature` (synthesized off `main` @ 9cf85ac3; pushed). Protected-branch rule: nothing merges to `main`; the feature branch is left open at run end as the roll-up review surface.
- **Sub-branch:** `claude/data-health-notify-001` (cut off the feature branch at the branch phase).
- **Item order:** 001 only (N=1).
- **Model contract:** plan subagent = `model="opus"`; impl/drift/verify/pr-review/fix subagents = `model="sonnet"`. Every dispatch declares `model=` explicitly.

## Workspace (important for resume)

Work happens in the git worktree `.claude/worktrees/data-health-notify` (session entered via EnterWorktree; main tree must stay on `main` — launchd scheduled runs execute whatever is checked out there, and the main tree holds the user's uncommitted review-session edits to CLAUDE.md/README.md/FACTS.md which must NOT be swept into this feature).

Worktree plumbing (all gitignored / locally excluded):
- `outputs -> <main>/outputs`, `data -> <main>/data` symlinks (anchored `/data`,`/outputs` added to `.git/info/exclude`) — for AC1–AC5 runtime proofs against today's real artifacts.
- `config/` = tracked files + overlay-copy of main's untracked runtime YAML (identical tracked content, zero diff).
- `.env` copied from main. It contains **no `IRC_FEISHU_WEBHOOK_URL`** → runtime proofs fire macOS osascript notifications only, never Feishu. Do not add a webhook.

## Hard constraints (spec §10 + repo scar tissue — every worker prompt carries the relevant ones)

1. Every worker-subagent dispatch carries the literal line **"Calling the Agent tool is FORBIDDEN"**.
2. **Never run `pytest tests/commands/` whole-dir** — per-file only (documented hang).
3. `_build_health` fixtures MUST be production-shaped: copy real 2026-07-07 `eval_trace.json` / `rotation_radar.json` / `fund_flow_series.json` / 07-04 `gold_regime.json` shapes — never hand-craft.
4. Signature changes to `RunOutcome` / `classify_run_outcome`: grep ALL test callers (`tests/notify/`, `tests/commands/test_notify_cmd.py`, `tests/ops/`), not just the mirror file.
5. AC1–AC5 are runtime proofs against today's real artifacts — capture rendered notification bodies as evidence before claiming done.
6. TDD throughout; **no VERSION bump** (accumulate under CHANGELOG `[Unreleased]`).
7. ADR 0016 amendment + AC6 doc syncs land in the same branch as the code.
8. On completion add TODOS entries: trend-persistence deferral (G-Q7); monitor DARK→FRESH recovery-notice generalization (G-Q3).
9. Workers run irc commands against the symlinked real artifacts ONLY as `irc notify-status` (read-only + local notification). Never `irc monitor` / `irc run` / `irc rotation` / `flow-capture` from the worktree (real-data mutation + DuckDB single-writer).
10. FP + size budget per CLAUDE.md: pure builders, frozen dataclasses, files <200 lines, functions <20 lines, effects at edges.

## Baseline (verified 2026-07-07 16:30 in worktree)

`tests/notify/ tests/ops/` → 112 passed · `tests/commands/test_notify_cmd.py` → 26 passed. Affected areas green.

## Phase sequence (mode-spec contract)

spec ⏭️ → grill ⏭️ → plan (Opus writing-plans) → branch → impl (Sonnet subagent-driven-development) → drift → ship (/ship: PR + inline review) → [/verify ‖ /code-review] → fix loop → merge (into feature branch) → Phase 3 (doc-sync, run-level verify, feature-branch PR opened not merged).
