Verdict: PASS-WITH-NITS
Source: /ship steps 8+9
Subagents: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, adversarial (general-purpose) — all model=sonnet
Diff: origin/autodev/monitor-v4-explainability-feature...claude/monitor-v4-explainability-001

## Findings

- P0 (blocker): none (all three reviewers).
- Latent bugs: none. Adversarial verdict RISKS (P1/P2 only). Key positive evidence:
  - Today's REAL production state (both suites stale 16d) replayed through the real `_suite_eval → apply_eval_gate → caveat_row/caveat_tooltip` chain renders `⚠ 全部基金 caveated：LLM质量评估过期 16/16天 · 周六自动刷新`, non-empty gate.reason, correct tooltip, empty fund-specific segments.
  - Weekly wrapper rc-preservation executed (not string-matched) under `set -euo pipefail` — the `|| echo` guards can't touch `exit "$rc"`; `env` prefix verified genuinely required and correct through `run_with_watchdog`'s `shift; "$@" &`.
  - HTML injection attempted through `_chip`/`_card_caveat`/`caveat_row` with a crafted script-tag reason — all escape correctly (quote=True).
  - Schema 6→7: no consumer gates on the value; pre-v3 "5" trace degrades gracefully (tested); no stray "6" literals.
- Nits (noted — do not block):
  - P1 render_overview.py:222-231/265-280 — unmapped WARN-reason shape (e.g. future empty-reasons WARN row) falls back to splicing the literal English status ("WARN") into the Chinese sentence, unlogged. Cosmetic degrade; recorded in TODOS.md.
  - P2 staleness.resolve_health — `ran_at` in the future (clock skew) yields negative age → silently reads as fresh PASS. Not exploitable today (ran_at is self-written at eval time); recorded in TODOS.md.
