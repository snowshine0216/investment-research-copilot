# Foreign-fund Policy B relaxation (unblock 006809) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Policy B rule 2.5 — a foreign-heavy short-circuit that accepts fund-level NAV + announcement evidence in lieu of per-holding filings when ≥ 50 % of an active fund's top-N constituent weight is listed on HK or US exchanges. Unblocks `006809 泰康香港银行指数A` and any other CN equity fund whose holdings the per-holding CN filings pipeline can't reach.

**Architecture:** All effects (NAV + announcement fetches) live at the producer edge in `_build_active_fund_snapshot`. A new pure helper `_compute_foreign_listed_share` aggregates exchange-weight inside Policy B. The new rule 2.5 is inserted between rules 2 and 3 in `evaluate_policy_b`'s precedence chain. A new sibling helper `_stamp_fund_level_evidence_from_verdict` in `opportunity_cmd.py` merges the snapshot's fund-level evidence into the row's `thesis_evidence` on publishable rows.

**Tech Stack:** Python 3.12, frozen dataclasses, `dataclasses.replace`, pytest, AkShare adapters (`fetch_fund_nav_report`, `fetch_fund_announcements`), DuckDB unaffected.

**Fetch-budget note:** `IRC_FETCH_BUDGET_DEFAULT = 2000` (see `src/irc/commands/opportunity_cmd.py:82`). Adding 2 calls per active fund × ~50 active funds ≈ 100 extra calls — comfortably under budget; no preflight contract change.

---

## File map

| File | Action | Purpose |
|---|---|---|
| `tests/opportunity/test_policy_b.py` | Modify (append) | New failing tests for rule 2.5 + foreign-share helper |
| `src/irc/fundamentals/types.py` | Modify (append field) | `ActiveFundSnapshot.fund_level_evidence: tuple[ThesisEvidence, ...] = ()` |
| `src/irc/opportunity/policy_b.py` | Modify (append + insert) | `FOREIGN_HEAVY_THRESHOLD`, `_compute_foreign_listed_share`, rule 2.5 inside `evaluate_policy_b` |
| `src/irc/opportunity/rejection_log.py` | Modify | New `RejectionReasonCode` literal `"foreign_heavy_evidence_missing"` + new `_GAP_TO_REASON` entry (appended LAST) |
| `src/irc/fundamentals/snapshot.py` | Modify | `_build_active_fund_snapshot` calls `fetch_fund_nav_report` + `fetch_fund_announcements`, stamps `fund_level_evidence` |
| `src/irc/fundamentals/snapshot_cache.py` | Modify | `_active_fund_to_dict` / `_active_fund_from_dict` round-trip the new field |
| `src/irc/commands/opportunity_cmd.py` | Modify | New `_stamp_fund_level_evidence_from_verdict` helper; wired alongside `_stamp_audit_errors_from_verdict` on publishable verdicts |
| `tests/fundamentals/test_snapshot.py` | Modify (append) | Test that `_build_active_fund_snapshot` populates `fund_level_evidence` from injected adapter calls (via monkeypatch) |
| `tests/fundamentals/test_snapshot_cache.py` | Modify (append) | Round-trip test for `fund_level_evidence` on `ActiveFundSnapshot` JSON |

---

## Task 1 — TDD: failing tests for the foreign-share helper + rule 2.5

**Files:**
- Test: `tests/opportunity/test_policy_b.py` (append at end of file)

- [ ] **Step 1: Add the new test cases at the bottom of `tests/opportunity/test_policy_b.py`**

Append the following block verbatim AFTER the existing `test_evaluate_policy_b_thesis_state_never_modified` test (which is currently the last test in the file):

