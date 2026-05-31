Verdict: PASS-WITH-NITS

Source: /code-review on PR #86
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/86#issuecomment-4586297681
Findings: 2
  - src/irc/fundamentals/akshare_filing.py:129 — nit — _profitability_metric uses math.isnan (not math.isfinite); inf ROE stored in FilingDigest.roe is fully screened by compute_ratios._finite() before any display path, so no user-visible impact today. Pre-existing identical gap in _common_metric is out of scope.
  - tests/fundamentals/test_ratios.py:97 — nit — ratios_reason_fragment imported mid-file with noqa:E402 suppression; could be moved to the top-level import block.

## Pre-verified FIXED items (not re-flagged)

Confirmed independently as fixed in commit d185648:
- _finite uses math.isfinite (blocks NaN + ±inf) — FIXED
- abs(roe) > 1.5 unit-error guard degrades implausible ROE to None — FIXED
- Fragment appended only when it fits whole within [:60] cap — FIXED

## Adversarial clean

- _evidence_for_constituent 2→3-tuple ripple: all 6 unpack sites (1 prod + 5 test) confirmed updated.
- Reason-only posture intact: no change to valuation_state / thesis_state / Policy B / core_dca / partition / citation set.
- len(candidate) <= 60 is char-based (Unicode code points), consistent with pre-existing [:60] cap.
- FilingDigest.roe not serialised in the _build_active_fund_snapshot hot path; ConstituentSnapshot.filings is a separate path unaffected by this PR.
- 729 passed / 13 skipped (tests/fundamentals/ + tests/opportunity/) — independently confirmed.
