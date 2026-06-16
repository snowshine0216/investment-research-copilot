# PROGRESS — Monitor Eval M0 + M1

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused gate

Mode: backlog · PR shape: A · Project type: non-web · Feature branch: monitor-eval · Item order: 001, 002

| id  | item            | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|-----|-----------------|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | M0 eval spine   | ✅   | ✅    | ✅   | ✅ claude/monitor-eval-m0-m1-001 | ✅ 821a8be | ✅    | 🔄 | ⏭️ | ⏳     | ⏳     | ⏳        | ⏳  | ⏳    |
| 002 | M1 LLM suites   | ⏳   | ⏳    | ⏳   | ⏳     | ⏳   | ⏳    | ⏳ | ⏭️ | ⏳     | ⏳     | ⏳        | ⏳  | ⏳    |

QA column ⏭️ for all rows: project type is non-web → `/verify` is the active post-ship verifier.

## Run-level

| gate            | status |
|-----------------|--------|
| run-doc-sync    | ⏳     |
| run-final-verify| ⏳     |
| run-close-out   | ⏳     |

## Artifact links (filled as phases complete)

- 001 spec: [items/001-spec.md](items/001-spec.md) — 32 acceptance criteria (commit 9de39ab)
- 001 grill: [items/001-grill.md](items/001-grill.md) — PASS, 7 Q/A; CONTEXT.md + ADR 0017 synced (commit 64c5aec); caught GateDecision name collision
- 001 plan: [items/001-plan.md](items/001-plan.md) — 20 tasks / 102 steps, strict TDD (commit af5c0f0)
- 001 impl: 20 TDD commits 27730a2..821a8be; 456 passed / 1 pre-existing fail (test_dag_acyclic, fails on base too) / 7 skipped; ruff clean. Removed off-plan stray docs/diagrams/monitor-eval-workflow.html.

## Notes

- Source spec: docs/superpowers/specs/2026-06-16-monitor-eval-m0-m1-design.md (rev 3).
- 001 (M0) must merge before 002 (M1) branches — M1 depends on M0's registry placeholders,
  eval-live scope, latest_stage_report, resolve_health, apply_eval_gate, GATING_STAGES_M0.
