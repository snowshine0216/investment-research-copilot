# Decision-confidence & blocked-cleanup plan — 2026-05-26

## Why

Today's reports (`outputs/2026-05-26/memo.md` + `decision_report.md`) do not let a reader
make a buy decision with confidence:

1. **Internal inconsistency.** `decision_report.md` lists 006809 as `actionable_buy`,
   but `memo.md` §5 picks table excludes it under "未能纳入精选：机会数据缺失"
   because all 10 HK-listed bank constituents fail Policy B's data-leg gate
   (`filing_empty:0xxxx` × 10).
2. **No when-to-buy signal.** Triggers like `weekly_drawdown_4pct` are declared
   in memo §7 but the *current value* of `instrument.weekly_return` is not
   shown, so the reader cannot tell whether the trigger is met now.
3. **No how-much signal.** Footnotes say "this plan does not size trades" and
   "target_weight 是上限". There is no per-tranche ¥/% suggestion.
4. **Vague rationale.** Every row's reason collapses to "估值=very_expensive、
   热度=normal". No structured why-yes / why-not / why-when.
5. **Blocked-table noise.** 29 venue-blocked ETFs and 5 QDII-premium-unknown
   rows clutter "Blocked — fixable today" even though most are redundant
   (role already met by proxy) or genuinely unreachable on the user's CMB-only
   account.
6. **014502 stuck at evidence_insufficient.** `cn_bond_yield_percentile` is
   defined in `OpportunityInput` but never populated — the field is dead code
   in `inputs_loader.py`. All three bond funds (014502, 511010, 511220) get
   `valuation_state="evidence_insufficient"` and their composite scores are
   "不得用于优先级比较".

## Goals (in priority order)

P0. **Decision-grade rendering.** Each actionable / pause / blocked row in
    both reports shows: why-yes / why-not / why-when, trigger condition with
    current state, and a `% of portfolio per tranche` size suggestion.
P0. **Consistency.** The set of "today's actions" in `decision_report.md` is
    a strict subset of memo §5 picks (or memo cites the same gap reason).
P0. **006809 reconciliation.** Mirror the 2026-05-25 QDII reform: when a
    fund's top-N holdings are predominantly non-CN-listed, accept fund-level
    NAV + announcements as the data leg (foreign-holding relaxation).
P0. **014502 valuation.** Ingest a 10Y CGB yield series (akshare
    `bond_china_yield_curve` or FRED `IRLTLT01CNM156N` as fallback), compute
    rolling percentile, populate `cn_bond_yield_percentile` in
    `inputs_loader.py`.
P1. **Blocked reduction.** (a) Recategorize rows whose role bucket is already
    proxy-met as "redundant — out of scope". (b) Render genuinely unreachable
    rows under a separate **"Out of scope — expand your account"** heading
    with concrete onboarding steps (which broker, what info to provide).
P1. **Onboarding doc.** `inputs/account.yaml` template + a short
    `docs/account-onboarding.md` explaining: how to add `cn_brokerage`,
    `hk_connect`, paper-gold venues; what fields are required.

## Non-goals

- New QDII premium fetcher (deferred — 5 rows; do not block release).
- New HK-listing filings fetcher (out of scope; the relaxation in P0 handles
  the symptom without needing one).

## Execution plan (TDD, one stage per commit)

### Stage 1 — Bond yield percentile fetcher
Files: `src/irc/commands/ingest_cmd.py`, `src/irc/opportunity/inputs_loader.py`,
       `tests/irc/opportunity/test_inputs_loader_bond_yield.py` (new).
- Add `_MacroSeriesSpec(source_id="IRLTLT01CNM156N", storage_id="cn_10y_yield")`
  (or akshare bond_china_yield_curve). Persist into `macro_series` table.
- In `inputs_loader.populate_inputs`, when `asset_class == "cn_bond_fund"`,
  read the last 3y of `cn_10y_yield`, compute current-vs-history percentile,
  assign to `cn_bond_yield_percentile`. Cheap-direction = high yield = high
  percentile (already aligned with `classify_bond_valuation` semantics).
- Tests: percentile boundary cases (0.0, 0.5, 1.0, missing).

### Stage 2 — Foreign-holding Policy B relaxation
Files: `src/irc/commands/opportunity_cmd.py`,
       `src/irc/opportunity/policy_b.py`,
       `tests/irc/opportunity/test_policy_b_foreign_holdings.py` (new).
