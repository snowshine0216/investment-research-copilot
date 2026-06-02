Verdict: PASS

Subagent: sonnet
Plan checklist items: 10 tasks (Tasks 1–10), 14 ACs, 5 flagged judgment calls
Verified present in diff: 10/10 tasks, all 14 ACs covered

---

## Drift findings

### T2/Judgment-call (a) — `_fund_level_eligible_target` builds `OpportunityInput` directly instead of calling `_build_input(..., provider=None)`

**Type:** Accepted deviation (consistent with plan's stated goal and fallback intent).

**Evidence:** `narrative_autobuild.py:57–79` — `_fund_level_eligible_target` constructs an `OpportunityInput` from `instr` fields directly, without calling `_build_input`. `inputs_build` is **not** imported. `map_lookthrough` is called on the directly-built `OpportunityInput`. The plan's T2 Step 3 prescribed `_build_input(..., provider=None)` as the primary approach, with an explicit fallback: "thread the real provider" if `provider=None` raises. The implementer took an equivalent-but-cleaner route: since `map_lookthrough` only reads `asset_class/theme/tracked_index/instrument_id/name_cn` (all available from `instr`), building the skeleton directly avoids the `provider` type-mismatch entirely and removes a function call whose output for the eligibility decision is deterministic from `instr` alone.

**Goal alignment:** The plan's stated goal for AC2/RD-3 is "effect-free, instr-derived resolution with no DB round-trip." The implementation satisfies this exactly. The con parameter is accepted but documented as unused (signature parity for forward compatibility). No regression: the plan's fallback covers this choice.

**Plan amendment:** Amend T2 Step 3 note to document the accepted deviation.

---

### T3/test — `_fund_level_build_one_skips_empty_quarter` uses a different technique than plan

**Type:** Incidental (test hygiene), accepted.

**Evidence:** `tests/narrative/test_narrative_autobuild.py` (T3 block) — the plan's version monkey-patches `build_snapshot` to return `_fund_level_snap("000B", "")` (snap with empty quarter string). The impl uses `dc_replace(snap, source_report_quarter="", nav_report=None)` so the produced snap actually has empty `source_report_quarter`. The sentinel helper `_fund_level_snap` in the plan set `source_report_quarter=quarter` in the `FundLevelSnapshot` even when `quarter=""` argument, but the `FundNavReport.source_report_quarter` was also `""`. The impl's approach yields a snap with `source_report_quarter=""` at the top level, which is what the guard checks. Semantically equivalent.

---

### T6/Judgment-call (b) — `_load_latest_nav_cached` imported from `opportunity_cmd` into `analyze.py`

**Type:** OK, matches plan (no cycle confirmed).

**Evidence:** `analyze.py:7` — `from irc.commands.opportunity_cmd import _load_latest_nav_cached`. The plan documented this import path and required a cycle check. `narrative_autobuild.py` also imports `_load_latest_nav_cached` from `opportunity_cmd` (line 14). Neither `opportunity_cmd` nor `snapshot_cache` imports from `irc.narrative.*`. No cycle.

---

### T6/Step 5 + T7 — existing test stubs updated from `autobuild_active_funds` to `autobuild_narrative`

**Type:** OK, matches plan (T7 Step 5 required this rename).

**Evidence:** `tests/narrative/test_narrative_cmd.py` lines ~115, ~249, ~347, ~466, ~503 — all five `autobuild_active_funds` monkeypatches renamed to `autobuild_narrative`; the `test_analyze_invokes_autobuild_with_resolved_quarter` lambda signature updated to include `instr_index, con` kwargs. Existing `test_analyze_recovers_active_fund_with_real_thesis` stub changed from `lambda *a, **k: object()` to `_active_inp()` returning a real `cn_equity_fund` `OpportunityInput` (required by T6 Step 5 note).

---

### T8 — `_passive_inp_bare()` helper added alongside `_passive_inp()`

**Type:** Incidental test hygiene, accepted.

**Evidence:** `tests/narrative/test_narrative_cmd.py:637–672` — the plan's T8 `_passive_inp()` was a minimal `OpportunityInput` with no valuation/heat/product data. The impl split this into two helpers: `_passive_inp()` (with `valuation_percentile_self=0.45`, `ret_1m/ret_3m`, `expense_ratio` to suppress structural evidence gaps for AC6 two-leg assertion) and `_passive_inp_bare()` (no data, for AC7/AC10 where "insufficient" outcome is asserted). The plan's T8 note says `_passive_inp` needed sufficient fields for `thesis_state=intact` to hold (AC6), but the plan's code block omitted the valuation fields. The split is correct: AC6 requires non-insufficient, AC7/AC10 require insufficient. The impl is faithful to the ACs; the plan's helper code was slightly underspecified.

---

### T10 — `narrative_autobuild.py` is 251 lines (plan budget: <200)

**Type:** NOTE — accepted soft-overage.

**Evidence:** `wc -l src/irc/commands/narrative_autobuild.py` → 251 lines. The plan allowed a split into `narrative_autobuild_passive.py` if the file approached 200 lines, with a note that "this keeps each function < 20 lines." The plan also documented the trade-off: "impl kept it unified for monkeypatch." All individual functions remain well within the 20-line target. The 51-line overage is docstring-heavy (each public function has a multi-line docstring covering AC citations, RD refs, and design rationale). This is not a real maintainability problem: the file has exactly one responsibility (narrative autobuild edge), three public functions, and four private helpers. The overage is documentation weight, not logic complexity. No split required.

---

## Spec/grill invariant verification

| Invariant | Status | Evidence |
|-----------|--------|----------|
| `analyze_fund` gained ONLY read-side dispatch; no fetch/build/cache-write | OK | `analyze.py:94–119` — `_load_snapshot_for_row` calls only `load_active_fund_cache` or `_load_latest_nav_cached`; `build_snapshot` never imported |
| `theme_report=None` for passive path (RD-1) | OK | `analyze.py:134` — `build_opportunity_row(inp, None, snapshot=snapshot, theme_report=None)` |
| No `基金概况` in production fetch code | OK | grep: no match in `narrative_autobuild.py`, `analyze.py`, `narrative_cmd.py` |
| No `fetch_budget_exhausted` sentinel written to rows | OK | grep: no match; `FetchBudgetExceeded` is raised, never stamped |
| No `evaluate_policy_b` in narrative path | OK | grep: no match |
| `build_opportunity_row` annotation widened to include `FundLevelSnapshot` (RD-6a) | OK | `states.py:526` — `ConstituentSnapshot \| ActiveFundSnapshot \| FundLevelSnapshot \| None` |
| Shared preflight `FetchPlan` via `autobuild_narrative` (RD-7a) | OK | `narrative_autobuild.py:212–251` — single combined plan over both legs |
| No new import cycle | OK | `narrative_autobuild.py` imports only `irc.narrative.schemas`; `analyze.py` already imported `irc.opportunity.*`; `opportunity_cmd` does not import `irc.narrative.*` |

---

## Plan amendment (T2 Step 3 note)

The T2 Step 3 note in the plan described `_build_input(..., provider=None)` as the primary approach. The implementer substituted direct `OpportunityInput` construction (no `_build_input` call), which is equivalent for the eligibility decision and avoids the `provider=None` type-mismatch. Amending the plan to record this accepted deviation.
