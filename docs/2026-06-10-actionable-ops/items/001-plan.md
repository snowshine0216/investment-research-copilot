# Item 001 — Sell surfacing + holdings-aware deltas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thread the discipline layer's already-derived sell-side signals (`risk_action` / `dca_action` / `portfolio_weight` / `is_holding`) through `opportunity_report.json` into the decision layer, where a pure mapper produces a real `portfolio_action` plus a current-vs-target weight delta, a new `## 持仓行动 / Sell · Trim · Review` report section, and additive machine-readable summary counts (`trim_count` / `exit_count` / `review_count`) for item 002's notifier.

**Architecture:** Approach B (ADR 0015 §1) — the opportunity stage emits the four discipline fields onto each *publishable* row via a defaulted `discipline_by_id` keyword on `compose_opportunity_report` (built at the command edge from `discipline_rows` + `positions[iid]`); the decision command reads them back out of the `opportunity_state_by_id` map it already loads and feeds them to a new pure `map_portfolio_action` mapper (`src/irc/decision/portfolio_action.py`). All I/O stays in `commands/`; mapper, gates, report, and models stay pure. Frozen dataclasses extended only via defaulted fields; public signatures extended only via defaulted keywords (back-compat preserved).

**Tech Stack:** Python 3.12, frozen dataclasses, pytest (targeted paths only — full suite ~18 min, not green on main), ruff (line-length 100, py312), uv.

**Reference contracts (read before starting):**
- `docs/2026-06-10-actionable-ops/items/001-spec.md` — the spec (REFINED; note the R1 strike-through about `compose_opportunity_report` signature)
- `docs/adr/0015-portfolio-action-emission-contract.md` — the locked emission contract

**Locked invariants this plan must leave provably untouched** (Task 6 runs the guard tests):
- H3 universal gapped-row invariant — only publishable rows (`evidence_gaps == ()`) reach `opportunity_report.json`; the four new keys are added to the *same* publishable-row dict.
- SAME-3 — no new `[ref:...]` markers; `select_citations(cap=3)` surfaces unchanged.
- `thesis_state` setter rule (ADR 0003) — this item only *reads* `risk_action`; never calls `derive_thesis_from_evidence`, never mutates `thesis_state`.
- Policy B — `evaluate_policy_b` / `evidence_gaps` / publishable partition untouched.

**Test/lint commands (use these exact forms — never the full suite):**
- Test: `uv run pytest <targeted paths>`
- Lint: `uv run ruff check <paths>`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/irc/decision/portfolio_action.py` | **Create** (~55 lines) | Pure `map_portfolio_action(...)` + `weight_delta(...)`. New home so `gates.py` does not grow further. |
| `tests/decision/test_portfolio_action.py` | **Create** | Truth-table unit tests for the mapper + `weight_delta`. |
| `src/irc/decision/models.py` | Modify | Widen `PortfolioAction` & `DecisionStatus` literals; remove Phase-3 TODO; add `current_weight` / `weight_delta` `DecisionRow` fields. |
| `src/irc/opportunity/report.py` | Modify | `compose_opportunity_report` gains `discipline_by_id` keyword; `_row_to_dict` emits the 4 new keys. |
| `tests/opportunity/test_report.py` | Modify | Assert the 4 new keys (populated + default). |
| `src/irc/commands/opportunity_cmd.py` | Modify | Build `discipline_by_id` map at the command edge; pass it into `compose_opportunity_report`. |
| `src/irc/decision/gates.py` | Modify | `decide_row` gains 4 sell-side params; `_build_decision_row` calls `map_portfolio_action` + stamps weights; `compute_decision_status` gains `review_sell_later`. |
| `tests/decision/test_gates.py` | Modify | Assert mapped `portfolio_action`, weights, `review_sell_later`, back-compat defaults. |
| `src/irc/decision/report.py` | Modify | `_holdings_action_section` renderer; `_summary` gains 3 counts; wired into `render_decision_markdown`. |
| `tests/decision/test_report.py` | Modify | Assert section (populated + empty), summary counts. |
| `src/irc/decision/report.py` (`_build_rows`) + `src/irc/commands/decision_cmd.py` | Modify | Thread the 4 fields from `opportunity_state_by_id` → `decide_row`. |
| `CHANGELOG.md` | Modify | Entry under `[Unreleased]`. No VERSION bump. |

---

## Task 1 — Pure mapper: `map_portfolio_action` + `weight_delta`

Delivers AC3, AC4. Pure functions, no I/O, no mocks. This is the enforcement locus for the `is_holding` gate (ADR 0015 §2 / R4).

**Files:**
- Create: `src/irc/decision/portfolio_action.py`
- Test: `tests/decision/test_portfolio_action.py`

- [ ] **Step 1.1: Write the failing test file**

Create `tests/decision/test_portfolio_action.py`:

```python
from __future__ import annotations

import pytest

from irc.decision.portfolio_action import map_portfolio_action, weight_delta


def _map(**overrides):
    base = dict(
        risk_action="none",
        score_action="watch",
        allocation_selected=False,
        is_holding=False,
        blocking_reasons=(),
    )
    base.update(overrides)
    return map_portfolio_action(**base)


def test_blocked_row_is_never_an_action() -> None:
    # Precedence (a): any blocking reason short-circuits to no_trade,
    # even when a sell signal + holding would otherwise fire.
    assert _map(
        risk_action="exit_review",
        is_holding=True,
        blocking_reasons=("data_incomplete",),
    ) == "no_trade"


def test_exit_review_holding_maps_to_exit_review() -> None:
    assert _map(risk_action="exit_review", is_holding=True) == "exit_review"


def test_trim_review_holding_maps_to_trim_review() -> None:
    assert _map(risk_action="trim_review", is_holding=True) == "trim_review"


def test_review_required_holding_maps_to_review() -> None:
    # review_required is "NEVER auto-sell" -> the softer `review`, not trim/exit.
    assert _map(risk_action="review_required", is_holding=True) == "review"


def test_buy_candidate_selected_maps_to_buy() -> None:
    assert _map(
        risk_action="none",
        score_action="buy_candidate",
        allocation_selected=True,
    ) == "buy"


def test_strong_buy_candidate_selected_maps_to_buy() -> None:
    assert _map(
        score_action="strong_buy_candidate",
        allocation_selected=True,
    ) == "buy"


def test_buy_candidate_not_selected_is_no_trade() -> None:
    assert _map(score_action="buy_candidate", allocation_selected=False) == "no_trade"


def test_default_is_no_trade() -> None:
    assert _map() == "no_trade"


@pytest.mark.parametrize("risk", ["exit_review", "trim_review", "review_required"])
def test_sell_branches_require_is_holding(risk) -> None:
    # R4 / AC7: derive_risk_action can return trim/exit for a NON-holding via
    # its legacy `overweight` branch. The mapper is the enforcement locus:
    # a non-holding never gets a sell-side action.
    assert _map(risk_action=risk, is_holding=False) == "no_trade"