```python
# ── Item 001 (decision-confidence-followup): rule 2.5 foreign-heavy ──────────


def _evidence_data_instrument(fund_id: str = "006809"):
    """Build an instrument-scope, data-leg ThesisEvidence (NAV-style)."""
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type="snapshot",
        source=fund_id,
        url="",
        date="2024-04-15",
        summary=f"NAV=1.2345 @ 2024-04-15",
        scope="instrument",
        citation_kind="data",
        owner_instrument_id=fund_id,
        parent_fund_id=None,
        constituent_key=None,
    )


def _evidence_info_instrument(fund_id: str = "006809"):
    """Build an instrument-scope, information-leg ThesisEvidence (announcement-style)."""
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type="news",
        source="fund_announcement_report_em",
        url="",
        date="2024-04-15",
        summary="[REP-001] 季度报告",
        scope="instrument",
        citation_kind="information",
        owner_instrument_id=fund_id,
        parent_fund_id=None,
        constituent_key=None,
    )


def _snapshot_with_fund_level_evidence(
    analyses=(),
    fund_level_failure_reasons=(),
    fund_level_evidence=(),
    fund_id: str = "006809",
):
    """Snapshot factory that supplies fund_level_evidence (item 001 field)."""
    from irc.fundamentals.types import ActiveFundSnapshot
    return ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="",
        constituent_analyses=analyses,
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=fund_level_failure_reasons,
        fund_level_evidence=fund_level_evidence,
    )


def test_foreign_heavy_threshold_constant_is_half() -> None:
    from irc.opportunity.policy_b import FOREIGN_HEAVY_THRESHOLD
    assert FOREIGN_HEAVY_THRESHOLD == 0.50


def test_compute_foreign_listed_share_all_hk_returns_one() -> None:
    from irc.opportunity.policy_b import (
        _compute_foreign_listed_share,
        _rank_by_weight,
    )
    ranked = _rank_by_weight(tuple(
        _ca(f"0070{i}.HK", 1.0) for i in range(10)
    ))
    assert _compute_foreign_listed_share(ranked) == 1.0


def test_compute_foreign_listed_share_all_cn_returns_zero() -> None:
    from irc.opportunity.policy_b import (
        _compute_foreign_listed_share,
        _rank_by_weight,
    )
    # SH symbols (start with 6, 6 digits).
    ranked = _rank_by_weight(tuple(
        _ca(f"60000{i}", 1.0) for i in range(10)
    ))
    assert _compute_foreign_listed_share(ranked) == 0.0


def test_compute_foreign_listed_share_empty_input_returns_zero() -> None:
    from irc.opportunity.policy_b import _compute_foreign_listed_share
    assert _compute_foreign_listed_share(()) == 0.0


def test_compute_foreign_listed_share_mixed_below_threshold() -> None:
    """5 HK at weight 4.9 + 5 SH at weight 5.1 → foreign share 49 %."""
    from irc.opportunity.policy_b import (
        _compute_foreign_listed_share,
        _rank_by_weight,
    )
    hk = tuple(_ca(f"0070{i}.HK", 4.9) for i in range(5))
    sh = tuple(_ca(f"60000{i}", 5.1) for i in range(5))
    ranked = _rank_by_weight(hk + sh)
    share = _compute_foreign_listed_share(ranked)
    assert abs(share - 0.49) < 1e-9


def test_compute_foreign_listed_share_exact_50_pct_boundary() -> None:
    """5 HK @ 5.0 + 5 SH @ 5.0 → foreign share == 0.50 exactly."""
    from irc.opportunity.policy_b import (
        _compute_foreign_listed_share,
        _rank_by_weight,
    )
    hk = tuple(_ca(f"0070{i}.HK", 5.0) for i in range(5))
    sh = tuple(_ca(f"60000{i}", 5.0) for i in range(5))
    ranked = _rank_by_weight(hk + sh)
    assert _compute_foreign_listed_share(ranked) == 0.5


def test_compute_foreign_listed_share_unknown_exchange_treated_non_foreign() -> None:
    """UNKNOWN exchange symbols are conservatively NOT counted as foreign (spec non-goal)."""
    from irc.opportunity.policy_b import (
        _compute_foreign_listed_share,
        _rank_by_weight,
    )
    # "ZZZ" → _infer_exchange returns "US" because it's alpha; pick a symbol
    # whose shape forces UNKNOWN: digits but wrong length.
    ranked = _rank_by_weight((
        _ca("123", 5.0),       # UNKNOWN (3-digit; not 4/5/6)
        _ca("600000", 5.0),    # SH
    ))
    # Foreign share = 0 / 10 = 0.0 (UNKNOWN excluded; SH excluded).
    assert _compute_foreign_listed_share(ranked) == 0.0


def test_evaluate_policy_b_rule_2_5_foreign_heavy_publishable() -> None:
    """006809 fixture: 10 HK constituents, no CN filings, fund-level evidence present."""
    from irc.opportunity.policy_b import evaluate_policy_b
    # All 10 holdings are HK and lack data leg (no CN filings reach HK).
    # In the legacy precedence this triggers rule 3; rule 2.5 must short-circuit.
    analyses = tuple(
        _ca(
            f"0070{i}.HK", 10.0 - i,
            evidence=(),  # no per-holding filings; the whole point of rule 2.5
            failure_reasons=(f"filing_fetch_failed:0070{i}.HK:KeyError",),
        )
        for i in range(10)
    )
    snap = _snapshot_with_fund_level_evidence(
        analyses=analyses,
        fund_level_evidence=(
            _evidence_data_instrument("006809"),
            _evidence_info_instrument("006809"),
        ),
    )
    v = evaluate_policy_b(snap, top_n=10)
    assert v.gap_codes == ()
    assert v.audit_errors == ()
    assert v.decision_rule.startswith("foreign-heavy (share=100%)")
    assert "fund-level" in v.decision_rule


def test_evaluate_policy_b_rule_2_5_foreign_heavy_missing_evidence_fails() -> None:
    """Foreign-heavy fund WITHOUT fund_level_evidence → new gap code."""
    from irc.opportunity.policy_b import evaluate_policy_b
    analyses = tuple(
        _ca(
            f"0070{i}.HK", 10.0 - i,
            evidence=(),
            failure_reasons=(f"filing_fetch_failed:0070{i}.HK:KeyError",),
        )
        for i in range(10)
    )
    snap = _snapshot_with_fund_level_evidence(
        analyses=analyses,
        fund_level_evidence=(),  # empty → rule 2.5 fails
    )
    v = evaluate_policy_b(snap, top_n=10)
    assert v.gap_codes == ("foreign_heavy_fund_level_evidence_missing",)
    # decision_rule must mention which leg is missing.
    assert "data" in v.decision_rule or "information" in v.decision_rule


def test_evaluate_policy_b_rule_2_5_data_only_missing_info_fails() -> None:
    """Foreign-heavy with fund-level NAV (data leg) but no announcement (info leg)."""
    from irc.opportunity.policy_b import evaluate_policy_b
    analyses = tuple(
        _ca(
            f"0070{i}.HK", 10.0 - i,
            evidence=(),
            failure_reasons=(f"filing_fetch_failed:0070{i}.HK:KeyError",),
        )
        for i in range(10)
    )
    snap = _snapshot_with_fund_level_evidence(
        analyses=analyses,
        fund_level_evidence=(_evidence_data_instrument("006809"),),  # data only
    )
    v = evaluate_policy_b(snap, top_n=10)
    assert v.gap_codes == ("foreign_heavy_fund_level_evidence_missing",)
    assert "information" in v.decision_rule


def test_evaluate_policy_b_rule_2_5_exact_50_pct_threshold_triggers() -> None:
    """Comparison is `>=`: a fund at exactly 50.0 % HK weight triggers rule 2.5."""
    from irc.opportunity.policy_b import evaluate_policy_b
    hk = tuple(
        _ca(f"0070{i}.HK", 5.0, evidence=(),
            failure_reasons=(f"filing_empty:0070{i}.HK",))
        for i in range(5)
    )
    sh = tuple(
        _ca(f"60000{i}", 5.0, evidence=(),
            failure_reasons=(f"filing_empty:60000{i}",))
        for i in range(5)
    )
    snap = _snapshot_with_fund_level_evidence(
        analyses=hk + sh,
        fund_level_evidence=(
            _evidence_data_instrument("006809"),
            _evidence_info_instrument("006809"),
        ),
    )
    v = evaluate_policy_b(snap, top_n=10)
    # Rule 2.5 fires (share == 0.50, `>=` boundary inclusive) → publishable.
    assert v.gap_codes == ()
    assert v.decision_rule.startswith("foreign-heavy (share=50%)")


def test_evaluate_policy_b_rule_2_5_below_threshold_falls_through_to_rule_3() -> None:
    """49 % HK weight does NOT trigger rule 2.5; existing rule 3 fires on missing data legs."""
    from irc.opportunity.policy_b import evaluate_policy_b
    hk = tuple(
        _ca(f"0070{i}.HK", 4.9, evidence=(),
            failure_reasons=(f"filing_empty:0070{i}.HK",))
        for i in range(5)
    )
    sh = tuple(
        _ca(f"60000{i}", 5.1, evidence=(),
            failure_reasons=(f"filing_empty:60000{i}",))
        for i in range(5)
    )
    snap = _snapshot_with_fund_level_evidence(
        analyses=hk + sh,
        fund_level_evidence=(
            _evidence_data_instrument("006809"),
            _evidence_info_instrument("006809"),
        ),
    )
    v = evaluate_policy_b(snap, top_n=10)
    # Below 50 % → rule 2.5 falls through → rule 3 catches missing data legs.
    assert v.gap_codes == ("incomplete_constituent_data",)


def test_evaluate_policy_b_rule_2_5_cn_only_unchanged_regression_guard() -> None:
    """CN-only fund (0 % foreign) is unaffected by rule 2.5 — existing rule 4 still fires."""
    from irc.opportunity.policy_b import evaluate_policy_b
    # All 10 SH holdings have data leg but no info leg → rule 4 fires.
    analyses = tuple(
        _ca(
            f"60000{i}", 10.0 - i,
            evidence=(_evidence_data(f"60000{i}"),),
        )
        for i in range(10)
    )
    snap = _snapshot_with_fund_level_evidence(
        analyses=analyses,
        fund_level_evidence=(
            _evidence_data_instrument("006809"),
            _evidence_info_instrument("006809"),
        ),
    )
    v = evaluate_policy_b(snap, top_n=10)
    # Foreign share = 0 → rule 2.5 falls through silently → rule 4 fires.
    assert v.gap_codes == ("insufficient_info_coverage_top_half",)


def test_evaluate_policy_b_rule_2_5_does_not_override_rule_1() -> None:
    """Rule 1 (holdings_fetch_failed) precedes rule 2.5 — empty analyses cannot
    be salvaged by fund-level evidence."""
    from irc.opportunity.policy_b import evaluate_policy_b
    snap = _snapshot_with_fund_level_evidence(
        analyses=(),
        fund_level_failure_reasons=("holdings_fetch_failed:006809:Timeout",),
        fund_level_evidence=(
            _evidence_data_instrument("006809"),
            _evidence_info_instrument("006809"),
        ),
    )
    v = evaluate_policy_b(snap, top_n=10)
    assert v.gap_codes == ("holdings_fetch_failed",)


def test_evaluate_policy_b_rule_2_5_does_not_override_rule_2() -> None:
    """Rule 2 (incomplete_constituent_record audit-error) precedes rule 2.5."""
    from irc.opportunity.policy_b import evaluate_policy_b
    # Two HK holdings shape-corrupt: evidence==() AND failure_reasons==().
    analyses = (
        _ca("00700.HK", 6.0, evidence=(), failure_reasons=()),
        _ca("00388.HK", 4.0, evidence=(), failure_reasons=()),
    )
    snap = _snapshot_with_fund_level_evidence(
        analyses=analyses,
        fund_level_evidence=(
            _evidence_data_instrument("006809"),
            _evidence_info_instrument("006809"),
        ),
    )
    v = evaluate_policy_b(snap, top_n=10)
    # Rule 2 fires first; rule 2.5 must NOT paper over the audit error.
    assert v.gap_codes == ("incomplete_constituent_record",)


def test_rejection_reason_code_foreign_heavy_evidence_missing_is_registered() -> None:
    """The new gap code must map to a new RejectionReasonCode."""
    from irc.opportunity.rejection_log import _GAP_TO_REASON
    assert (
        _GAP_TO_REASON["foreign_heavy_fund_level_evidence_missing"]
        == "foreign_heavy_evidence_missing"
    )


def test_active_fund_snapshot_fund_level_evidence_defaults_to_empty() -> None:
    """Backward-compat: existing snapshot constructors compile without supplying the new field."""
    from irc.fundamentals.types import ActiveFundSnapshot
    snap = ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
    )
    assert snap.fund_level_evidence == ()
```

