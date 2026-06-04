Verdict: PASS-WITH-NITS
Source: /code-review on PR #105
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/105#issuecomment-4618787945
Findings: 3
  - tests/opportunity/test_inputs_loader.py:234 — nit — comment says "< 30 points" but gate is MIN_PE_POINTS = 120; stale threshold reference
  - tests/opportunity/test_inputs_loader.py:593-607 — nit — test_sector_short_span_below_min_days_yields_none exercises the point-count gate (1 row after INSERT OR REPLACE dedup), not the span gate as the comment claims; assertion is still correct
  - src/irc/narrative/risk.py:35-42 — nit — rationale "valuation withheld — no fundamental anchor" fires for any evidence_insufficient valuation (bonds/equity missing data too), not only the metals guard; intentional per spec §4 but may confuse future maintainers

Non-findings:
  - risk.py driver breadth: intentional per spec §4 (pre-triaged)
  - CSI codes 000819/931892: unverified-offline known follow-up (pre-triaged)
  - _fetch_frame bare-except: pre-existing shared infra, out of scope (pre-triaged)
  - Broad index PE via display name ("沪深300" → slug miss): pre-existing non-working path, not introduced by this PR

## Resolution (orchestrator triage)
Exit contract met: verify PASS · review PASS-WITH-NITS · pr-review PASS-WITH-NITS — zero blockers, zero latent bugs.
- Nit 1 (stale "< 30 points" comment) — FIXED (commit on branch; comment now references MIN_PE_POINTS=120).
- Nit 2 (span-gate test only exercised the point-count gate) — FIXED: test_sector_short_span_below_min_days_yields_none now seeds 130 DISTINCT daily dates (129-day span, ≥120 points) so it isolates the MIN_PE_DAYS span gate. Closes a real coverage gap on a load-bearing condition. Re-ran tests/opportunity/test_inputs_loader.py → 23 passed; no new ruff errors.
- Nit 3 (risk.py driver breadth) — KEPT by design (spec §4 intent: surface ANY withheld valuation; rationale text accurate for both paths). Verdict stays PASS-WITH-NITS for this intentional item.