def test_sell_signal_wins_over_buy_when_both_present() -> None:
    # Sell-side precedence is above the buy branch.
    assert _map(
        risk_action="exit_review",
        is_holding=True,
        score_action="buy_candidate",
        allocation_selected=True,
    ) == "exit_review"


def test_weight_delta_positive_overweight() -> None:
    assert weight_delta(0.07, 0.05) == pytest.approx(0.02)


def test_weight_delta_negative_underweight() -> None:
    assert weight_delta(0.03, 0.05) == pytest.approx(-0.02)


def test_weight_delta_none_current_treated_as_zero() -> None:
    assert weight_delta(None, 0.05) == pytest.approx(-0.05)


def test_weight_delta_none_target_treated_as_zero() -> None:
    assert weight_delta(0.05, None) == pytest.approx(0.05)
```

- [ ] **Step 1.2: Run the test to verify it fails**

Run: `uv run pytest tests/decision/test_portfolio_action.py -q`
Expected: collection/import error — `ModuleNotFoundError: No module named 'irc.decision.portfolio_action'` (or `ImportError`). RED.

- [ ] **Step 1.3: Write the minimal implementation**

Create `src/irc/decision/portfolio_action.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from irc.decision.models import PortfolioAction

_BUY_ACTIONS = frozenset({"buy_candidate", "strong_buy_candidate"})


def map_portfolio_action(
    *,
    risk_action: str,
    score_action: str,
    allocation_selected: bool,
    is_holding: bool,
    blocking_reasons: Sequence[str],
) -> PortfolioAction:
    """Project a discipline ``risk_action`` (+ buy signal) onto a portfolio action.

    Fixed precedence (ADR 0015 §2):
      (a) any blocking reason            -> no_trade  (a blocked row is never an action)
      (b) exit_review  AND is_holding    -> exit_review
      (c) trim_review  AND is_holding    -> trim_review
      (d) review_required AND is_holding -> review     (NEVER auto-sell)
      (e) buy-candidate AND allocation_selected -> buy
      (f) otherwise                      -> no_trade

    The ``is_holding`` gate on the three sell branches is load-bearing
    (R4): ``derive_risk_action`` can return trim/exit for a non-holding.
    """
    if blocking_reasons:
        return "no_trade"
    if is_holding:
        if risk_action == "exit_review":
            return "exit_review"
        if risk_action == "trim_review":
            return "trim_review"
        if risk_action == "review_required":
            return "review"
    if score_action in _BUY_ACTIONS and allocation_selected:
        return "buy"
    return "no_trade"


def weight_delta(current: float | None, target: float | None) -> float:
    """Return ``current - target`` in weight-fraction units (0.02 = +2pp).

    None is treated as 0.0 (a missing current weight means "not held yet";
    a missing target means "no allocation slot"). Pure subtraction — no
    accumulation — so it is deterministic across re-runs (ADR 0004 / R5).
    """
    return (current or 0.0) - (target or 0.0)
```

> NOTE: importing `PortfolioAction` from `models.py` requires the Task 2 widening
> to be present for the *type* to include the sell values, but the import itself
> resolves today (the symbol exists). Tests in this task only assert string
> equality, so they pass before Task 2. Do not reorder: Task 2 widens the literal
> that this module's return annotation references.

- [ ] **Step 1.4: Run the test to verify it passes**

Run: `uv run pytest tests/decision/test_portfolio_action.py -q`
Expected: PASS — 16 passed.

- [ ] **Step 1.5: Lint**

Run: `uv run ruff check src/irc/decision/portfolio_action.py tests/decision/test_portfolio_action.py`
Expected: `All checks passed!`

- [ ] **Step 1.6: Commit**

```bash
git add src/irc/decision/portfolio_action.py tests/decision/test_portfolio_action.py
git commit -m "feat(decision): pure map_portfolio_action + weight_delta (item 001)"
```

### ✅ Verification gate — Task 1

Run: `uv run pytest tests/decision/test_portfolio_action.py -q && uv run ruff check src/irc/decision/portfolio_action.py`
Expected: all tests pass, lint clean. The mapper is pure (no I/O imports), the `is_holding` sell-gate and blocked short-circuit are tested, `weight_delta` handles `None`. AC3 + AC4 satisfied at unit level.

---

## Task 2 — Widen `models.py` literals + add `DecisionRow` weight fields

Delivers AC2 and the dataclass fields AC5/Task 5 depend on. Frozen dataclass extended only by defaulted fields (back-compat).

**Files:**
- Modify: `src/irc/decision/models.py`
- Test: `tests/decision/test_models.py` (new file — `models.py` has no existing test)

- [ ] **Step 2.1: Write the failing test**

Create `tests/decision/test_models.py`:

```python
from __future__ import annotations

from typing import get_args

from irc.decision.models import (
    DecisionRow,
    DecisionStatus,
    PortfolioAction,
)


def test_portfolio_action_members() -> None:
    assert set(get_args(PortfolioAction)) == {
        "no_trade",
        "buy",
        "trim_review",
        "exit_review",
        "review",
    }


def test_decision_status_includes_review_sell_later() -> None:
    assert "review_sell_later" in get_args(DecisionStatus)


def test_decision_row_weight_fields_default_to_zero() -> None:
    row = DecisionRow(
        instrument_id="518880",
        asset_class="gold",
        score_action="watch",
        decision_status="watch_only",
        portfolio_action="no_trade",
        conviction="low",
        data_completeness=1.0,
        missing_data=(),
        target_weight_valid=True,
        venue_status="direct",
        memo_evidence_status="evidence_linked",
    )
    assert row.current_weight == 0.0
    assert row.weight_delta == 0.0
    assert row.target_weight == 0.0


def test_decision_row_weight_fields_serialize() -> None:
    row = DecisionRow(
        instrument_id="518880",
        asset_class="gold",
        score_action="watch",
        decision_status="review_sell_later",
        portfolio_action="exit_review",
        conviction="low",
        data_completeness=1.0,
        missing_data=(),
        target_weight_valid=True,
        venue_status="direct",
        memo_evidence_status="evidence_linked",
        current_weight=0.07,
        weight_delta=0.02,
        target_weight=0.05,
    )
    d = row.to_dict()
    assert d["current_weight"] == 0.07
    assert d["weight_delta"] == 0.02
    assert d["portfolio_action"] == "exit_review"
    assert d["decision_status"] == "review_sell_later"