- [ ] **Step 2: Run the new tests; expect them to FAIL**

Run:
```
uv run pytest tests/opportunity/test_policy_b.py -q
```

Expected: existing tests still pass (count: ~32 currently); the ~15 new `test_..._foreign_heavy_*` / `test_compute_foreign_listed_share_*` / `test_foreign_heavy_threshold_constant_is_half` / `test_active_fund_snapshot_fund_level_evidence_defaults_to_empty` / `test_rejection_reason_code_foreign_heavy_evidence_missing_is_registered` tests FAIL with `ImportError`, `AttributeError`, or `TypeError` (e.g. `FOREIGN_HEAVY_THRESHOLD` not defined; `_compute_foreign_listed_share` not defined; `ActiveFundSnapshot.__init__() got an unexpected keyword argument 'fund_level_evidence'`).

- [ ] **Step 3: Commit the failing tests (TDD red phase)**

```bash
git add tests/opportunity/test_policy_b.py
git commit -m "test(policy_b): failing tests for rule 2.5 foreign-heavy short-circuit"
```

---

## Task 2 — Add `fund_level_evidence` field to `ActiveFundSnapshot`

**Files:**
- Modify: `src/irc/fundamentals/types.py:227-234`

- [ ] **Step 1: Append the new field to `ActiveFundSnapshot`**

In `src/irc/fundamentals/types.py`, locate the existing dataclass (currently lines 226–234):

```python
@dataclass(frozen=True)
class ActiveFundSnapshot:
    fund_id: str
    source_report_date: str
    source_report_quarter: str
    cache_probed_at: str
    constituent_analyses: tuple[ConstituentAnalysis, ...]
    failure_reasons_by_symbol: dict[str, tuple[str, ...]]
    fund_level_failure_reasons: tuple[str, ...] = ()
```

Replace it with:

```python
@dataclass(frozen=True)
class ActiveFundSnapshot:
    fund_id: str
    source_report_date: str
    source_report_quarter: str
    cache_probed_at: str
    constituent_analyses: tuple[ConstituentAnalysis, ...]
    failure_reasons_by_symbol: dict[str, tuple[str, ...]]
    fund_level_failure_reasons: tuple[str, ...] = ()
    # Item 001 (decision-confidence-followup): row-level evidence (NAV + announcements)
    # consumed by Policy B rule 2.5 (foreign-heavy short-circuit). Same shape as
    # FundLevelSnapshot.evidence: scope="instrument", owner_instrument_id=fund_id,
    # parent_fund_id=None, constituent_key=None. See ADR 0003 §7.
    fund_level_evidence: tuple[ThesisEvidence, ...] = ()
```

- [ ] **Step 2: Run the backward-compat regression test**

Run:
```
uv run pytest tests/opportunity/test_policy_b.py::test_active_fund_snapshot_fund_level_evidence_defaults_to_empty -q
```

Expected: PASS.

- [ ] **Step 3: Verify existing snapshot tests still pass**

Run:
```
uv run pytest tests/fundamentals/test_snapshot.py tests/fundamentals/test_snapshot_cache.py -q
```

Expected: PASS (no regression from the new defaulted field).

---

## Task 3 — Add `FOREIGN_HEAVY_THRESHOLD` constant + `_compute_foreign_listed_share` helper

**Files:**
- Modify: `src/irc/opportunity/policy_b.py:9-15` (imports) and `:82` (after `_infer_exchange`)

- [ ] **Step 1: Add the constant at module top**

In `src/irc/opportunity/policy_b.py`, find the existing import block (lines 9–15):

```python
from __future__ import annotations

import math
from dataclasses import dataclass

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis
```

Replace with:

```python
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


# Item 001 (decision-confidence-followup): foreign-heavy threshold for Policy B rule 2.5.
# Hardcoded per ADR 0003 §7 — operators tuning thresholds at runtime would silently
# weaken the audit trail. Future promotion to env var follows IRC_CACHE_FRESHNESS_DAYS.
FOREIGN_HEAVY_THRESHOLD: Final[float] = 0.50
_FOREIGN_EXCHANGES: Final[frozenset[str]] = frozenset({"HK", "US"})
```

- [ ] **Step 2: Add the `_compute_foreign_listed_share` helper after `_rank_by_weight`**

In `src/irc/opportunity/policy_b.py`, locate `_rank_by_weight` (currently ends around line 91). Immediately after its closing `return tuple(sorted(...))`, insert:

```python
def _compute_foreign_listed_share(
    ranked: tuple[ConstituentAnalysis, ...],
) -> float:
    """Weight share of constituents listed on HK or US exchanges.

    Returns a fraction in [0.0, 1.0]. Returns 0.0 on empty input or when
    `sum(weight_pct)` is 0 (defensive guard; rule 1 should have caught this).
    Pure, deterministic. Foreign = `_infer_exchange(symbol) in {"HK", "US"}`.
    `UNKNOWN` and `BJ` are NOT counted as foreign (spec non-goal; conservative
    fail-safe per ADR 0003 §7).
    """
    if not ranked:
        return 0.0
    total = sum(c.weight_pct for c in ranked)
    if total <= 0:
        return 0.0
    foreign = sum(
        c.weight_pct for c in ranked
        if _infer_exchange(c.symbol) in _FOREIGN_EXCHANGES
    )
    return foreign / total
```

- [ ] **Step 3: Run the helper tests; expect PASS**

Run:
```
uv run pytest tests/opportunity/test_policy_b.py::test_foreign_heavy_threshold_constant_is_half tests/opportunity/test_policy_b.py::test_compute_foreign_listed_share_all_hk_returns_one tests/opportunity/test_policy_b.py::test_compute_foreign_listed_share_all_cn_returns_zero tests/opportunity/test_policy_b.py::test_compute_foreign_listed_share_empty_input_returns_zero tests/opportunity/test_policy_b.py::test_compute_foreign_listed_share_mixed_below_threshold tests/opportunity/test_policy_b.py::test_compute_foreign_listed_share_exact_50_pct_boundary tests/opportunity/test_policy_b.py::test_compute_foreign_listed_share_unknown_exchange_treated_non_foreign -q
```

