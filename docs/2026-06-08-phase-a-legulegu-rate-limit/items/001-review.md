Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial review)
Subagents: pr-review-toolkit:code-reviewer (sonnet), pr-review-toolkit:silent-failure-hunter (sonnet), general-purpose adversarial (sonnet)
PR: https://github.com/snowshine0216/investment-research-copilot/pull/121

## Verdict rationale
Zero production blockers. Adversarial review CLEAN; no real P0. Two small test-quality
nits to be applied in the fix phase. One "P0" was a verified false positive.

## Findings

### Blockers (P0): none

### Should-fix nits (P1) — routed to triage-fix
- **P1-A — `tests/fundamentals/test_index_valuation_live.py` (speculative sweep):** the
  informational 12-call sweep now routes through `fetch_legulegu_frame`, which can raise
  `LeguleguCooldownExhausted` mid-loop. The loop has no guard, so the "never-fails"
  informational test would ERROR on a hot limiter instead of clean-stopping. Add
  `except LeguleguCooldownExhausted: break` around the loop body. (test-only; affects the
  deferred operator gate UX.)
- **P1-B — `tests/data/test_index_valuation_ingestor.py` (PB-missing skip test):** the
  PE-missing test asserts the skip WARNING text (`"pe"` + `"cache preserved"`) via caplog;
  the symmetric PB-missing test only asserts `written==0` + DB state, NOT the `"pb"`
  warning text. The spec declares both skip-warning axes a *tested* contract — close the
  asymmetry with a caplog assertion on the `"pb"` token.

### Notes / deferred (not fixed this PR)
- **False positive (was flagged P0):** "`fetch_cn_index_valuation` catches
  `LeguleguCooldownExhausted` → None silently." NOT silent — the throttle WARNING fires at
  `src/irc/fundamentals/legulegu_fetch.py:100-103` BEFORE the raise (terminal-failure
  logging is centralized in `fetch_legulegu_frame`, per spec line 133). Event IS logged.
- **Cosmetic:** the centralized warning text says "suspending broad-leg sweep"; on the
  single-shot/provider path there is no sweep. Message slightly imprecise on that rare
  path but the throttle signal is still emitted. Not worth fixing.
- **Optional enhancement (deferred):** a first-throttle that RECOVERS on the cooldown retry
  is not logged (only terminal outcomes log). Logging recovered throttles would aid gate-#4
  GAP calibration, but it is outside the ratified scope; the ADR's deferred run-level
  ingest diagnostic artifact covers chronicity. Not in this PR.

## Loop bounds / contracts verified by reviewers
- Retry loop bounded: network ≤ 3, cooldown ≤ 1; mixed net→throttle→net sequence terminates
  within 4 iterations; GAP slept before every attempt; no infinite loop, no shared mutable
  module state (counters are per-call locals).
- ADR 0014 deliberate contracts all present & correct: raise/catch asymmetry, dual
  JSONDecodeError match, KeyError('data') fatal, csindex unpaced, hardcoded constants.
- Both-axes guard correctly gates the DELETE; disjoint-date pass-through is the
  ADR-ratified D5 limitation (deferred carry-forward), not a new bug.
