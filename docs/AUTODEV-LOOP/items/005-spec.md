# Item 005 — Don't classify `constituent_not_applicable` as an evidence gap

## Problem

`opportunity_report.json` for 2026-05-17 contains 100+ instances of `"constituent_not_applicable"` listed under `evidence_gaps`. Per `src/irc/opportunity/thesis_evidence.py:169-193`, this code fires when `asset_class ∈ {"gold", "cn_bond_fund", "cn_equity_fund"}` — asset classes that *cannot* have a top-N equity constituent snapshot. Treating an expected non-feature as a "gap" pollutes signal-to-noise: a reader can't distinguish "we tried and couldn't find data" from "this asset class doesn't have that kind of data by design".

## Acceptance criteria

- `evidence_gaps` no longer contains `"constituent_not_applicable"` for any non-indexable asset class.
- The downstream `OpportunityRow` keeps the same overall behavior — the thesis path it takes (theme_report fallback) is unchanged.
- A new `expected_omissions` field is added to whatever struct currently carries `evidence_gaps`, capturing the structural reason ("constituent_not_applicable") so the information isn't lost — just relocated.
- Existing tests pass. A new test verifies that for a gold instrument, `evidence_gaps` does not contain `"constituent_not_applicable"` and `expected_omissions` does.

## Files (expected)

- `src/irc/opportunity/thesis_evidence.py` — modify `:169-193` (the constituent_not_applicable emission site) and the data model that returns it.
- `src/irc/opportunity/states.py:272-273` — same code re-emitted, must be updated for consistency.
- The schema / dataclass that holds `evidence_gaps` — add `expected_omissions` field.
- `tests/opportunity/` — add the regression test.

## Non-goals

- Renaming `evidence_gaps` itself.
- Changing the thesis-fallback logic (still falls through to theme_report path).
- Touching `missing_constituent_snapshot` or `missing_recent_news` — those are real gaps.