Expected: 7 passed.

- [ ] **Step 4: Verify existing Policy B tests still pass (no helper regressions)**

Run:
```
uv run pytest tests/opportunity/test_policy_b.py -q
```

Expected: existing tests + 7 helper tests pass; the rule 2.5 / cache / snapshot tests still FAIL (those need the rule + plumbing).

---

## Task 4 — Insert rule 2.5 into `evaluate_policy_b`

**Files:**
- Modify: `src/irc/opportunity/policy_b.py:215-235` (between rule 2 and rule 3)

- [ ] **Step 1: Insert the rule 2.5 block between rule 2 and rule 3**

In `src/irc/opportunity/policy_b.py`, locate the rule 2 block. It ends with the publishable-style return inside the `if missing:` branch. Immediately AFTER that block (i.e. after the line `)` that closes the rule-2 `return PolicyBVerdict(...)` and BEFORE the comment `# Rule 3: per-holding data leg required for ALL ranked holdings.`), insert this new block:

```python
    # Rule 2.5: foreign-heavy short-circuit (item 001, ADR 0003 §7).
    # Active CN equity funds with ≥ 50 % top-N weight listed on HK or US
    # exchanges (e.g. 006809) cannot satisfy rule 3's per-holding data leg
    # because the CN filings pipeline doesn't reach HK/US tickers. Accept
    # fund-level NAV + announcement evidence as the dual-coverage substitute.
    foreign_share = _compute_foreign_listed_share(ranked)
    if foreign_share >= FOREIGN_HEAVY_THRESHOLD:
        fund_evidence = snapshot.fund_level_evidence
        has_data = any(e.citation_kind == "data" for e in fund_evidence)
        has_info = any(e.citation_kind == "information" for e in fund_evidence)
        share_pct = f"{foreign_share * 100:.0f}%"
        if has_data and has_info:
            return PolicyBVerdict(
                gap_codes=(),
                audit_errors=(),
                decision_rule=(
                    f"foreign-heavy (share={share_pct}); fund-level "
                    f"NAV+announcements accepted"
                ),
                material_symbols=_material_symbols(ranked, top_n),
                constituent_coverage=_build_coverage_entries(ranked, top_n),
            )
        missing_legs: list[str] = []
        if not has_data:
            missing_legs.append("data")
        if not has_info:
            missing_legs.append("information")
        return PolicyBVerdict(
            gap_codes=("foreign_heavy_fund_level_evidence_missing",),
            audit_errors=(),
            decision_rule=(
                f"foreign-heavy (share={share_pct}); fund-level evidence "
                f"missing legs: {missing_legs}"
            ),
            material_symbols=_material_symbols(ranked, top_n),
            constituent_coverage=_build_coverage_entries(ranked, top_n),
        )

```

- [ ] **Step 2: Update the module docstring**

In `src/irc/opportunity/policy_b.py`, replace the existing docstring (lines 1–8):

```python
"""Item 006 Slice H2.v2 — Policy B weight-aware quorum evaluator.

Five-rule precedence (1 → 2 → 3 → 4 → 5), locked by ADR 0003 §1. Each rule
short-circuits when it fires. Applies ONLY to `ActiveFundSnapshot` — passive
`FundLevelSnapshot` and legacy `ConstituentSnapshot` never feed this module.

See `docs/adr/0003-failure-mode-policy-b.md` for the full rationale.
"""
```

With:

```python
"""Item 006 Slice H2.v2 — Policy B weight-aware quorum evaluator.

Six-rule precedence (1 → 2 → 2.5 → 3 → 4 → 5), locked by ADR 0003 §1+§7.
Each rule short-circuits when it fires. Applies ONLY to `ActiveFundSnapshot`
— passive `FundLevelSnapshot` and legacy `ConstituentSnapshot` never feed
this module. Rule 2.5 (item 001 amendment) accepts fund-level NAV+announcement
evidence in lieu of per-holding filings when foreign weight share ≥ 50 %.

See `docs/adr/0003-failure-mode-policy-b.md` for the full rationale.
"""
```

- [ ] **Step 3: Run the rule 2.5 tests; expect PASS**

Run:
```
uv run pytest tests/opportunity/test_policy_b.py -q
```

Expected: ALL Policy B tests pass except the `test_rejection_reason_code_foreign_heavy_evidence_missing_is_registered` (which Task 5 implements). Specifically the new rule 2.5 publishable / missing-evidence / threshold / regression-guard / precedence tests should all PASS.

- [ ] **Step 4: Commit the rule + helper**

```bash
git add src/irc/opportunity/policy_b.py src/irc/fundamentals/types.py
git commit -m "feat(policy_b): add rule 2.5 foreign-heavy short-circuit (item 001)"
```

---

## Task 5 — Register the new `RejectionReasonCode` literal

**Files:**
- Modify: `src/irc/opportunity/rejection_log.py:23-34` (Literal tuple) and `:63-98` (dict)

- [ ] **Step 1: Add the new literal to `RejectionReasonCode`**

In `src/irc/opportunity/rejection_log.py`, replace the existing `RejectionReasonCode` definition (lines 23–34):

```python
RejectionReasonCode = Literal[
    "holdings_fetch_failed",
    "incomplete_constituent_record",
    "incomplete_constituent_data",
    "insufficient_info_coverage_top_half",
    "incomplete_constituent_coverage",
    "qdii_information_unavailable",
    "fund_nav_unavailable",
    "fund_announcements_unavailable",
    "missing_us_news_adapter",
    "citation_gate_blocked",  # Item 009 Q4 — set by opportunity-stage citation gate.
]
```

With:

```python
RejectionReasonCode = Literal[
    "holdings_fetch_failed",
    "incomplete_constituent_record",
    "incomplete_constituent_data",
    "insufficient_info_coverage_top_half",
    "incomplete_constituent_coverage",
    "qdii_information_unavailable",
    "fund_nav_unavailable",
    "fund_announcements_unavailable",
    "missing_us_news_adapter",
    "citation_gate_blocked",  # Item 009 Q4 — set by opportunity-stage citation gate.
    # Item 001 (decision-confidence-followup): Policy B rule 2.5 failure branch.
    "foreign_heavy_evidence_missing",
]
```

- [ ] **Step 2: Append the new entry LAST in `_GAP_TO_REASON`**

In the same file, locate the closing `}` of `_GAP_TO_REASON` (currently at line 98 — the line right after the `"citation_gate_blocked": "citation_gate_blocked",` entry). Insert one new entry immediately BEFORE the closing brace:

Find:

```python
    # Item 009 Q4: opportunity-stage citation gate stamp.
    # Identity mapping (gap code IS the rejection reason). Appended LAST so
    # existing precedence (qdii first, etc.) is unchanged. Item 008 AC11's
    # hard-coded "qdii_information_unavailable" string stays valid.
    "citation_gate_blocked":                "citation_gate_blocked",
}
```

Replace with:

