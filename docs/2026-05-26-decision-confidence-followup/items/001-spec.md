# Item 001 Spec — Foreign-fund Policy B relaxation (unblock 006809)

**Date:** 2026-05-26
**Backlog:** `docs/2026-05-26-decision-confidence-followup/MASTER-SPEC.md`
**Mode:** autodev backlog → per-item spec
**ADR impact:** addendum to `docs/adr/0003-failure-mode-policy-b.md` §7

## Goal

Active CN equity funds whose top-N constituents are weight-majority listed
outside Mainland China (HK or US) — e.g. `006809 泰康香港银行指数A` whose
top-10 are all HK names — currently fail Policy B rule 3 with
`incomplete_constituent_data` because the per-holding CN filing pipeline does
not reach HK/US tickers. The fund itself is a publishable, investable CN
vehicle: it discloses fund-level NAV via `fetch_fund_nav_report` and
fund-level announcements via `fetch_fund_announcements`, exactly as gold,
bond, broad_index, and (post-2026-05-25) QDII funds already do. This item
introduces a Policy B precedence relaxation — **rule 2.5** — that accepts
fund-level NAV + announcement evidence as the dual-coverage gate substitute
for per-holding filings when the fund's top-N weight share listed in
`{HK, US}` exchanges is ≥ 50 %. The `## 持仓明细` appendix and
`constituent_analyses` payload are preserved, so the operator still sees the
underlying HK/US holdings as context.

## Acceptance criteria

1. A new module-level constant `FOREIGN_HEAVY_THRESHOLD: float = 0.50` lives
   in `src/irc/opportunity/policy_b.py`. Hardcoded; no YAML knob.
2. A new pure helper
   `_compute_foreign_listed_share(ranked: tuple[ConstituentAnalysis, ...]) -> float`
   returns the weight share of constituents whose `_infer_exchange(symbol)`
   is in `{"HK", "US"}`. Output is a fraction in `[0.0, 1.0]`. Returns `0.0`
   on empty input. Pure, deterministic.
3. `ActiveFundSnapshot` (in `src/irc/fundamentals/types.py`) gains one new
   field: `fund_level_evidence: tuple[ThesisEvidence, ...] = ()`. Default
   `()` preserves all existing call sites and cached fixtures.
4. `_build_active_fund_snapshot` in `src/irc/fundamentals/snapshot.py`
   ALWAYS fetches fund-level NAV + announcements for the fund_id (same
   `fetch_fund_nav_report` + `fetch_fund_announcements` calls used by
   `_build_fund_level_snapshot`) and stamps the result on
   `ActiveFundSnapshot.fund_level_evidence`. Fetch failures are appended to
   `fund_level_failure_reasons` (existing field) without raising.
5. `evaluate_policy_b` is amended with a new rule 2.5 inserted between
   current rule 2 (`incomplete_constituent_record`) and current rule 3
   (`incomplete_constituent_data`). Order of evaluation: 1 → 2 → 2.5 → 3 →
   4 → 5. Rule 2.5 fires only when
   `_compute_foreign_listed_share(ranked) >= FOREIGN_HEAVY_THRESHOLD`.
   Inside the rule:
   - If `snapshot.fund_level_evidence` contains ≥1 entry with
     `citation_kind="data"` AND ≥1 with `citation_kind="information"` →
     return a publishable `PolicyBVerdict` (`gap_codes=()`) with
     `decision_rule=f"foreign-heavy (share={share:.0%}); fund-level "
     f"NAV+announcements accepted"`.
   - Else → return a `PolicyBVerdict` with
     `gap_codes=("foreign_heavy_fund_level_evidence_missing",)` and an
     explanatory `decision_rule` listing which leg is missing.
6. When rule 2.5 publishes, downstream is unchanged: the row carries the
   fund-level evidence in `thesis_evidence` so the dual-coverage gate, the
   picks-table 证据 cell, the evidence-pool, and the discipline thesis
   bullets all see `≥1 data + ≥1 information` citations at
   `scope="instrument"`. (Achieved by the `_stamp_audit_errors_from_verdict`
   companion path in `opportunity_cmd.py` reading `fund_level_evidence` into
   `row.thesis_evidence` when rule 2.5 fires — see implementation
   notes below.)
7. New gap code `foreign_heavy_fund_level_evidence_missing` is registered in
   `_GAP_TO_REASON` (in `src/irc/opportunity/rejection_log.py`) with a
   `RejectionReasonCode` literal value sorted with the existing literals.
   The criterion-19 regression test that raises on unrecognised codes
   continues to pass.