```

- [ ] **Step 2.2: Run the test to verify it fails**

Run: `uv run pytest tests/decision/test_models.py -q`
Expected: FAIL — `test_portfolio_action_members` (only `no_trade` today), `test_decision_status_includes_review_sell_later`, and `test_decision_row_weight_fields_*` (no `current_weight` attr → `TypeError: unexpected keyword`). RED.

- [ ] **Step 2.3: Widen the literals + remove the Phase-3 TODO**

In `src/irc/decision/models.py`, replace the `DecisionStatus` block (lines 7–14) and `PortfolioAction` (line 14):

```python
DecisionStatus = Literal[
    "actionable_buy",
    "watch_only",
    "avoid",
    "blocked",
    "review_sell_later",
]
PortfolioAction = Literal["no_trade", "buy", "trim_review", "exit_review", "review"]
```

(The `# TODO (Phase 3): ...` comment is deleted by this replacement — AC2.)

- [ ] **Step 2.4: Add the two `DecisionRow` fields**

In `src/irc/decision/models.py`, the existing `target_weight: float = 0.0` field stays. Immediately after the `target_weight` field (before `role`), add:

```python
    # Item 001: holdings-aware weights for the 持仓行动 section.
    # current_weight is COST-BASIS (portfolio_weight = cost_basis_cny /
    # portfolio_total_cny), not live market value (ADR 0015 §2 / OQ3).
    # weight_delta = current_weight - target_weight (fraction units; 0.02 = +2pp).
    current_weight: float = 0.0
    weight_delta: float = 0.0
```

Placement detail: in the current file `target_weight: float = 0.0` is at line 57 and `role: str = ""` at line 60 (with a comment between). Insert the two new fields between the `target_weight` comment/field block and the `role` comment so field order reads `... target_weight, current_weight, weight_delta, role`. All three default, so `asdict` serializes them and every existing caller compiles unchanged.

- [ ] **Step 2.5: Run the test to verify it passes**

Run: `uv run pytest tests/decision/test_models.py -q`
Expected: PASS — 4 passed.