```python
    # Item 009 Q4: opportunity-stage citation gate stamp.
    # Identity mapping (gap code IS the rejection reason). Appended LAST so
    # existing precedence (qdii first, etc.) is unchanged. Item 008 AC11's
    # hard-coded "qdii_information_unavailable" string stays valid.
    "citation_gate_blocked":                "citation_gate_blocked",
    # Item 001 (decision-confidence-followup): Policy B rule 2.5 failure branch.
    # Identity mapping. Appended LAST (mirroring `citation_gate_blocked` precedent)
    # so existing precedence (QDII first, structural Policy B codes next) is
    # unchanged. See ADR 0003 §7.
    "foreign_heavy_fund_level_evidence_missing": "foreign_heavy_evidence_missing",
}
```

- [ ] **Step 3: Run the rejection-log test; expect PASS**

Run:
```
uv run pytest tests/opportunity/test_policy_b.py::test_rejection_reason_code_foreign_heavy_evidence_missing_is_registered tests/opportunity/test_rejection_log.py -q
```

Expected: PASS (new mapping test + all existing rejection-log tests).

- [ ] **Step 4: Commit the rejection-log change**

```bash
git add src/irc/opportunity/rejection_log.py
git commit -m "feat(rejection_log): register foreign_heavy_evidence_missing code (item 001)"
```

---

## Task 6 — Wire `_build_active_fund_snapshot` to fetch fund-level NAV + announcements

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py:446-494`

- [ ] **Step 1: Add a small fund-level evidence builder helper in `snapshot.py`**

In `src/irc/fundamentals/snapshot.py`, immediately BEFORE `_build_active_fund_snapshot` (currently line 446), insert a new helper that mirrors the citation shape used by `_build_fund_level_snapshot`:

```python
def _fetch_active_fund_level_evidence(
    fund_id: str,
) -> tuple[tuple[ThesisEvidence, ...], list[str]]:
    """Fetch fund-level NAV + announcements for an active fund.

    Mirrors the citation shape produced by `_build_fund_level_snapshot`:
    scope="instrument", owner_instrument_id=fund_id, parent_fund_id=None,
    constituent_key=None. Returns (evidence_tuple, failure_reasons_list).
    Item 001 (ADR 0003 §7): Policy B rule 2.5 consumes the data + information
    legs to short-circuit foreign-heavy funds. Per-fund call delta = 2 AkShare
    calls; see `_fetch_budget` in opportunity_cmd.py (default budget 2000).
    """
    evidence: list[ThesisEvidence] = []
    failures: list[str] = []
    try:
        nav = fetch_fund_nav_report(fund_id)
    except Exception as exc:
        failures.append(f"fund_nav_fetch_failed:{fund_id}:{type(exc).__name__}")
        nav = None
    if nav is not None:
        evidence.append(ThesisEvidence(
            type="snapshot",
            source=fund_id,
            url="",
            date=nav.latest_nav_date,
            summary=f"NAV={nav.latest_nav:.4f} @ {nav.latest_nav_date}",
            scope="instrument",
            citation_kind="data",
            owner_instrument_id=fund_id,
            parent_fund_id=None,
            constituent_key=None,
        ))
    else:
        failures.append(f"fund_nav_unavailable:{fund_id}")
    try:
        anns = fetch_fund_announcements(fund_id)
    except Exception as exc:
        failures.append(
            f"fund_announcements_fetch_failed:{fund_id}:{type(exc).__name__}"
        )
        anns = ()
    if anns:
        for a in anns[:_FUND_LEVEL_INFO_CAP]:
            evidence.append(ThesisEvidence(
                type="news",
                source=f"fund_announcement_{a.topic}_em",
                url="",
                date=a.date,
                summary=f"[{a.report_id}] {a.title}",
                scope="instrument",
                citation_kind="information",
                owner_instrument_id=fund_id,
                parent_fund_id=None,
                constituent_key=None,
            ))
    else:
        failures.append(f"fund_announcements_unavailable:{fund_id}")
    return tuple(evidence), failures
```

- [ ] **Step 2: Plumb the helper into `_build_active_fund_snapshot`**

In `src/irc/fundamentals/snapshot.py`, locate `_build_active_fund_snapshot` (currently lines 446–494). Replace the function body's existing tail (the final `return ActiveFundSnapshot(...)` block in the success path AND the early-return empty-holdings block) with versions that thread `fund_level_evidence` through. Find:

```python
def _build_active_fund_snapshot(
    target: LookthroughTarget, *, top_n: int,
) -> ActiveFundSnapshot:
    """Fetch holdings then per-constituent evidence per exchange routing."""
    fund_id = target.provider_symbol
    holdings = fetch_cn_etf_holdings(target.provider_symbol, top_n=top_n)
    if not holdings.constituents:
        return ActiveFundSnapshot(
            fund_id=fund_id,
            source_report_date=holdings.source_report_date,
            source_report_quarter=holdings.source_report_quarter,
            cache_probed_at="",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
            fund_level_failure_reasons=(
                f"holdings_fetch_failed:{fund_id}:empty",
            ),
        )
```

Replace with:

```python
def _build_active_fund_snapshot(
    target: LookthroughTarget, *, top_n: int,
) -> ActiveFundSnapshot:
    """Fetch holdings then per-constituent evidence per exchange routing.

    Item 001 (ADR 0003 §7): ALWAYS fetches fund-level NAV + announcements so
    Policy B rule 2.5 can short-circuit foreign-heavy funds whose top-N
    holdings are HK/US-listed (and therefore unreachable by the per-holding
    CN filings pipeline).
    """
    fund_id = target.provider_symbol
    holdings = fetch_cn_etf_holdings(target.provider_symbol, top_n=top_n)
    fund_evidence, fund_evidence_failures = _fetch_active_fund_level_evidence(fund_id)
    if not holdings.constituents:
        return ActiveFundSnapshot(
            fund_id=fund_id,
            source_report_date=holdings.source_report_date,
            source_report_quarter=holdings.source_report_quarter,
            cache_probed_at="",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
            fund_level_failure_reasons=(
                f"holdings_fetch_failed:{fund_id}:empty",
            ) + tuple(fund_evidence_failures),
            fund_level_evidence=fund_evidence,
        )
```

Then find the success-path return at the bottom of `_build_active_fund_snapshot`:

```python
    return ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date=holdings.source_report_date,
        source_report_quarter=holdings.source_report_quarter,
        cache_probed_at="",
        constituent_analyses=tuple(analyses),
        failure_reasons_by_symbol=fail_by_symbol,
        fund_level_failure_reasons=tuple(fund_level_failures),
    )
```

Replace with:

```python
    return ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date=holdings.source_report_date,
        source_report_quarter=holdings.source_report_quarter,
        cache_probed_at="",
        constituent_analyses=tuple(analyses),
        failure_reasons_by_symbol=fail_by_symbol,
        fund_level_failure_reasons=tuple(fund_level_failures) + tuple(fund_evidence_failures),
        fund_level_evidence=fund_evidence,
    )
