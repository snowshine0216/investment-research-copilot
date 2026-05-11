# Decision Readiness Design

## Purpose

The current daily output can produce a readable memo, scoring file, allocation file, and trade plan, but it does not yet answer the user's practical question: "Can I make a buy or sell decision from this package?"

This design adds a decision-readiness layer that turns existing outputs into a clear, conservative action surface. The first implementation plan should cover Phase 1 and Phase 2 in one file. Phase 3 is documented here as the next dependent step, but should not be implemented until the first two phases make recommendations decision-grade.

## Current Gap

The 2026-05-11 output exposed five issues:

1. `scoring.json` has no buy or sell actions, only low-conviction watch/avoid rows.
2. Every scored instrument has `data_completeness: 0.0`, so the financial basis is not strong enough for real execution.
3. `proposed_allocation.yaml` reports `diagnostics.total_weight: 3.0`, so selected `target_weight` values cannot be treated as whole-portfolio weights.
4. `trade_plan.yaml` emits buy methods and venue notes, but does not compare against current holdings and cannot produce true buy/sell deltas.
5. `memo_traceability.json` has `coverage_ratio: 0.0`, so the memo is useful as narrative context only, not as evidence for execution.

## Goals

- Produce one daily decision report that says whether each instrument is actionable, blocked, watch-only, or avoid.
- Make missing financial data visible by instrument and by required field.
- Block buy/sell execution whenever pipeline health, data completeness, target weights, venue compatibility, or traceability are insufficient.
- Keep the first implementation small and testable: derive the report from existing files before changing portfolio-delta logic.
- Improve financial-data completeness after the decision gate exists, so the system can graduate from conservative blocking to usable recommendations.

## Non-Goals

- Do not place orders or integrate broker APIs.
- Do not calculate sell or trim amounts in the first implementation.
- Do not trust memo prose as evidence unless traceability coverage is nonzero and cited sources can be linked back to raw refs.
- Do not force recommendations when data quality is weak; blocked output is a valid and desired result.

## Phase 1: Decision Report MVP

### Inputs

The report reads the current day's generated artifacts:

- `outputs/<date>/scoring.json`
- `outputs/<date>/proposed_allocation.yaml`
- `outputs/<date>/trade_plan.yaml`
- `outputs/<date>/memo_traceability.json`
- `outputs/<date>/PIPELINE_HALTED.md` when present
- `inputs/account.yaml`

### Outputs

The report writes two files:

- `outputs/<date>/decision_report.json` for machine-readable checks.
- `outputs/<date>/decision_report.md` for human review.

The JSON format contains a top-level summary and a row per instrument:

```json
{
  "date": "2026-05-11",
  "overall_status": "blocked",
  "blocking_reasons": ["pipeline_halted", "target_weights_invalid"],
  "summary": {
    "actionable_buy_count": 0,
    "watch_count": 5,
    "avoid_count": 17,
    "blocked_count": 22
  },
  "rows": [
    {
      "instrument_id": "518850",
      "asset_class": "gold",
      "score_action": "watch",
      "decision_status": "blocked",
      "portfolio_action": "no_trade",
      "conviction": "low",
      "data_completeness": 0.0,
      "missing_data": [
        "expense_ratio",
        "drawdown_3y",
        "vol_1y",
        "downside_capture",
        "aum_stability_pct",
        "manager_tenure_years",
        "holdings_concentration_top10"
      ],
      "target_weight_valid": false,
      "venue_status": "blocked_no_proxy",
      "reason": "Blocked because data completeness is below 0.80 and whole-portfolio target weights are invalid.",
      "next_step": "Repair required financial metrics and rerun scoring/allocation before considering execution."
    }
  ]
}
```

### Decision Status Values

- `actionable_buy`: score supports buy, data is complete, target weights are valid, venue is executable, and pipeline is healthy.
- `watch_only`: instrument is worth tracking, but one or more execution gates prevent trading.
- `avoid`: scoring action is avoid or strong avoid, with no immediate execution suggested.
- `blocked`: system-level or instrument-level checks make the row unsuitable for decisions.
- `review_sell_later`: reserved for Phase 3 when current holdings and target deltas exist.

### Hard Gates

The report applies these rules in order:

1. If `PIPELINE_HALTED.md` exists for the output date, set `overall_status: blocked` and prevent all buy/sell decisions.
2. If `data_completeness < 0.80`, prevent `actionable_buy` and include exact missing fields.
3. If selected target weights do not sum close to `1.0`, mark `target_weight_valid: false` and prevent portfolio-size recommendations.
4. If an instrument has incompatible venue and no proxy, prevent executable trading.
5. If memo traceability coverage is `0.0`, mark memo evidence as narrative-only.
6. If score action is `avoid` or `strong_avoid`, never upgrade it through allocation or trade-plan presence.

