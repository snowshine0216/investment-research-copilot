# PROGRESS — Monitor Eval M0 + M1

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused gate

Mode: backlog · PR shape: A · Project type: non-web · Feature branch: monitor-eval · Item order: 001, 002

| id  | item            | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|-----|-----------------|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | M0 eval spine   | ✅   | ✅    | ✅   | ✅ claude/monitor-eval-m0-m1-001 | ✅ 821a8be | ✅    | ✅ #132 | ⏭️ | ✅     | ✅     | ✅ PASS-WITH-NITS | ✅ 2 rounds | ✅ 88c629d |
| 002 | M1 LLM suites   | ✅   | ✅    | ✅   | ✅ claude/monitor-eval-m0-m1-002 | ✅ 6e3b7f7 | 🔄    | ⏳ | ⏭️ | ⏳     | ⏳     | ⏳        | ⏳  | ⏳    |

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
- 001 drift: [items/001-drift.md](items/001-drift.md) — PASS, all 20 tasks verified in diff; plan amended for fixtures (7d3f682)
- 001 ship: [items/001-ship.md](items/001-ship.md) — PR [#132](https://github.com/snowshine0216/investment-research-copilot/pull/132) into monitor-eval. /ship steps 8+9 found blocker+5 bugs → all fixed pre-push (c095f74..e8750b2).
- 001 review (inline /ship 8+9): [items/001-review.md](items/001-review.md) — PASS (findings found+fixed pre-push). Spawned follow-up for pre-existing eval_cmd print-swallow.
- 001 verify: [items/001-verify.md](items/001-verify.md) — PASS, 32 criteria via live CLI (eval SKIPPED rc 3, --all excludes live) + integration tests
- 001 pr-review: [items/001-pr-review.md](items/001-pr-review.md) — PASS-WITH-NITS, 2 nits, 0 bugs ([comment](https://github.com/snowshine0216/investment-research-copilot/pull/132#issuecomment-4714793673))
- 001 fix: [items/001-fix.md](items/001-fix.md) — round 1 (6 pre-push fixes) + round 2 (2 nits polished); all 3 post-ship verdicts clean
- 001 merge: ✅ squash 88c629d into monitor-eval (PR #132 MERGED)
- 002 spec: [items/002-spec.md](items/002-spec.md) — 21 acceptance criteria, 5 OQs resolved (commit 62cc983)
- 002 grill: [items/002-grill.md](items/002-grill.md) — PASS, 8 Q/A; CONTEXT.md + ADR 0017 M1 sections (b1f15d3); fixed attribution_strength 2-vs-4-value framing
- 002 plan: [items/002-plan.md](items/002-plan.md) — 15 tasks / ~75 steps, strict TDD (commit 45a3bd3)
- 002 impl: 15 TDD commits 02263d4..6e3b7f7; 92 M1 tests pass + 49 M0-wiring regression pass (gating flip ok); 2 live tests skipped (double-gated); ruff clean on M1 files.

## Notes

- Source spec: docs/superpowers/specs/2026-06-16-monitor-eval-m0-m1-design.md (rev 3).
- 001 (M0) must merge before 002 (M1) branches — M1 depends on M0's registry placeholders,
  eval-live scope, latest_stage_report, resolve_health, apply_eval_gate, GATING_STAGES_M0.