```

- [ ] **Step 3: Add producer-side test in `tests/fundamentals/test_snapshot.py`**

Append the following test at the end of `tests/fundamentals/test_snapshot.py`:

```python
def test_build_active_fund_snapshot_populates_fund_level_evidence(monkeypatch):
    """Item 001: _build_active_fund_snapshot must fetch NAV + announcements
    and stamp them on `fund_level_evidence`."""
    from datetime import date as _date
    from irc.fundamentals import snapshot as _snap_mod
    from irc.fundamentals.types import (
        FundAnnouncement,
        FundHolding,
        FundNavReport,
        HoldingsResult,
        LookthroughTarget,
    )

    fund_id = "006809"

    def _fake_holdings(provider_symbol: str, *, top_n: int) -> HoldingsResult:
        assert provider_symbol == fund_id
        return HoldingsResult(
            constituents=(
                FundHolding(
                    symbol="00700.HK",
                    name_cn="腾讯控股",
                    weight_pct=10.0,
                    exchange="HK",
                    provider_symbol="00700.HK",
                ),
            ),
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
        )

    def _fake_nav(fid: str) -> FundNavReport:
        assert fid == fund_id
        return FundNavReport(
            fund_id=fid,
            fund_name="泰康香港银行指数A",
            latest_nav=1.2345,
            latest_nav_date="2024-04-15",
            nav_history=(("2024-04-15", 1.2345),),
            source_report_quarter="2024Q1",
        )

    def _fake_announcements(fid: str):
        assert fid == fund_id
        return (
            FundAnnouncement(
                fund_id=fid,
                title="季度报告",
                topic="report",
                date="2024-04-10",
                report_id="REP-1",
            ),
        )

    def _fake_evidence_for_constituent(holding, *, fund_id):
        # HK holding hits the no-filings path in real code; emulate empty.
        return (), [f"filing_fetch_failed:{holding.symbol}:KeyError"]

    monkeypatch.setattr(_snap_mod, "fetch_cn_etf_holdings", _fake_holdings)
    monkeypatch.setattr(_snap_mod, "fetch_fund_nav_report", _fake_nav)
    monkeypatch.setattr(_snap_mod, "fetch_fund_announcements", _fake_announcements)
    monkeypatch.setattr(
        _snap_mod, "_evidence_for_constituent", _fake_evidence_for_constituent
    )

    target = LookthroughTarget(
        kind="active_fund",
        key=fund_id,
        display_cn="泰康香港银行指数A",
        provider_symbol=fund_id,
    )
    snap = _snap_mod._build_active_fund_snapshot(target, top_n=10)

    assert len(snap.fund_level_evidence) == 2
    kinds = sorted(e.citation_kind for e in snap.fund_level_evidence)
    assert kinds == ["data", "information"]
    for e in snap.fund_level_evidence:
        assert e.scope == "instrument"
        assert e.owner_instrument_id == fund_id
        assert e.parent_fund_id is None
        assert e.constituent_key is None
```

- [ ] **Step 4: Run the producer test**

Run:
```
uv run pytest tests/fundamentals/test_snapshot.py::test_build_active_fund_snapshot_populates_fund_level_evidence -q
```

Expected: PASS.

- [ ] **Step 5: Run the broader fundamentals suite to check no regressions**

Run:
```
uv run pytest tests/fundamentals/ -q
```

Expected: PASS (the new defaulted field + new fetch path do not break existing tests because the AkShare mocks in those tests don't intercept `fetch_fund_nav_report` / `fetch_fund_announcements`, which now run for real — verify they don't break offline; if any test fails because it hits the network, monkeypatch those adapters in those tests too. As a fallback, keep the new fetch path resilient to exceptions per Task 6 Step 1).

If any existing test breaks because `_build_active_fund_snapshot` now calls the two adapters, monkeypatch them in that test's setup to return `None` / `()`. Document the patch inline.

---

## Task 7 — Round-trip `fund_level_evidence` through the active-fund cache

**Files:**
- Modify: `src/irc/fundamentals/snapshot_cache.py:172-208`

- [ ] **Step 1: Add the field to `_active_fund_to_dict`**

In `src/irc/fundamentals/snapshot_cache.py`, find:

```python
def _active_fund_to_dict(snap: ActiveFundSnapshot) -> dict[str, Any]:
    return {
        "fund_id": snap.fund_id,
        "source_report_date": snap.source_report_date,
        "source_report_quarter": snap.source_report_quarter,
        "cache_probed_at": snap.cache_probed_at,
        "constituent_analyses": [
            _constituent_to_dict(c) for c in snap.constituent_analyses
        ],
        "failure_reasons_by_symbol": {
            k: list(v) for k, v in snap.failure_reasons_by_symbol.items()
        },
        "fund_level_failure_reasons": list(snap.fund_level_failure_reasons),
    }
```

Replace with:

```python
def _active_fund_to_dict(snap: ActiveFundSnapshot) -> dict[str, Any]:
    return {
        "fund_id": snap.fund_id,
        "source_report_date": snap.source_report_date,
        "source_report_quarter": snap.source_report_quarter,
        "cache_probed_at": snap.cache_probed_at,
        "constituent_analyses": [
            _constituent_to_dict(c) for c in snap.constituent_analyses
        ],
        "failure_reasons_by_symbol": {
            k: list(v) for k, v in snap.failure_reasons_by_symbol.items()
        },
        "fund_level_failure_reasons": list(snap.fund_level_failure_reasons),
        # Item 001 (ADR 0003 §7): row-level NAV+announcement evidence consumed
        # by Policy B rule 2.5. Older cache files lacking this key re-hydrate
        # with `()`; the next freshness probe fires a fresh fetch.
        "fund_level_evidence": [
            _evidence_to_dict(e) for e in snap.fund_level_evidence
        ],
    }
```

- [ ] **Step 2: Add the field to `_active_fund_from_dict`**

Find:

```python
def _active_fund_from_dict(body: dict[str, Any]) -> ActiveFundSnapshot | None:
    needed = {"fund_id", "source_report_quarter", "constituent_analyses"}
    if not needed.issubset(body):
        return None
    try:
        analyses = tuple(
            _constituent_from_dict(c) for c in body["constituent_analyses"]
        )
    except (KeyError, TypeError, ValueError):
        return None
    return ActiveFundSnapshot(
        fund_id=str(body["fund_id"]),
        source_report_date=str(body.get("source_report_date", "")),
        source_report_quarter=str(body["source_report_quarter"]),
        cache_probed_at=str(body.get("cache_probed_at", "")),
        constituent_analyses=analyses,
        failure_reasons_by_symbol={
            k: tuple(v) for k, v in body.get("failure_reasons_by_symbol", {}).items()
        },
        fund_level_failure_reasons=tuple(body.get("fund_level_failure_reasons", ())),
    )
```

Replace with:

```python
def _active_fund_from_dict(body: dict[str, Any]) -> ActiveFundSnapshot | None:
    needed = {"fund_id", "source_report_quarter", "constituent_analyses"}
    if not needed.issubset(body):
        return None
    try:
        analyses = tuple(
            _constituent_from_dict(c) for c in body["constituent_analyses"]
        )
        fund_level_evidence = tuple(
            _evidence_from_dict(e) for e in body.get("fund_level_evidence", [])
        )
    except (KeyError, TypeError, ValueError):
        return None
    return ActiveFundSnapshot(
        fund_id=str(body["fund_id"]),
        source_report_date=str(body.get("source_report_date", "")),
        source_report_quarter=str(body["source_report_quarter"]),
        cache_probed_at=str(body.get("cache_probed_at", "")),
        constituent_analyses=analyses,
        failure_reasons_by_symbol={
            k: tuple(v) for k, v in body.get("failure_reasons_by_symbol", {}).items()
        },
        fund_level_failure_reasons=tuple(body.get("fund_level_failure_reasons", ())),
        fund_level_evidence=fund_level_evidence,
    )