- [ ] **Step 2.6: Re-run Task 1 tests (no regression on the mapper's return type)**

Run: `uv run pytest tests/decision/test_portfolio_action.py tests/decision/test_models.py -q`
Expected: PASS — 20 passed.

- [ ] **Step 2.7: Lint**

Run: `uv run ruff check src/irc/decision/models.py tests/decision/test_models.py`
Expected: `All checks passed!`

- [ ] **Step 2.8: Commit**

```bash
git add src/irc/decision/models.py tests/decision/test_models.py
git commit -m "feat(decision): widen PortfolioAction/DecisionStatus + DecisionRow weight fields (item 001)"
```

### ✅ Verification gate — Task 2

Run: `uv run pytest tests/decision/test_models.py tests/decision/test_portfolio_action.py -q && uv run ruff check src/irc/decision/models.py`
Expected: all pass, lint clean. `PortfolioAction` has 5 members, `DecisionStatus` has `review_sell_later`, the Phase-3 TODO is gone, `DecisionRow` carries `current_weight` / `weight_delta`. AC2 satisfied. `models.py` stays well under 200 lines.

---

## Task 3 — Surface the four fields through `opportunity_report.json`

Delivers AC1. `compose_opportunity_report` gains a defaulted `discipline_by_id` keyword (R1); `_row_to_dict` looks the values up by `instrument_id`; the command edge builds the map. Composition stays pure; effects stay in `opportunity_cmd`.

**Files:**
- Modify: `src/irc/opportunity/report.py` (`_row_to_dict`, `compose_opportunity_report`)
- Modify: `src/irc/commands/opportunity_cmd.py` (`_write_opportunity_outputs`, ~line 1373)
- Test: `tests/opportunity/test_report.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/opportunity/test_report.py` (the file already imports `_row_to_dict`, `compose_opportunity_report`, `OpportunityRow`, `LookthroughTarget` and has a `_row(...)` factory):

```python
def test_opportunity_report_emits_default_discipline_keys() -> None:
    # No discipline_by_id passed -> byte-identical defaults (back-compat).
    report = compose_opportunity_report([_row()], "2026-06-10")
    row = report["rows"][0]
    assert row["risk_action"] == "none"
    assert row["dca_action"] is None
    assert row["portfolio_weight"] is None
    assert row["is_holding"] is False


def test_opportunity_report_emits_discipline_values_from_map() -> None:
    r = _row(instrument_id="510300")
    discipline_by_id = {
        "510300": {
            "risk_action": "trim_review",
            "dca_action": "slow_dca",
            "portfolio_weight": 0.08,
            "is_holding": True,
        }
    }
    report = compose_opportunity_report(
        [r], "2026-06-10", discipline_by_id=discipline_by_id
    )
    row = report["rows"][0]
    assert row["risk_action"] == "trim_review"
    assert row["dca_action"] == "slow_dca"
    assert row["portfolio_weight"] == 0.08
    assert row["is_holding"] is True


def test_row_to_dict_keeps_existing_keys_when_map_absent() -> None:
    # The four new keys are additive; the existing schema is unchanged.
    d = _row_to_dict(_row())
    for key in (
        "instrument_id", "valuation_state", "heat_state", "thesis_state",
        "opportunity_state", "evidence_gaps", "thesis_evidence",
    ):
        assert key in d
    assert d["risk_action"] == "none"
```

> NOTE: `_row_to_dict` is currently one-arg. These tests call `_row_to_dict(_row())`
> with no map — the implementation must keep that arity working by defaulting the
> map param. See Step 3.3.

- [ ] **Step 3.2: Run the tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_report.py -q -k "discipline_keys or discipline_values or keeps_existing_keys"`
Expected: FAIL — `compose_opportunity_report()` got an unexpected keyword `discipline_by_id`, and the new keys are absent. RED.

- [ ] **Step 3.3: Update `_row_to_dict` and `compose_opportunity_report`**

In `src/irc/opportunity/report.py`, replace the `_row_to_dict` signature and add the four keys at the end of the returned dict; then replace `compose_opportunity_report`:

```python
def _row_to_dict(
    row: OpportunityRow,
    discipline_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    disc = (discipline_by_id or {}).get(row.instrument_id, {})
    return {
        "instrument_id": row.instrument_id,
        "name_cn": row.name_cn,
        "asset_class": row.asset_class,
        "theme": row.theme,
        "lookthrough_target": row.lookthrough_target.display_cn,
        "lookthrough_kind": row.lookthrough_target.kind,
        "lookthrough_key": row.lookthrough_target.key,
        "valuation_state": row.valuation_state,
        "heat_state": row.heat_state,
        "thesis_state": row.thesis_state,
        "product_quality_state": row.product_quality_state,
        "opportunity_state": row.opportunity_state,
        "opportunity_reason": row.opportunity_reason,
        "evidence_gaps": list(row.evidence_gaps),
        "expected_omissions": list(row.expected_omissions),
        "advisory_gaps": list(row.advisory_gaps),
        # New schema (item 002):
        "thesis_evidence": [asdict(e) for e in row.thesis_evidence],
        "contributing_dimensions": sorted(row.contributing_dimensions),
        "constituent_analyses": [
            asdict(c) for c in getattr(row, "constituent_analyses", ())
        ],
        "fetch_types_attempted": list(row.fetch_types_attempted),
        # Item 001: discipline-derived sell-side fields for the decision layer.
        # Default (no map / id absent) is byte-identical to pre-change.
        "risk_action": disc.get("risk_action", "none"),
        "dca_action": disc.get("dca_action"),
        "portfolio_weight": disc.get("portfolio_weight"),
        "is_holding": disc.get("is_holding", False),
    }


def compose_opportunity_report(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    date: str,
    *,
    discipline_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summary = {
        "core_dca_count": 0,
        "small_watch_count": 0,
        "pause_wait_count": 0,
        "exclude_count": 0,
    }
    for r in rows:
        summary[f"{r.opportunity_state}_count"] += 1
    return {
        "date": date,
        "summary": summary,
        "rows": [_row_to_dict(r, discipline_by_id) for r in rows],
    }
```

- [ ] **Step 3.4: Run the tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_report.py -q`
Expected: PASS — the whole `test_report.py` module passes (new tests green, no regression in existing report tests).

- [ ] **Step 3.5: Build `discipline_by_id` at the command edge**

In `src/irc/commands/opportunity_cmd.py`, inside `_write_opportunity_outputs`, immediately before the `atomic_write_text(out_dir / "opportunity_report.json", ...)` call (currently ~line 1370), add the map construction. `discipline_rows` (the post-demotion list, line 1254/1280) and `positions` (a `dict[str, PositionContext]`) are both in scope:

```python
    # Item 001: discipline-derived sell-side fields keyed by instrument_id,
    # passed into the pure composer so opportunity_report.json carries them
    # for the decision layer (ADR 0015 §1). Effects-at-edges: the command
    # threads the data; compose_opportunity_report stays pure.
    discipline_by_id = {
        dr.instrument_id: {
            "risk_action": dr.risk_action,
            "dca_action": dr.dca_action,
            "portfolio_weight": positions[dr.instrument_id].portfolio_weight,
            "is_holding": positions[dr.instrument_id].is_holding,
        }
        for dr in discipline_rows
    }
```

Then change the compose call (currently `compose_opportunity_report(publishable_rows, today)`) to:

```python
            compose_opportunity_report(
                publishable_rows, today, discipline_by_id=discipline_by_id
            ),
```

> CORRECTNESS NOTE: `discipline_rows` is built **only from `publishable_rows`**
> (lines 1254–1256, re-derived at 1279–1281 after any block-mode demotion), so
> the map keys are exactly the publishable instrument ids — the SAME set the
> composer iterates. H3 is preserved by construction: no gapped row gains a key.

- [ ] **Step 3.6: Lint**

Run: `uv run ruff check src/irc/opportunity/report.py src/irc/commands/opportunity_cmd.py tests/opportunity/test_report.py`
Expected: `All checks passed!`

- [ ] **Step 3.7: Commit**

```bash
git add src/irc/opportunity/report.py src/irc/commands/opportunity_cmd.py tests/opportunity/test_report.py
git commit -m "feat(opportunity): emit risk_action/dca_action/portfolio_weight/is_holding on report rows (item 001)"
```

### ✅ Verification gate — Task 3

Run: `uv run pytest tests/opportunity/test_report.py tests/opportunity/test_report_appendix.py -q && uv run ruff check src/irc/opportunity/report.py`
Expected: all pass, lint clean. `opportunity_report.json` rows carry the four new keys (populated from the map, defaulted otherwise); the appendix-line regex contract test still passes (no markdown-side change). AC1 satisfied.

---

## Task 4 — Thread fields into `decide_row` and stamp the action + weights

Delivers AC7, AC8, AC9 and the wiring for AC5/AC6. `decide_row` gains four defaulted sell-side params; `_build_decision_row` calls `map_portfolio_action`; `compute_decision_status` learns `review_sell_later`.

**Files:**
- Modify: `src/irc/decision/gates.py`
- Test: `tests/decision/test_gates.py`

- [ ] **Step 4.1: Write the failing tests**

Append to `tests/decision/test_gates.py` (the file already imports `decide_row` and has a `_score(**overrides)` factory returning a dict with `action`):

```python
def _decide(score_overrides=None, **kw):
    score = _score(**(score_overrides or {}))
    base = dict(
        allocation_selected=False,
        target_weight_valid=True,
        trade=None,
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
        available_venues=["broker_a"],
        venue_required=["broker_a"],
    )
    base.update(kw)
    return decide_row(score, **base)


def test_held_exit_review_maps_to_exit_review_and_review_sell_later() -> None:
    row = _decide(
        score_overrides={"action": "watch"},
        risk_action="exit_review",
        is_holding=True,
        portfolio_weight=0.08,
        target_weight=0.05,
    )
    assert row["portfolio_action"] == "exit_review"
    assert row["decision_status"] == "review_sell_later"
    assert row["current_weight"] == 0.08
    assert row["weight_delta"] == 0.03
    assert row["target_weight"] == 0.05


def test_non_held_overheated_does_not_get_sell_action() -> None:
    # AC7: a non-holding never gets trim/exit/review even if risk_action says so.
    row = _decide(
        score_overrides={"action": "watch"},
        risk_action="trim_review",
        is_holding=False,
        portfolio_weight=None,
    )
    assert row["portfolio_action"] == "no_trade"
    assert row["decision_status"] != "review_sell_later"


def test_buy_candidate_selected_maps_to_buy() -> None:
    row = _decide(
        score_overrides={"action": "buy_candidate"},
        allocation_selected=True,
    )
    assert row["portfolio_action"] == "buy"
    assert row["decision_status"] == "actionable_buy"


def test_blocked_buy_is_not_review_sell_later() -> None:
    # AC9 boundary: a blocked row keeps `blocked`, not review_sell_later,
    # even if it carries a sell signal.
    row = _decide(
        score_overrides={"action": "watch"},
        risk_action="exit_review",
        is_holding=True,
        pipeline_halted=True,
    )
    assert row["decision_status"] == "blocked"
    assert row["portfolio_action"] == "no_trade"  # blocked short-circuits the mapper


def test_legacy_call_without_sell_params_is_no_trade() -> None:
    # AC8 back-compat: omitting the four params reproduces today's behavior.
    row = _decide(score_overrides={"action": "watch"})
    assert row["portfolio_action"] == "no_trade"
    assert row["current_weight"] == 0.0
    assert row["weight_delta"] == 0.0
```

- [ ] **Step 4.2: Run the tests to verify they fail**

Run: `uv run pytest tests/decision/test_gates.py -q -k "exit_review or non_held or maps_to_buy or review_sell_later or legacy_call"`
Expected: FAIL — `decide_row()` got an unexpected keyword `risk_action`. RED.

- [ ] **Step 4.3: Add `review_sell_later` to `compute_decision_status`**

In `src/irc/decision/gates.py`, replace `compute_decision_status` (lines 242–258) so a held sell-signal row that is neither avoid/blocked/actionable_buy becomes `review_sell_later`:

```python
def compute_decision_status(
    score_action: str,
    blocking_reasons: list[str],
    allocation_selected: bool,
    portfolio_action: str = "no_trade",
) -> DecisionStatus:
    """Pure verdict on a row given its score action, blockers, and allocation.

    Buy-side precedence is unchanged (avoid > blocked > actionable_buy >
    watch_only). Item 001 adds one slot: a held row carrying a sell/trim/
    exit/review portfolio_action that is NOT avoid/blocked/actionable_buy
    becomes `review_sell_later` instead of `watch_only` (ADR 0015 §3 / R6).
    """
    if score_action in _AVOID_ACTIONS:
        return "avoid"
    if blocking_reasons:
        return "blocked"
    if score_action in _BUY_ACTIONS and allocation_selected:
        return "actionable_buy"
    if portfolio_action in ("trim_review", "exit_review", "review"):
        return "review_sell_later"
    return "watch_only"
```

> The defaulted `portfolio_action="no_trade"` keeps every existing caller
> (memo §5 `compute_decision_status`) working unchanged.

- [ ] **Step 4.4: Add the four params to `decide_row` and compute the action + weights**

In `src/irc/decision/gates.py`, add the import at the top (after the existing `from irc.decision.models import ...` line):

```python
from irc.decision.portfolio_action import map_portfolio_action, weight_delta
```

Add four defaulted keyword params to `decide_row` (after `qdii_max_premium_pct`):

```python
    qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT,
    risk_action: str = "none",
    dca_action: str | None = None,
    portfolio_weight: float | None = None,
    is_holding: bool = False,
```

Inside `decide_row`, replace the `decision_status = _decision_status(...)` line and the `return _build_decision_row(...)` block. The action must be computed BEFORE the status (status now depends on it):

```python
    portfolio_action = map_portfolio_action(
        risk_action=risk_action,
        score_action=score_action,
        allocation_selected=allocation_selected,
        is_holding=is_holding,
        blocking_reasons=tuple(blocking_reasons),
    )
    decision_status = _decision_status(
        score_action, blocking_reasons, allocation_selected, portfolio_action
    )
    watch_reason = _watch_reason(decision_status, score_action, allocation_selected, venue_status)
    current_weight = portfolio_weight or 0.0
    return _build_decision_row(
        score=score,
        score_action=score_action,
        completeness=completeness,
        missing_data=missing_data,
        target_weight_valid=target_weight_valid,
        venue_status=venue_status,
        evidence_status=evidence_status,
        blocking_reasons=blocking_reasons,
        decision_status=decision_status,
        watch_reason=watch_reason,
        instrument_name=instrument_name,
        target_weight=target_weight,
        role=role,
        portfolio_action=portfolio_action,
        current_weight=current_weight,
        weight_delta=weight_delta(current_weight, target_weight),
    ).to_dict()
```

- [ ] **Step 4.5: Update `_build_decision_row` to accept and stamp the new fields**

In `src/irc/decision/gates.py`, add three defaulted params to `_build_decision_row` (after `role: str = ""`):

```python
    portfolio_action: str = "no_trade",
    current_weight: float = 0.0,
    weight_delta: float = 0.0,
```

> NAME-SHADOW NOTE: `weight_delta` is also the imported function name. Inside
> `_build_decision_row` it is a *parameter* (a float); the function is not called
> here, so the shadow is local and harmless. The call to the `weight_delta`
> function happens in `decide_row` (Step 4.4), where no parameter shadows it.

Then replace the hard-coded `portfolio_action="no_trade"` literal (currently line 191) and add the two weight fields in the `DecisionRow(...)` construction:

```python
    return DecisionRow(
        instrument_id=str(score.get("instrument_id", "")),
        asset_class=str(score.get("asset_class", "unknown")),
        score_action=score_action,
        decision_status=decision_status,
        portfolio_action=portfolio_action,
        conviction=str(score.get("conviction", "low")),
        data_completeness=completeness,
        missing_data=missing_data,
        target_weight_valid=target_weight_valid,
        venue_status=venue_status,
        memo_evidence_status=evidence_status,
        blocking_reasons=tuple(blocking_reasons),
        reason=_reason(decision_status, blocking_reasons, score_action),
        next_step=_next_step(blocking_reasons, decision_status),
        watch_reason=watch_reason,
        instrument_name=instrument_name,
        target_weight=target_weight,
        current_weight=current_weight,
        weight_delta=weight_delta,
        role=role,
    )
```

- [ ] **Step 4.6: Run the tests to verify they pass**

Run: `uv run pytest tests/decision/test_gates.py -q`
Expected: PASS — new tests green and the full existing `test_gates.py` module still passes (back-compat).

- [ ] **Step 4.7: Re-run the watch-reason + completeness + memo callers of `compute_decision_status`**

Run: `uv run pytest tests/decision/test_watch_reason.py tests/decision/test_completeness.py -q`
Expected: PASS — the defaulted `portfolio_action` param did not change any existing verdict.

- [ ] **Step 4.8: Lint**

Run: `uv run ruff check src/irc/decision/gates.py tests/decision/test_gates.py`
Expected: `All checks passed!`

- [ ] **Step 4.9: Commit**

```bash
git add src/irc/decision/gates.py tests/decision/test_gates.py
git commit -m "feat(decision): map portfolio_action + stamp weights + review_sell_later in decide_row (item 001)"
```

### ✅ Verification gate — Task 4

Run: `uv run pytest tests/decision/test_gates.py tests/decision/test_watch_reason.py tests/decision/test_completeness.py -q && uv run ruff check src/irc/decision/gates.py`
Expected: all pass, lint clean. A held `exit_review` → `portfolio_action=exit_review` + `decision_status=review_sell_later` + correct weights; a non-holding stays `no_trade` (AC7); a blocked row stays `blocked`/`no_trade` (AC9); legacy calls reproduce today (AC8). `gates.py` grew by ~15 lines — verify it has not introduced functions > 20 lines (the mapper lives in `portfolio_action.py`, so `decide_row` stays a thin orchestrator).

---

## Task 5 — Report section, summary counts, and command-edge threading

Delivers AC5, AC6, AC10 and the `_build_rows` → `decide_row` wiring. The renderer is pure; the I/O lives in `decision_cmd`.

**Files:**
- Modify: `src/irc/decision/report.py` (`_summary`, new `_holdings_action_section`, `render_decision_markdown`, `_build_rows`)
- Modify: `src/irc/commands/decision_cmd.py` (thread the 4 fields)
- Test: `tests/decision/test_report.py`

- [ ] **Step 5.1: Write the failing tests**

Append to `tests/decision/test_report.py`. First inspect the top of that file for an existing row/report factory; if none fits, use these self-contained helpers:

```python
from irc.decision.report import (
    _holdings_action_section,
    _summary,
    render_decision_markdown,
    compose_decision_report,
)


def _drow(**overrides):
    base = dict(
        instrument_id="510300",
        instrument_name="沪深300ETF",
        asset_class="cn_etf",
        score_action="watch",
        decision_status="review_sell_later",
        portfolio_action="trim_review",
        conviction="med",
        data_completeness=1.0,
        missing_data=[],
        target_weight_valid=True,
        venue_status="direct",
        memo_evidence_status="evidence_linked",
        blocking_reasons=[],
        reason="",
        next_step="",
        watch_reason=None,
        target_weight=0.05,
        current_weight=0.08,
        weight_delta=0.03,
        is_holding=True,
        role="",
    )
    base.update(overrides)
    return base


def test_summary_counts_sell_actions() -> None:
    rows = [
        _drow(portfolio_action="trim_review"),
        _drow(portfolio_action="exit_review"),
        _drow(portfolio_action="review"),
        _drow(portfolio_action="review"),
        _drow(portfolio_action="no_trade", decision_status="watch_only"),
    ]
    summary = _summary(rows)
    assert summary["trim_count"] == 1
    assert summary["exit_count"] == 1
    assert summary["review_count"] == 2
    assert "sell_count" not in summary
    # Existing keys preserved (additive-only).
    assert "actionable_buy_count" in summary
    assert "watch_count" in summary
    assert "avoid_count" in summary
    assert "blocked_count" in summary


def test_holdings_action_section_renders_held_sell_rows() -> None:
    rows = [_drow(portfolio_action="trim_review")]
    lines = _holdings_action_section(rows)
    text = "\n".join(lines)
    assert "## 持仓行动 / Sell · Trim · Review" in text
    assert "510300" in text
    assert "trim_review" in text
    # Δpp rendered as percentage points: 0.03 -> +3.0
    assert "+3.0" in text


def test_holdings_action_section_empty_state() -> None:
    rows = [_drow(portfolio_action="no_trade", decision_status="watch_only", is_holding=False)]
    lines = _holdings_action_section(rows)
    assert "（无持仓调整建议）" in "\n".join(lines)


def test_holdings_action_section_excludes_non_holdings() -> None:
    # AC7 at the renderer: a non-holding with a stray sell action does not appear.
    rows = [_drow(portfolio_action="trim_review", is_holding=False)]
    lines = _holdings_action_section(rows)
    assert "（无持仓调整建议）" in "\n".join(lines)


def test_markdown_contains_holdings_section_above_blocked() -> None:
    report = {
        "date": "2026-06-10",
        "overall_status": "ok",
        "blocking_reasons": [],
        "summary": _summary([_drow(portfolio_action="trim_review")]),
        "rows": [_drow(portfolio_action="trim_review")],
    }
    md = render_decision_markdown(report)
    assert "## 持仓行动 / Sell · Trim · Review" in md
    holdings_idx = md.index("## 持仓行动")
    blocked_idx = md.index("## Blocked — fixable today")
    assert holdings_idx < blocked_idx
```

- [ ] **Step 5.2: Run the tests to verify they fail**

Run: `uv run pytest tests/decision/test_report.py -q -k "summary_counts or holdings_action or holdings_section"`
Expected: FAIL — `_holdings_action_section` does not exist; `_summary` lacks the three counts. RED.

- [ ] **Step 5.3: Add the three counts to `_summary`**

In `src/irc/decision/report.py`, replace `_summary` (lines 325–332):

```python
def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    statuses = [row.get("decision_status") for row in rows]
    actions = [row.get("portfolio_action") for row in rows]
    return {
        "actionable_buy_count": statuses.count("actionable_buy"),
        "watch_count": statuses.count("watch_only"),
        "avoid_count": statuses.count("avoid"),
        "blocked_count": statuses.count("blocked"),
        # Item 001 (ADR 0015 §3): additive sell/review counts keyed off
        # portfolio_action. NO sell_count — item 002 sums trim+exit itself.
        "trim_count": actions.count("trim_review"),
        "exit_count": actions.count("exit_review"),
        "review_count": actions.count("review"),
    }
```

- [ ] **Step 5.4: Add the `_holdings_action_section` renderer**

In `src/irc/decision/report.py`, add this function near the other section renderers (e.g. just before `_blocked_fixable_section`):

```python
_HOLDINGS_ACTION_SET = frozenset({"trim_review", "exit_review", "review"})


def _holdings_action_section(rows: list[dict[str, Any]]) -> list[str]:
    """Render the 持仓行动 / Sell·Trim·Review table.

    One row per HELD instrument carrying a trim/exit/review portfolio_action
    (ADR 0015 §2: the sell branches are is_holding-gated, so is_holding is
    True here by construction; the explicit filter is belt-and-suspenders for
    legacy/hand-built rows). Empty-state line `（无持仓调整建议）` when none.
    Current % is COST-BASIS weight (OQ3).
    """
    held = [
        r for r in rows
        if r.get("portfolio_action") in _HOLDINGS_ACTION_SET and r.get("is_holding")
    ]
    out = ["## 持仓行动 / Sell · Trim · Review", ""]
    if not held:
        out.extend(["（无持仓调整建议）", ""])
        return out
    out.append(
        "| Instrument | Name | Action | Current % (cost-basis) | Target % | Δ (pp) | Why |"
    )
    out.append("|---|---|---|---:|---:|---:|---|")
    for r in held:
        current_pct = float(r.get("current_weight") or 0.0) * 100
        target_pct = float(r.get("target_weight") or 0.0) * 100
        delta_pp = float(r.get("weight_delta") or 0.0) * 100
        out.append(
            "| {iid} | {name} | {action} | {cur:.1f} | {tgt:.1f} | {delta:+.1f} | {why} |".format(
                iid=_md(r["instrument_id"]),
                name=_name_cell(r),
                action=_md(r.get("portfolio_action") or ""),
                cur=current_pct,
                tgt=target_pct,
                delta=delta_pp,
                why=_md(r.get("reason") or _score_action_cell(r)),
            )
        )
    out.append("")
    return out
```

> Function is ~22 lines including the docstring; the body (logic) is < 20 lines.
> If a strict reviewer flags it, extract the row-format `.format(...)` into a
> 5-line `_holdings_action_row(r)` helper. Not required for green.

- [ ] **Step 5.5: Wire the section into `render_decision_markdown` (above Blocked)**

In `src/irc/decision/report.py`, in `render_decision_markdown`, the Blocked section is emitted by `_blocked_fixable_section` (currently after the decision-sheet block, ~line 193). Insert the holdings-action section immediately before it:

```python
    lines.extend(_decision_sheet_section(
        rows,
        trades=report.get("trade_plan_trades") or [],
        build_mode=report.get("build_mode") or "build",
        macro_snapshot=report.get("macro_snapshot") or {},
        weekly_return_by_id=report.get("weekly_return_by_id") or {},
        opportunity_state_by_id=report.get("opportunity_state_by_id") or {},
    ))
    lines.append("")
    lines.extend(_holdings_action_section(rows))
    lines.append("")
    lines.extend(_blocked_fixable_section(rows, report.get("proxy_coverage", {})))
```

- [ ] **Step 5.6: Thread the four fields from the opportunity-state map into `_build_rows`**

The decision command already loads `opportunity_state_by_id` (a `dict[id, rowdict]` carrying the four new keys from Task 3) and passes it to `compose_decision_report`. `_build_rows` must read them per id and pass them to `decide_row`. In `src/irc/decision/report.py`, `_build_rows` already receives `opportunity_published_ids` etc. — add an `opportunity_state_by_id` param and use it.

First, in `compose_decision_report`, the `_build_rows(...)` call (lines 68–83) must forward the already-available `opportunity_state_by_id`. Add to that call:

```python
        opportunity_state_by_id=opportunity_state_by_id or {},
```

Then change the `_build_rows` signature (add the keyword, after `trade_plan_targets`):

```python
    trade_plan_targets: set[str],
    opportunity_state_by_id: dict[str, dict[str, Any]] | None = None,
    qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT,
```

Inside the `for score in scoring.get("scores", []):` loop, before the `rows.append(decide_row(...))`, look up the per-id opportunity row and pass the four fields:

```python
        opp = (opportunity_state_by_id or {}).get(iid, {})
        rows.append(decide_row(
            score=score,
            allocation_selected=iid in selected_ids,
            target_weight_valid=target_weight_valid,
            trade=trades_by_target.get(iid),
            pipeline_halted=pipeline_halted,
            memo_traceability_coverage=coverage,
            venue_required=venue_requirements_by_id.get(iid),
            available_venues=available_venues,
            proxy_id=proxies_by_id.get(iid),
            instrument_name=names_by_id.get(iid),
            target_weight=target_weight_by_id.get(iid, 0.0),
            role=role_by_id.get(iid, ""),
            excluded_from_opportunity=excluded,
            qdii_max_premium_pct=qdii_max_premium_pct,
            risk_action=str(opp.get("risk_action", "none")),
            dca_action=opp.get("dca_action"),
            portfolio_weight=opp.get("portfolio_weight"),
            is_holding=bool(opp.get("is_holding", False)),
        ))
```

> `decision_cmd.py` needs NO change here — it already passes
> `opportunity_state_by_id=opportunity_states` into `compose_decision_report`
> (line 189). The fields ride that existing map. AC8 (missing file / missing id)
> is satisfied because `.get(iid, {})` → all four defaults → `no_trade`.

- [ ] **Step 5.7: Run the report tests to verify they pass**

Run: `uv run pytest tests/decision/test_report.py tests/decision/test_three_section_markdown.py -q`
Expected: PASS — new tests green, existing markdown/section tests still green (the new section is additive).

- [ ] **Step 5.8: Lint**

Run: `uv run ruff check src/irc/decision/report.py src/irc/commands/decision_cmd.py tests/decision/test_report.py`
Expected: `All checks passed!`

- [ ] **Step 5.9: Commit**

```bash
git add src/irc/decision/report.py src/irc/commands/decision_cmd.py tests/decision/test_report.py
git commit -m "feat(decision): 持仓行动 section + trim/exit/review counts + thread sell fields (item 001)"
```

### ✅ Verification gate — Task 5

Run: `uv run pytest tests/decision/ -q && uv run ruff check src/irc/decision/report.py src/irc/commands/decision_cmd.py`
Expected: the whole `tests/decision/` suite passes, lint clean. `_summary` carries `trim_count`/`exit_count`/`review_count` and no `sell_count` (AC5); the section renders above Blocked, populated + empty (AC6); non-holdings excluded (AC7); the four fields thread from the opportunity map (AC8 default path covered).

---

## Task 6 — Invariant guard, end-to-end smoke, CHANGELOG

Delivers AC10, AC11 and proves the locked invariants (H3, SAME-3, thesis_state, Policy B) are untouched.

**Files:**
- Modify: `CHANGELOG.md`
- No new source (verification + docs only).

- [ ] **Step 6.1: Run the locked-invariant guard tests for the touched areas**

Run: `uv run pytest tests/opportunity/test_report.py tests/opportunity/test_report_appendix.py tests/opportunity/test_policy_b.py tests/opportunity/test_thesis_evidence.py tests/opportunity/test_cards.py -q`
Expected: PASS. These cover: H3 publishable-row partition + SAME-3 appendix citation contract (`test_report_appendix`), Policy B publishability (`test_policy_b`), `thesis_state` provenance / `derive_thesis_from_evidence` (`test_thesis_evidence`, `test_cards`). None changed → invariants provably untouched.

- [ ] **Step 6.2: Run the full decision suite + the opportunity report suite together (regression sweep of touched modules)**

Run: `uv run pytest tests/decision/ tests/opportunity/test_report.py tests/opportunity/test_report_appendix.py tests/opportunity/test_discipline.py -q`
Expected: PASS — every targeted module green. (Do NOT run the full suite; it is ~18 min and has 8 known pre-existing failures unrelated to this item.)

- [ ] **Step 6.3: End-to-end smoke (AC10) — `irc decision` against the latest on-disk outputs, network-free**

Run:
```bash
LATEST=$(ls -d outputs/2*/ 2>/dev/null | sort | tail -1)
echo "latest=$LATEST"
uv run irc decision; echo "exit=$?"
```
Expected: `exit=0` and a line `decision <status> -> outputs/<date>/decision_report.md`. If `outputs/` is empty (clean checkout), this step is N/A — record "no on-disk outputs; AC10 deferred to CI/operator run" and proceed (unit tests already cover the wiring).

- [ ] **Step 6.4: Verify the new JSON keys + fields landed in the artifact**

Run (only if Step 6.3 produced a report):
```bash
LATEST=$(ls -d outputs/2*/ | sort | tail -1)
uv run python -c "
import json, sys
d = json.load(open(f'$LATEST/decision_report.json'))
s = d['summary']
for k in ('trim_count','exit_count','review_count','actionable_buy_count','watch_count','avoid_count','blocked_count'):
    assert k in s, f'missing summary key {k}'
assert 'sell_count' not in s, 'sell_count must NOT be emitted'
r = d['rows'][0]
for k in ('portfolio_action','current_weight','weight_delta','target_weight'):
    assert k in r, f'missing row key {k}'
print('OK: summary keys', sorted(s))
"
```
Expected: `OK: summary keys [...]` with the three new counts present and `sell_count` absent.

- [ ] **Step 6.5: Add the CHANGELOG entry (no VERSION bump)**

In `CHANGELOG.md`, under the existing `## [Unreleased]` heading (line 8), add a new `### Added` block as the FIRST entry beneath `[Unreleased]` (above the existing 2026-06-10 valuation-axis block):

```markdown
### Added — Sell surfacing + holdings-aware deltas (2026-06-10)

- **The decision report now tells the operator what to TRIM / EXIT / REVIEW, not
  just what to BUY.** The discipline layer's `risk_action` / `dca_action` /
  `portfolio_weight` / `is_holding` are surfaced onto each publishable
  `opportunity_report.json` row (via a defaulted `discipline_by_id` keyword on
  the pure `compose_opportunity_report`, built at the command edge). The decision
  layer maps them through a new pure `map_portfolio_action`
  (`src/irc/decision/portfolio_action.py`) into a five-value `portfolio_action`
  (`no_trade` / `buy` / `trim_review` / `exit_review` / `review`), gated on
  `is_holding` so a non-held overheated instrument never renders as a trim
  (ADR 0015). `decision_report.md` gains a `## 持仓行动 / Sell · Trim · Review`
  section with current-vs-target cost-basis weight deltas (Δpp), and
  `decision_report.json` `summary` gains additive `trim_count` / `exit_count` /
  `review_count` counts for item 002's notifier (no `sell_count` — the notifier
  composes its own rollup). A held row carrying a sell signal that is not also
  blocked or an actionable buy gets `decision_status == "review_sell_later"`.
  No existing JSON key changed; H3 / SAME-3 / Policy B / the `thesis_state`
  setter rule are all untouched. See ADR 0015.
```

- [ ] **Step 6.6: Lint the full touched set + assert file sizes**

Run:
```bash
uv run ruff check src/irc/decision/portfolio_action.py src/irc/decision/models.py src/irc/decision/gates.py src/irc/decision/report.py src/irc/opportunity/report.py src/irc/commands/opportunity_cmd.py src/irc/commands/decision_cmd.py
wc -l src/irc/decision/portfolio_action.py src/irc/decision/models.py
```
Expected: `All checks passed!`. `portfolio_action.py` < 60 lines and `models.py` < 80 lines (AC11 for the new/small files). NOTE: `gates.py` (~325) and `report.py` (~720) were already over the 200-line ideal *before this item* — this item adds ≤ ~30 lines each and is not obligated to retro-split them (the new mapper deliberately lives in its own file to avoid growing `gates.py` further, per the spec's size-budget constraint). Record the pre-existing over-budget state in the commit message.

- [ ] **Step 6.7: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): item 001 sell surfacing + holdings-aware deltas (Unreleased)"
```

### ✅ Verification gate — Task 6 (final)

Run: `uv run pytest tests/decision/ tests/opportunity/test_report.py tests/opportunity/test_report_appendix.py tests/opportunity/test_policy_b.py tests/opportunity/test_thesis_evidence.py tests/opportunity/test_cards.py tests/opportunity/test_discipline.py -q && uv run ruff check src/irc/decision src/irc/opportunity/report.py src/irc/commands/opportunity_cmd.py src/irc/commands/decision_cmd.py`
Expected: all targeted tests pass, lint clean. Invariant guards (H3 / SAME-3 / Policy B / thesis_state) green and unmodified; the e2e artifact (if outputs exist) carries the new keys with `sell_count` absent. All 11 acceptance criteria covered.

---

## Acceptance-criteria → task map (self-review)

| AC | Covered by |
|---|---|
| AC1 — 4 keys on `opportunity_report.json` rows | Task 3 (Step 3.1–3.5) |
| AC2 — widened literals + TODO removed | Task 2 (Step 2.3–2.4) |
| AC3 — pure `map_portfolio_action` precedence | Task 1 (Step 1.1–1.3) |
| AC4 — `weight_delta` units + None handling | Task 1 (Step 1.1, 1.3) |
| AC5 — `trim/exit/review_count`, no `sell_count`, existing keys kept | Task 5 (Step 5.3) |
| AC6 — 持仓行动 section above Blocked, populated + empty | Task 5 (Step 5.4–5.5) |
| AC7 — non-held never gets sell action / section | Task 1 (`require_is_holding`), Task 4 (`non_held`), Task 5 (`excludes_non_holdings`) |
| AC8 — legacy/missing-row back-compat = `no_trade`/`buy` | Task 4 (`legacy_call`), Task 5 (Step 5.6 `.get(iid, {})`) |
| AC9 — held exit_review → `review_sell_later`, precedence boundary | Task 4 (`review_sell_later`, `blocked_buy_is_not`) |
| AC10 — e2e `irc decision` exit 0 + new fields | Task 6 (Step 6.3–6.4) |
| AC11 — ruff clean + size budget | Task 6 (Step 6.6), per-task lint steps |

## Invariant guard map (self-review)

| Invariant | Guarded by | Why untouched |
|---|---|---|
| H3 gapped-row partition | `tests/opportunity/test_report_appendix.py`, `test_report.py` | 4 keys added to the SAME publishable-row dict; `discipline_by_id` keyed only from `discipline_rows` (publishable). |
| SAME-3 citation set | `tests/opportunity/test_report_appendix.py` | New fields are plain scalars; no `[ref:...]` emitted; `select_citations(cap=3)` untouched. |
| `thesis_state` setter (ADR 0003) | `tests/opportunity/test_thesis_evidence.py`, `test_cards.py` | Decision layer only reads `risk_action`; never calls `derive_thesis_from_evidence`. |
| Policy B | `tests/opportunity/test_policy_b.py` | No change to `evaluate_policy_b` / `evidence_gaps` / publishable partition. |

## Spec gaps / judgment calls made in this plan

1. **`tests/decision/test_models.py` is a NEW test file** — `models.py` has no existing mirror test (the spec's "tests mirror source" rule implies one should exist). Created it to cover AC2 with a `get_args` assertion rather than relying solely on lint. (Spec §Constraints "TDD mandatory" / AC2.)
2. **Empty-state literal `（无持仓调整建议）`** chosen verbatim from the spec's parenthetical example (AC6 / spec line 174). Locked as the greppable sentinel.
3. **`_summary` reads `portfolio_action` off row dicts** (not `decision_status`) per AC5/OQ4 canonical definitions — `review_count` counts `portfolio_action == "review"`, independent of `review_sell_later` status. Documented inline.
4. **`gates.py` / `report.py` remain over the 200-line ideal** (325 / ~720 lines before this item). The plan does NOT retro-split them — the spec's size-budget constraint is satisfied by putting the new mapper in its own `portfolio_action.py` file; retro-splitting pre-existing files is out of scope (would balloon the diff and risk the invariants). Recorded in Step 6.6. (Spec §Constraints "File / function size budget".)
