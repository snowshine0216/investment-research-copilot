# MASTER-PLAN — Monitor report verdict-justification redesign

Mode: spec (N=1)
PR shape: A (per-item PR into the feature branch)
Project type: non-web (Python CLI → static HTML) → Verify (not QA)
Feature branch: `autodev/monitor-report-verdict-feature` (off `main`; `main` is PROTECTED — never auto-merge)
Sub-branch (item 001): `autodev/001-monitor-verdict-render`

## Phase flow (item 001)

spec ⏭️ (pre-authored) → grill ⏭️ (pre-completed) → plan (Opus writing-plans) →
branch → impl (subagent-driven-development) → drift → ship (/ship → PR into feature
branch) → [ verify ‖ pr-review ] → fix loop → merge (into feature branch).

Phase 3: doc-sync + build/test sanity + run-level verify (the report refresh exit gate)
+ open feature-branch PR into `main` (left OPEN, not merged).

## Exit gate (user-specified)

Refresh `outputs/2026-06-15/monitor/report.html` with the new renderer and confirm the
per-fund cards render as in mockup `monitor_card_redesign_mockup`. Prefer reusing cached
`impacts.json` / `narrative.json` (hash-stable same-day rerun) so no new LLM spend.
