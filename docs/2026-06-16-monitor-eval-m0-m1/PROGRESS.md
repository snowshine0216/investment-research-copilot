# PROGRESS — Monitor Eval M0 + M1

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused gate

Mode: backlog · PR shape: A · Project type: non-web · Feature branch: monitor-eval · Item order: 001, 002

| id  | item            | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|-----|-----------------|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | M0 eval spine   | ⏳   | ⏳    | ⏳   | ⏳     | ⏳   | ⏳    | ⏳ | ⏭️ | ⏳     | ⏳     | ⏳        | ⏳  | ⏳    |
| 002 | M1 LLM suites   | ⏳   | ⏳    | ⏳   | ⏳     | ⏳   | ⏳    | ⏳ | ⏭️ | ⏳     | ⏳     | ⏳        | ⏳  | ⏳    |

QA column ⏭️ for all rows: project type is non-web → `/verify` is the active post-ship verifier.

## Run-level

| gate            | status |
|-----------------|--------|
| run-doc-sync    | ⏳     |
| run-final-verify| ⏳     |
| run-close-out   | ⏳     |

## Artifact links (filled as phases complete)

(none yet)

## Notes

- Source spec: docs/superpowers/specs/2026-06-16-monitor-eval-m0-m1-design.md (rev 3).
- 001 (M0) must merge before 002 (M1) branches — M1 depends on M0's registry placeholders,
  eval-live scope, latest_stage_report, resolve_health, apply_eval_gate, GATING_STAGES_M0.