```

- [ ] **Step 3: Add a round-trip test in `tests/fundamentals/test_snapshot_cache.py`**

Append at the end of `tests/fundamentals/test_snapshot_cache.py`:

```python
def test_active_fund_cache_round_trips_fund_level_evidence(tmp_path):
    """Item 001 (ADR 0003 §7): fund_level_evidence is preserved across
    write_active_fund_cache → load_active_fund_cache."""
    from irc.fundamentals.snapshot_cache import (
        load_active_fund_cache,
        write_active_fund_cache,
    )
    from irc.fundamentals.types import ActiveFundSnapshot, ThesisEvidence

    fund_id = "006809"
    nav_evidence = ThesisEvidence(
        type="snapshot",
        source=fund_id,
        url="",
        date="2024-04-15",
        summary="NAV=1.2345 @ 2024-04-15",
        scope="instrument",
        citation_kind="data",
        owner_instrument_id=fund_id,
        parent_fund_id=None,
        constituent_key=None,
    )
    ann_evidence = ThesisEvidence(
        type="news",
        source="fund_announcement_report_em",
        url="",
        date="2024-04-10",
        summary="[REP-1] 季度报告",
        scope="instrument",
        citation_kind="information",
        owner_instrument_id=fund_id,
        parent_fund_id=None,
        constituent_key=None,
    )
    snap = ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="2024-04-20",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=(),
        fund_level_evidence=(nav_evidence, ann_evidence),
    )
    # Snapshots with empty constituent_analyses still serialise — the cache
    # writer doesn't gate on that.
    write_active_fund_cache(snap, tmp_path)
    loaded = load_active_fund_cache(fund_id, "2024Q1", tmp_path)
    assert loaded is not None
    assert len(loaded.fund_level_evidence) == 2
    assert {e.citation_kind for e in loaded.fund_level_evidence} == {"data", "information"}
    assert all(e.owner_instrument_id == fund_id for e in loaded.fund_level_evidence)


def test_active_fund_cache_legacy_file_rehydrates_with_empty_fund_level_evidence(tmp_path):
    """Older cache files missing `fund_level_evidence` re-hydrate to `()`."""
    import json
    from irc.fundamentals.snapshot_cache import (
        active_fund_cache_path,
        load_active_fund_cache,
    )

    fund_id = "005827"
    quarter = "2024Q1"
    path = active_fund_cache_path(fund_id, quarter, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "fund_id": fund_id,
        "source_report_date": "2024-03-31",
        "source_report_quarter": quarter,
        "cache_probed_at": "",
        "constituent_analyses": [],
        "failure_reasons_by_symbol": {},
        "fund_level_failure_reasons": [],
    }), encoding="utf-8")
    loaded = load_active_fund_cache(fund_id, quarter, tmp_path)
    assert loaded is not None
    assert loaded.fund_level_evidence == ()
```

- [ ] **Step 4: Run the cache tests**

Run:
```
uv run pytest tests/fundamentals/test_snapshot_cache.py -q
```

Expected: PASS (new round-trip + legacy-file tests + all existing snapshot_cache tests).

- [ ] **Step 5: Commit the producer + cache changes**

```bash
git add src/irc/fundamentals/snapshot.py src/irc/fundamentals/snapshot_cache.py tests/fundamentals/test_snapshot.py tests/fundamentals/test_snapshot_cache.py
git commit -m "feat(fundamentals): stamp fund_level_evidence on ActiveFundSnapshot (item 001)"
```

---

## Task 8 — Wire `_stamp_fund_level_evidence_from_verdict` into the opportunity command

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py:978-994` (verdict-stamping branch) and `:1045-1075` (sibling helper)

- [ ] **Step 1: Add the new helper next to `_stamp_audit_errors_from_verdict`**

In `src/irc/commands/opportunity_cmd.py`, immediately AFTER the existing `_stamp_audit_errors_from_verdict` function (which currently ends around line 1074), insert:

```python
def _stamp_fund_level_evidence_from_verdict(
    row: OpportunityRow,
    snapshot: ActiveFundSnapshot,
    verdict: PolicyBVerdict,
) -> OpportunityRow:
    """Merge `snapshot.fund_level_evidence` into `row.thesis_evidence` when
    Policy B rule 2.5 fires with `gap_codes=()`.

    Item 001 (ADR 0003 §7): rule 2.5 is the foreign-heavy short-circuit;
    publishable rows must carry the fund-level NAV + announcement citations
    so the downstream dual-coverage gate, picks table, evidence pool, and
    discipline thesis bullets see ≥1 data + ≥1 information citation at
    scope="instrument" with owner_instrument_id == row.instrument_id.

    Pure copy-replace via `dataclasses.replace`. Skipped when:
    - the verdict is not publishable (`gap_codes != ()`);
    - the snapshot already has empty `fund_level_evidence` (defensive — the
      rule wouldn't have published, but guard for clarity).

    Distinct from `_stamp_audit_errors_from_verdict` (which merges
    per-constituent audit_errors into `constituent_analyses`); the two
    helpers run in sequence on publishable rows. See spec Q-G3 / grill.
    """
    if verdict.gap_codes:
        return row
    if not snapshot.fund_level_evidence:
        return row
    # Only stamp when the publishable verdict came via rule 2.5. Identify by
    # the decision_rule prefix locked in `evaluate_policy_b` rule 2.5.
    if not verdict.decision_rule.startswith("foreign-heavy"):
        return row
    return replace(
        row,
        thesis_evidence=row.thesis_evidence + snapshot.fund_level_evidence,
    )
```

- [ ] **Step 2: Call the new helper alongside `_stamp_audit_errors_from_verdict`**

In `src/irc/commands/opportunity_cmd.py`, locate the verdict-stamping block (currently lines 981–990):

```python
            if isinstance(snap_obj, ActiveFundSnapshot):
                verdict = evaluate_policy_b(snap_obj, top_n=TOP_N_DEFAULT)
                if verdict.gap_codes:
                    row = replace(
                        row,
                        evidence_gaps=row.evidence_gaps + verdict.gap_codes,
                    )
                else:
                    row = _stamp_audit_errors_from_verdict(row, verdict)
                pending_verdicts[row.instrument_id] = verdict
```

Replace with:

```python
            if isinstance(snap_obj, ActiveFundSnapshot):
                verdict = evaluate_policy_b(snap_obj, top_n=TOP_N_DEFAULT)
                if verdict.gap_codes:
                    row = replace(
                        row,
                        evidence_gaps=row.evidence_gaps + verdict.gap_codes,
                    )
                else:
                    row = _stamp_audit_errors_from_verdict(row, verdict)
                    # Item 001 (ADR 0003 §7): rule 2.5 publishable rows must
                    # surface fund-level NAV+announcement evidence on the row
                    # so the dual-coverage gate accepts them.
                    row = _stamp_fund_level_evidence_from_verdict(
                        row, snap_obj, verdict,
                    )
                pending_verdicts[row.instrument_id] = verdict
```

- [ ] **Step 3: Run the full Policy B suite + cmd-adjacent tests**

Run:
```
uv run pytest tests/opportunity/test_policy_b.py tests/opportunity/test_rejection_log.py tests/opportunity/test_failure_renderer.py tests/fundamentals/test_snapshot.py tests/fundamentals/test_snapshot_cache.py -q
```

Expected: ALL tests pass — full Policy B (including the ~15 new tests), rejection log, failure renderer, snapshot, snapshot cache.

- [ ] **Step 4: Run the full unit + integration suite (no network)**

Run:
```
uv run pytest -q
```

