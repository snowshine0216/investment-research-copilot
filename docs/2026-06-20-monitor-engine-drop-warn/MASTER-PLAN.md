# MASTER-PLAN — Monitor forward-eval engine-drop WARN (FU1)

**Mode:** spec
**Project type:** non-web    # Python CLI — post-ship verifier is `/verify`, not `/qa`
**PR shape:** A    # per-item PRs (no `--rollup` in the invocation)

## Branch strategy

- **Default branch:** `main` (protected — never auto-merged).
- **Feature branch (synthesized):** `autodev/monitor-engine-drop-warn-feature` — cut off `main`. All sub-PRs land here. Left **open** at end of run as a roll-up review surface; the user lands it onto `main`.
- **Item sub-branch:** `claude/monitor-engine-drop-warn-001` — cut off the feature branch. Sub-PR base = the feature branch.

## Per-mode skill skips (spec mode)

| Phase | Status | Reason |
|-------|--------|--------|
| brainstorming | ⏭️ skipped | User authored the spec; brainstorming would rewrite intent. |
| grill | ⏭️ pre-completed | Spec status = *"Approved (brainstorming + spec grill 2026-06-20)"* — user already grilled. Orchestrator must NOT auto-invoke. |
| writing-plans | ✅ runs | Opus `superpowers:writing-plans` reads the spec → `items/001-plan.md` (ENTRY). |

## Phase sequence (per item)

```
spec (⏭️) → grill (⏭️) → plan (Opus writing-plans)
  → branch → impl (Sonnet subagent-driven-development) → drift (Sonnet)
  → ship (/ship: PR + docs + inline review)
  → [(verify) ‖ pr-review]  (non-web → /verify, NOT /qa)
  → fix → merge (into feature branch)
```

## Models (subagent contract)

- Orchestrator: session default (no override).
- plan: **opus**.
- impl / drift / verify / pr-review / fix: **sonnet**.

## Verdict files required before merge (loop exit contract)

`items/001-{drift,ship,verify,review,pr-review}.md` all `^Verdict: PASS|PASS-WITH-NITS`
(`verify` is the non-web XOR branch — no `qa.md`), plus `001-spec.md` + `001-plan.md`
presence. Grill verdict is absence-OK in spec mode (PROGRESS ⏭️).

## Verification discipline (from source spec §7)

Run the **whole** `tests/evals/`, `tests/monitor/`, and `tests/commands/` dirs
(not just the mirror) before claiming green — the runner output feeds all three,
and a prior signature-change regression hid in `tests/commands/` while
`tests/monitor/` was green. Also `uv run ruff check src tests evals`.
