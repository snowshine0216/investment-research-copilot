# 001-spec (inferred from plan)

Goal: Make the spend gate learn — each gated `irc` command records its actual paid-API usage (LLM tokens per task + search units per provider), folds it into a rolling EWMA `usage_profile.json` so the next estimate converges on reality, auto-decrements the local ledger (`consumption.json`), and emits estimated-vs-actual artifacts — hands-off on every gated run, with pure cores and I/O confined to the command edge (ADR 0013).

Acceptance criteria:
  - Recorder round-trip green — Tasks 2 (`recorder.actuals_from_costs`), 5 (`ledger.apply_usage`), 8 (`record_run.record_command_run`) pass their unit tests.
  - Convergence proven numerically — `samples` goes 0→1 and the estimate moves toward the actual; `memo_synthesis` seed `avg_prompt_tokens` 4000 → folded 3100 (= 0.3·1000 + 0.7·4000) after one folded actual (Task 3 + Task 10 round-trip).
  - Artifacts written: `outputs/<date>/spend_estimate.json` (irc-run-only, Task 9) and `outputs/<date>/spend_actuals.json` (Tasks 8/10); `data/spend/usage_profile.json` + `data/spend/consumption.json` updated.
  - Ledger auto-decrement proven — mechanism via Task 8's `apply_usage` + `write_consumption` round-trip; wallet→`consumed_since`, quota→`consumed_this_period`, kind derived from `spend_balances.yaml` (not passed in); end-to-end via Task 12d (a `research` run decrements Tavily/Bocha/Jina/Brave → `irc spend status` shows reduced wallet / advanced quota).
  - README "Spend / balance gate" §13 expanded with the three literal artifact paths, auto-convergence, trigger-command list, `IRC_SPEND_MARGIN` knob, and exit code 5; docs grep test (Task 11) green.
  - Recorder is hands-off and non-fatal — fires on both success and failure paths via `finally`; a recorder exception logs a WARNING and never alters the command's real rc/exception; a command with no paid calls records nothing (empty-history guard).
  - No NEW test failures vs the ~8-failure known baseline; `ruff check` clean on touched paths.
  - §15.3 final acceptance: two consecutive gated runs with injected (deterministic, no real spend) actuals — run 2's `spend_estimate.json` `amount` reflects run 1's recorded actuals (show the two amounts + delta).

Constraints: Pure FP + immutability (no mutated args, no module-global accumulator, frozen dataclasses); effects only at the command edge / thin I/O wrappers; files <200 lines, funcs <20 lines; ruff line-length 100; TDD red→green→commit per task. Protected base `main` — work lands on the synthesized feature branch only. `IRC_SKIP_SPEND_GATE` autouse fixture and the 6 locked `preflight_gate(repo_root, "<cmd>")` call sites must stay byte-identical (`test_gate_wiring` green). Honour ADR 0013 (usage-as-data).