Expected: full green. If any test breaks because `_build_active_fund_snapshot` now eagerly fetches NAV/announcements during tests that aren't mocking those adapters, monkeypatch them in those specific tests to return `None` / `()`. Do NOT regress green to amber.

- [ ] **Step 5: Lint**

Run:
```
uv run ruff check src tests
```

Expected: clean.

- [ ] **Step 6: Commit the stamper wiring**

```bash
git add src/irc/commands/opportunity_cmd.py
git commit -m "feat(opportunity): stamp fund_level_evidence on rule 2.5 rows (item 001)"
```

---

## Task 9 — Spec acceptance: confirm 006809 unblocks end-to-end (best-effort, offline)

**Files:**
- No source changes; this task verifies AC16 if a 2026-05-26 fixture exists.

- [ ] **Step 1: Inspect existing 2026-05-26 fixtures**

Run:
```
ls outputs/2026-05-26/ 2>/dev/null || echo "no fixture for today"
ls outputs/ | tail -5
```

If a `2026-05-26` output dir exists, proceed to Step 2. Otherwise, this task is a documentation-only acceptance: the unit tests in Task 1 cover the structural behaviour, and the operator can re-run `irc opportunity` against today's cache after the deploy.

- [ ] **Step 2: Re-run `irc opportunity` if cache is present and 006809 is in the universe**

Run:
```
uv run irc opportunity
```

Expected: process completes; `outputs/2026-05-26/rejections.json` no longer carries an entry for `006809` with `rejection_reason == "incomplete_constituent_data"`. If the cache is stale, the run will trigger a fresh fetch (rule-2.5 NAV+announcements path), which lands the new field on disk.

- [ ] **Step 3: Verify the rejection JSON**

Run:
```
uv run python -c "
import json, pathlib
p = pathlib.Path('outputs/2026-05-26/rejections.json')
if not p.exists():
    print('no rejections.json — skipping')
else:
    doc = json.loads(p.read_text())
    for e in doc.get('entries', []):
        if e.get('instrument_id') == '006809':
            print('006809 still rejected:', e.get('rejection_reason'))
            break
    else:
        print('006809 not rejected (passes Policy B rule 2.5)')
"
```

Expected output: `006809 not rejected (passes Policy B rule 2.5)` OR `no rejections.json — skipping`. If the script prints `006809 still rejected: incomplete_constituent_data`, the rule didn't fire — re-check Task 4 Step 1.

- [ ] **Step 4: No commit if no code change**

If `irc opportunity` produced new outputs, do NOT commit them unless explicitly requested.

---

## Self-Review

**Spec coverage:**
- AC1 (`FOREIGN_HEAVY_THRESHOLD: float = 0.50` module constant) — Task 3.
- AC2 (`_compute_foreign_listed_share` pure helper, returns `[0.0, 1.0]`, `0.0` on empty) — Task 3 + Task 1 tests.
- AC3 (`ActiveFundSnapshot.fund_level_evidence: tuple[ThesisEvidence, ...] = ()`) — Task 2.
- AC4 (`_build_active_fund_snapshot` ALWAYS fetches NAV+announcements; failures append to `fund_level_failure_reasons`) — Task 6.
- AC5 (rule 2.5 inserted between rules 2 and 3; `>=` threshold; data + info → publishable; missing → new gap code) — Task 4.
- AC6 (`_stamp_fund_level_evidence_from_verdict` new sibling helper) — Task 8.
- AC7 (`foreign_heavy_evidence_missing` RejectionReasonCode literal + `_GAP_TO_REASON` entry appended LAST) — Task 5.
- AC8 (publishable fixture: `"foreign-heavy (share=100%)"` prefix) — Task 1.
- AC9 (missing-evidence fixture: `("foreign_heavy_fund_level_evidence_missing",)` with leg detail) — Task 1.
- AC10 (CN-only fixture unchanged) — Task 1 regression-guard test.
- AC11 (49 % HK does NOT trigger) — Task 1 below-threshold test.
- AC12 (exact 50 % triggers because `>=`) — Task 1 boundary test.
- AC13 (ADR §7 amendment) — already committed in grill commit `d882685`.
- AC14 (CONTEXT.md bullet) — already committed in grill commit `d882685`.
- AC15 (TDD: failing test before implementation) — Task 1 Step 3 commits tests first; Task 4 Step 4 commits the rule.
- AC16 (end-to-end 006809 unblock) — Task 9 (best-effort).

**Placeholder scan:** no `TBD`/`TODO`/`implement later`/`appropriate error handling` strings. All code blocks are verbatim. Exact commands with expected output included.

**Type consistency:** `_compute_foreign_listed_share`, `FOREIGN_HEAVY_THRESHOLD`, `fund_level_evidence`, `_stamp_fund_level_evidence_from_verdict`, `foreign_heavy_fund_level_evidence_missing` (gap code) and `foreign_heavy_evidence_missing` (rejection-reason literal) all match between definition and consumer tasks.

---

**Step count:** 9 tasks, 35 individually-numbered steps.

**Test strategy summary:**
- `test_foreign_heavy_threshold_constant_is_half` — constant exists and equals 0.50.
- `test_compute_foreign_listed_share_*` (6 cases) — pure helper: all-HK → 1.0, all-CN → 0.0, empty → 0.0, mixed below threshold → 0.49, exact 50 % boundary, UNKNOWN/BJ excluded.
- `test_evaluate_policy_b_rule_2_5_foreign_heavy_publishable` — full-HK fund with NAV+announcement evidence publishes (`gap_codes=()`, decision_rule prefix `"foreign-heavy (share=100%)"`).
- `test_evaluate_policy_b_rule_2_5_foreign_heavy_missing_evidence_fails` — full-HK fund with empty `fund_level_evidence` fails with new code.
- `test_evaluate_policy_b_rule_2_5_data_only_missing_info_fails` — NAV but no announcement → still fails (information leg required).
- `test_evaluate_policy_b_rule_2_5_exact_50_pct_threshold_triggers` — boundary inclusive.
- `test_evaluate_policy_b_rule_2_5_below_threshold_falls_through_to_rule_3` — 49 % HK → existing rule 3 still fires (regression guard).
- `test_evaluate_policy_b_rule_2_5_cn_only_unchanged_regression_guard` — 0 % foreign → existing rule 4 unchanged.
- `test_evaluate_policy_b_rule_2_5_does_not_override_rule_1` / `..._rule_2` — precedence preserved.
- `test_rejection_reason_code_foreign_heavy_evidence_missing_is_registered` — `_GAP_TO_REASON` mapping.
- `test_active_fund_snapshot_fund_level_evidence_defaults_to_empty` — backward-compat (constructors compile).
- `test_build_active_fund_snapshot_populates_fund_level_evidence` — producer monkeypatched to confirm the snapshot carries the fund-level citations.
- `test_active_fund_cache_round_trips_fund_level_evidence` — serializer write/load round-trip preserves the new field.
- `test_active_fund_cache_legacy_file_rehydrates_with_empty_fund_level_evidence` — older cache files without the field load with `()`.

**Spec gaps (judgment calls):**
- Spec §AC16 ties end-to-end success to today's `outputs/2026-05-26/`. Treated as best-effort verification (Task 9) — the unit-test suite proves the structural behaviour; the e2e proof requires the operator's live cache.
- Spec implementation-note mentions a possible rename of `_stamp_audit_errors_from_verdict` to `_stamp_publishable_extras_from_verdict`. Grill Q-G3 supersedes this with "factor a NEW helper alongside". Plan follows the grill outcome (Task 8); no rename.
