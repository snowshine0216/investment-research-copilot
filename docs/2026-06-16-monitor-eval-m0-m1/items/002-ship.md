PR: https://github.com/snowshine0216/investment-research-copilot/pull/133
Mode: A
Branch: claude/monitor-eval-m0-m1-002
Base: monitor-eval
Title: feat(monitor): M1 LLM suites — impact/narrative corpora, scorers, live_gated runners, gating flip (002)

## /ship workflow notes
- Base overridden to feature branch monitor-eval (non-protected) — not main. Depends on #132 (M0).
- Merge base: already up to date.
- Tests (step 5): focused M1 + M0-regression suite green (165 passed); live_llm test double-gated/skipped.
- Steps 8+9 review found 6 real P0/P1 bugs → all fixed pre-push (ded3a44, 8726780, 5eb6284); 1
  adversarial P0 rejected as false positive. Review verdict: items/002-review.md (PASS).
- Version: no bump (CHANGELOG [Unreleased] M1 entry) per project convention.
