# MASTER-PLAN — Monitor report v4 explainability

**Mode:** backlog
**Project type:** non-web  (Python CLI `irc` — post-ship verifier is `/verify`, never `/qa`)
**PR shape: A** — per-item PRs into the feature branch (no `--rollup` in the invocation)
**Feature branch:** `autodev/monitor-v4-explainability-feature` (synthesized off `main`; no protected-branch merge opt-in this turn — the Phase 3 roll-up PR into `main` is opened but NOT merged; user lands it)
**Branch prefix:** `claude/monitor-v4-explainability-<id>`
**Run dir:** `docs/2026-07-03-monitor-v4-explainability/`

Item order: 003, 001, 002, 004
(Locked at grill 2026-07-03 in the source spec: WS-3 → WS-1 → WS-2 → WS-4. Confirmed by dependency scan — see PROGRESS.md notes.)

## Per-mode phase contract (backlog — no skips)

Every item runs the full pipeline: spec (brainstorming) → grill (grill-with-docs auto-accept) → plan (writing-plans) → branch → impl (subagent-driven-development, Sonnet) → drift (Sonnet) → ship (/ship, inline review) → verify (/verify, Sonnet) ‖ pr-review (/code-review, Sonnet) → fix loop → merge (squash into feature branch).

- Spec/grill/plan subagents: **no model override** (inherit session model).
- Impl/drift/verify/pr-review/fix subagents: **model="sonnet"**.
- No Sonnet override for spec/plan (N=4 < 5; no cost opt-in requested).
- Every worker dispatch carries the literal line "Calling the Agent tool is FORBIDDEN" (memory: subagent meta-delegation trap).

## Cross-item constraints (from source spec §2 P9 + acceptance §4)

1. `_ENGINE_VERSION` untouched in every item — acceptance-tested.
2. ONE eval-trace `schema_version` bump 6→7 for the whole run. First item to land a new trace field carries it (expected: 001, which populates `gate.reason`; 002 and 004 add fields under the already-bumped 7).
3. Narrative prompt version 2→3 lands with 002 only.
4. `flow_reconciliation` byte-identical after 004 (f127 must not perturb f184 parsing).
5. Lint + tests per item: `uv run ruff check src tests`, `uv run pytest tests/monitor/`, and `tests/commands/` **per-file** (whole-dir hangs).
6. Docs sync per standing convention: `docs/monitor/README.md` ops manual + workflow diagram updated alongside monitor changes (mainly 001 weekly wrapper + 004).

## Post-merge ops (NOT autodev's to run — recorded for close-out summary)

One manual `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact` + `monitor_narrative` (clears today's caveats) → reinstall the weekly launchd agent (wrapper changed in 001) → verify next 12:15 brief.