8. A fixture mirroring 006809 (10 HK constituents, no CN filings, with
   non-empty `fund_level_evidence` carrying ≥1 data + ≥1 information
   citation) is accepted by `evaluate_policy_b` with `gap_codes=()` and the
   exact `decision_rule` prefix `"foreign-heavy (share=100%)"`.
9. A fixture mirroring 006809 but with EMPTY `fund_level_evidence` returns
   `gap_codes=("foreign_heavy_fund_level_evidence_missing",)` and a
   `decision_rule` that mentions which leg(s) are missing.
10. A CN-only fixture (existing top-10 with weight-majority SH/SZ/BJ
    symbols) is **unchanged** by the new rule: rule 2.5 falls through
    silently because `foreign_share < 0.50`, and the existing rule-3/4/5
    behaviour drives the verdict. All existing
    `tests/opportunity/test_policy_b.py` tests stay green without
    modification.
11. A mixed fixture (5 HK + 5 SH, weight share 49 % HK) does NOT trigger
    rule 2.5 (below threshold). The existing rules continue to evaluate.
12. A mixed fixture sitting exactly at the threshold weight (50.0 % HK) DOES
    trigger rule 2.5 (comparison is `>=`).
13. ADR 0003 receives a new §7 "Foreign-heavy fund relaxation (rule 2.5)"
    documenting: rationale, the runtime-aggregation choice, the 50 %
    threshold, why fund-level NAV+announcements are accepted in lieu of
    per-holding filings, and the precedence-list amendment. The section
    header table in §1 is bumped to read "six rules in fixed precedence".
14. CONTEXT.md "Failure-mode + audit policy" gains a bullet for
    `rule_2_5_foreign_heavy_short_circuit` and `FOREIGN_HEAVY_THRESHOLD`,
    consistent with the existing `MATERIAL_HOLDING_QUORUM` glossary entry.
15. TDD order is followed: at least one failing test in
    `tests/opportunity/test_policy_b.py` is committed before any production
    code in `src/irc/opportunity/policy_b.py` is changed (verified via
    commit log: a test-only commit precedes the implementation commit).
16. Running `uv run irc opportunity` end-to-end on the 2026-05-26 fixtures
    produces an `outputs/2026-05-26/rejections.json` in which `006809`
    no longer appears as a `RejectionRecord` with reason
    `incomplete_constituent_data`. (The pipeline must reach this state via
    Policy B alone, not via a discovery-stage exclusion.) `ruff check src
    tests` is clean.

## Non-goals

- **No re-routing through `FundLevelSnapshot`.** Active funds remain on the
  `ActiveFundSnapshot` path so the `## 持仓明细` appendix and per-constituent
  rendering keep working. (See Q4 below.)
- **No producer-side `foreign_share_pct` field on the snapshot dataclass.**
  Foreign share is derived inside Policy B from the constituent symbols
  already present — never persisted. (See Q1 below; mirrors ADR 0003 §2's
  "audit_errors derived, never persisted" principle.)
- **No YAML knob for the threshold in V1.** `FOREIGN_HEAVY_THRESHOLD` is a
  module-level constant. Promotion to env var or YAML happens later if
  operational need arises.
- **No new ADR.** This is an amendment to ADR 0003, not ADR 0005.
- **No NAV-only path.** The relaxed evidence must satisfy the dual-coverage
  gate's data + information legs both. NAV alone is insufficient because
  the downstream dual-coverage gate (CONTEXT.md "Evidence & citation")
  would still reject the row.
- **No exchange-list extension in V1.** Foreign = `{HK, US}` only. `UNKNOWN`
  and `BJ` are NOT counted as foreign. (CN equity funds with BJ exchange
  holdings are mainland; UNKNOWN is treated conservatively.)
- **No QDII reform contradiction.** Funds already routed through
  `_build_fund_level_snapshot` (gold / bond / cn_etf / broad_index / sector_theme
  with provider_symbol; QDII per 2026-05-25 memory) still bypass Policy B
  entirely. Rule 2.5 only fires for `kind="active_fund"`.
- **Out-of-scope from MASTER-SPEC item 003**: this item does NOT touch the
  memo §5 picks table or the decision_report renderer. It only touches
  Policy B, the active-fund producer, the rejection log, ADR 0003, and
  CONTEXT.md.

## Constraints

- **TDD enforced** (CLAUDE.md, AC15): red → green → refactor. First commit on
  the per-item branch is a failing test; second commit makes it pass.
- **Pure functions** for the new helper and the rule logic. No I/O, no
  logging, no mutation inside `evaluate_policy_b`. Effects (NAV +
  announcement fetches) stay at the producer edge in
  `_build_active_fund_snapshot`.
