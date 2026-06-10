Verdict: PASS

Subagent: opus
Questions resolved: 8
Docs touched:
  - CONTEXT.md (commit e14d6ef)
  - docs/adr/0015-portfolio-action-emission-contract.md (commit e14d6ef)
Spec refined: items/001-spec.md (commit e14d6ef)

## Resolved decisions

- Q: Where do `risk_action`/`dca_action`/`portfolio_weight`/`is_holding` come from
     when `compose_opportunity_report(rows, date)` receives only `OpportunityRow`s?
  A: Add a defaulted keyword `discipline_by_id: dict | None = None` to
     `compose_opportunity_report`; build it at the command edge from the existing
     `discipline_rows` + `positions[iid]`. Default `None` ⇒ byte-identical to today.
  Rationale: `OpportunityRow` carries none of the four fields (they live on
     `DisciplineRow`/`ThesisCard` and `OpportunityInput`/`PositionContext`); a pure
     composer can't reach them without a signature change. Defaulted keyword keeps
     public-API stability.
  Doc impact: spec components #1/#2 corrected in place; CONTEXT.md `portfolio_action`.

- Q: Do the four new `opportunity_report.json` keys interact with H3 or SAME-3?
  A: No. Added to the SAME publishable-row dict (`evidence_gaps == ()` partition
     unchanged); no new `[ref:...]` markers; `select_citations(cap=3)` surfaces
     untouched. Determinism preserved (cached scalars).
  Rationale: the fields are plain scalars, never cited; the partition predicate and
     failure-section 4-field renderer are unchanged.
  Doc impact: ADR-0015 §Consequences.

- Q: Does mapping `risk_action → portfolio_action` risk writing `thesis_state` or
     touching Policy B publishability?
  A: No. `portfolio_action` is a downstream projection set ONLY by the pure
     `map_portfolio_action`; the decision layer reads `risk_action`, never calls
     `derive_thesis_from_evidence` and never touches Policy B.
  Rationale: ADR 0003 setter rule preserved by construction.
  Doc impact: CONTEXT.md `map_portfolio_action`; ADR-0015 §2.

- Q: Is the `is_holding` gate on the sell branches redundant given `risk_action`
     already exists?
  A: No — load-bearing. `derive_risk_action` can return `trim_review`/`exit_review`
     for a NON-holding (legacy `overweight` branch in `discipline.py`). The mapper
     enforces the holdings-only contract; without the gate AC7 breaks.
  Rationale: enforcement locus is the mapper, not the discipline derivation.
  Doc impact: CONTEXT.md `map_portfolio_action`; ADR-0015 §2.

- Q: Is the Δpp arithmetic stable across runs (ADR 0004 determinism)?
  A: Yes. `current_weight` (cost-basis `portfolio_weight`) and `target_weight`
     (`proposed_allocation.yaml`) are cached scalars read network-free;
     `weight_delta = current − target` is one subtraction, no accumulation.
  Rationale: `irc decision` is network-free off cached artifacts; cost-basis chosen
     deliberately (live-NAV re-pricing out of scope).
  Doc impact: CONTEXT.md `current_weight`/`weight_delta`; ADR-0015 §2.

- Q: Is `review_sell_later` the right `DecisionStatus` name, or the spec's widening?
  A: `review_sell_later` — the `models.py:12` Phase-3 TODO already named it; adopt
     verbatim, no rename. Buy-side precedence (`avoid > blocked > actionable_buy`)
     unchanged.
  Rationale: settle the contract on the name already chosen in code.
  Doc impact: CONTEXT.md `review_sell_later`.

- Q: Exact `decision_report.json` summary key names for item 002's notifier?
  A: `trim_count` / `exit_count` / `review_count` (keyed off `portfolio_action`);
     NO `sell_count`. Existing four counts preserved (additive-only).
  Rationale: "sell" is ambiguous (exit-only vs trim+exit); explicit non-overlapping
     keys, notifier composes its own rollup. Names LOCKED for item 002.
  Doc impact: CONTEXT.md "Decision summary sell/review counts"; ADR-0015 §3.

- Q: Does any durable decision here clear the three-of-three ADR bar?
  A: Yes — the `portfolio_action` emission contract (vocabulary + summary-count
     names + mapping precedence). Recorded as ADR 0015.
  Rationale: hard to reverse (machine-read artifact consumed by item 002),
     surprising without context (`review_required→review`, the `is_holding` gate,
     no `sell_count`), real trade-off (approaches A/B/C; collapse-vs-three-action).
  Doc impact: ADR-0015 created.
