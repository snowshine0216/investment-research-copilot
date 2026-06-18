# MASTER-PLAN — Monitor valuation + heat factor wiring

**Mode:** spec (authoring semantics) · **N:** 3 (author's vertical slices)
**Project type:** non-web
**PR shape:** A (per-item PRs into the feature branch; no `--rollup` in invocation)
**Feature branch:** `monitor-valuation-heat-wiring`
**Base for final roll-up PR:** `main` (opened, NOT merged — no explicit "merge to main" opt-in this turn)
**Item order:** 001 → 002 → 003

## Per-mode skill skips (spec mode)

| Phase | Action |
|-------|--------|
| brainstorming | **skipped** — user authored the design spec; brainstorming would rewrite intent |
| grill | **pre-completed ⏭️** per item — user-grilled; orchestrator must NOT auto-invoke |
| writing-plans | **runs** (Opus) per item, reading that item's refined spec excerpt |
| impl | Sonnet `superpowers:subagent-driven-development` |
| drift | Sonnet in-prompt; must PASS before ship |
| ship | `/ship` (primary) → PR into `monitor-valuation-heat-wiring` + docs + inline review |
| post-ship verify | `/verify` (non-web; XOR with /qa) |
| pr-review | `/code-review` on the open PR |
| fix | Sonnet triage loop over the 3 post-ship verdicts |
| merge | `gh pr merge --squash --delete-branch` into the feature branch (non-protected → allowed) |

## Model contract

- Orchestrator: session default (no override).
- plan: `model="opus"`.
- impl / drift / verify / pr-review / fix: `model="sonnet"`.

## Sub-branch naming

`claude/monitor-valuation-heat-factors-<id>` cut from `monitor-valuation-heat-wiring`.

## Loop exit contract (per item)

Merge only when all of: `drift` PASS · `ship` PR url · `verify` PASS · `review`
PASS|PASS-WITH-NITS (inline from /ship) · `pr-review` PASS|PASS-WITH-NITS. Grill verdict
absence-OK (spec mode ⏭️). No retry budget — environmental stops only.

## Invariants the impl must preserve (from spec §6)

- Profile eligibility unchanged: `gold`/`qdii_global` valuation stays `profile_ineligible`
  (NOT `valuation_no_anchor`).
- All emitted N/A reasons remain in `KNOWN_NA_REASONS`
  (`valuation_no_anchor`, `valuation_unknown_state`, `heat_no_data`) so the `monitor_signal`
  recompute still matches and `apply_eval_gate` is unaffected. Nothing regresses to
  `caveated`/`gated` from this change.
- Determinism: same cached artifacts → identical signal.
- CN endpoints stay **direct** (no `IRC_HTTPS_PROXY`) per the project http-proxy rule.
- TDD throughout (red → green → refactor); test file mirrors source.