- **Frozen dataclasses preserved.** `ActiveFundSnapshot` is `frozen=True`;
  the new field is appended with a default of `()` so existing
  `replace(snap, ...)` call sites work unchanged. No mutation of existing
  instances anywhere.
- **Deterministic outputs.** `_compute_foreign_listed_share` returns the
  same float for the same input (no float drift introduced — sum of
  `weight_pct` is divided by the sum of all `weight_pct`, not by a
  hard-coded `100.0`, so funds whose disclosed top-N sum to < 100 % still
  compute correctly).
- **Effects at edges.** Fund-level NAV and announcement fetches live in the
  existing `_build_fund_level_snapshot` adapter wrappers, called from
  `_build_active_fund_snapshot`. Policy B itself touches no I/O.
- **Cache-shape compatibility.** Adding `fund_level_evidence` to the
  `ActiveFundSnapshot` JSON requires the cache serializer
  (`write_active_fund_cache` / `read_active_fund_cache`) to round-trip the
  new field. Older cache files missing the field re-hydrate with `()` and
  trigger a fresh fetch on the next freshness probe — graceful migration,
  no manual cache invalidation.
- **No mutation of cached `ConstituentAnalysis`.** ADR 0003 §2: cache files
  are byte-identical before and after `evaluate_policy_b`. Rule 2.5
  honours this — it reads `snapshot.fund_level_evidence` and never modifies
  `constituent_analyses`.
- **File size budget.** `policy_b.py` is currently ~300 lines; the new
  helper + rule add ~40 lines. Still under the 200-line ideal-but-not-hard
  budget; if it grows past 350, extract the rule into a sibling module
  `policy_b_foreign_heavy.py`. (Defer this decision to the
  implementation pass — no preemptive split.)

## Open questions resolved during brainstorming

### Q1. Where to detect foreign-share

**A.** Runtime aggregation in Policy B via a new pure helper
`_compute_foreign_listed_share`.

**Rationale.** Policy B already computes per-constituent exchange via
`_infer_exchange(symbol)` to populate `ConstituentCoverageEntry.exchange`.
Aggregating one more `sum(weight_pct for c in foreign_set) /
sum(weight_pct for c in ranked)` ratio is trivial reuse. Producer-side
`foreign_share_pct` on the dataclass (option c) would force a producer-side
contract change for a value Policy B already has all inputs to derive — and
ADR 0003 §2 explicitly says derived values like `audit_errors` are
never persisted on disk. YAML opt-in (option b) requires per-fund manual
maintenance and is wrong-by-construction: the foreign share changes as
holdings rotate.

### Q2. Threshold value and configurability

**A.** Hardcoded module constant `FOREIGN_HEAVY_THRESHOLD: float = 0.50`,
comparison `>=`. No YAML/env-var knob in V1.

**Rationale.** Handoff pinned 50 %. The threshold is a policy decision that
belongs in code+ADR, not config — operators tuning thresholds at runtime is
a feature with no current use case and would silently weaken the audit
trail. A future need can promote it to env var `IRC_FOREIGN_HEAVY_THRESHOLD`
via the same pattern as `IRC_CACHE_FRESHNESS_DAYS` without an API change.
Comparison is `>=` so a fund sitting exactly at 50.0 % HK weight is
accepted (matches the "≥ 50 %" language in the handoff).

### Q3. What evidence counts as the data leg in the relaxed path

**A.** Fund-level NAV report (data leg) + fund-level announcement (info
leg) — both required. Mirrors the 2026-05-25 QDII fetch reform exactly.

**Rationale.** Setting the bar at NAV-only would not actually unblock the
fund: the downstream dual-coverage gate in `irc.opportunity.audit` requires
≥1 `citation_kind="data"` AND ≥1 `citation_kind="information"` per row, both
at `scope in {"instrument","constituent"}` with matching
`owner_instrument_id`. Fund-level NAV + announcement together satisfy both
legs at `scope="instrument"`. The same shape works for gold and QDII per
ADR 0002 §5.

### Q4. Dispatch in `opportunity_cmd.py` — new precedence rule vs route through `FundLevelSnapshot`

**A.** New precedence rule in Policy B. The active_fund dispatch in
`opportunity_cmd.py` lines 952–982 is unchanged.

