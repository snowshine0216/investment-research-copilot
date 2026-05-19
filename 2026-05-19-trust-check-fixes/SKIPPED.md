# SKIPPED — out-of-scope items

Items from `outputs/2026-05-19/adversarial_review_trust_check.md` that
are not in scope for this run, with rationale.

## Strategy Sanity Check S1–S7

The trust-check doc's "Strategy Sanity Check" section catalogs 7
signal-layer concerns (S1–S7). Most are already shipped or are
fundamental strategy decisions outside reader-trust scope:

- **S1 diversification claim (S&P + Nasdaq correlated)** — addressed
  by prior `008 — correlation filter caps intra-index dupes`
  (commit `7cb1401`).
- **S2 bond valuation method wrong** — addressed by prior
  `005 — bond yield-percentile anchor` (commit `ee9baf1`).
- **S3 gold "6-driver model" is just ADX/vol** — addressed by prior
  `006 — honest tilt combination of regime × drivers` (commit
  `574eb23`).
- **S4 thesis_news=50 filler** — addressed by prior items
  `001/002/003/004` (theme query relevance, thesis intact, provider
  degradation, source-tier).
- **S5 15% cash drift** — drift alert exists in memo (prior 013);
  this run's item 004 surfaces it in decision_report.md.
- **S6 triggers rarely fire** — accurate observation but a strategy
  decision (the tactical overlay is intentionally rare-firing). Not
  a reader-trust fix.
- **S7 no trim-side discipline** — addressed by prior
  `012 — symmetric trim-side triggers` (commit `a3eb258`).

## A3 — "Completeness: 1.00" reads as "100% confident"

Partially mitigated by item 001 (glossary entry for
`data_completeness`). A deeper fix — replacing field-count
completeness with a confidence score — is a larger model change
beyond reader-trust surface fixes.

**Recommended unblock path:** if user wants this, a separate
autodev-loop item would compute a per-row confidence index from
(audit_pass × premium_known × news_relevance × valuation_method_valid)
and surface that alongside completeness. ~1-day effort.

## B5 — Pipeline state invisible

The current `outputs/2026-05-19/decision_report.md` already correctly
shows `Verdict: No buy/sell decision is supported today.` and `Why
Blocked: pipeline_halted` when the pipeline halted upstream. The
trust-check doc was written against the *pre-halt* 14:14 report. No
action needed — already fixed.