### Human Report Structure

The Markdown report should lead with a direct conclusion:

```markdown
# Decision Report 2026-05-11

## Verdict

No buy/sell decision is supported today.

## Why Blocked

- Pipeline halted at ingest.
- Scoring data completeness is below 0.80 for all instruments.
- Allocation target weights are invalid for whole-portfolio sizing.
- Memo traceability is zero, so narrative claims are not evidence-grade.

## Watchlist Only

| Instrument | Score Action | Conviction | Data Completeness | Venue | Next Step |
|---|---|---|---:|---|---|
| 518850 | watch | low | 0.00 | blocked_no_proxy | Repair metrics and rerun. |
```

## Phase 2: Financial Data Completeness

Phase 2 improves the data underneath the decision report. The scoring pipeline already expects these required fields:

- `expense_ratio`
- `drawdown_3y`
- `vol_1y`
- `downside_capture`
- `aum_stability_pct`
- `manager_tenure_years`
- `holdings_concentration_top10`

The implementation should add a small completeness audit that runs before scoring output is trusted. It should produce:

- per-instrument missing-field lists
- aggregate completeness by asset class
- a fail/warn/pass status for scoring readiness
- explicit eval failures when a buy candidate has incomplete data

Recommended thresholds:

- `PASS`: average completeness >= 0.90 and all buy candidates >= 0.80
- `WARN`: average completeness >= 0.75 and no buy candidates below 0.80
- `FAIL`: any buy candidate below 0.80, or average completeness below 0.75

Phase 2 should also make ingestion or metric derivation fill as many required fields as possible from existing price/NAV histories before adding new external providers. Derived risk metrics should be deterministic and tested from local sample series.

## Phase 3: Portfolio Buy/Sell Deltas

Phase 3 comes after decision readiness and data completeness. It adds real portfolio actions by comparing current holdings against valid target weights.

Required account input fields:

- instrument identifier or asset-class proxy
- current market value in CNY
- units when available
- cost basis when available
- account venue

Outputs added in Phase 3:

- current portfolio weight
- target portfolio weight
- delta weight
- buy amount CNY
- sell or trim amount CNY
- action type: `add`, `hold`, `trim`, `exit_review`, `no_trade`

Phase 3 must distinguish between:

- selling because an instrument is fundamentally weak
- trimming because the position is overweight
- doing nothing because target quality is blocked

## Architecture

Add a focused decision module with pure functions first, and connect it to CLI/output generation after tests exist.

Recommended module boundaries:

- `src/irc/decision/models.py`: typed immutable row and report structures.
- `src/irc/decision/completeness.py`: required-field and missing-field logic.
- `src/irc/decision/gates.py`: pure hard-gate evaluation.
- `src/irc/decision/report.py`: compose JSON and Markdown report data.
- `src/irc/commands/decision_cmd.py`: CLI wrapper that reads/writes files.

Keep I/O at the command boundary. The report composer should accept already-loaded dictionaries and return plain data structures.

## Testing Strategy

Use TDD with fixture-sized files under `tests/decision/`.

Required test scenarios:

1. Pipeline halt blocks every row.
2. Low data completeness demotes a buy-capable score to non-actionable.
3. Invalid allocation total blocks target-weight recommendations.
4. Incompatible venue with no proxy blocks executable trades.
5. Avoid scoring action remains avoid even if allocation selected the instrument.
6. Zero memo traceability marks memo evidence as narrative-only.
7. Complete data, valid weights, healthy pipeline, and compatible venue can produce `actionable_buy`.
8. Markdown report starts with a clear verdict and lists blocking reasons.

## Acceptance Criteria

- Running the new decision command on the 2026-05-11 artifacts produces `overall_status: blocked`.
- The report explicitly states that no buy/sell decision is supported for 2026-05-11.
- Every blocked instrument includes a concrete reason and next step.
- Missing financial fields are listed by instrument.
- Target-weight invalidity is detected from the current allocation output.
- The memo is labeled narrative-only when traceability coverage is zero.
- Unit tests cover hard gates and report composition without network access.
- Existing pipeline commands continue to work.

## Implementation Plan Scope

The next implementation plan should be one file covering Phase 1 and Phase 2 only. Phase 3 should remain documented as a follow-up until target weights and financial completeness are reliable.
