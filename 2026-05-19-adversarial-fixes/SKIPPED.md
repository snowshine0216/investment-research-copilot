# SKIPPED — Out-of-scope or deferred

Findings from `outputs/2026-05-19/adversarial_review.md` that are NOT
being implemented in this run, with the reason for each.

## I. "What's actually good" — preserve, not change

Section I of the review lists five things to preserve. These are not
defects, so they require no fix. They are noted here to flag that
nothing in this run should regress them.

- multi-state model (`valuation × heat × thesis × quality → opportunity_state`)
- venue-compatibility gate
- "don't auto-sell on drawdown" behavioral rule
- discovery hard filters (AUM, ER, inception)
- "exclude evidence-insufficient from positive recommendations" instinct

**Action:** none in this run. Phase 3 verification reads the regenerated
artifacts and confirms each is still present and unchanged in behavior.

## D. Triggers "almost never fire" (`real_yield_low`, `vix_high`)

The review correctly notes that the configured buy-side thresholds
(`real_yield_low <= 0`, `vix_high > 25`) fire ~5% of the time. Tuning
these thresholds is a research-judgement call that needs market-historical
analysis to set responsibly, not a deterministic code change.

**Action skipped because:** out of scope for an autonomous code fix. Would
require backtesting infrastructure to justify the new thresholds.
Recommended unblock path: open a separate plan that runs trigger
back-tests over 2010–2025 and proposes thresholds with documented hit-rate
expectations.

## D. `macro_view.yaml: active: false`

This is a user configuration decision (whether to inject a manual macro
prior). Toggling it in code would override user intent. Item 011 (scoring
reweight) instead **gates** the macro_fit factor on `macro_view.active`
so a disabled macro overlay drops the 25% weight to 0% and redistributes,
rather than forcing the user to turn macro on.

**Action redirected into 011**, not skipped silently.

## H. Self-referential proxy bug on 000176 ("proxy via 000176")

The review notes this in §H but item 009 (audit becomes blocking gate)
forces the publish step to halt on any P-tier finding, which catches this
class of bug at the gate. The deeper fix (preventing the trade planner
from ever emitting a self-proxy) is a separate task whose fix in
`trades/venue_check.py` would be misclassified under this review's scope;
it is documented here as a follow-up.

**Action:** the audit gate (item 009) catches it on the next run. Adding
a `proxy_id != instrument_id` assertion in `venue_check.py` is logged as
TODO but not implemented in this run because it is unrelated to the
strategy-layer critique that drives this review.

## §H. Memo audit P1/P2/P3 specific re-fixes

The review notes the original audit caught name-missing on `512960/003624`
and an action↔reason contradiction on `000190`. Items 009 + 010 + 014
together change the pipeline so:

- Audit failures block publishing (009).
- Role-bucket-failure context appears in the memo (010).
- Numeric/text diagnostics surface in the memo where they belong (014).

But the specific PRs that originally remediated the 11/11 audit findings
(see `94e5eed`, `51f6a8f`, `d9fca75`, etc.) are already merged. Re-running
the pipeline will regenerate a clean memo; we are not re-doing those past
fixes here.

## E. Data-completeness rejections (32× missing inception_years/aum/ER)

The review notes 32 rejections for missing data fields point to a
data-completeness problem upstream. This is a data-source fix in the
fundamentals/openbb adapter, not a strategy-layer fix. Documented as
follow-up; the role-bucket banner (item 010) at least makes the
under-population visible.

**Action:** out of scope for this run. Recommended unblock path: run a
data-completeness audit over the universe and patch the OpenBB/EDGAR
adapters' fallback logic.
