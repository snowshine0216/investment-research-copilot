# Decision Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a conservative daily decision report that clearly says whether buy/sell decisions are supported, and add financial-completeness gates so weak data cannot masquerade as actionable advice.

**Architecture:** Add a pure `irc.decision` package that composes existing scoring, allocation, trade-plan, traceability, and pipeline-health artifacts into JSON/Markdown reports. Then enrich scoring with missing-field lists and local metric loading so the decision layer can explain exactly why an instrument is blocked. CLI wrappers handle file I/O; pure modules do the classification.

**Tech Stack:** Python 3.12, Click, Pydantic-style typed dataclasses, Pandas, DuckDB, PyYAML, pytest, existing `atomic_write_text` helper.

---

## Scope

This plan implements Phase 1 and Phase 2 from [docs/superpowers/specs/2026-05-11-decision-readiness-design.md](../specs/2026-05-11-decision-readiness-design.md).

Phase 3 portfolio deltas are deliberately excluded. Do not calculate `buy_amount_cny`, `sell_amount_cny`, `trim_amount_cny`, or true sell/trim recommendations in this plan. The output may include `portfolio_action: no_trade`, but not real order sizing.

`inputs/account.yaml` is listed as a Phase 1 input in the spec but is **not consumed** by Phase 1 because no holdings/delta logic is computed yet. The decision command does not read or require it. It remains documented as a Phase 1 input for forward compatibility with Phase 3, where current-holdings comparison is added.

Vocabulary: `overall_status` takes one of `"blocked"` (any system-level blocking reason fires) or `"ok"` (no system-level blockers; per-row statuses still determine actionability). The spec only shows `"blocked"`; `"ok"` is introduced here as the non-blocked counterpart and is used by tests and the Markdown verdict.

Commits are not included as executable steps because this environment requires explicit user approval before committing. Use `git diff --check` checkpoints instead.

## File Structure

- Create `src/irc/decision/__init__.py`: package marker and public exports.
- Create `src/irc/decision/completeness.py`: required financial-field constants, missing-field detection, and completeness summaries.
- Create `src/irc/decision/models.py`: immutable decision-row/report structures.
- Create `src/irc/decision/gates.py`: pure hard-gate logic for pipeline, weights, venue, traceability, and score action.
- Create `src/irc/decision/report.py`: compose JSON payload and Markdown text from loaded artifacts.
- Create `src/irc/commands/decision_cmd.py`: CLI wrapper that locates current/latest outputs and writes `decision_report.json` plus `decision_report.md`.
- Modify `src/irc/cli.py`: register `irc decision` command.
- Modify `src/irc/scoring/pipeline.py`: include `missing_data` in score rows.
- Create `src/irc/scoring/metrics_loader.py`: load/derive scoring metrics from local DuckDB tables.
- Modify `src/irc/commands/score_cmd.py`: use the local metrics loader instead of an empty metrics frame.
- Modify `evals/scoring/metrics.py`: add scoring data-completeness metrics.
- Modify `evals/scoring/runner.py`: fail/warn when completeness is insufficient.
- Create `tests/decision/`: unit tests for decision completeness, gates, report composition, Markdown rendering, and CLI output.
- Modify existing scoring/eval tests to cover missing-field lists and local metric loading.
- Modify `README.md`: document `irc decision` and decision-report files.

---

### Task 1: Financial Completeness Helpers

**Files:**
- Create: `src/irc/decision/__init__.py`
- Create: `src/irc/decision/completeness.py`
- Create: `tests/decision/__init__.py`
- Create: `tests/decision/test_completeness.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/decision/__init__.py` as an empty file.

Create `tests/decision/test_completeness.py`:

```python
from __future__ import annotations

from irc.decision.completeness import (
    REQUIRED_METRIC_FIELDS,
    completeness_ratio,
    missing_required_fields,
    summarize_completeness,
)


def test_missing_required_fields_returns_all_fields_for_absent_row() -> None:
    assert missing_required_fields(None) == REQUIRED_METRIC_FIELDS


def test_missing_required_fields_treats_none_and_nan_as_missing() -> None:
    row = {
        "expense_ratio": 0.001,
        "drawdown_3y": None,
        "vol_1y": float("nan"),
        "downside_capture": 0.9,
        "aum_stability_pct": 0.05,
        "manager_tenure_years": 8.0,
        "holdings_concentration_top10": 0.25,
    }

    assert missing_required_fields(row) == ("drawdown_3y", "vol_1y")


def test_completeness_ratio_counts_present_required_fields() -> None:
    row = {
        "expense_ratio": 0.001,
        "drawdown_3y": 0.2,
        "vol_1y": 0.18,
        "downside_capture": 0.9,
        "aum_stability_pct": 0.05,
        "manager_tenure_years": 8.0,
        "holdings_concentration_top10": 0.25,
    }

    assert completeness_ratio(row) == 1.0


def test_summarize_completeness_groups_by_asset_class() -> None:
    rows = [
        {"instrument_id": "A", "asset_class": "gold", "data_completeness": 1.0},
        {"instrument_id": "B", "asset_class": "gold", "data_completeness": 0.0},
        {"instrument_id": "C", "asset_class": "us_etf", "data_completeness": 0.5},
    ]

    summary = summarize_completeness(rows)

    assert summary["overall_avg"] == 0.5
    assert summary["by_asset_class"] == {"gold": 0.5, "us_etf": 0.5}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/decision/test_completeness.py -q
```

Expected: FAIL because `irc.decision.completeness` does not exist.

- [ ] **Step 3: Implement the helpers**

Create `src/irc/decision/__init__.py`:

```python
from __future__ import annotations
```

Create `src/irc/decision/completeness.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


REQUIRED_METRIC_FIELDS: tuple[str, ...] = (
    "expense_ratio",
    "drawdown_3y",
    "vol_1y",
    "downside_capture",
    "aum_stability_pct",
    "manager_tenure_years",
    "holdings_concentration_top10",
)


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def missing_required_fields(
    row: Mapping[str, Any] | None,
    required: Sequence[str] = REQUIRED_METRIC_FIELDS,
) -> tuple[str, ...]:
    if row is None:
        return tuple(required)
    return tuple(field for field in required if is_missing(row.get(field)))


def completeness_ratio(
    row: Mapping[str, Any] | None,
    required: Sequence[str] = REQUIRED_METRIC_FIELDS,
) -> float:
    if not required:
        return 1.0
    missing = missing_required_fields(row, required)
    return (len(required) - len(missing)) / len(required)


def summarize_completeness(rows: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    if not rows:
        return {"overall_avg": 1.0, "by_asset_class": {}}
    values = [float(row.get("data_completeness", 0.0)) for row in rows]
    by_class_values: dict[str, list[float]] = {}
    for row in rows:
        asset_class = str(row.get("asset_class", "unknown"))
        by_class_values.setdefault(asset_class, []).append(float(row.get("data_completeness", 0.0)))
    by_asset_class = {
        asset_class: sum(class_values) / len(class_values)
        for asset_class, class_values in by_class_values.items()
    }
    return {"overall_avg": sum(values) / len(values), "by_asset_class": by_asset_class}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/decision/test_completeness.py -q
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git diff --check -- src/irc/decision/__init__.py src/irc/decision/completeness.py tests/decision/__init__.py tests/decision/test_completeness.py
```

