# MASTER-PLAN — actionable-ops

Mode: backlog
Project type: non-web        # Python CLI — post-ship verifier is /verify (never /qa)
PR shape: A                  # per-item PRs (no --rollup from user)
Feature branch: autodev/actionable-ops-feature   # synthesized off main (protected; no merge-to-main opt-in)
Branch prefix: claude/actionable-ops-
Item order: 003, 001, 002   # locked 2026-06-10 — dependency scan: 003 self-contained
                            # (valuation axis + docs, smallest/lowest-risk); 001 introduces
                            # decision_report.json sell/review fields; 002's notifier
                            # consumes them, so 002 runs last. Approved verbatim.

## Per-mode skill contract (backlog)

Every item runs the full pipeline — no skips:
spec (Opus brainstorming) → grill (Opus grill-with-docs auto-accept) → plan (Opus
writing-plans) → branch → impl (Sonnet subagent-driven-development) → drift (Sonnet
in-prompt) → ship (/ship; inline review) → [/verify ‖ /code-review] → fix loop → merge
(squash into feature branch).

## Workflow rules (project-specific — bind every subagent)

- **TDD is mandatory** (CLAUDE.md): failing test first, mirror layout
  `src/irc/foo.py → tests/.../test_foo.py`.
- **Versioning**: do NOT bump `VERSION` per item. Accumulate under CHANGELOG
  `[Unreleased]` at the static VERSION (project convention; overrides generic /ship
  step).
- **Test baseline**: main is NOT green — 8 known pre-existing failures + flaky/hang-
  prone e2e research gate; full suite ~18 min. Verifiers must diff-scope failures
  against baseline before declaring regressions. Prefer targeted test paths over the
  full suite inside the loop; full suite once at run-level validation.
- **Functional/immutable style**, files <200 lines ideal, effects at edges
  (CLAUDE.md).
- **Locked invariants** (CONTEXT.md / ADRs): H3 gapped-row, SAME-3, citation id
  16-hex, `OpportunityRow.thesis_state` set only by `derive_thesis_from_evidence`,
  opportunity runs before memo in `STAGE_NAMES`.
- Secrets stay in `.env`; YAML references env names only.

## Run-level tail

run-doc-sync → run-final-verify (/verify smoke: `uv run irc decision` end-to-end) →
close-out (leave feature branch PR open into main for user review — autodev never
merges to main).