**Rationale.** Re-routing 006809 through `_build_fund_level_snapshot`
(QDII-style) would strip its `constituent_analyses` payload, breaking the
`## 持仓明细` appendix renderer (CONTEXT.md "持仓明细 appendix") which
requires per-constituent bullets. Even though the data leg is fund-level,
the operator still needs to see WHICH HK names the fund holds — that
visibility is the whole point of the appendix. A new Policy B rule keeps
the snapshot type unchanged, only adjusting the verdict; the producer-side
change is limited to ALSO fetching fund-level NAV+announcements during
`_build_active_fund_snapshot`. Rule placement is between current rules 2
and 3: rule 1 (holdings_fetch_failed) and rule 2 (audit-error
shape-corruption) still take precedence — rule 2.5 must not paper over a
fundamentally broken snapshot.

### Q5. Backward compatibility

**A.** Zero existing tests should require modification. All existing Policy
B tests use CN-only fixtures (weight share 0 % foreign), so rule 2.5 falls
through silently. The new `fund_level_evidence` field on
`ActiveFundSnapshot` defaults to `()`, so existing test factories that
construct snapshots positionally or by keyword continue to compile.

**Verification.** AC10 makes this an explicit acceptance criterion. The
implementer must run `uv run pytest tests/opportunity/test_policy_b.py`
after the rule is added and observe ZERO modifications to any existing
test (only additions). If any existing test breaks, the contract is wrong.

### Q6. Naming

**A.**
- Constant: `FOREIGN_HEAVY_THRESHOLD: float = 0.50` (module-level in
  `policy_b.py`).
- Helper: `_compute_foreign_listed_share(ranked) -> float` (private,
  underscored — pattern matches `_infer_exchange`, `_rank_by_weight`,
  `_material_set_with_ties`).
- Gap code: `"foreign_heavy_fund_level_evidence_missing"` (verbose but
  greppable; mirrors existing `qdii_information_unavailable` and
  `fund_announcements_unavailable`).
- Rejection-reason literal: `"foreign_heavy_evidence_missing"` (added to
  `RejectionReasonCode` and `_GAP_TO_REASON`).
- Rule reference in docstrings + ADR: "rule 2.5
  (foreign-heavy short-circuit)".
- Snapshot field: `fund_level_evidence: tuple[ThesisEvidence, ...]`
  (singular field name on the active-fund dataclass; the same name is NOT
  on `FundLevelSnapshot` because `FundLevelSnapshot.evidence` already
  serves that purpose. Choosing different names avoids confusing
  serializer logic.)

### Q7. ADR — new 0005 vs addendum to 0003

**A.** Addendum: a new §7 in `docs/adr/0003-failure-mode-policy-b.md`. The
§1 precedence table is amended from "five rules" to "six rules" (rule 2.5
inserted). The "Status" line gets an "Amended 2026-05-26 (item 001)" note.

**Rationale.** ADR 0003 §1 IS the precedence-list ADR. A reader landing in
0003 must see rule 2.5; a sibling ADR 0005 that overrides it from outside
would invite drift. The QDII reform set the precedent of memory-only
amendments for fetch routing, but a precedence change to Policy B is
load-bearing enough that it deserves an ADR-level write-up — just inside
the existing ADR, not a new one.

## Implementation notes (non-binding hints for the autodev plan stage)

- TDD order: add `tests/opportunity/test_policy_b.py::test_rule_2_5_*`
  failing tests first (one for the threshold edge, one for
  `fund_level_evidence` missing, one for the publishable case, one for
  CN-only no-op). Commit that test-only diff. Then implement
  `_compute_foreign_listed_share` + the rule + the snapshot field.
- The producer-side fetch of fund-level NAV + announcements inside
  `_build_active_fund_snapshot` will consume 2 additional AkShare calls per
  active fund. Confirm this lands under the existing `IRC_FETCH_BUDGET`
  (default 2000) on a full run; document the per-fund delta in a small note
  to ADR 0003 §7.
- `_stamp_audit_errors_from_verdict` (the helper at
  `opportunity_cmd.py:1045+`) is the natural place to also merge
  `snapshot.fund_level_evidence` into `row.thesis_evidence` when rule 2.5
  publishes, so downstream consumers (picks table, evidence pool,
  discipline section, dual-coverage gate) see the fund-level citations on
  the row. This may need a small rename to
  `_stamp_publishable_extras_from_verdict` or similar — discuss in plan.
- The active-fund cache JSON gains the new `fund_level_evidence` array.
  Existing cache files re-hydrate with `fund_level_evidence=()`; the
  fail-closed freshness probe (ADR 0002 §2) will fire a fresh fetch on the
  next canonical run, which then populates the new field. No manual cache
  invalidation required, but document the behaviour in ADR 0003 §7.
