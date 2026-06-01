Verdict: PASS-WITH-NITS

Source: /code-review on PR #91
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/91#issuecomment-4592319230
Findings: 5
  - src/irc/opportunity/fund_eval.py:87 — nit — `_sort_key` first element `(0 if ev.core_dca else 1)` is redundant with the severity map (core_dca=True → severity=0 always). Harmless; confidence 52.
  - src/irc/commands/fund_eval_cmd.py:23 — nit — `--ids` is silently ignored when `--ids-file` is also provided; no warning emitted to user.
  - tests/opportunity/test_fund_eval.py:108 — nit — mutates frozen dataclass via `__dict__` instead of idiomatic `dataclasses.replace(inp, ...)`.
  - src/irc/opportunity/states.py (pre-existing/deferred) — latent-bug — `ActiveFundSnapshot` thesis branch lacks the dual-leg coverage check; already filed to TODOS.md (eval-funds ship adversarial review 2026-06-01). Not introduced by this PR.
  - src/irc/fundamentals/snapshot_cache.py (pre-existing/deferred) — latent-bug — `load_active_fund_cache` swallows `OSError`/`ValueError` without logging; already filed to TODOS.md (eval-funds ship silent-failure review 2026-06-01). Not introduced by this PR.

## Notes

Seven-angle high-effort review (line-by-line diff scan, removed-behavior audit,
cross-file trace, reuse, simplification, efficiency, altitude). No new correctness
bugs found in the PR diff. The core honesty invariant holds: missing snapshot or
insufficient inputs degrade gracefully to `evidence_insufficient` / `small_watch`,
never assert `core_dca=True` falsely. The `_build_input` extraction is
behavior-identical (byte-identical body; both call sites updated). All four
pre-landing fixes (A–D, commit `9ad77a2`) confirmed present and correct.

Items 4–5 are pre-existing issues already recorded in TODOS.md under Reliability;
per triage instructions they are classified as PASS-WITH-NITS (known/deferred),
not FAIL.