Expected: no output.

---

### Task 2: Add Missing Data to Scoring Output

**Files:**
- Modify: `src/irc/scoring/pipeline.py`
- Modify: `tests/scoring/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Append these assertions to existing tests in `tests/scoring/test_pipeline.py`.

In `test_pipeline_produces_one_score_per_instrument`, after `assert "composite_score" in out["scores"][0]`, add:

```python
    assert out["scores"][0]["missing_data"] == []
```

In `test_pipeline_treats_nan_metrics_as_missing`, after `assert score["data_completeness"] == 0.0`, add:

```python
    assert score["missing_data"] == [
        "expense_ratio",
        "drawdown_3y",
        "vol_1y",
        "downside_capture",
        "aum_stability_pct",
        "manager_tenure_years",
        "holdings_concentration_top10",
    ]
```

In `test_pipeline_instrument_missing_from_metrics_uses_defaults`, after `assert out["scores"][0]["data_completeness"] == 0.0`, add:

```python
    assert out["scores"][0]["missing_data"] == [
        "expense_ratio",
        "drawdown_3y",
        "vol_1y",
        "downside_capture",
        "aum_stability_pct",
        "manager_tenure_years",
        "holdings_concentration_top10",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/scoring/test_pipeline.py -q
```

Expected: FAIL with `KeyError: 'missing_data'`.

- [ ] **Step 3: Implement scoring output enrichment**

Modify `src/irc/scoring/pipeline.py` imports:

```python
from irc.decision.completeness import REQUIRED_METRIC_FIELDS, missing_required_fields
```

Replace the local `_REQUIRED` tuple with:

```python
_REQUIRED = REQUIRED_METRIC_FIELDS
```

In `run_scoring`, immediately after:

```python
        m = by_id.get(r.instrument_id, {})
        completeness = _completeness(m, _REQUIRED)
```

add:

```python
        missing_data = list(missing_required_fields(m, _REQUIRED))
```

In the score output dictionary, add:

```python
            "missing_data": missing_data,
```

The final output block should include both fields:

```python
        out.append({
            "instrument_id": score_obj.instrument_id,
            "composite_score": score_obj.composite_score,
            "action": score_obj.action,
            "conviction": score_obj.conviction,
            "factor_breakdown": score_obj.factor_breakdown,
            "data_completeness": score_obj.data_completeness,
            "missing_data": missing_data,
            "weights_version": score_obj.weights_version,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/decision/test_completeness.py tests/scoring/test_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git diff --check -- src/irc/scoring/pipeline.py tests/scoring/test_pipeline.py
```

Expected: no output.

---

### Task 3: Decision Models and Hard Gates

**Files:**
- Create: `src/irc/decision/models.py`
- Create: `src/irc/decision/gates.py`
- Create: `tests/decision/test_gates.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/decision/test_gates.py`:

```python
from __future__ import annotations

from irc.decision.gates import decide_row, target_weights_are_valid


def _score(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "instrument_id": "518850",
        "asset_class": "gold",
        "action": "buy_candidate",
        "conviction": "med",
        "data_completeness": 1.0,
        "missing_data": [],
    }
    return {**row, **overrides}


def test_target_weights_are_valid_requires_total_near_one() -> None:
    assert target_weights_are_valid({"diagnostics": {"total_weight": 1.0}})
    assert not target_weights_are_valid({"diagnostics": {"total_weight": 3.0}})


def test_pipeline_halt_blocks_everything() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=True,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert decision["portfolio_action"] == "no_trade"
    assert "pipeline_halted" in decision["blocking_reasons"]


def test_low_data_completeness_blocks_buy() -> None:
    decision = decide_row(
        score=_score(data_completeness=0.0, missing_data=["expense_ratio"]),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert "data_incomplete" in decision["blocking_reasons"]


def test_avoid_action_stays_avoid_even_when_selected() -> None:
    decision = decide_row(
        score=_score(action="avoid"),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "avoid"
    assert decision["portfolio_action"] == "no_trade"


def test_incompatible_venue_without_proxy_blocks_execution() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": False, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "blocked"
    assert decision["venue_status"] == "blocked_no_proxy"


def test_complete_healthy_buy_candidate_can_be_actionable() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=1.0,
    )

    assert decision["decision_status"] == "actionable_buy"
    assert decision["portfolio_action"] == "no_trade"


def test_zero_memo_traceability_marks_evidence_narrative_only() -> None:
    decision = decide_row(
        score=_score(),
        allocation_selected=True,
        target_weight_valid=True,
        trade={"venue_compatible": True, "proxy_id": None},
        pipeline_halted=False,
        memo_traceability_coverage=0.0,
    )

    assert decision["memo_evidence_status"] == "narrative_only"
    assert "memo_narrative_only" in decision["blocking_reasons"]
    assert decision["decision_status"] == "blocked"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/decision/test_gates.py -q
```

Expected: FAIL because `irc.decision.gates` does not exist.

- [ ] **Step 3: Implement models**

Create `src/irc/decision/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DecisionStatus = Literal[
    "actionable_buy",
    "watch_only",
    "avoid",
    "blocked",
    "review_sell_later",
]
PortfolioAction = Literal["no_trade"]
VenueStatus = Literal["direct", "proxy_available", "blocked_no_proxy", "unknown"]


@dataclass(frozen=True)
class DecisionRow:
    instrument_id: str
    asset_class: str
    score_action: str
    decision_status: DecisionStatus
    portfolio_action: PortfolioAction
    conviction: str
    data_completeness: float
    missing_data: list[str]
    target_weight_valid: bool
    venue_status: VenueStatus
    memo_evidence_status: str
    blocking_reasons: list[str] = field(default_factory=list)
    reason: str = ""
    next_step: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 4: Implement gates**

Create `src/irc/decision/gates.py`:

```python
from __future__ import annotations

from typing import Any

from irc.decision.completeness import REQUIRED_METRIC_FIELDS
from irc.decision.models import DecisionRow, VenueStatus


_BUY_ACTIONS = {"buy_candidate", "strong_buy_candidate"}
_AVOID_ACTIONS = {"avoid", "strong_avoid"}


def target_weights_are_valid(allocation: dict[str, Any], tolerance: float = 1e-3) -> bool:
    total = allocation.get("diagnostics", {}).get("total_weight")
    if total is None:
        selected = allocation.get("selected_instruments", [])
        total = sum(float(row.get("target_weight", 0.0)) for row in selected)
    try:
        return abs(float(total) - 1.0) <= tolerance
    except (TypeError, ValueError):
        return False


def venue_status_for_trade(trade: dict[str, Any] | None) -> VenueStatus:
    if trade is None:
        return "unknown"
    if bool(trade.get("venue_compatible")):
        return "direct"
    if trade.get("proxy_id") is not None:
        return "proxy_available"
    return "blocked_no_proxy"


def memo_evidence_status(coverage: float) -> str:
    return "evidence_linked" if coverage > 0.0 else "narrative_only"


def decide_row(
    score: dict[str, Any],
    allocation_selected: bool,
    target_weight_valid: bool,
    trade: dict[str, Any] | None,
    pipeline_halted: bool,
    memo_traceability_coverage: float,
    completeness_threshold: float = 0.80,
) -> dict[str, Any]:
    score_action = str(score.get("action", "unknown"))
    completeness = float(score.get("data_completeness", 0.0))
    missing_data = list(score.get("missing_data") or REQUIRED_METRIC_FIELDS)
    venue_status = venue_status_for_trade(trade)
    evidence_status = memo_evidence_status(memo_traceability_coverage)
    blocking_reasons = _blocking_reasons(
        pipeline_halted=pipeline_halted,
        completeness=completeness,
        completeness_threshold=completeness_threshold,
        target_weight_valid=target_weight_valid,
        venue_status=venue_status,
        evidence_status=evidence_status,
        score_action=score_action,
    )
    decision_status = _decision_status(score_action, blocking_reasons, allocation_selected)
    row = DecisionRow(
        instrument_id=str(score.get("instrument_id", "")),
        asset_class=str(score.get("asset_class", "unknown")),
        score_action=score_action,
        decision_status=decision_status,
        portfolio_action="no_trade",
        conviction=str(score.get("conviction", "low")),
        data_completeness=completeness,
        missing_data=missing_data,
        target_weight_valid=target_weight_valid,
        venue_status=venue_status,
        memo_evidence_status=evidence_status,
        blocking_reasons=blocking_reasons,
        reason=_reason(decision_status, blocking_reasons, score_action),
        next_step=_next_step(blocking_reasons, decision_status),
    )
    return row.to_dict()


def _blocking_reasons(
    pipeline_halted: bool,
    completeness: float,
    completeness_threshold: float,
    target_weight_valid: bool,
    venue_status: VenueStatus,
    evidence_status: str,
    score_action: str,
) -> list[str]:
    reasons: list[str] = []
    if pipeline_halted:
        reasons.append("pipeline_halted")
    if completeness < completeness_threshold:
        reasons.append("data_incomplete")
    if not target_weight_valid:
        reasons.append("target_weights_invalid")
    if venue_status == "blocked_no_proxy":
        reasons.append("venue_blocked")
    if evidence_status == "narrative_only":
        reasons.append("memo_narrative_only")
    if score_action in _AVOID_ACTIONS:
        reasons.append("score_avoid")
    return reasons


def _decision_status(score_action: str, blocking_reasons: list[str], allocation_selected: bool) -> str:
    if score_action in _AVOID_ACTIONS:
        return "avoid"
    if blocking_reasons:
        return "blocked"
    if score_action in _BUY_ACTIONS and allocation_selected:
        return "actionable_buy"
    return "watch_only"


def _reason(decision_status: str, blocking_reasons: list[str], score_action: str) -> str:
    if decision_status == "actionable_buy":
        return "Score, data, allocation, venue, pipeline, and traceability gates are all clear."
    if decision_status == "avoid":
        return f"Scoring action is {score_action}; allocation or trade-plan presence cannot upgrade an avoid signal."
    return "Blocked by: " + ", ".join(blocking_reasons)


def _next_step(blocking_reasons: list[str], decision_status: str) -> str:
    if decision_status == "actionable_buy":
        return "Review manually before any order; this plan does not size trades."
    if "pipeline_halted" in blocking_reasons:
        return "Fix the halted stage and rerun the pipeline."
    if "data_incomplete" in blocking_reasons:
        return "Repair required financial metrics and rerun scoring."
    if "target_weights_invalid" in blocking_reasons:
        return "Fix allocation normalization before using target weights."
    if "venue_blocked" in blocking_reasons:
        return "Add a compatible account venue or exact proxy."
    if "memo_narrative_only" in blocking_reasons:
        return "Improve memo traceability before treating narrative claims as evidence."
    return "Keep on watchlist and rerun after new data."
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/decision/test_gates.py -q
```

Expected: PASS.

- [ ] **Step 6: Checkpoint**

Run:

```bash
git diff --check -- src/irc/decision/models.py src/irc/decision/gates.py tests/decision/test_gates.py
```

Expected: no output.

---

### Task 4: Decision Report Composition and Markdown Rendering

**Files:**
- Create: `src/irc/decision/report.py`
- Create: `tests/decision/test_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/decision/test_report.py`:

```python
from __future__ import annotations

from irc.decision.report import compose_decision_report, render_decision_markdown


def _scoring() -> dict[str, object]:
    return {
        "scores": [
            {
                "instrument_id": "518850",
                "asset_class": "gold",
                "action": "watch",
                "conviction": "low",
                "data_completeness": 0.0,
                "missing_data": ["expense_ratio"],
            },
            {
                "instrument_id": "050025",
                "asset_class": "us_etf",
                "action": "buy_candidate",
                "conviction": "med",
                "data_completeness": 1.0,
                "missing_data": [],
            },
        ]
    }


def test_compose_decision_report_blocks_when_pipeline_halted_and_weights_invalid() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring=_scoring(),
        allocation={
            "selected_instruments": [
                {"instrument_id": "518850", "target_weight": 0.5},
                {"instrument_id": "050025", "target_weight": 0.5},
            ],
            "diagnostics": {"total_weight": 3.0},
        },
        trade_plan={
            "trades": [
                {"target": "518850", "venue_compatible": False, "proxy_id": None},
                {"target": "050025", "venue_compatible": True, "proxy_id": None},
            ]
        },
        memo_traceability={"coverage_ratio": 0.0},
        pipeline_halted=True,
    )

    assert report["overall_status"] == "blocked"
    assert "pipeline_halted" in report["blocking_reasons"]
    assert "target_weights_invalid" in report["blocking_reasons"]
    assert report["summary"]["actionable_buy_count"] == 0
    assert report["summary"]["blocked_count"] == 2


def test_compose_decision_report_allows_actionable_buy_when_all_gates_clear() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring={"scores": [_scoring()["scores"][1]]},
        allocation={
            "selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}],
            "diagnostics": {"total_weight": 1.0},
        },
        trade_plan={"trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}]},
        memo_traceability={"coverage_ratio": 1.0},
        pipeline_halted=False,
    )

    assert report["overall_status"] == "ok"
    assert report["rows"][0]["decision_status"] == "actionable_buy"


def test_markdown_report_starts_with_clear_verdict() -> None:
    report = compose_decision_report(
        date="2026-05-11",
        scoring=_scoring(),
        allocation={"selected_instruments": [], "diagnostics": {"total_weight": 3.0}},
        trade_plan={"trades": []},
        memo_traceability={"coverage_ratio": 0.0},
        pipeline_halted=True,
    )

    markdown = render_decision_markdown(report)

    assert markdown.startswith("# Decision Report 2026-05-11")
    assert "No buy/sell decision is supported today." in markdown
    assert "pipeline_halted" in markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/decision/test_report.py -q
```

Expected: FAIL because `irc.decision.report` does not exist.

- [ ] **Step 3: Implement report composition**

Create `src/irc/decision/report.py`:

```python
from __future__ import annotations

from typing import Any

from irc.decision.gates import decide_row, target_weights_are_valid


def compose_decision_report(
    date: str,
    scoring: dict[str, Any],
    allocation: dict[str, Any],
    trade_plan: dict[str, Any],
    memo_traceability: dict[str, Any],
    pipeline_halted: bool,
) -> dict[str, Any]:
    target_weight_valid = target_weights_are_valid(allocation)
    selected_ids = {str(row.get("instrument_id")) for row in allocation.get("selected_instruments", [])}
    trades_by_target = {str(row.get("target")): row for row in trade_plan.get("trades", [])}
    coverage = float(memo_traceability.get("coverage_ratio", 0.0))
    rows = [
        decide_row(
            score=score,
            allocation_selected=str(score.get("instrument_id")) in selected_ids,
            target_weight_valid=target_weight_valid,
            trade=trades_by_target.get(str(score.get("instrument_id"))),
            pipeline_halted=pipeline_halted,
            memo_traceability_coverage=coverage,
        )
        for score in scoring.get("scores", [])
    ]
    blocking_reasons = _overall_blocking_reasons(rows, pipeline_halted, target_weight_valid)
    return {
        "date": date,
        "overall_status": "blocked" if blocking_reasons else "ok",
        "blocking_reasons": blocking_reasons,
        "summary": _summary(rows),
        "rows": rows,
    }


def render_decision_markdown(report: dict[str, Any]) -> str:
    verdict = (
        "No buy/sell decision is supported today."
        if report["overall_status"] == "blocked"
        else "At least one instrument passed decision-readiness gates. Review manually before execution."
    )
    lines = [
        f"# Decision Report {report['date']}",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Why Blocked",
        "",
    ]
    reasons = report.get("blocking_reasons", [])
    if reasons:
        lines.extend(f"- {reason}" for reason in reasons)
    else:
        lines.append("- No system-level blocking reason detected.")
    lines.extend([
        "",
        "## Instrument Decisions",
        "",
        "| Instrument | Status | Score Action | Conviction | Completeness | Venue | Next Step |",
        "|---|---|---|---|---:|---|---|",
    ])
    for row in report.get("rows", []):
        lines.append(
            "| {instrument_id} | {decision_status} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} | {next_step} |".format(**row)
        )
    lines.append("")
    return "\n".join(lines)


def _overall_blocking_reasons(rows: list[dict[str, Any]], pipeline_halted: bool, target_weight_valid: bool) -> list[str]:
    reasons: list[str] = []
    if pipeline_halted:
        reasons.append("pipeline_halted")
    if not target_weight_valid:
        reasons.append("target_weights_invalid")
    if any(row.get("memo_evidence_status") == "narrative_only" for row in rows):
        reasons.append("memo_narrative_only")
    if any("data_incomplete" in row.get("blocking_reasons", []) for row in rows):
        reasons.append("data_incomplete")
    return reasons


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    statuses = [row.get("decision_status") for row in rows]
    return {
        "actionable_buy_count": statuses.count("actionable_buy"),
        "watch_count": statuses.count("watch_only"),
        "avoid_count": statuses.count("avoid"),
        "blocked_count": statuses.count("blocked"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/decision/test_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git diff --check -- src/irc/decision/report.py tests/decision/test_report.py
```

Expected: no output.

---

### Task 5: Decision CLI Command

**Files:**
- Create: `src/irc/commands/decision_cmd.py`
- Modify: `src/irc/cli.py`
- Create: `tests/commands/test_decision_cmd.py`
- Modify: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write the failing command tests**

Create `tests/commands/test_decision_cmd.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from irc.commands.decision_cmd import run_decision
from irc.commands.init_cmd import run_init


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def test_decision_returns_2_when_required_outputs_missing(tmp_path: Path) -> None:
    run_init(str(tmp_path), force=False)

    assert run_decision(repo_root=str(tmp_path)) == 2


def test_decision_writes_json_and_markdown(tmp_path: Path) -> None:
    run_init(str(tmp_path), force=False)
    out_dir = tmp_path / "outputs" / _today()
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps({
        "scores": [{
            "instrument_id": "050025",
            "asset_class": "us_etf",
            "action": "buy_candidate",
            "conviction": "med",
            "data_completeness": 1.0,
            "missing_data": [],
        }]
    }), encoding="utf-8")
    (out_dir / "proposed_allocation.yaml").write_text(yaml.safe_dump({
        "selected_instruments": [{"instrument_id": "050025", "target_weight": 1.0}],
        "diagnostics": {"total_weight": 1.0},
    }), encoding="utf-8")
    (out_dir / "trade_plan.yaml").write_text(yaml.safe_dump({
        "mode": "build",
        "trades": [{"target": "050025", "venue_compatible": True, "proxy_id": None}],
    }), encoding="utf-8")
    (out_dir / "memo_traceability.json").write_text(json.dumps({"coverage_ratio": 1.0}), encoding="utf-8")

    assert run_decision(repo_root=str(tmp_path)) == 0

    report_json = out_dir / "decision_report.json"
    report_md = out_dir / "decision_report.md"
    assert report_json.exists()
    assert report_md.exists()
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["rows"][0]["decision_status"] == "actionable_buy"
    assert report_md.read_text(encoding="utf-8").startswith(f"# Decision Report {_today()}")
```

Modify `tests/test_cli_smoke.py` in `test_cli_help_lists_subcommands`:

```python
    for cmd in ("init", "config", "freshness", "universe", "decision"):
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/commands/test_decision_cmd.py tests/test_cli_smoke.py::test_cli_help_lists_subcommands -q
```

Expected: FAIL because `decision_cmd` and `irc decision` do not exist.

- [ ] **Step 3: Implement the command wrapper**

Create `src/irc/commands/decision_cmd.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from irc.decision.report import compose_decision_report, render_decision_markdown
from irc.io_utils import atomic_write_text


_TZ = timezone(timedelta(hours=8))
_REQUIRED_ARTIFACTS = (
    "scoring.json",
    "proposed_allocation.yaml",
    "trade_plan.yaml",
    "memo_traceability.json",
)


def run_decision(repo_root: str) -> int:
    root = Path(repo_root)
    out_dir = _resolve_output_dir(root)
    missing = [name for name in _REQUIRED_ARTIFACTS if not (out_dir / name).exists()]
    if missing:
        print(f"ERROR: missing decision inputs in {out_dir}: {', '.join(missing)}")
        return 2
    scoring = _read_json(out_dir / "scoring.json")
    allocation = _read_yaml(out_dir / "proposed_allocation.yaml")
    trade_plan = _read_yaml(out_dir / "trade_plan.yaml")
    memo_traceability = _read_json(out_dir / "memo_traceability.json")
    report = compose_decision_report(
        date=out_dir.name,
        scoring=scoring,
        allocation=allocation,
        trade_plan=trade_plan,
        memo_traceability=memo_traceability,
        pipeline_halted=(out_dir / "PIPELINE_HALTED.md").exists(),
    )
    atomic_write_text(out_dir / "decision_report.json", json.dumps(report, ensure_ascii=False, indent=2))
    atomic_write_text(out_dir / "decision_report.md", render_decision_markdown(report))
    print(f"decision {report['overall_status']} -> {out_dir / 'decision_report.md'}")
    return 0


def _resolve_output_dir(root: Path) -> Path:
    today = datetime.now(_TZ).date().isoformat()
    today_dir = root / "outputs" / today
    if today_dir.exists():
        return today_dir
    candidates = sorted(path for path in (root / "outputs").glob("*") if path.is_dir())
    return candidates[-1] if candidates else today_dir


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
```

Modify `src/irc/cli.py` after the `plan` command:

```python
@main.command(help="Compose decision-readiness report from today's outputs.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def decision(repo_root: str) -> None:
    from irc.commands.decision_cmd import run_decision
    rc = run_decision(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/commands/test_decision_cmd.py tests/test_cli_smoke.py::test_cli_help_lists_subcommands -q
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git diff --check -- src/irc/commands/decision_cmd.py src/irc/cli.py tests/commands/test_decision_cmd.py tests/test_cli_smoke.py
```

Expected: no output.

---

### Task 6: Scoring Completeness Eval Gate

**Why this task is critical:** the existing `evals/scoring/runner.py` reads from `outputs/scoring/scores.json` and treats the file as a top-level list. The actual score command writes `{"scores": [...]}` to `outputs/<date>/scoring.json`. Without fixing the input path and format, the new completeness metrics will silently see an empty input on real artifacts and never FAIL — defeating Phase 2's "explicit eval failures when a buy candidate has incomplete data" requirement.

**Files:**
- Modify: `evals/scoring/metrics.py`
- Modify: `evals/scoring/runner.py`
- Modify: `tests/evals/test_scoring_metrics.py`
- Create: `tests/evals/test_scoring_runner.py`

- [ ] **Step 1: Write the failing metric tests**

Append to `tests/evals/test_scoring_metrics.py`:

```python
from evals.scoring.metrics import (
    buy_candidate_min_completeness,
    scoring_data_completeness_avg,
)


def test_scoring_data_completeness_avg() -> None:
    scores = [{"data_completeness": 1.0}, {"data_completeness": 0.5}]
    assert scoring_data_completeness_avg(scores) == 0.75


def test_scoring_data_completeness_empty_scores() -> None:
    assert scoring_data_completeness_avg([]) == 1.0


def test_buy_candidate_min_completeness_uses_only_buy_actions() -> None:
    scores = [
        {"action": "buy_candidate", "data_completeness": 0.7},
        {"action": "strong_buy_candidate", "data_completeness": 0.9},
        {"action": "watch", "data_completeness": 0.1},
    ]

    assert buy_candidate_min_completeness(scores) == 0.7


def test_buy_candidate_min_completeness_no_buy_candidates() -> None:
    assert buy_candidate_min_completeness([{"action": "watch", "data_completeness": 0.0}]) == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/evals/test_scoring_metrics.py -q
```

Expected: FAIL because the new metric functions do not exist.

- [ ] **Step 3: Implement metrics**

Modify `evals/scoring/metrics.py`:

```python
def scoring_data_completeness_avg(scores: list[dict]) -> float:
    if not scores:
        return 1.0
    values = [float(score.get("data_completeness", 0.0)) for score in scores]
    return sum(values) / len(values)


def buy_candidate_min_completeness(scores: list[dict]) -> float:
    buy_actions = {"buy_candidate", "strong_buy_candidate"}
    values = [
        float(score.get("data_completeness", 0.0))
        for score in scores
        if score.get("action") in buy_actions
    ]
    return min(values) if values else 1.0
```

- [ ] **Step 4: Write failing runner tests for path + format fix**

Create `tests/evals/test_scoring_runner.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals.scoring.runner import run


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _scoring_payload(scores: list[dict]) -> dict:
    return {"scores": scores}


def _full_factor_breakdown() -> dict:
    return {
        k: {"value": 0.5, "raw_refs": [f"ref_{k}"]}
        for k in ("valuation_cost", "risk", "quality", "macro_fit", "thesis_news")
    }


def test_runner_reads_dated_scoring_json(tmp_path: Path) -> None:
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps(_scoring_payload([
        {
            "instrument_id": "VTI",
            "action": "buy_candidate",
            "composite_score": 80.0,
            "data_completeness": 1.0,
            "factor_breakdown": _full_factor_breakdown(),
        }
    ])), encoding="utf-8")

    rc = run(tmp_path)

    report_path = tmp_path / "outputs" / today / "evals" / "scoring" / "report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    metric_names = {m["name"] for m in report["metrics"]}
    assert "scoring_data_completeness_avg" in metric_names
    assert "buy_candidate_min_completeness" in metric_names
    assert rc == 0


def test_runner_fails_when_buy_candidate_below_threshold(tmp_path: Path) -> None:
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps(_scoring_payload([
        {
            "instrument_id": "VTI",
            "action": "buy_candidate",
            "composite_score": 80.0,
            "data_completeness": 0.0,
            "factor_breakdown": _full_factor_breakdown(),
        }
    ])), encoding="utf-8")

    rc = run(tmp_path)

    assert rc == 2
    report = json.loads((tmp_path / "outputs" / today / "evals" / "scoring" / "report.json").read_text(encoding="utf-8"))
    buy_metric = next(m for m in report["metrics"] if m["name"] == "buy_candidate_min_completeness")
    assert buy_metric["status"] == "FAIL"
```

Run:

```bash
uv run pytest tests/evals/test_scoring_runner.py -q
```

Expected: FAIL (runner still reads stale `outputs/scoring/scores.json` path and lacks completeness metrics).

- [ ] **Step 5: Wire metrics into scoring eval runner and fix path/format**

Replace `evals/scoring/runner.py` contents:

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.scoring.metrics import (
    buy_candidate_min_completeness,
    factor_breakdown_completeness,
    historical_sanity_rho,
    raw_ref_reachability,
    score_distribution_stability,
    scoring_data_completeness_avg,
)

_TZ = timezone(timedelta(hours=8))
_FBC_TH = {"warn_below": 0.99, "fail_below": 0.9}
_RRR_TH = {"warn_below": 0.99, "fail_below": 0.9}
_RHO_TH = {"warn_below": 0.0, "fail_below": -0.5}
_STABILITY_TH = {"warn_above": 0.1, "fail_above": 0.2}
_DATA_COMPLETENESS_AVG_TH = {"warn_below": 0.90, "fail_below": 0.75}
# Spec: FAIL when any buy candidate < 0.80; no WARN band for buys.
# warn_below == fail_below collapses the WARN tier; classify_status returns FAIL or PASS only.
_BUY_COMPLETENESS_TH = {"warn_below": 0.80, "fail_below": 0.80}


def _load_scores(repo_root: Path) -> tuple[list[dict], Path | None]:
    today = datetime.now(_TZ).date().isoformat()
    today_path = repo_root / "outputs" / today / "scoring.json"
    if today_path.exists():
        return _parse_scores(today_path), today_path
    candidates = sorted((repo_root / "outputs").glob("*/scoring.json"))
    if candidates:
        latest = candidates[-1]
        return _parse_scores(latest), latest
    return [], None


def _parse_scores(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return list(raw.get("scores", []))
    if isinstance(raw, list):
        return list(raw)
    return []


def run(repo_root: Path) -> int:
    scores, source = _load_scores(repo_root)
    if source is None:
        report = _pass_report()
        _write(repo_root, report)
        print(f"scoring eval: {report.overall} (no input file)")
        return 0

    index: set[str] = set()
    for s in scores:
        for v in s.get("factor_breakdown", {}).values():
            index.update(v.get("raw_refs", []))

    fbc = factor_breakdown_completeness(scores)
    rrr = raw_ref_reachability(scores, index)
    rho = historical_sanity_rho(scores)
    data_completeness_avg = scoring_data_completeness_avg(scores)
    buy_min_completeness = buy_candidate_min_completeness(scores)

    mid = len(scores) // 2
    comp_a = [s.get("composite_score", 0.0) for s in scores[:mid]]
    comp_b = [s.get("composite_score", 0.0) for s in scores[mid:]]
    stability = score_distribution_stability(comp_a, comp_b)

    metrics: list[MetricReport] = [
        MetricReport(
            name="scoring_data_completeness_avg",
            value=data_completeness_avg,
            status=classify_status(data_completeness_avg, _DATA_COMPLETENESS_AVG_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_DATA_COMPLETENESS_AVG_TH,
        ),
        MetricReport(
            name="buy_candidate_min_completeness",
            value=buy_min_completeness,
            status=classify_status(buy_min_completeness, _BUY_COMPLETENESS_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_BUY_COMPLETENESS_TH,
        ),
        MetricReport(
            name="factor_breakdown_completeness",
            value=fbc,
            status=classify_status(fbc, _FBC_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_FBC_TH,
        ),
        MetricReport(
            name="raw_ref_reachability",
            value=rrr,
            status=classify_status(rrr, _RRR_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_RRR_TH,
        ),
        MetricReport(
            name="historical_sanity_rho",
            value=rho,
            status=classify_status(rho, _RHO_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_RHO_TH,
        ),
        MetricReport(
            name="score_distribution_stability",
            value=stability,
            status=classify_status(stability, _STABILITY_TH, "lower_is_better"),
            n_observations=len(scores),
            threshold=_STABILITY_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="scoring",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(source)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"scoring eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="scoring", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "scoring")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/evals/test_scoring_metrics.py tests/evals/test_scoring_runner.py -q
```

Expected: PASS.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git diff --check -- evals/scoring/metrics.py evals/scoring/runner.py tests/evals/test_scoring_metrics.py tests/evals/test_scoring_runner.py
```

Expected: no output.

---

### Task 7: Local Scoring Metrics Loader

**Files:**
- Create: `src/irc/scoring/metrics_loader.py`
- Modify: `src/irc/commands/score_cmd.py`
- Create: `tests/scoring/test_metrics_loader.py`
- Modify: `tests/commands/test_score_cmd.py`

- [ ] **Step 1: Write failing unit tests for local metric derivation**

Create `tests/scoring/test_metrics_loader.py`:

```python
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from irc.data.duckdb_helper import connect, ensure_schema
from irc.scoring.metrics_loader import derive_risk_metrics, load_scoring_metrics


def test_derive_risk_metrics_from_price_series() -> None:
    series = pd.Series(
        [100.0, 110.0, 105.0, 120.0, 90.0, 95.0],
        index=pd.date_range("2026-01-01", periods=6),
    )

    metrics = derive_risk_metrics(series)

    assert metrics["drawdown_3y"] == 0.25
    assert metrics["vol_1y"] > 0.0
    assert metrics["downside_capture"] >= 0.0


def test_load_scoring_metrics_combines_instruments_prices_and_holdings(tmp_path: Path) -> None:
    con = connect(tmp_path / "local.duckdb")
    ensure_schema(con)
    ingested_at = "2026-05-11 00:00:00"
    con.execute(
        "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["050025", "050025", "cn_off_exchange", "博时标普500", None, "us_etf", "cny", date(2012, 1, 1), 0.006, 1_000_000_000.0, "S&P 500", 8.0, ingested_at, "test", "ref_inst"],
    )
    start = date(2026, 1, 1)
    for offset, close in enumerate([100.0, 102.0, 101.0, 104.0, 103.0, 105.0]):
        con.execute(
            "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["050025", start + timedelta(days=offset), None, None, None, close, 1000.0, ingested_at, "test", f"ref_price_{offset}"],
        )
    for rank, weight in enumerate([20.0, 15.0, 10.0], start=1):
        con.execute(
            "INSERT INTO fund_holdings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["050025", date(2026, 3, 31), f"H{rank}", f"Holding {rank}", weight, ingested_at, "test", f"ref_holding_{rank}"],
        )

    metrics = load_scoring_metrics(con, ["050025"])

    assert list(metrics["instrument_id"]) == ["050025"]
    row = metrics.iloc[0].to_dict()
    assert row["expense_ratio"] == 0.006
    assert row["manager_tenure_years"] == 8.0
    assert row["holdings_concentration_top10"] == 0.45
    assert row["drawdown_3y"] >= 0.0
    # aum_stability_pct must stay NaN until a real AUM-history derivation lands.
    # Phase 2 honest-missing-data goal forbids faking a 0.0 stability value.
    assert pd.isna(row["aum_stability_pct"])
    con.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/scoring/test_metrics_loader.py -q
```

Expected: FAIL because `irc.scoring.metrics_loader` does not exist.

- [ ] **Step 3: Implement metrics loader**

Create `src/irc/scoring/metrics_loader.py`:

```python
from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import duckdb
import pandas as pd


def derive_risk_metrics(values: pd.Series) -> dict[str, float]:
    series = values.dropna().astype(float)
    if len(series) < 2:
        return {"drawdown_3y": math.nan, "vol_1y": math.nan, "downside_capture": math.nan}
    running_max = series.cummax()
    drawdowns = (running_max - series) / running_max
    returns = series.pct_change().dropna()
    downside = returns[returns < 0]
    return {
        "drawdown_3y": float(drawdowns.max()),
        "vol_1y": float(returns.std(ddof=0) * math.sqrt(252)) if not returns.empty else math.nan,
        "downside_capture": float(abs(downside.mean()) / abs(returns.mean())) if not downside.empty and returns.mean() != 0 else 0.0,
    }


def load_scoring_metrics(con: duckdb.DuckDBPyConnection, instrument_ids: Iterable[str]) -> pd.DataFrame:
    ids = tuple(str(instrument_id) for instrument_id in instrument_ids)
    if not ids:
        return _empty_metrics_frame()
    rows = [_metrics_for_instrument(con, instrument_id) for instrument_id in ids]
    return pd.DataFrame(rows)


def _metrics_for_instrument(con: duckdb.DuckDBPyConnection, instrument_id: str) -> dict[str, Any]:
    base = _instrument_base(con, instrument_id)
    latest_fund = _latest_fund_metrics(con, instrument_id)
    prices = _price_or_nav_series(con, instrument_id)
    risk = derive_risk_metrics(prices) if not prices.empty else {}
    concentration = _latest_holdings_concentration(con, instrument_id)
    # aum_stability_pct requires a multi-period AUM history we do not yet ingest.
    # Honest "missing" (NaN) is required so Phase 2 completeness gates fire correctly
    # on instruments lacking AUM-stability evidence. Do not fake a 0.0 stability value.
    return {
        "instrument_id": instrument_id,
        "expense_ratio": base.get("expense_ratio"),
        "drawdown_3y": _coalesce(latest_fund.get("drawdown_3y"), risk.get("drawdown_3y")),
        "vol_1y": _coalesce(latest_fund.get("vol_1y"), risk.get("vol_1y")),
        "downside_capture": _coalesce(latest_fund.get("downside_capture"), risk.get("downside_capture")),
        "aum_stability_pct": math.nan,
        "manager_tenure_years": base.get("manager_tenure_years"),
        "holdings_concentration_top10": concentration,
    }


def _coalesce(*values: Any) -> Any:
    """Return the first non-None, non-NaN value, else NaN.

    `dict.get(key, fallback)` only returns `fallback` when the key is absent;
    if the key exists but the value is None or NaN, the fallback is skipped.
    This helper makes fund_metrics → derived-from-prices fallback honest.
    """
    for value in values:
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        return value
    return math.nan


def _instrument_base(con: duckdb.DuckDBPyConnection, instrument_id: str) -> dict[str, Any]:
    result = con.execute(
        "SELECT expense_ratio, aum, manager_tenure_years FROM instruments WHERE instrument_id = ?",
        [instrument_id],
    ).fetchone()
    if result is None:
        return {}
    return {"expense_ratio": result[0], "aum": result[1], "manager_tenure_years": result[2]}


def _latest_fund_metrics(con: duckdb.DuckDBPyConnection, instrument_id: str) -> dict[str, Any]:
    result = con.execute(
        """
        SELECT drawdown_3y, vol_1y, downside_capture
        FROM fund_metrics
        WHERE instrument_id = ?
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
        [instrument_id],
    ).fetchone()
    if result is None:
        return {}
    return {"drawdown_3y": result[0], "vol_1y": result[1], "downside_capture": result[2]}


def _price_or_nav_series(con: duckdb.DuckDBPyConnection, instrument_id: str) -> pd.Series:
    prices = con.execute(
        "SELECT date, close FROM prices WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetchdf()
    if not prices.empty:
        return pd.Series(prices["close"].to_numpy(), index=pd.to_datetime(prices["date"]))
    nav = con.execute(
        "SELECT date, nav FROM nav_history WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetchdf()
    if nav.empty:
        return pd.Series(dtype=float)
    return pd.Series(nav["nav"].to_numpy(), index=pd.to_datetime(nav["date"]))


def _latest_holdings_concentration(con: duckdb.DuckDBPyConnection, instrument_id: str) -> float:
    result = con.execute(
        """
        SELECT SUM(weight_pct) / 100.0
        FROM (
            SELECT weight_pct
            FROM fund_holdings
            WHERE instrument_id = ?
              AND report_date = (SELECT MAX(report_date) FROM fund_holdings WHERE instrument_id = ?)
            ORDER BY weight_pct DESC
            LIMIT 10
        )
        """,
        [instrument_id, instrument_id],
    ).fetchone()
    if result is None or result[0] is None:
        return math.nan
    return float(result[0])


def _empty_metrics_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "instrument_id",
        "expense_ratio",
        "drawdown_3y",
        "vol_1y",
        "downside_capture",
        "aum_stability_pct",
        "manager_tenure_years",
        "holdings_concentration_top10",
    ])
```

- [ ] **Step 4: Modify score command to use the loader**

In `src/irc/commands/score_cmd.py`, add:

```python
from irc.scoring.metrics_loader import load_scoring_metrics
```

Replace the temporary empty metrics block:

```python
    # Metrics are loaded from local DuckDB tables and deterministic derived series.
    metrics = pd.DataFrame(columns=[
        "instrument_id", "expense_ratio", "drawdown_3y", "vol_1y",
        "downside_capture", "aum_stability_pct", "manager_tenure_years",
        "holdings_concentration_top10",
    ])
```

with:

```python
    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        metrics = load_scoring_metrics(con, watchlist["instrument_id"].astype(str).tolist())
    finally:
        con.close()
```

Keep the existing macro summary query, but avoid opening two connections by folding both operations into one connection block:

```python
    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        regime = _macro_summary(con)
        metrics = load_scoring_metrics(con, watchlist["instrument_id"].astype(str).tolist())
    finally:
        con.close()
```

- [ ] **Step 5: Add command-level assertion**

In `tests/commands/test_score_cmd.py`, in `test_score_preserves_leading_zero_fund_ids`, after:

```python
    watchlist = mock_run_scoring.call_args.kwargs["watchlist"]
```

add:

```python
    metrics = mock_run_scoring.call_args.kwargs["metrics"]
    assert "missing_data" not in metrics.columns
```

This confirms the command passes a metrics dataframe and leaves missing-data annotation to `run_scoring`.

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/scoring/test_metrics_loader.py tests/commands/test_score_cmd.py tests/scoring/test_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git diff --check -- src/irc/scoring/metrics_loader.py src/irc/commands/score_cmd.py tests/scoring/test_metrics_loader.py tests/commands/test_score_cmd.py
```

Expected: no output.

---

### Task 8: README and Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README command list**

In `README.md`, after the `uv run irc memo` line, add:

```markdown
uv run irc decision                  # decision-readiness report → decision_report.json + decision_report.md
```

In the generated output list near the pipeline command descriptions, mention:

```markdown
uv run irc decision                  # gates scoring/allocation/trade-plan/memo artifacts before any buy/sell decision
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
uv run pytest tests/decision tests/scoring/test_pipeline.py tests/scoring/test_metrics_loader.py tests/evals/test_scoring_metrics.py tests/evals/test_scoring_runner.py tests/commands/test_decision_cmd.py tests/commands/test_score_cmd.py tests/test_cli_smoke.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: Generate decision report for current outputs**

Run:

```bash
uv run irc decision --repo-root .
```

Expected: exit code 0 and printed line similar to:

```text
decision blocked -> outputs/2026-05-11/decision_report.md
```

- [ ] **Step 5: Inspect generated report**

Run:

```bash
jq '{overall_status, summary, blocking_reasons}' outputs/2026-05-11/decision_report.json
```

Expected output includes:

```text
blocked
```

and `blocking_reasons` includes at least `pipeline_halted`, `target_weights_invalid`, or `data_incomplete` for the current artifacts.

- [ ] **Step 6: Final diff check**

Run:

```bash
git diff --check
```

Expected: no output.

---

## Self-Review Checklist

**Spec coverage — Phase 1 hard gates (design.md lines 102–112):**
- Gate 1 (`PIPELINE_HALTED.md` → `overall_status: blocked`): Tasks 3, 4 (`pipeline_halted` flag plumbed through `decide_row` and `_overall_blocking_reasons`).
- Gate 2 (`data_completeness < 0.80` blocks `actionable_buy` and surfaces missing fields): Tasks 1, 2, 3.
- Gate 3 (target weights not ≈ 1.0 invalidates portfolio sizing): Tasks 3, 4 (`target_weights_are_valid`).
- Gate 4 (incompatible venue with no proxy blocks execution): Task 3 (`venue_status_for_trade`).
- Gate 5 (coverage 0.0 marks memo evidence narrative-only): Task 3 (`memo_evidence_status`).
- Gate 6 (avoid stays avoid): Task 3 (`_decision_status` short-circuits before blocking).

**Spec coverage — Phase 1 test scenarios (design.md lines 210–219):**
- 1. Pipeline halt blocks every row → `test_pipeline_halt_blocks_everything`.
- 2. Low completeness demotes a buy candidate → `test_low_data_completeness_blocks_buy`.
- 3. Invalid allocation total blocks target-weight recs → `test_target_weights_are_valid_requires_total_near_one` + report tests.
- 4. Incompatible venue without proxy blocks → `test_incompatible_venue_without_proxy_blocks_execution`.
- 5. Avoid stays avoid when selected → `test_avoid_action_stays_avoid_even_when_selected`.
- 6. Zero memo traceability marks narrative-only → `test_zero_memo_traceability_marks_evidence_narrative_only`.
- 7. Complete healthy buy candidate → `test_complete_healthy_buy_candidate_can_be_actionable`.
- 8. Markdown verdict + blocking reasons → `test_markdown_report_starts_with_clear_verdict`.

**Spec coverage — Phase 2 completeness audit (design.md lines 138–164):**
- Per-instrument missing-field lists: Tasks 1, 2 (`missing_required_fields`, scoring output enrichment).
- Aggregate completeness by asset class: Task 1 (`summarize_completeness`).
- Fail/warn/pass status for scoring readiness: Task 6 (`scoring_data_completeness_avg` thresholds 0.90/0.75).
- Explicit eval failures when a buy candidate has incomplete data: Task 6 (`buy_candidate_min_completeness` with `fail_below=0.80`) **AND** Task 6 runner path/format fix so the metric actually fires on real outputs.
- Fill required fields from price/NAV history before adding new providers: Task 7 (`derive_risk_metrics`, deterministic, tested from local sample series).

**Spec coverage — acceptance criteria (design.md lines 221–230):**
- Blocked report on 2026-05-11 artifacts: Task 8 step 4.
- "No buy/sell decision is supported today" statement: Task 4 (`render_decision_markdown` verdict branch).
- Every blocked instrument has reason + next step: Task 3 (`_reason`, `_next_step`).
- Missing fields listed by instrument: Tasks 1, 2.
- Target-weight invalidity detected: Task 3 (`target_weights_are_valid`).
- Memo labeled narrative-only when coverage 0.0: Task 3 + new gate test.
- Unit tests cover hard gates and report composition without network: Tasks 1, 3, 4 (all use plain dicts).
- Existing pipeline commands continue to work: Task 8 step 3 (full pytest).

**Scope discipline:**
- No order sizing, portfolio deltas, broker APIs, or sell/trim logic (Phase 3 excluded).
- `inputs/account.yaml` documented as Phase 1 input but not yet consumed.
- `overall_status: "ok"` is the non-blocked counterpart of `"blocked"` (introduced here; spec only shows `"blocked"`).
- Tests are deterministic and network-free.
- The current 2026-05-11 output should produce a blocked report, not a buy/sell recommendation.

## Execution Options

Plan complete and saved to `docs/superpowers/plans/2026-05-11-decision-readiness.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task and review between tasks.

**2. Inline Execution** - Execute tasks in this session using execution checkpoints.

Choose one before implementation starts.