- Add `is_foreign_holdings_fund(snapshot) -> bool`: True when ≥ 50% of
  weight in top-N is non-CN-listed (exchange ∈ {HK, US, ...}).
- In `_active_snapshot_has_required_data_leg_gap` (and Policy B's coverage
  gate), when foreign-holdings, treat fund-level `nav + fund_announcement`
  as the data leg AND require constituent evidence as INFO-leg only.
- Acceptance test: 006809 with all-HK constituents + valid fund-level NAV
  + fund_announcement passes the gate.

### Stage 3 — Decision-grade renderer (memo §5 + decision_report §Actionable)
Files: `src/irc/memo/picks_table.py`, `src/irc/decision/report.py`,
       `src/irc/decision/sizing.py` (new), `tests/...`
- Add `sizing.suggest_tranche_pct(target_weight, build_mode, weekly_return)`:
  - `build` mode → 4 tranches → per-tranche size ≈ `target_weight / 4`.
  - When `weekly_return ≤ trigger_threshold` → 1× size (full tranche).
  - When `weekly_return > trigger_threshold` and trigger is the only
    condition → return 0 (current_size=0; wait for trigger).
  - When `weekly_return` is None → return None (data missing).
- Add `current_trigger_state(triggers, current_data) -> Literal["met","not_met","missing"]`.
- Extend `PickRow` with: `triggers`, `current_weekly_return`,
  `current_macro_snapshot`, `tranche_pct_suggested`,
  `why_yes / why_not / why_when` strings (filled by classifier).
- New render mode: keep the existing picks table but append a "今日操作摘要"
  per-instrument bullet block under §5, one card per pick, format:
  ```
  - **✅ 003318 ...**
    - **Why YES**: thesis_state=intact, product_quality=weak, …
    - **Why WHEN**: trigger `weekly_drawdown_4pct` (instrument.weekly_return ≤ -4%);
      current = -1.20% ⇒ ✗ NOT MET this week.
    - **Suggested size**: ≤ 2.8% of portfolio (target 11.2% ÷ 4 tranches),
      only when trigger fires.
  - **⏸️ 161716 ...**
    - **Why NOT**: 估值=very_expensive, 暂停加仓 until percentile re-enters
      reasonable band.
    - **Trigger to resume**: vix>25 OR weekly_drawdown_4pct.
    - **Suggested size**: 0 this week (waiting).
  ```
- Decision_report.md "Actionable buys" table gains 3 new columns:
  `Why` (one line), `Trigger met?` (✓/✗/⚠), `Suggested size`.

### Stage 4 — Blocked-table cleanup + onboarding section
Files: `src/irc/decision/report.py`,
       `inputs/account.yaml` (extend template),
       `docs/account-onboarding.md` (new).
- In `_blocked_fixable_section`: split into two subsections:
  1. **Blocked — fixable today** (data refresh / config tweak the user CAN
     resolve immediately): only QDII-premium and data_incomplete categories.
  2. **Out of scope — account expansion required**: venue-blocked rows
     whose role bucket is already met OR whose only path to reach is a
     missing broker venue. Render with the onboarding pointer.
- Account onboarding doc: list each venue tier (`cmb_fund`, `cmb_gold`,
  `cn_brokerage`, `hk_connect`, `us_brokerage`), what real-world account
  unlocks it, what fields to add to `inputs/account.yaml`, and the
  per-venue instrument count it would unlock.

### Stage 5 — Re-run pipeline & verify outputs
- `uv run irc run --from opportunity` (after stages 1+2 land).
- `uv run irc opportunity` then `uv run irc decision` (after stage 3).
- Manual diff: confirm 006809 + 014502 appear in memo §5 with non-evidence-
  insufficient states; confirm both reports cite the same actionable set;
  confirm new "今日操作摘要" cards render; confirm blocked count drops below
  the 1%-of-universe threshold.

## Acceptance

A reader of `outputs/2026-05-26/memo.md` + `decision_report.md` can answer,
for each actionable instrument, all three of:

1. **Why** they would buy it (positive thesis bullets cited).
2. **When** they should add (trigger condition + current state).
3. **How much** in % of portfolio per tranche.

And the visible Blocked count in decision_report.md drops to ≤ 1% of total
instruments scored. The remainder is moved to an "Out of scope" appendix
with onboarding remediation, not "Blocked — fixable today".
