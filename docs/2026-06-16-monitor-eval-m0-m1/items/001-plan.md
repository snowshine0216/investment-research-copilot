# M0 — eval spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the monitor eval spine — persist `eval_trace.json` per run, write the forward ledger, add the pure eval cores (types/structural/staleness/gate/forward_log/trace/panel) + `monitor_signal` artifact eval with shared-infra plumbing, and wire in-run structural health into the live run so structurally-unsound funds render `EVAL_GATED`.

**Architecture:** All eval *logic* is pure (frozen dataclasses, no I/O, no AkShare/LLM/settings imports per ADR 0017 §3.3). Effects live only at four edges: `append_ledger` (real append-mode JSONL), `latest_stage_report` (read), `atomic_write_text` (trace), and the `eval_cmd`/`monitor_cmd` orchestrators. M0 gates **only** on the always-fresh in-run `monitor_signal_health` (`GATING_STAGES_M0 = frozenset({"monitor_signal"})`); the LLM suites are `live_gated` placeholders that cannot gate yet (M1 flips them).

**Tech Stack:** Python 3.12, uv, pytest, ruff (line-length 100, py312), DuckDB/pandas elsewhere (not here). Mirrors the existing `evals/_shared/` + `evals/scoring/runner.py` pattern.

---

## Source-of-truth references

- Item spec (REFINED): `docs/2026-06-16-monitor-eval-m0-m1/items/001-spec.md` — AC #1–#32.
- Design spec: `docs/superpowers/specs/2026-06-16-monitor-eval-m0-m1-design.md` §2 (interfaces), §5 (errors), §6 (tests), §7 (pinned), §8 (file list).
- Roadmap: `docs/superpowers/specs/2026-06-16-monitor-eval-roadmap.md` §3.2b/d (ledger), §3.5 (gate), §3.6 (trace schema).
- Domain: `CONTEXT.md` "Monitor eval spine"; `docs/adr/0017-monitor-evidence-isolation.md`.

## Naming-collision guard (READ FIRST — AC #9, grill Q3)

There are **two** `GateDecision` types in this repo:

- `irc.spend.types.GateDecision` — the spend-preflight verdict (`blocked/warnings/ok`). PRE-EXISTING. Do not touch.
- `irc.monitor.eval.types.GateDecision` — the eval gate verdict (`fund_id/suppressed/failed_stages/badge/reason`). NEW, built here.

**Rule:** in any module that touches both, import the eval one by qualified path
(`from irc.monitor.eval import types as eval_types` → `eval_types.GateDecision`) and never bare-import
both `GateDecision` names into the same module. `monitor_cmd.py` already imports nothing from
`irc.spend.types`, so a bare `from irc.monitor.eval.types import GateDecision` is safe there.

## File structure (what each new file owns)

| File | Responsibility | Purity |
|---|---|---|
| `src/irc/monitor/eval/__init__.py` | package marker | — |
| `src/irc/monitor/eval/types.py` | `HealthStatus`, `Badge`, `StageHealth`, `GateDecision`, `FundTraceBundle` | pure |
| `src/irc/monitor/eval/structural.py` | `signal_consistency`/`citation_integrity`/`nav_quality`/`monitor_signal_health` over a trace-fund dict | pure |
| `src/irc/monitor/eval/staleness.py` | `resolve_health(StageReport\|None,...)` + `STALE_AFTER_DAYS` | pure |
| `src/irc/monitor/eval/gate.py` | `apply_eval_gate`, `published_state`, `GATING_STAGES_M0` | pure |
| `src/irc/monitor/eval/trace.py` | `build_eval_trace`, `dedup_by_citation_id` (trace serialization) | pure |
| `src/irc/monitor/eval/forward_log.py` | `ledger_row` (pure), `latest_per_key` (pure), `append_ledger` (EDGE) | mixed |
| `src/irc/monitor/eval/panel.py` | `validation_panel_html` Validation section | pure |
| `evals/_shared/latest_report.py` | `latest_stage_report` (EDGE read) | edge |
| `evals/monitor_signal/__init__.py` | package marker | — |
| `evals/monitor_signal/metrics.py` | `oracle_signal_match`/`citation_resolution`/`nav_completeness` over the trace dict | pure |
| `evals/monitor_signal/runner.py` | locate → metrics → StageReport → write_report | edge |

**Modified:** `evals/_shared/{status,missing_input,registry}.py`, `src/irc/spend/scope.py`,
`src/irc/commands/eval_cmd.py`, `src/irc/commands/monitor_cmd.py`, `src/irc/monitor/render_html.py`.

## Trace-fund dict shape (the projection all cores read)

`build_eval_trace` produces `trace["funds"][fund_id]` with these keys (roadmap §3.6). The pure cores
(`structural.py`, `metrics.py`) read THIS dict, never the dataclasses:

```python
{
  "resolved": {"analysis_profile", "weights", "bands", "minimum_confidence"},
  "nav": {"as_of_date", "latest_unit_nav", "nav_acc", "acc_series", "obs_count", "max_gap_days"},
  "evidence_pool": [{"source","title","date","url","owner_fund_id","citation_id"}, ...],
  "factor_scores": [{"name","value","eligible","reason","confidence"}, ...],
  "signal": {"status","bias","composite","signal_confidence","available_weight",
             "present_families","contributions":[{"name","renorm_weight","value","contribution","confidence"}],
             "divergence_codes"},
  "impacts": {"macro":[{"key","weight","impact","confidence","citation_ids"}], "constituent":[...]},
  "narrative": {"status","price_action":[{"claim","attribution_strength","citation_ids"}],
                "signal_rationale":[...], "risk":[...]},
  "gate": {"suppressed","failed_stages","reason"},
  "published_state": str,
  "validation_badge": str,
}
```

---

## Task 1: `eval/` package + types (AC #9)

**Files:**
- Create: `src/irc/monitor/eval/__init__.py`
- Create: `src/irc/monitor/eval/types.py`
- Test: `tests/monitor/eval/__init__.py`, `tests/monitor/eval/test_types.py`

- [ ] **Step 1: Create test package marker**

```bash
mkdir -p src/irc/monitor/eval tests/monitor/eval
printf '' > src/irc/monitor/eval/__init__.py
printf '' > tests/monitor/eval/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/monitor/eval/test_types.py`:

```python
from __future__ import annotations
import dataclasses
import pytest
from irc.monitor.eval.types import StageHealth, GateDecision, FundTraceBundle


def test_stage_health_is_frozen():
    h = StageHealth(stage="monitor_signal", status="PASS", reasons=())
    assert h.stage == "monitor_signal" and h.status == "PASS" and h.reasons == ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        h.status = "FAIL"  # type: ignore[misc]


def test_gate_decision_is_frozen_eval_shape():
    g = GateDecision(
        fund_id="008986", suppressed=True,
        failed_stages=("monitor_signal",), badge="gated", reason="nav_quality FAIL",
    )
    assert g.fund_id == "008986" and g.suppressed is True
    assert g.failed_stages == ("monitor_signal",) and g.badge == "gated"
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.suppressed = False  # type: ignore[misc]


def test_fund_trace_bundle_defaults_for_non_lookthrough():
    b = FundTraceBundle(
        fund_id="008986", macro_impacts=(), constituent_impacts=(), constituent_pool=(),
    )
    assert b.constituent_impacts == () and b.constituent_pool == ()


def test_eval_gate_decision_is_not_spend_gate_decision():
    from irc.spend.types import GateDecision as SpendGate
    assert GateDecision is not SpendGate
    assert {f.name for f in dataclasses.fields(GateDecision)} == {
        "fund_id", "suppressed", "failed_stages", "badge", "reason",
    }
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.eval.types'`.

- [ ] **Step 4: Write minimal implementation**

Create `src/irc/monitor/eval/types.py`:

```python
"""PURE eval types. ADR 0017 §3.3: no AkShare/provider/LLM/settings/filesystem imports.

NAMING GUARD: this GateDecision is DISTINCT from irc.spend.types.GateDecision
(the spend-preflight verdict). Import this one by qualified path in any module
that also touches irc.spend.types — never bare-import both.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from irc.monitor.impact_validate import ValidatedImpact
from irc.monitor.types import EvidenceItem

HealthStatus = Literal["PASS", "WARN", "FAIL", "UNKNOWN"]
Badge = Literal["validated", "caveated", "gated"]


@dataclass(frozen=True)
class StageHealth:
    stage: str
    status: HealthStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class GateDecision:
    fund_id: str
    suppressed: bool
    failed_stages: tuple[str, ...]
    badge: Badge
    reason: str


@dataclass(frozen=True)
class FundTraceBundle:
    """Un-aggregated per-fund eval inputs, kept off the render FundView.
    For non-lookthrough funds (gold/qdii) constituent_* are ()."""
    fund_id: str
    macro_impacts: tuple[ValidatedImpact, ...]
    constituent_impacts: tuple[ValidatedImpact, ...]
    constituent_pool: tuple[EvidenceItem, ...]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_types.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/eval/__init__.py src/irc/monitor/eval/types.py \
        tests/monitor/eval/__init__.py tests/monitor/eval/test_types.py
git commit -m "feat(monitor-eval): pure eval types (StageHealth, GateDecision, FundTraceBundle)"
```

---

## Task 2: `structural.py` — in-run health (AC #10, OQ2)

**Files:**
- Create: `src/irc/monitor/eval/structural.py`
- Test: `tests/monitor/eval/test_structural.py`

The cores read a trace-fund dict (shape above). A shared test fixture builds a minimal good fund.

- [ ] **Step 1: Write the failing test**

Create `tests/monitor/eval/test_structural.py`:

```python
from __future__ import annotations
from irc.monitor.eval.structural import (
    signal_consistency, citation_integrity, nav_quality, monitor_signal_health,
)


def _good_fund():
    return {
        "resolved": {"analysis_profile": "gold_etf", "weights": {"trend": 1.0},
                     "bands": {"buy": 0.1, "sell": -0.1}, "minimum_confidence": 0.5},
        "nav": {"as_of_date": "2026-06-16", "latest_unit_nav": 2.0, "nav_acc": 2.5,
                "acc_series": [["2026-06-15", 2.4], ["2026-06-16", 2.5]],
                "obs_count": 2, "max_gap_days": 1},
        "evidence_pool": [{"citation_id": "aaaa000000000000"}],
        "factor_scores": [{"name": "trend", "value": 0.3, "eligible": True, "reason": "", "confidence": 1.0}],
        "signal": {"status": "ok", "bias": "ADD_BIAS", "composite": 0.3, "signal_confidence": 1.0,
                   "available_weight": 1.0, "present_families": ["price-momentum"],
                   "contributions": [{"name": "trend", "renorm_weight": 1.0, "value": 0.3,
                                      "contribution": 0.3, "confidence": 1.0}],
                   "divergence_codes": []},
        "impacts": {"macro": [{"key": "gold", "citation_ids": ["aaaa000000000000"]}], "constituent": []},
        "narrative": {"status": "ok", "price_action": [{"claim": "x", "citation_ids": ["aaaa000000000000"]}],
                      "signal_rationale": [], "risk": []},
    }


def test_signal_consistency_pass_on_good_fund():
    assert signal_consistency(_good_fund()).status == "PASS"


def test_signal_consistency_fail_when_composite_diverges_from_contributions():
    t = _good_fund()
    t["signal"]["composite"] = 0.9   # != Σcontribution (0.3)
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_when_renorm_weights_not_unit():
    t = _good_fund()
    t["signal"]["contributions"][0]["renorm_weight"] = 0.5  # Σ != 1
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_when_bias_present_but_status_not_ok():
    t = _good_fund()
    t["signal"]["status"] = "low_confidence"   # bias must be None when status != ok
    assert signal_consistency(t).status == "FAIL"


def test_citation_integrity_pass_when_all_ids_resolve():
    assert citation_integrity(_good_fund()).status == "PASS"


def test_citation_integrity_fail_on_unresolved_narrative_id():
    t = _good_fund()
    t["narrative"]["price_action"][0]["citation_ids"] = ["dead000000000000"]
    assert citation_integrity(t).status == "FAIL"


def test_citation_integrity_resolves_constituent_against_unified_pool():
    t = _good_fund()
    t["evidence_pool"].append({"citation_id": "bbbb000000000000"})
    t["impacts"]["constituent"] = [{"key": "600519", "citation_ids": ["bbbb000000000000"]}]
    assert citation_integrity(t).status == "PASS"


def test_nav_quality_fail_when_obs_count_zero():
    t = _good_fund()
    t["nav"] = {"as_of_date": "N/A", "latest_unit_nav": 0.0, "nav_acc": None,
                "acc_series": [], "obs_count": 0, "max_gap_days": None}
    assert nav_quality(t, minimum_observations=2, stale_days=7).status == "FAIL"


def test_nav_quality_fail_when_below_minimum_observations():
    t = _good_fund()
    t["nav"]["obs_count"] = 1
    assert nav_quality(t, minimum_observations=2, stale_days=7).status == "FAIL"


def test_nav_quality_fail_when_as_of_older_than_stale_days():
    t = _good_fund()
    t["nav"]["as_of_date"] = "2000-01-01"
    assert nav_quality(t, minimum_observations=2, stale_days=7).status == "FAIL"


def test_nav_quality_warn_on_single_gap_over_five_days():
    t = _good_fund()
    t["nav"]["max_gap_days"] = 9
    t["nav"]["as_of_date"] = "2026-06-16"
    import datetime as _dt
    t["nav"]["as_of_date"] = _dt.date.today().isoformat()
    assert nav_quality(t, minimum_observations=2, stale_days=7).status == "WARN"


def test_nav_quality_does_not_compare_na_as_of():
    t = _good_fund()
    t["nav"]["as_of_date"] = "N/A"
    t["nav"]["obs_count"] = 0
    t["nav"]["nav_acc"] = None
    # FAIL comes from obs/nav_acc, NOT from a date-parse crash
    assert nav_quality(t, minimum_observations=2, stale_days=7).status == "FAIL"


def test_monitor_signal_health_worst_wins_and_stage_name():
    t = _good_fund()
    t["nav"]["obs_count"] = 0          # nav_quality FAIL
    t["nav"]["nav_acc"] = None
    h = monitor_signal_health(t, minimum_observations=2, stale_days=7)
    assert h.stage == "monitor_signal" and h.status == "FAIL"


def test_monitor_signal_health_pass_on_good_fund():
    import datetime as _dt
    t = _good_fund()
    t["nav"]["as_of_date"] = _dt.date.today().isoformat()
    assert monitor_signal_health(t, minimum_observations=2, stale_days=7).status == "PASS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_structural.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.eval.structural'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/eval/structural.py`:

```python
"""PURE per-fund in-run structural health over the eval_trace projection.
ADR 0017 §3.3: no I/O, no AkShare/LLM/settings imports."""
from __future__ import annotations
from datetime import date
from irc.monitor.eval.types import StageHealth
from evals._shared.status import worst_status

_EPS = 1e-9
_WARN_GAP_DAYS = 5


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def signal_consistency(t: dict) -> StageHealth:
    sig = t["signal"]
    contribs = sig.get("contributions", [])
    sum_contrib = sum(c.get("contribution", 0.0) for c in contribs)
    sum_renorm = sum(c.get("renorm_weight", 0.0) for c in contribs)
    reasons: list[str] = []
    if abs(sig.get("composite", 0.0) - sum_contrib) >= _EPS:
        reasons.append("composite != Σcontribution")
    if contribs and abs(sum_renorm - 1.0) >= _EPS:
        reasons.append("Σrenorm_weight != 1")
    bias_none = sig.get("bias") is None
    status_ok = sig.get("status") == "ok"
    if bias_none == status_ok:
        reasons.append("bias-None must hold iff status != ok")
    status = "FAIL" if reasons else "PASS"
    return StageHealth(stage="signal_consistency", status=status, reasons=tuple(reasons))


def _pool_ids(t: dict) -> set[str]:
    return {e.get("citation_id") for e in t.get("evidence_pool", [])}


def _claim_ids(t: dict) -> list[str]:
    narr = t.get("narrative", {})
    ids: list[str] = []
    for field in ("price_action", "signal_rationale", "risk"):
        for claim in narr.get(field, []):
            ids.extend(claim.get("citation_ids", ()))
    for leg in ("macro", "constituent"):
        for imp in t.get("impacts", {}).get(leg, []):
            ids.extend(imp.get("citation_ids", ()))
    return ids


def citation_integrity(t: dict) -> StageHealth:
    pool = _pool_ids(t)
    unresolved = [cid for cid in _claim_ids(t) if cid not in pool]
    if unresolved:
        return StageHealth("citation_integrity", "FAIL", (f"unresolved: {unresolved[0]}",))
    return StageHealth("citation_integrity", "PASS", ())


def nav_quality(t: dict, *, minimum_observations: int, stale_days: int) -> StageHealth:
    nav = t["nav"]
    obs = nav.get("obs_count", 0)
    as_of = nav.get("as_of_date", "N/A")
    if obs == 0 or nav.get("nav_acc") is None or as_of == "N/A":
        return StageHealth("nav_quality", "FAIL", ("missing NAV",))
    if obs < minimum_observations:
        return StageHealth("nav_quality", "FAIL", (f"obs<{minimum_observations}",))
    parsed = _parse_date(as_of)
    if parsed is not None and (date.today() - parsed).days > stale_days:
        return StageHealth("nav_quality", "FAIL", (f"as_of older than {stale_days}d",))
    gap = nav.get("max_gap_days")
    if gap is not None and gap > _WARN_GAP_DAYS:
        return StageHealth("nav_quality", "WARN", (f"gap {gap}d",))
    return StageHealth("nav_quality", "PASS", ())


def monitor_signal_health(t: dict, *, minimum_observations: int, stale_days: int) -> StageHealth:
    parts = (
        signal_consistency(t),
        citation_integrity(t),
        nav_quality(t, minimum_observations=minimum_observations, stale_days=stale_days),
    )
    overall = worst_status([p.status for p in parts])  # only PASS/WARN/FAIL here (no UNKNOWN)
    reasons = tuple(r for p in parts for r in p.reasons)
    return StageHealth(stage="monitor_signal", status=overall, reasons=reasons)
```

NOTE: `worst_status` ranks only PASS/WARN/FAIL — the three checks never return UNKNOWN, so this is
safe (AC #21).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_structural.py -v`
Expected: PASS (14 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/structural.py tests/monitor/eval/test_structural.py
git commit -m "feat(monitor-eval): pure structural in-run health checks"
```

---

## Task 3: `staleness.py` — resolve suite reports (AC #11, OQ3)

**Files:**
- Create: `src/irc/monitor/eval/staleness.py`
- Test: `tests/monitor/eval/test_staleness.py`

- [ ] **Step 1: Write the failing test**

Create `tests/monitor/eval/test_staleness.py`:

```python
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from evals._shared.report_schema import StageReport
from irc.monitor.eval.staleness import resolve_health, STALE_AFTER_DAYS

_TZ = timezone(timedelta(hours=8))
_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=_TZ)


def _report(overall: str, *, ran_at: datetime) -> StageReport:
    return StageReport(stage="monitor_impact", ran_at=ran_at.isoformat(),
                       based_on=[], metrics=[], overall=overall)


def test_stale_after_days_default_is_14():
    assert STALE_AFTER_DAYS == 14


def test_absent_report_is_unknown_absent():
    h = resolve_health(None, now=_NOW, stale_after_days=14)
    assert h.status == "UNKNOWN" and "absent" in h.reasons[0]


def test_skipped_report_is_unknown_skipped():
    h = resolve_health(_report("SKIPPED", ran_at=_NOW), now=_NOW, stale_after_days=14)
    assert h.status == "UNKNOWN" and "skipped" in h.reasons[0]


def test_stale_report_is_unknown_stale():
    old = _NOW - timedelta(days=20)
    h = resolve_health(_report("PASS", ran_at=old), now=_NOW, stale_after_days=14)
    assert h.status == "UNKNOWN" and "stale" in h.reasons[0]


def test_fresh_pass_passes_through():
    h = resolve_health(_report("PASS", ran_at=_NOW), now=_NOW, stale_after_days=14)
    assert h.status == "PASS"


def test_fresh_fail_passes_through():
    h = resolve_health(_report("FAIL", ran_at=_NOW), now=_NOW, stale_after_days=14)
    assert h.status == "FAIL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_staleness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.eval.staleness'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/eval/staleness.py`:

```python
"""PURE: latest suite StageReport → StageHealth for the gate (roadmap §3.5).
M0 unit-tests this but does NOT wire it into apply_eval_gate (OQ3) — M1 does."""
from __future__ import annotations
from datetime import datetime
from evals._shared.report_schema import StageReport
from irc.monitor.eval.types import StageHealth

STALE_AFTER_DAYS = 14


def resolve_health(
    report: StageReport | None, *, now: datetime, stale_after_days: int,
) -> StageHealth:
    if report is None:
        return StageHealth("monitor_suite", "UNKNOWN", ("absent",))
    if report.overall == "SKIPPED":
        return StageHealth(report.stage, "UNKNOWN", ("skipped",))
    ran_at = datetime.fromisoformat(report.ran_at)
    if (now - ran_at).days > stale_after_days:
        return StageHealth(report.stage, "UNKNOWN", ("stale",))
    return StageHealth(report.stage, report.overall, ())  # type: ignore[arg-type]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_staleness.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/staleness.py tests/monitor/eval/test_staleness.py
git commit -m "feat(monitor-eval): pure resolve_health staleness mapping"
```

---

## Task 4: `gate.py` — the gate (AC #13, #14, #15)

**Files:**
- Create: `src/irc/monitor/eval/gate.py`
- Test: `tests/monitor/eval/test_gate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/monitor/eval/test_gate.py`:

```python
from __future__ import annotations
from irc.monitor.eval.gate import apply_eval_gate, published_state, GATING_STAGES_M0
from irc.monitor.eval.types import StageHealth
from irc.monitor.types import SignalRecord


def _signal(status="ok", bias="ADD_BIAS"):
    return SignalRecord(fund_id="008986", status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0, present_families=(),
                        contributions=(), divergence_codes=())


def test_gating_stages_m0_is_monitor_signal_only():
    assert GATING_STAGES_M0 == frozenset({"monitor_signal"})


def test_fresh_fail_suppresses_and_badge_gated():
    h = (StageHealth("monitor_signal", "FAIL", ("nav_quality FAIL",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is True and g.badge == "gated"
    assert g.failed_stages == ("monitor_signal",)


def test_warn_is_caveated_not_suppressed():
    h = (StageHealth("monitor_signal", "WARN", ("gap",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is False and g.badge == "caveated"


def test_unknown_is_caveated():
    h = (StageHealth("monitor_signal", "UNKNOWN", ("stale",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is False and g.badge == "caveated"


def test_all_pass_is_validated():
    h = (StageHealth("monitor_signal", "PASS", ()),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is False and g.badge == "validated"


def test_non_gating_stage_is_ignored():
    h = (StageHealth("monitor_impact", "FAIL", ("x",)),)  # not in GATING_STAGES_M0
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is False and g.badge == "validated"


def test_published_state_no_call_when_status_not_ok():
    g = apply_eval_gate(_signal(status="low_confidence", bias=None),
                        health=(StageHealth("monitor_signal", "PASS", ()),),
                        gating_stages=GATING_STAGES_M0)
    assert published_state(_signal(status="low_confidence", bias=None), g) == "NO_CALL"


def test_published_state_no_call_precedence_over_eval_gated():
    # status != ok AND suppressed → NO_CALL wins (can't gate a call never made)
    h = (StageHealth("monitor_signal", "FAIL", ("x",)),)
    sig = _signal(status="insufficient_evidence", bias=None)
    g = apply_eval_gate(sig, health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is True
    assert published_state(sig, g) == "NO_CALL"


def test_published_state_eval_gated_when_suppressed():
    h = (StageHealth("monitor_signal", "FAIL", ("x",)),)
    sig = _signal()
    g = apply_eval_gate(sig, health=h, gating_stages=GATING_STAGES_M0)
    assert published_state(sig, g) == "EVAL_GATED"


def test_published_state_is_bias_when_validated():
    h = (StageHealth("monitor_signal", "PASS", ()),)
    sig = _signal(bias="REDUCE_BIAS")
    g = apply_eval_gate(sig, health=h, gating_stages=GATING_STAGES_M0)
    assert published_state(sig, g) == "REDUCE_BIAS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.eval.gate'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/eval/gate.py`:

```python
"""PURE eval gate (roadmap §3.5). M0 gating set = {monitor_signal} only."""
from __future__ import annotations
from irc.monitor.eval.types import GateDecision, StageHealth
from irc.monitor.types import SignalRecord

GATING_STAGES_M0 = frozenset({"monitor_signal"})


def apply_eval_gate(
    signal: SignalRecord, *, health: tuple[StageHealth, ...], gating_stages: frozenset[str],
) -> GateDecision:
    considered = [h for h in health if h.stage in gating_stages]
    failed = tuple(h.stage for h in considered if h.status == "FAIL")
    if failed:
        reason = "; ".join(r for h in considered if h.status == "FAIL" for r in h.reasons)
        return GateDecision(signal.fund_id, True, failed, "gated", reason or "fresh FAIL")
    if any(h.status in ("WARN", "UNKNOWN") for h in considered):
        return GateDecision(signal.fund_id, False, (), "caveated", "")
    return GateDecision(signal.fund_id, False, (), "validated", "")


def published_state(signal: SignalRecord, gate: GateDecision) -> str:
    if signal.status != "ok":
        return "NO_CALL"
    if gate.suppressed:
        return "EVAL_GATED"
    return signal.bias  # type: ignore[return-value]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_gate.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/gate.py tests/monitor/eval/test_gate.py
git commit -m "feat(monitor-eval): pure apply_eval_gate + published_state"
```

---

## Task 5: `forward_log.py` — ledger (AC #16, #17, #18)

**Files:**
- Create: `src/irc/monitor/eval/forward_log.py`
- Test: `tests/monitor/eval/test_forward_log.py`

- [ ] **Step 1: Write the failing test**

Create `tests/monitor/eval/test_forward_log.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
from irc.monitor.eval.forward_log import ledger_row, append_ledger, latest_per_key
from irc.monitor.eval.gate import apply_eval_gate, GATING_STAGES_M0
from irc.monitor.eval.types import StageHealth
from irc.monitor.types import SignalRecord


def _signal():
    return SignalRecord(fund_id="008986", status="ok", bias="ADD_BIAS", composite=0.3,
                        signal_confidence=0.9, available_weight=1.0, present_families=(),
                        contributions=(), divergence_codes=())


def _gate():
    return apply_eval_gate(_signal(), health=(StageHealth("monitor_signal", "PASS", ()),),
                           gating_stages=GATING_STAGES_M0)


def test_ledger_row_fields_and_nav_basis_literal():
    row = ledger_row(
        run_date="2026-06-16", fund_id="008986", written_at="2026-06-16T09:00:00+08:00",
        signal=_signal(), nav_acc=2.5, nav_unit=2.0, as_of_date="2026-06-16",
        published_state="ADD_BIAS", gate=_gate(), manifest_versions={"engine": "1"},
    )
    assert row["nav_basis"] == "coalesce(nav_acc,nav)"
    assert row["nav_acc"] == 2.5 and row["nav_unit"] == 2.0
    assert row["raw_status"] == "ok" and row["raw_bias"] == "ADD_BIAS"
    assert row["raw_composite"] == 0.3 and row["published_state"] == "ADD_BIAS"
    for k in ("run_date", "fund_id", "written_at", "signal_confidence",
              "gate_reason", "as_of_date", "manifest_versions"):
        assert k in row


def test_ledger_row_nav_acc_null_for_degraded():
    row = ledger_row(
        run_date="2026-06-16", fund_id="008986", written_at="t",
        signal=_signal(), nav_acc=None, nav_unit=0.0, as_of_date="N/A",
        published_state="EVAL_GATED", gate=_gate(), manifest_versions={"engine": "1"},
    )
    assert row["nav_acc"] is None


def test_append_ledger_is_real_append_not_overwrite(tmp_path: Path):
    p = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    append_ledger(p, [{"run_date": "2026-06-15", "fund_id": "a", "written_at": "1"}])
    append_ledger(p, [{"run_date": "2026-06-16", "fund_id": "b", "written_at": "2"}])
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["fund_id"] == "a"
    assert json.loads(lines[1])["fund_id"] == "b"


def test_append_ledger_swallows_write_failure(tmp_path: Path):
    # point at a path whose parent is a FILE → mkdir/open fails; must not raise
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad = blocker / "monitor" / "forward_ledger.jsonl"
    append_ledger(bad, [{"run_date": "x", "fund_id": "y", "written_at": "1"}])  # no exception


def test_latest_per_key_collapses_rerun_to_last_written_at():
    rows = [
        {"run_date": "2026-06-16", "fund_id": "a", "written_at": "2026-06-16T09:00:00", "v": 1},
        {"run_date": "2026-06-16", "fund_id": "a", "written_at": "2026-06-16T10:00:00", "v": 2},
        {"run_date": "2026-06-16", "fund_id": "b", "written_at": "2026-06-16T09:00:00", "v": 3},
    ]
    out = latest_per_key(rows)
    by_key = {(r["run_date"], r["fund_id"]): r["v"] for r in out}
    assert by_key[("2026-06-16", "a")] == 2  # later written_at wins
    assert by_key[("2026-06-16", "b")] == 3
    assert len(out) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_forward_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.eval.forward_log'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/eval/forward_log.py`:

```python
"""Forward ledger: pure ledger_row + latest_per_key; EDGE append_ledger.
Roadmap §3.2b (schema) / §3.2d (idempotency). Real append-mode JSONL — a single
line < PIPE_BUF is atomic on POSIX, so concurrent/rerun rows are never lost.
ADR 0017 §"Monitor-eval data contracts": deliberate deviation from temp+replace."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Iterable
from irc.monitor.eval.types import GateDecision
from irc.monitor.types import SignalRecord

_log = logging.getLogger(__name__)


def ledger_row(
    *, run_date: str, fund_id: str, written_at: str, signal: SignalRecord,
    nav_acc: float | None, nav_unit: float, as_of_date: str,
    published_state: str, gate: GateDecision, manifest_versions: dict,
) -> dict:
    """PURE: one forward-ledger row. nav_acc is COALESCE(nav_acc, nav) perf basis."""
    return {
        "run_date": run_date,
        "fund_id": fund_id,
        "written_at": written_at,
        "raw_status": signal.status,
        "raw_bias": signal.bias,
        "raw_composite": signal.composite,
        "signal_confidence": signal.signal_confidence,
        "published_state": published_state,
        "gate_reason": gate.reason,
        "nav_acc": nav_acc,
        "nav_unit": nav_unit,
        "nav_basis": "coalesce(nav_acc,nav)",
        "as_of_date": as_of_date,
        "manifest_versions": manifest_versions,
    }


def append_ledger(path: Path, rows: list[dict]) -> None:
    """EDGE: real append (open(path,"a")), one JSON object per line. Failures are
    logged and swallowed — never crash the brief."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("append_ledger failed for %s", path, exc_info=True)


def latest_per_key(rows: Iterable[dict]) -> list[dict]:
    """PURE: dedup by (run_date, fund_id) keeping max written_at (tie → last line)."""
    best: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["run_date"], row["fund_id"])
        cur = best.get(key)
        if cur is None or row["written_at"] >= cur["written_at"]:
            best[key] = row
    return list(best.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_forward_log.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/forward_log.py tests/monitor/eval/test_forward_log.py
git commit -m "feat(monitor-eval): forward ledger row/append/latest_per_key"
```

---

## Task 6: `trace.py` — eval_trace serialization (AC #1–#8, B/C, OQ2)

**Files:**
- Create: `src/irc/monitor/eval/trace.py`
- Test: `tests/monitor/eval/test_trace.py`

This serializes `(MonitorFund, FundView, GateDecision, FundTraceBundle)` tuples into the §3.6 dict,
including the unified evidence pool and degradation-safe NAV.

- [ ] **Step 1: Write the failing test**

Create `tests/monitor/eval/test_trace.py`:

```python
from __future__ import annotations
import json
from irc.monitor.eval.trace import build_eval_trace, dedup_by_citation_id
from irc.monitor.eval.gate import apply_eval_gate, published_state, GATING_STAGES_M0
from irc.monitor.eval.structural import monitor_signal_health
from irc.monitor.eval.types import FundTraceBundle, StageHealth
from irc.monitor.evidence import make_evidence_item
from irc.monitor.impact_validate import ValidatedImpact
from irc.monitor.render_types import FundView
from irc.monitor.types import (
    MonitorFund, SignalRecord, FactorScore, FactorContribution, NarrativeDoc, Claim,
)


def _fund(fid="008986", profile="gold_etf"):
    return MonitorFund(id=fid, name_cn="测试", market="CN", analysis_profile=profile,
                       themes=("gold",), constituent_news=False,
                       weights={"trend": 1.0}, bands={"buy": 0.1, "sell": -0.1},
                       minimum_confidence=0.5)


def _ev(fid, url):
    return make_evidence_item("Reuters", "t", "2026-06-16", url, owner_fund_id=fid)


def _signal(fid="008986", bias="ADD_BIAS"):
    return SignalRecord(fund_id=fid, status="ok", bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                        divergence_codes=())


def _good_view(fid="008986", ev=None):
    ev = ev or _ev(fid, "https://a")
    narr = NarrativeDoc(fid, (Claim("x", "consistent_with", (ev.citation_id,)),), (), (), "ok")
    return FundView(fund_id=fid, name_cn="测试", latest_nav=2.0, as_of_date="2026-06-16",
                    nav_series=(("2026-06-15", 2.4), ("2026-06-16", 2.5)), signal=_signal(fid),
                    narrative=narr, evidence_pool=(ev,), return_table={},
                    factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=(FactorScore("trend", 0.3, True, "", 1.0),))


def _degraded_view(fid="600000"):
    return FundView(fund_id=fid, name_cn="降级", latest_nav=0.0, as_of_date="N/A",
                    nav_series=(), signal=_signal(fid), narrative=NarrativeDoc(fid, (), (), (), "ok"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=())


def _bundle(fid="008986", macro=()):
    return FundTraceBundle(fund_id=fid, macro_impacts=macro, constituent_impacts=(), constituent_pool=())


def _gate(view):
    h = (monitor_signal_health(_project(view), minimum_observations=2, stale_days=7),)
    return apply_eval_gate(view.signal, health=h, gating_stages=GATING_STAGES_M0)


def _project(view):
    # helper mirroring build_eval_trace's per-fund dict (only fields monitor_signal_health needs)
    trace = build_eval_trace(((_fund(view.fund_id), view, _stub_gate(view), _bundle(view.fund_id)),),
                             engine_version="1", run_date="2026-06-16")
    return trace["funds"][view.fund_id]


def _stub_gate(view):
    from irc.monitor.eval.types import GateDecision
    return GateDecision(view.fund_id, False, (), "validated", "")


def test_top_level_keys():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    assert set(t) == {"schema_version", "engine_version", "run_date", "funds"}
    assert t["engine_version"] == "1" and t["run_date"] == "2026-06-16"
    assert "008986" in t["funds"]


def test_per_fund_schema_keys():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    f = t["funds"]["008986"]
    assert set(f) == {"resolved", "nav", "evidence_pool", "factor_scores", "signal",
                      "impacts", "narrative", "gate", "published_state", "validation_badge"}
    assert set(f["resolved"]) == {"analysis_profile", "weights", "bands", "minimum_confidence"}
    assert set(f["nav"]) == {"as_of_date", "latest_unit_nav", "nav_acc", "acc_series",
                             "obs_count", "max_gap_days"}


def test_round_trip_json_serializable():
    t = build_eval_trace(
        ((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),
         (_fund("600000", "qdii_proxy"), _degraded_view(), _stub_gate(_degraded_view()), _bundle("600000"))),
        engine_version="1", run_date="2026-06-16")
    reloaded = json.loads(json.dumps(t))
    assert reloaded == t


def test_degraded_nav_no_indexerror_and_nulls():
    t = build_eval_trace(((_fund("600000"), _degraded_view(), _stub_gate(_degraded_view()), _bundle("600000")),),
                         engine_version="1", run_date="2026-06-16")
    nav = t["funds"]["600000"]["nav"]
    assert nav["nav_acc"] is None and nav["obs_count"] == 0
    assert nav["max_gap_days"] is None and nav["latest_unit_nav"] == 0.0


def test_good_nav_fields_computed():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    nav = t["funds"]["008986"]["nav"]
    assert nav["nav_acc"] == 2.5 and nav["obs_count"] == 2
    assert nav["max_gap_days"] == 1


def test_dedup_by_citation_id_merges_overlap():
    ev1 = _ev("008986", "https://a")
    ev2 = _ev("008986", "https://a")   # same preimage → same id
    ev3 = _ev("008986", "https://b")
    out = dedup_by_citation_id((ev1, ev2, ev3))
    ids = [e["citation_id"] for e in out]
    assert len(ids) == len(set(ids)) == 2


def test_unified_pool_contains_macro_and_constituent_ids():
    macro_ev = _ev("008986", "https://macro")
    const_ev = _ev("008986", "https://const")
    view = _good_view("008986", ev=macro_ev)
    bundle = FundTraceBundle("008986", macro_impacts=(), constituent_impacts=(),
                             constituent_pool=(const_ev,))
    t = build_eval_trace(((_fund(), view, _stub_gate(view), bundle),),
                         engine_version="1", run_date="2026-06-16")
    pool_ids = {e["citation_id"] for e in t["funds"]["008986"]["evidence_pool"]}
    assert macro_ev.citation_id in pool_ids and const_ev.citation_id in pool_ids


def test_constituent_impact_citation_resolves_against_unified_pool():
    from irc.monitor.eval.structural import citation_integrity
    const_ev = _ev("008986", "https://const")
    view = _good_view("008986")
    const_imp = ValidatedImpact(key="600519", impact=0.5, confidence=0.8,
                                citation_ids=(const_ev.citation_id,))
    bundle = FundTraceBundle("008986", macro_impacts=(), constituent_impacts=(const_imp,),
                             constituent_pool=(const_ev,))
    t = build_eval_trace(((_fund(), view, _stub_gate(view), bundle),),
                         engine_version="1", run_date="2026-06-16")
    assert citation_integrity(t["funds"]["008986"]).status == "PASS"


def test_impacts_macro_and_constituent_serialized():
    macro_imp = ValidatedImpact("gold", 0.3, 0.9, ())
    const_imp = ValidatedImpact("600519", 0.5, 0.8, ())
    view = _good_view()
    bundle = FundTraceBundle("008986", macro_impacts=(macro_imp,),
                             constituent_impacts=(const_imp,), constituent_pool=())
    t = build_eval_trace(((_fund(), view, _stub_gate(view), bundle),),
                         engine_version="1", run_date="2026-06-16")
    imp = t["funds"]["008986"]["impacts"]
    assert imp["macro"][0]["key"] == "gold" and imp["constituent"][0]["key"] == "600519"


def test_gate_and_published_state_serialized():
    view = _good_view()
    g = _stub_gate(view)
    t = build_eval_trace(((_fund(), view, g, _bundle()),),
                         engine_version="1", run_date="2026-06-16")
    f = t["funds"]["008986"]
    assert f["gate"] == {"suppressed": False, "failed_stages": [], "reason": ""}
    assert f["validation_badge"] == "validated"
    # status==ok, not suppressed → published_state is the bias
    assert f["published_state"] == "ADD_BIAS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_trace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.eval.trace'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/eval/trace.py`:

```python
"""PURE eval_trace serialization (roadmap §3.6). Degradation-safe NAV (AC B);
unified macro ⊕ constituent evidence pool deduped by citation_id (AC C).
ADR 0017 §3.3: no I/O imports."""
from __future__ import annotations
from datetime import date
from irc.monitor.eval.gate import published_state
from irc.monitor.eval.types import FundTraceBundle, GateDecision
from irc.monitor.impact_validate import ValidatedImpact
from irc.monitor.render_types import FundView
from irc.monitor.types import EvidenceItem, MonitorFund

_SCHEMA_VERSION = "1"


def dedup_by_citation_id(items: tuple[EvidenceItem, ...]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for ev in items:
        if ev.citation_id in seen:
            continue
        seen.add(ev.citation_id)
        out.append({"source": ev.source, "title": ev.title, "date": ev.date,
                    "url": ev.url, "owner_fund_id": ev.owner_fund_id,
                    "citation_id": ev.citation_id})
    return out


def _parse(d: str) -> date | None:
    try:
        return date.fromisoformat(d)
    except (ValueError, TypeError):
        return None


def _max_gap_days(series: tuple[tuple[str, float], ...]) -> int | None:
    if len(series) < 2:
        return None
    deltas: list[int] = []
    for (d0, _), (d1, _) in zip(series, series[1:]):
        a, b = _parse(d0), _parse(d1)
        if a is not None and b is not None:
            deltas.append((b - a).days)
    return max(deltas) if deltas else None


def _nav(view: FundView) -> dict:
    series = view.nav_series
    nav_acc = series[-1][1] if series else None
    return {
        "as_of_date": view.as_of_date,
        "latest_unit_nav": view.latest_nav,
        "nav_acc": nav_acc,
        "acc_series": [list(pt) for pt in series],
        "obs_count": len(series),
        "max_gap_days": _max_gap_days(series),
    }


def _impact(imp: ValidatedImpact) -> dict:
    return {"key": imp.key, "weight": 1.0, "impact": imp.impact,
            "confidence": imp.confidence, "citation_ids": list(imp.citation_ids)}


def _impacts(bundle: FundTraceBundle) -> dict:
    return {"macro": [_impact(i) for i in bundle.macro_impacts],
            "constituent": [_impact(i) for i in bundle.constituent_impacts]}


def _signal(sig) -> dict:
    return {
        "status": sig.status, "bias": sig.bias, "composite": sig.composite,
        "signal_confidence": sig.signal_confidence, "available_weight": sig.available_weight,
        "present_families": list(sig.present_families),
        "contributions": [{"name": c.name, "renorm_weight": c.renorm_weight, "value": c.value,
                           "contribution": c.contribution, "confidence": c.confidence}
                          for c in sig.contributions],
        "divergence_codes": list(sig.divergence_codes),
    }


def _claims(claims) -> list[dict]:
    return [{"claim": c.claim, "attribution_strength": c.attribution_strength,
             "citation_ids": list(c.citation_ids)} for c in claims]


def _narrative(narr) -> dict:
    return {"status": narr.status,
            "price_action": _claims(narr.price_action_commentary),
            "signal_rationale": _claims(narr.signal_rationale_commentary),
            "risk": _claims(narr.risk_commentary)}


def _fund_entry(fund: MonitorFund, view: FundView, gate: GateDecision,
                bundle: FundTraceBundle) -> dict:
    return {
        "resolved": {"analysis_profile": fund.analysis_profile, "weights": dict(fund.weights),
                     "bands": dict(fund.bands), "minimum_confidence": fund.minimum_confidence},
        "nav": _nav(view),
        "evidence_pool": dedup_by_citation_id(view.evidence_pool + bundle.constituent_pool),
        "factor_scores": [{"name": s.name, "value": s.value, "eligible": s.eligible,
                           "reason": s.reason, "confidence": s.confidence}
                          for s in view.factor_scores],
        "signal": _signal(view.signal),
        "impacts": _impacts(bundle),
        "narrative": _narrative(view.narrative),
        "gate": {"suppressed": gate.suppressed, "failed_stages": list(gate.failed_stages),
                 "reason": gate.reason},
        "published_state": published_state(view.signal, gate),
        "validation_badge": gate.badge,
    }


def build_eval_trace(
    items: tuple[tuple[MonitorFund, FundView, GateDecision, FundTraceBundle], ...],
    *, engine_version: str, run_date: str,
) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "engine_version": engine_version,
        "run_date": run_date,
        "funds": {fund.id: _fund_entry(fund, view, gate, bundle)
                  for fund, view, gate, bundle in items},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_trace.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/trace.py tests/monitor/eval/test_trace.py
git commit -m "feat(monitor-eval): pure build_eval_trace serialization (unified pool, degradation-safe NAV)"
```

---

## Task 7: `panel.py` — Validation panel (AC #30 panel bullet)

**Files:**
- Create: `src/irc/monitor/eval/panel.py`
- Test: `tests/monitor/eval/test_panel.py`

- [ ] **Step 1: Write the failing test**

Create `tests/monitor/eval/test_panel.py`:

```python
from __future__ import annotations
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import StageHealth


def test_panel_renders_monitor_signal_row_with_counts():
    health = StageHealth("monitor_signal", "PASS", ())
    badges = ("validated", "validated", "gated", "caveated")
    html = validation_panel_html(stage_health=health, ran_at="2026-06-16T09:00:00+08:00",
                                 badge_counts={"validated": 2, "caveated": 1, "gated": 1})
    assert "Validation" in html
    assert "monitor_signal" in html
    assert "2026-06-16T09:00:00+08:00" in html
    assert "PASS" in html
    assert "validated: 2" in html and "gated: 1" in html and "caveated: 1" in html


def test_panel_is_pure_string():
    html = validation_panel_html(stage_health=StageHealth("monitor_signal", "FAIL", ("nav",)),
                                 ran_at="t", badge_counts={"gated": 7})
    assert isinstance(html, str) and html.startswith("<section")
    assert "FAIL" in html and "gated: 7" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.eval.panel'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/eval/panel.py`:

```python
"""PURE Validation panel HTML. M0: one row (monitor_signal). No I/O."""
from __future__ import annotations
from html import escape
from irc.monitor.eval.types import StageHealth

_BADGE_ORDER = ("validated", "caveated", "gated")


def _counts_str(badge_counts: dict[str, int]) -> str:
    parts = [f"{b}: {badge_counts[b]}" for b in _BADGE_ORDER if b in badge_counts]
    return ", ".join(parts)


def validation_panel_html(
    *, stage_health: StageHealth, ran_at: str, badge_counts: dict[str, int],
) -> str:
    reasons = "; ".join(stage_health.reasons)
    return (
        '<section class="validation-panel"><h2>Validation</h2>'
        '<table class="validation"><tr><th>stage</th><th>overall</th>'
        '<th>ran_at</th><th>badges</th></tr>'
        f"<tr><td>{escape(stage_health.stage)}</td>"
        f"<td>{escape(stage_health.status)}</td>"
        f"<td>{escape(ran_at)}</td>"
        f"<td>{escape(_counts_str(badge_counts))}</td></tr></table>"
        f'<p class="muted">{escape(reasons)}</p></section>'
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_panel.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/panel.py tests/monitor/eval/test_panel.py
git commit -m "feat(monitor-eval): pure Validation panel renderer"
```

---

## Task 8: shared-infra — `status.py` SKIPPED (AC #21)

**Files:**
- Modify: `evals/_shared/status.py`
- Test: `tests/evals/test_status.py` (extend)

- [ ] **Step 1: Write the failing test (append to existing file)**

Append to `tests/evals/test_status.py`:

```python
def test_status_literal_includes_skipped():
    import typing
    from evals._shared.status import Status
    assert "SKIPPED" in typing.get_args(Status)


def test_worst_status_unchanged_ranks_only_pass_warn_fail():
    # worst_status must NOT be passed SKIPPED; it ranks only PASS/WARN/FAIL.
    assert worst_status(["PASS", "FAIL"]) == "FAIL"
    assert worst_status(["PASS", "WARN"]) == "WARN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_status.py::test_status_literal_includes_skipped -v`
Expected: FAIL — `"SKIPPED"` not in `Status` args.

- [ ] **Step 3: Modify implementation**

In `evals/_shared/status.py`, change line 5:

```python
Status = Literal["PASS", "WARN", "FAIL", "SKIPPED"]
```

Leave `_RANK` and `worst_status` unchanged (SKIPPED is never ranked — it is a whole-stage `overall`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_status.py -v`
Expected: PASS (all, including the 2 new).

- [ ] **Step 5: Commit**

```bash
git add evals/_shared/status.py tests/evals/test_status.py
git commit -m "feat(eval-shared): add SKIPPED to Status literal (worst_status unchanged)"
```

---

## Task 9: shared-infra — `missing_input.py` EVAL_RC_SKIPPED + skipped_report (AC #22)

**Files:**
- Modify: `evals/_shared/missing_input.py`
- Test: `tests/evals/test_missing_input_helper.py` (extend)

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/evals/test_missing_input_helper.py`:

```python
def test_eval_rc_skipped_is_3():
    from evals._shared.missing_input import EVAL_RC_SKIPPED
    assert EVAL_RC_SKIPPED == 3


def test_skipped_report_has_overall_skipped():
    from evals._shared.missing_input import skipped_report
    r = skipped_report("monitor_impact", "env absent; not executed")
    assert r.stage == "monitor_impact"
    assert r.overall == "SKIPPED"
    assert "env absent" in r.notes
    assert r.metrics == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_missing_input_helper.py::test_eval_rc_skipped_is_3 -v`
Expected: FAIL — `ImportError: cannot import name 'EVAL_RC_SKIPPED'`.

- [ ] **Step 3: Modify implementation**

In `evals/_shared/missing_input.py`, after the `EVAL_RC_FAIL = 2` line (line 22) add:

```python
EVAL_RC_SKIPPED = 3
```

And add this function after `missing_input_report` (before `write_missing_input_report`):

```python
def skipped_report(stage: str, reason: str) -> StageReport:
    """Build a SKIPPED StageReport (live_gated stage not executed; env absent)."""
    return StageReport(
        stage=stage,
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[],
        metrics=[],
        overall="SKIPPED",
        notes=reason,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_missing_input_helper.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/_shared/missing_input.py tests/evals/test_missing_input_helper.py
git commit -m "feat(eval-shared): EVAL_RC_SKIPPED=3 + skipped_report"
```

---

## Task 10: shared-infra — `registry.py` live_gated + placeholders (AC #23, OQ5)

**Files:**
- Modify: `evals/_shared/registry.py`
- Test: `tests/evals/test_registry.py` (extend)

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/evals/test_registry.py`:

```python
def test_live_gated_is_a_lifecycle_value() -> None:
    import typing
    from evals._shared.registry import Lifecycle
    assert "live_gated" in typing.get_args(Lifecycle)


def test_monitor_signal_registered_active_in_all_suite() -> None:
    spec = REGISTRY["monitor_signal"]
    assert spec.lifecycle == "active"
    assert spec.in_all_suite is True
    assert spec.runner_module == "evals.monitor_signal.runner"
    assert "monitor_signal" in active_suite_stages()


def test_monitor_llm_suites_are_live_gated_placeholders() -> None:
    from evals._shared.registry import is_live_gated
    for stage in ("monitor_impact", "monitor_narrative"):
        spec = REGISTRY[stage]
        assert spec.lifecycle == "live_gated"
        assert spec.in_all_suite is False
        assert is_live_gated(spec) is True
        assert stage not in active_suite_stages()


def test_is_live_gated_false_for_active() -> None:
    from evals._shared.registry import is_live_gated
    assert is_live_gated(REGISTRY["monitor_signal"]) is False


def test_live_gated_placeholder_importability_not_required() -> None:
    # The placeholder runner module need not import in M0 — only the path string matters.
    spec = REGISTRY["monitor_impact"]
    assert spec.runner_module == "evals.monitor_impact.runner"  # string, lazily resolved
```

NOTE: the existing `test_all_thirteen_known_stages_present` and
`test_runner_module_path_is_dotted_evals_path` will now also need the three new stages. Update them
in this step too (see Step 3).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_registry.py -v`
Expected: FAIL — new tests fail (KeyError `monitor_signal` / `live_gated` not in Lifecycle) AND the
two existing count/path tests fail once stages are added (run after Step 3 to confirm).

- [ ] **Step 3: Modify implementation**

In `evals/_shared/registry.py`:

(a) Extend the `Lifecycle` literal (line 26-31):

```python
Lifecycle = Literal[
    "active",
    "inactive_legacy",
    "inactive_uninstrumented",
    "unimplemented_active",
    "live_gated",
]
```

(b) Add three rows to `_SPECS` (after the `queries` row, line 55):

```python
    EvalStageSpec("monitor_signal",    "evals.monitor_signal.runner",    "active", True),
    EvalStageSpec("monitor_impact",    "evals.monitor_impact.runner",    "live_gated", False),
    EvalStageSpec("monitor_narrative", "evals.monitor_narrative.runner", "live_gated", False),
```

(c) Add helper after `is_inactive` (end of file):

```python
def is_live_gated(spec: EvalStageSpec) -> bool:
    return spec.lifecycle == "live_gated"
```

(d) Fix the two existing registry tests in `tests/evals/test_registry.py`:

In `test_all_thirteen_known_stages_present`, rename it and update the expected set + add the three
stages:

```python
def test_all_known_stages_present() -> None:
    expected = {
        "data", "research", "discovery", "scoring", "gold_score",
        "allocation", "trade_plan", "memo", "architecture", "opportunity",
        "triggers", "news", "queries",
        "monitor_signal", "monitor_impact", "monitor_narrative",
    }
    assert set(REGISTRY) == expected
```

The `test_runner_module_path_is_dotted_evals_path` test already asserts
`spec.runner_module == f"evals.{stage}.runner"` for every stage — the new rows satisfy it, no change.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_registry.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add evals/_shared/registry.py tests/evals/test_registry.py
git commit -m "feat(eval-shared): live_gated lifecycle + monitor_signal/impact/narrative specs"
```

---

## Task 11: shared-infra — `latest_report.py` (AC #12, #24)

**Files:**
- Create: `evals/_shared/latest_report.py`
- Test: `tests/evals/test_latest_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/evals/test_latest_report.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from evals._shared.latest_report import latest_stage_report
from evals._shared.report_schema import StageReport, report_to_dict
from irc.monitor.eval.staleness import resolve_health

_TZ = timezone(timedelta(hours=8))


def _write(root: Path, stage: str, date_str: str, overall: str = "PASS") -> None:
    d = root / "outputs" / date_str / "evals" / stage
    d.mkdir(parents=True)
    rep = StageReport(stage=stage, ran_at=f"{date_str}T09:00:00+08:00",
                      based_on=[], metrics=[], overall=overall)
    (d / "report.json").write_text(json.dumps(report_to_dict(rep)), encoding="utf-8")


def test_absent_returns_none(tmp_path: Path):
    assert latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16") is None


def test_multiple_dates_returns_newest(tmp_path: Path):
    _write(tmp_path, "monitor_impact", "2026-06-10", overall="FAIL")
    _write(tmp_path, "monitor_impact", "2026-06-14", overall="PASS")
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    assert rep is not None and rep.ran_at.startswith("2026-06-14")
    assert rep.overall == "PASS"


def test_ignores_dates_after_today(tmp_path: Path):
    _write(tmp_path, "monitor_impact", "2026-06-14", overall="PASS")
    _write(tmp_path, "monitor_impact", "2026-06-20", overall="FAIL")  # future
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    assert rep is not None and rep.ran_at.startswith("2026-06-14")


def test_today_present_returns_today(tmp_path: Path):
    _write(tmp_path, "monitor_impact", "2026-06-16", overall="WARN")
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    assert rep is not None and rep.overall == "WARN"


def test_skipped_today_resolves_to_unknown(tmp_path: Path):
    _write(tmp_path, "monitor_impact", "2026-06-16", overall="SKIPPED")
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    now = datetime(2026, 6, 16, 12, tzinfo=_TZ)
    h = resolve_health(rep, now=now, stale_after_days=14)
    assert h.status == "UNKNOWN" and "skipped" in h.reasons[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_latest_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals._shared.latest_report'`.

- [ ] **Step 3: Write minimal implementation**

Create `evals/_shared/latest_report.py`:

```python
"""EDGE read: newest StageReport for a stage, China-date max <= today.
There is no 'newest report for a stage' API in locator.py (artifact-set oriented),
so this adds one (roadmap §2.4)."""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from evals._shared.report_schema import MetricReport, StageReport

_TZ = timezone(timedelta(hours=8))
_DATE_LEN = 10


def _today_iso() -> str:
    return datetime.now(_TZ).date().isoformat()


def _is_date_dir(name: str) -> bool:
    if len(name) != _DATE_LEN:
        return False
    try:
        date.fromisoformat(name)
        return True
    except ValueError:
        return False


def _parse_report(path: Path) -> StageReport:
    raw = json.loads(path.read_text(encoding="utf-8"))
    metrics = [MetricReport(**m) for m in raw.get("metrics", [])]
    return StageReport(
        stage=raw["stage"], ran_at=raw["ran_at"], based_on=raw.get("based_on", []),
        metrics=metrics, overall=raw["overall"], notes=raw.get("notes", ""),
        config_versions=raw.get("config_versions", {}),
    )


def latest_stage_report(
    repo_root: Path, stage: str, *, today_iso: str | None = None,
) -> StageReport | None:
    outputs = repo_root / "outputs"
    if not outputs.is_dir():
        return None
    today = today_iso if today_iso is not None else _today_iso()
    dates = sorted(
        (d.name for d in outputs.iterdir()
         if d.is_dir() and _is_date_dir(d.name) and d.name <= today),
        reverse=True,
    )
    for d in dates:
        report_path = outputs / d / "evals" / stage / "report.json"
        if report_path.is_file():
            return _parse_report(report_path)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_latest_report.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/_shared/latest_report.py tests/evals/test_latest_report.py
git commit -m "feat(eval-shared): latest_stage_report China-date lookup"
```

---

## Task 12: `evals/monitor_signal/metrics.py` (AC #19, OQ1)

**Files:**
- Create: `evals/monitor_signal/__init__.py`
- Create: `evals/monitor_signal/metrics.py`
- Test: `tests/evals/test_monitor_signal_metrics.py`

- [ ] **Step 1: Create package marker**

```bash
mkdir -p evals/monitor_signal
printf '' > evals/monitor_signal/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/evals/test_monitor_signal_metrics.py`:

> **Oracle fixture note (verified against `compute_signal`):** a single eligible `trend` factor
> yields `status="insufficient_evidence"`, `bias=None`, `composite=0.3`, `signal_confidence=1.0`
> (needs ≥2 families + trend present + Σw≥0.60 for `status="ok"`). The faithful fixture MUST store
> exactly these recomputed values so `oracle_signal_match == 1.0`.

```python
from __future__ import annotations
from evals.monitor_signal.metrics import (
    oracle_signal_match, citation_resolution, nav_completeness,
)


def _fund(*, composite=0.3, status="insufficient_evidence", bias=None, obs=2,
          pool_ids=("aaaa000000000000",), claim_ids=("aaaa000000000000",)):
    return {
        "resolved": {"analysis_profile": "gold_etf", "weights": {"trend": 1.0},
                     "bands": {"buy": 0.1, "sell": -0.1}, "minimum_confidence": 0.5},
        "nav": {"obs_count": obs},
        "evidence_pool": [{"citation_id": c} for c in pool_ids],
        "factor_scores": [{"name": "trend", "value": 0.3, "eligible": True,
                           "reason": "", "confidence": 1.0}],
        "signal": {"status": status, "bias": bias, "composite": composite,
                   "signal_confidence": 1.0, "available_weight": 1.0,
                   "present_families": ["price-momentum"],
                   "contributions": [{"name": "trend", "renorm_weight": 1.0, "value": 0.3,
                                      "contribution": 0.3, "confidence": 1.0}],
                   "divergence_codes": []},
        "impacts": {"macro": [], "constituent": []},
        "narrative": {"status": "ok",
                      "price_action": [{"claim": "x", "citation_ids": list(claim_ids)}],
                      "signal_rationale": [], "risk": []},
    }


def _trace(funds):
    return {"schema_version": "1", "engine_version": "1", "run_date": "2026-06-16",
            "funds": funds}


def test_oracle_match_is_one_when_signal_faithful():
    # composite=0.3 with one trend factor of value 0.3 weight 1.0 → compute_signal reproduces it
    assert oracle_signal_match(_trace({"a": _fund()})) == 1.0


def test_oracle_match_below_one_when_composite_tampered():
    bad = _fund(composite=0.99)  # persisted composite no longer == recomputed
    assert oracle_signal_match(_trace({"a": bad})) < 1.0


def test_citation_resolution_one_when_all_resolve():
    assert citation_resolution(_trace({"a": _fund()})) == 1.0


def test_citation_resolution_below_one_on_dangling():
    bad = _fund(claim_ids=("dead000000000000",))
    assert citation_resolution(_trace({"a": bad})) < 1.0


def test_nav_completeness_fraction():
    funds = {"a": _fund(obs=2), "b": _fund(obs=0)}
    # minimum_observations default 2 → 1 of 2 complete
    assert nav_completeness(_trace(funds), minimum_observations=2) == 0.5
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_monitor_signal_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.monitor_signal.metrics'`.

- [ ] **Step 4: Write minimal implementation**

Create `evals/monitor_signal/metrics.py`:

```python
"""PURE metrics over the eval_trace.json projection (roadmap §2.7).
oracle_signal_match re-runs compute_signal from resolved + factor_scores (OQ1):
compute_signal reads ONLY fund.{id, weights, bands, minimum_confidence}."""
from __future__ import annotations
from irc.monitor.signal import compute_signal
from irc.monitor.types import FactorScore, MonitorFund


def _rebuild_fund(fund_id: str, resolved: dict) -> MonitorFund:
    return MonitorFund(
        id=fund_id, name_cn="", market="", analysis_profile=resolved["analysis_profile"],
        themes=(), constituent_news=False, weights=dict(resolved["weights"]),
        bands=dict(resolved["bands"]), minimum_confidence=resolved["minimum_confidence"],
    )


def _scores(factor_scores: list[dict]) -> tuple[FactorScore, ...]:
    return tuple(
        FactorScore(name=s["name"], value=s["value"], eligible=s["eligible"],
                    reason=s["reason"], confidence=s.get("confidence", 1.0))
        for s in factor_scores
    )


def _frac(numer: int, denom: int) -> float:
    return numer / denom if denom else 1.0


def oracle_signal_match(trace: dict) -> float:
    funds = trace.get("funds", {})
    if not funds:
        return 1.0
    matched = 0
    for fund_id, f in funds.items():
        rec = compute_signal(_rebuild_fund(fund_id, f["resolved"]), _scores(f["factor_scores"]))
        sig = f["signal"]
        if (rec.status == sig["status"] and rec.bias == sig["bias"]
                and rec.composite == sig["composite"]
                and rec.signal_confidence == sig["signal_confidence"]):
            matched += 1
    return _frac(matched, len(funds))


def _claim_ids(f: dict) -> list[str]:
    ids: list[str] = []
    narr = f.get("narrative", {})
    for field in ("price_action", "signal_rationale", "risk"):
        for claim in narr.get(field, []):
            ids.extend(claim.get("citation_ids", ()))
    for leg in ("macro", "constituent"):
        for imp in f.get("impacts", {}).get(leg, []):
            ids.extend(imp.get("citation_ids", ()))
    return ids


def citation_resolution(trace: dict) -> float:
    total = resolved = 0
    for f in trace.get("funds", {}).values():
        pool = {e["citation_id"] for e in f.get("evidence_pool", [])}
        for cid in _claim_ids(f):
            total += 1
            if cid in pool:
                resolved += 1
    return _frac(resolved, total)


def nav_completeness(trace: dict, *, minimum_observations: int = 2) -> float:
    funds = trace.get("funds", {})
    if not funds:
        return 1.0
    complete = sum(1 for f in funds.values()
                   if f["nav"].get("obs_count", 0) >= minimum_observations)
    return _frac(complete, len(funds))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_monitor_signal_metrics.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add evals/monitor_signal/__init__.py evals/monitor_signal/metrics.py \
        tests/evals/test_monitor_signal_metrics.py
git commit -m "feat(monitor-signal-eval): pure oracle/citation/nav metrics"
```

---

## Task 13: `evals/monitor_signal/runner.py` (AC #20)

**Files:**
- Create: `evals/monitor_signal/runner.py`
- Test: `tests/evals/test_monitor_signal_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/evals/test_monitor_signal_runner.py`:

```python
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from evals.monitor_signal.runner import run


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _good_fund(composite=0.3):
    return {
        "resolved": {"analysis_profile": "gold_etf", "weights": {"trend": 1.0},
                     "bands": {"buy": 0.1, "sell": -0.1}, "minimum_confidence": 0.5},
        "nav": {"obs_count": 2},
        "evidence_pool": [{"citation_id": "aaaa000000000000"}],
        "factor_scores": [{"name": "trend", "value": 0.3, "eligible": True,
                           "reason": "", "confidence": 1.0}],
        "signal": {"status": "insufficient_evidence", "bias": None, "composite": composite,
                   "signal_confidence": 1.0, "available_weight": 1.0,
                   "present_families": ["price-momentum"],
                   "contributions": [{"name": "trend", "renorm_weight": 1.0, "value": 0.3,
                                      "contribution": 0.3, "confidence": 1.0}],
                   "divergence_codes": []},
        "impacts": {"macro": [], "constituent": []},
        "narrative": {"status": "ok",
                      "price_action": [{"claim": "x", "citation_ids": ["aaaa000000000000"]}],
                      "signal_rationale": [], "risk": []},
    }


def _write_trace(root: Path, funds: dict, date_str: str | None = None) -> None:
    date_str = date_str or _today()
    d = root / "outputs" / date_str / "monitor"
    d.mkdir(parents=True)
    trace = {"schema_version": "1", "engine_version": "1", "run_date": date_str, "funds": funds}
    (d / "eval_trace.json").write_text(json.dumps(trace), encoding="utf-8")


def test_runner_pass_on_good_trace(tmp_path: Path):
    _write_trace(tmp_path, {"a": _good_fund()})
    rc = run(tmp_path)
    report = json.loads(
        (tmp_path / "outputs" / _today() / "evals" / "monitor_signal" / "report.json")
        .read_text(encoding="utf-8"))
    names = {m["name"] for m in report["metrics"]}
    assert {"oracle_signal_match", "citation_resolution", "nav_completeness"} <= names
    assert rc == 0 and report["overall"] == "PASS"


def test_runner_fail_on_tampered_composite(tmp_path: Path):
    # compute_signal would reproduce a value != 0.99 → oracle_signal_match < 1.0 → FAIL
    _write_trace(tmp_path, {"a": _good_fund(composite=0.99)})
    rc = run(tmp_path)
    assert rc == 2
    report = json.loads(
        (tmp_path / "outputs" / _today() / "evals" / "monitor_signal" / "report.json")
        .read_text(encoding="utf-8"))
    oracle = next(m for m in report["metrics"] if m["name"] == "oracle_signal_match")
    assert oracle["status"] == "FAIL"


def test_runner_fail_when_input_missing(tmp_path: Path):
    (tmp_path / "outputs").mkdir(parents=True)
    rc = run(tmp_path)
    assert rc == 2
    candidates = list(tmp_path.rglob("evals/monitor_signal/report.json"))
    assert candidates
    assert json.loads(candidates[0].read_text(encoding="utf-8"))["overall"] == "FAIL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_monitor_signal_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.monitor_signal.runner'`.

- [ ] **Step 3: Write minimal implementation**

Create `evals/monitor_signal/runner.py`:

```python
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from evals._shared.locator import locate
from evals._shared.missing_input import (
    EVAL_RC_FAIL, EVAL_RC_PASS, EVAL_RC_WARN,
    missing_input_report, write_missing_input_report,
)
from evals._shared.report_paths import write_report
from evals._shared.report_schema import MetricReport, StageReport
from evals._shared.status import classify_status, worst_status
from evals.monitor_signal.metrics import (
    citation_resolution, nav_completeness, oracle_signal_match,
)

_TZ = timezone(timedelta(hours=8))
_ORACLE_TH = {"fail_below": 1.0}
_CITATION_TH = {"fail_below": 1.0}
_NAV_TH = {"warn_below": 0.85, "fail_below": 0.6}


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("monitor/eval_trace.json",))
    if located is None:
        report = missing_input_report(
            stage="monitor_signal",
            reason="outputs/<date>/monitor/eval_trace.json missing — monitor did not run",
            based_on_path="outputs/<date>/monitor/eval_trace.json (or latest)",
        )
        write_missing_input_report(repo_root, report)
        print("monitor_signal eval: FAIL (no input file)")
        return EVAL_RC_FAIL

    source = located.paths[0]
    trace = json.loads(source.read_text(encoding="utf-8"))
    n = len(trace.get("funds", {}))

    oracle = oracle_signal_match(trace)
    citation = citation_resolution(trace)
    nav = nav_completeness(trace)
    metrics = [
        MetricReport("oracle_signal_match", oracle,
                     classify_status(oracle, _ORACLE_TH, "higher_is_better"), n, _ORACLE_TH),
        MetricReport("citation_resolution", citation,
                     classify_status(citation, _CITATION_TH, "higher_is_better"), n, _CITATION_TH),
        MetricReport("nav_completeness", nav,
                     classify_status(nav, _NAV_TH, "higher_is_better"), n, _NAV_TH),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="monitor_signal", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(source)], metrics=metrics, overall=overall,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"monitor_signal eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (
        EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_monitor_signal_runner.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/monitor_signal/runner.py tests/evals/test_monitor_signal_runner.py
git commit -m "feat(monitor-signal-eval): artifact-eval runner"
```

---

## Task 14: `scope.py` — eval-live scope (AC #26)

**Files:**
- Modify: `src/irc/spend/scope.py`
- Test: `tests/spend/test_scope.py` (extend)

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/spend/test_scope.py`:

```python
def test_eval_live_scope_is_both_monitor_tasks_no_search():
    scope = resolve_scope("eval-live")
    assert scope.tasks == frozenset({"monitor_impact", "monitor_narrative"})
    assert scope.search_providers == frozenset()
```

`test_every_llm_yaml_task_is_mapped_somewhere` must still pass (both tasks already in
`ALL_LLM_TASKS` via the `monitor` command).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/spend/test_scope.py::test_eval_live_scope_is_both_monitor_tasks_no_search -v`
Expected: FAIL — `eval-live` not in `COMMAND_TASKS`, so `tasks == frozenset()`.

- [ ] **Step 3: Modify implementation**

In `src/irc/spend/scope.py`, add to `COMMAND_TASKS` (after the `"monitor"` row):

```python
    "eval-live": ("monitor_impact", "monitor_narrative"),
```

No `COMMAND_SEARCH_PROVIDERS` entry for `eval-live` (the suites use constructed fixture pools, never
web search) → `search_providers` resolves to `frozenset()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/spend/test_scope.py -v`
Expected: PASS (all, including the new test + the completeness test).

- [ ] **Step 5: Commit**

```bash
git add src/irc/spend/scope.py tests/spend/test_scope.py
git commit -m "feat(spend): eval-live scope (monitor_impact+narrative, no search)"
```

---

## Task 15: `eval_cmd.py` — live_gated SKIPPED + gate-before-runner (AC #25, #27, OQ4, OQ5)

**Files:**
- Modify: `src/irc/commands/eval_cmd.py`
- Test: `tests/commands/test_eval_cmd.py` (extend)

The new path: in `run_eval`, after the `is_inactive` check, if `is_live_gated(spec)`:
- if `IRC_RUN_LIVE_LLM_EVAL` unset → write `skipped_report` (today's China date), print, return `EVAL_RC_SKIPPED`.
- else → `preflight_gate(repo_root, "eval-live")`; non-zero rc → return it WITHOUT resolving the runner.

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/commands/test_eval_cmd.py`:

```python
def test_live_gated_skips_without_env(tmp_path, monkeypatch, capsys):
    import json
    from datetime import datetime, timedelta, timezone
    from irc.commands.eval_cmd import run_eval
    monkeypatch.delenv("IRC_RUN_LIVE_LLM_EVAL", raising=False)
    rc = run_eval(str(tmp_path), stage="monitor_impact", all_stages=False)
    assert rc == 3
    out = capsys.readouterr().out.lower()
    assert "not executed" in out
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    report_path = tmp_path / "outputs" / today / "evals" / "monitor_impact" / "report.json"
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["overall"] == "SKIPPED"


def test_live_gated_skip_does_not_import_runner(tmp_path, monkeypatch):
    from irc.commands import eval_cmd
    monkeypatch.delenv("IRC_RUN_LIVE_LLM_EVAL", raising=False)
    called: list[str] = []

    def fake_import(name: str):
        called.append(name)
        raise AssertionError(f"runner module {name} must not import on SKIPPED path")

    monkeypatch.setattr(eval_cmd.importlib, "import_module", fake_import)
    rc = eval_cmd.run_eval(str(tmp_path), stage="monitor_impact", all_stages=False)
    assert rc == 3 and called == []


def test_live_gated_gate_blocks_before_runner(tmp_path, monkeypatch):
    from irc.commands import eval_cmd
    monkeypatch.setenv("IRC_RUN_LIVE_LLM_EVAL", "1")
    seen = {}

    def fake_gate(repo_root, command, **kw):
        seen["command"] = command
        return 5

    monkeypatch.setattr(eval_cmd, "preflight_gate", fake_gate)

    def fake_import(name: str):
        raise AssertionError(f"runner {name} must not import when gate blocks")

    monkeypatch.setattr(eval_cmd.importlib, "import_module", fake_import)
    rc = eval_cmd.run_eval(str(tmp_path), stage="monitor_impact", all_stages=False)
    assert rc == 5 and seen["command"] == "eval-live"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_eval_cmd.py -v -k live_gated`
Expected: FAIL — current `run_eval` resolves the (missing) runner and crashes / returns wrong rc.

- [ ] **Step 3: Modify implementation**

In `src/irc/commands/eval_cmd.py`:

(a) Update imports (lines 1-12):

```python
from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Callable

from evals._shared.missing_input import (
    EVAL_RC_SKIPPED,
    skipped_report,
    write_missing_input_report,
)
from evals._shared.registry import (
    EvalStageSpec,
    active_suite_stages,
    get_spec,
    is_inactive,
    is_live_gated,
)
from irc.commands.spend_cmd import preflight_gate

_LIVE_ENV = "IRC_RUN_LIVE_LLM_EVAL"
_TRUE = {"1", "true", "yes", "on"}
```

(b) Add this helper before `run_eval`:

```python
def _run_live_gated(root: Path, spec: EvalStageSpec) -> int:
    """SKIPPED when the env gate is unset; otherwise budget-gate before dispatch."""
    if os.environ.get(_LIVE_ENV, "").strip().lower() not in _TRUE:
        report = skipped_report(spec.stage, "env absent; not executed")
        write_missing_input_report(root, report)
        print(f"{spec.stage} eval: SKIPPED (env absent; not executed)")
        return EVAL_RC_SKIPPED
    gate = preflight_gate(str(root), "eval-live")
    if gate != 0:
        return gate
    return _resolve_runner(spec)(root)
```

(c) Insert the live_gated branch into `run_eval`, after the `is_inactive` block (after line 37,
before `return _resolve_runner(spec)(root)`):

```python
    if is_live_gated(spec):
        return _run_live_gated(root, spec)
```

NOTE: `write_missing_input_report` writes under today's China date by default (its `date_str=None`
path) — that satisfies "writes under today's China date" (§2.4) and the SKIPPED report becomes the
newest report for the stage.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_eval_cmd.py -v`
Expected: PASS (all — existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/eval_cmd.py tests/commands/test_eval_cmd.py
git commit -m "feat(eval-cmd): live_gated SKIPPED path + eval-live gate-before-runner"
```

---

## Task 16: `_process_fund` returns FundTraceBundle (AC #28)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Test: `tests/commands/test_monitor_cmd_trace.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_monitor_cmd_trace.py`:

```python
from __future__ import annotations
from pathlib import Path
from irc.commands import monitor_cmd
from irc.monitor.eval.types import FundTraceBundle
from irc.monitor.render_types import FundView
from irc.monitor.types import MonitorFund


class _Cfg:
    class history:
        minimum_observations = 2


def _fund(profile="gold_etf"):
    return MonitorFund(id="008986", name_cn="测试", market="CN", analysis_profile=profile,
                       themes=("gold",), constituent_news=False, weights={"trend": 1.0},
                       bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5)


def test_process_fund_returns_three_tuple_with_bundle(monkeypatch, tmp_path: Path):
    # Stub all edges so no network/LLM fires; non-lookthrough → constituent legs empty.
    monkeypatch.setattr(monitor_cmd, "nav_series_for", lambda fid: None)
    monkeypatch.setattr(monitor_cmd, "build_evidence_pool", lambda fund, repo_root: ())

    class _Imp:
        impacts = (); status = "empty_pool"; cost_entries = ()
    monkeypatch.setattr(monitor_cmd, "gather_impacts",
                        lambda **kw: _Imp())

    class _Narr:
        from irc.monitor.types import NarrativeDoc as _ND
        doc = _ND("008986", (), (), (), "empty_pool"); cost_entries = ()
    monkeypatch.setattr(monitor_cmd, "gather_narrative", lambda **kw: _Narr())

    out = monitor_cmd._process_fund(_fund(), _Cfg(), tmp_path, route_stub := object())
    assert len(out) == 3
    view, costs, bundle = out
    assert isinstance(view, FundView)
    assert isinstance(bundle, FundTraceBundle)
    assert bundle.fund_id == "008986"
    assert bundle.constituent_impacts == () and bundle.constituent_pool == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_trace.py -v`
Expected: FAIL — `_process_fund` returns a 2-tuple; `len(out) == 3` fails / unpack error.

- [ ] **Step 3: Modify implementation**

In `src/irc/commands/monitor_cmd.py`:

(a) Add the bundle import near the top (after line 39, the `irc.monitor.types` import):

```python
from irc.monitor.eval.types import FundTraceBundle
```

(b) Change the `_process_fund` signature and body. Replace lines 326-379. Track the macro impacts
result, the constituent impacts result, and the constituent pool, then return the bundle. The
constituent leg must capture `const_impacts.impacts` and `const_pool` (currently both are local but
discarded). Replace with:

```python
def _process_fund(
    fund: MonitorFund, cfg, root: Path, llm_config,
) -> tuple[FundView, list, FundTraceBundle]:
    """Process one fund: fetch → impacts → signal → narrative → view (+ eval bundle)."""
    from irc.monitor.profiles import PROFILES
    nav = nav_series_for(fund.id)
    pool = build_evidence_pool(fund, repo_root=root)
    impacts = gather_impacts(
        fund_id=fund.id, themes=fund.themes, pool=pool,
        route=llm_config, call=llm_call,
    )
    cost_history = list(impacts.cost_entries)
    macro_rows = _impact_rows_from(impacts, fund)

    constituent_rows: tuple = ()
    const_impacts_result = None
    const_pool: tuple = ()
    profile_spec = PROFILES.get(fund.analysis_profile)
    if profile_spec and profile_spec.lookthrough == "active_fund":
        const_pool = build_constituent_pool(fund.id, root=root)
        snap = load_latest_active_fund_cached(fund.id, root / "data")
        top_holdings: tuple = ()
        if snap is not None:
            top_holdings = tuple(
                sorted(snap.constituent_analyses, key=lambda c: c.weight_pct, reverse=True)
            )[:_TOP_N_HOLDINGS]
        if const_pool and top_holdings:
            holding_symbols = tuple(h.symbol for h in top_holdings)
            const_impacts_result = gather_impacts(
                fund_id=fund.id, themes=holding_symbols, pool=const_pool,
                route=llm_config, call=llm_call,
            )
            cost_history.extend(const_impacts_result.cost_entries)
            constituent_rows = _make_constituent_rows(const_impacts_result, top_holdings)

    inp = FactorInputs(
        acc_nav=nav.acc_series if nav else (),
        minimum_observations=cfg.history.minimum_observations,
        valuation_state=None,
        valuation_cached=False,
        restricted=None,
        aum_delta_pct=None,
        macro_rows=macro_rows,
        constituent_rows=constituent_rows,
    )
    scores = build_factor_scores(fund.analysis_profile, inp)
    signal = compute_signal(fund, scores)
    narr = gather_narrative(
        fund_id=fund.id, pool=pool, route=llm_config, call=llm_call,
    )
    cost_history.extend(narr.cost_entries)
    view = _make_view(fund, nav, signal, scores, narr.doc, pool, impacts.status)
    bundle = FundTraceBundle(
        fund_id=fund.id,
        macro_impacts=impacts.impacts,
        constituent_impacts=const_impacts_result.impacts if const_impacts_result else (),
        constituent_pool=const_pool,
    )
    return view, cost_history, bundle
```

(c) Update the caller in `run_monitor` (line 394-397) to unpack the bundle and keep it:

```python
    views: list[FundView] = []
    bundles: list[FundTraceBundle] = []
    all_costs: list = []
    for fund in funds:
        view, costs, bundle = _process_fund(fund, cfg, root, llm_config)
        views.append(view)
        bundles.append(bundle)
        all_costs.extend(costs)
```

(d) Keep a parallel `fund_views_bundles` mapping for Task 17. To avoid re-iterating, also collect the
funds in order — `funds` is already in scope and aligned with `views`/`bundles` by index.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_trace.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the existing monitor command tests (no regression)**

Run: `uv run pytest tests/commands/ tests/monitor/ -q`
Expected: PASS (no regressions from the return-shape change).

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_trace.py
git commit -m "feat(monitor): _process_fund returns FundTraceBundle for eval"
```

---

## Task 17: `run_monitor` wiring — gate + trace + ledger (AC #29, #5, #32, OQ6)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Test: `tests/commands/test_monitor_cmd_eval_wiring.py` (new)

`run_monitor` must, per fund (before `_write_outputs`): build the per-fund trace projection, compute
`health = (monitor_signal_health(...),)`, `gate = apply_eval_gate(...)`, then `build_eval_trace` →
`atomic_write_text` and `append_ledger`. Trace/ledger write failures are logged + swallowed (the
brief still renders). The gates feed render (Task 18).

Engine version provenance: reuse `_ENGINE_VERSION` (= `Provenance.engine_version`) for trace
`engine_version` and ledger `manifest_versions={"engine": _ENGINE_VERSION}` (OQ6).

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_monitor_cmd_eval_wiring.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
from irc.commands import monitor_cmd
from irc.monitor.eval.types import FundTraceBundle
from irc.monitor.render_types import FundView
from irc.monitor.types import (
    MonitorFund, SignalRecord, FactorContribution, NarrativeDoc,
)


def _fund(fid="008986"):
    return MonitorFund(id=fid, name_cn="测试", market="CN", analysis_profile="gold_etf",
                       themes=("gold",), constituent_news=False, weights={"trend": 1.0},
                       bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5)


def _signal(fid, status="ok", bias="ADD_BIAS"):
    return SignalRecord(fund_id=fid, status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                        divergence_codes=())


def _view(fid, *, degraded=False):
    series = () if degraded else (("2026-06-15", 2.4), ("2026-06-16", 2.5))
    return FundView(fund_id=fid, name_cn="测试", latest_nav=0.0 if degraded else 2.0,
                    as_of_date="N/A" if degraded else "2026-06-16", nav_series=series,
                    signal=_signal(fid), narrative=NarrativeDoc(fid, (), (), (), "ok"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=())


def _patch_pipeline(monkeypatch, funds, views):
    monkeypatch.setattr(monitor_cmd, "load_monitor_config", lambda root: object())
    monkeypatch.setattr(monitor_cmd, "resolve_funds", lambda cfg: funds)
    monkeypatch.setattr(monitor_cmd, "load_yaml", lambda *a, **k: object())
    monkeypatch.setattr(monitor_cmd, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(monitor_cmd, "record_command_run", lambda **k: None)
    monkeypatch.setattr(monitor_cmd, "_read_prior_signal", lambda root, today: None)
    view_iter = iter(views)
    monkeypatch.setattr(
        monitor_cmd, "_process_fund",
        lambda fund, cfg, root, llm: (next(view_iter), [],
                                      FundTraceBundle(fund.id, (), (), ())),
    )


def test_run_monitor_writes_eval_trace_and_ledger(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch_pipeline(monkeypatch, funds, [_view("008986")])
    rc = monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    trace_path = tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json"
    assert trace_path.exists()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert "008986" in trace["funds"]
    ledger = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    assert ledger.exists()
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["nav_basis"] == "coalesce(nav_acc,nav)"


def test_degraded_nav_fund_is_eval_gated_with_null_nav_acc(monkeypatch, tmp_path: Path):
    funds = [_fund("600000")]
    _patch_pipeline(monkeypatch, funds, [_view("600000", degraded=True)])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    trace = json.loads(
        (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json")
        .read_text(encoding="utf-8"))
    assert trace["funds"]["600000"]["published_state"] == "EVAL_GATED"
    rows = [json.loads(line) for line in
            (tmp_path / "data" / "monitor" / "forward_ledger.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert rows[0]["nav_acc"] is None


def test_run_monitor_still_renders_when_trace_write_fails(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch_pipeline(monkeypatch, funds, [_view("008986")])

    real_write = monitor_cmd.atomic_write_text

    def flaky_write(path, content, *a, **k):
        if path.name == "eval_trace.json":
            raise OSError("disk full")
        return real_write(path, content, *a, **k)

    monkeypatch.setattr(monitor_cmd, "atomic_write_text", flaky_write)
    rc = monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    assert (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -v`
Expected: FAIL — no `eval_trace.json` / ledger written yet.

- [ ] **Step 3: Modify implementation**

In `src/irc/commands/monitor_cmd.py`:

(a) Add imports near the top (after the `FundTraceBundle` import from Task 16):

```python
from irc.monitor.eval.gate import apply_eval_gate, GATING_STAGES_M0, published_state
from irc.monitor.eval.structural import monitor_signal_health
from irc.monitor.eval.trace import build_eval_trace
from irc.monitor.eval.forward_log import append_ledger, ledger_row
from irc.monitor.eval.types import GateDecision
```

(b) Add the NAV stale-days / minimum-observations constants near `_ENGINE_VERSION`:

```python
_NAV_STALE_DAYS = 7
```

(c) Add an eval-wiring helper before `run_monitor`:

```python
def _compute_gates(
    funds: list[MonitorFund], views: list[FundView], bundles: list[FundTraceBundle],
    *, min_obs: int,
) -> tuple[GateDecision, ...]:
    """PURE-ish: build each fund's trace projection, derive its monitor_signal health,
    and apply the M0 gate. Two-pass: a stub trace gives the projection the structural
    checks read; the real trace (Task: _write_eval_artifacts) re-serializes with the gate."""
    gates: list[GateDecision] = []
    for fund, view, bundle in zip(funds, views, bundles):
        stub = GateDecision(fund.id, False, (), "validated", "")
        projection = build_eval_trace(
            ((fund, view, stub, bundle),), engine_version=_ENGINE_VERSION,
            run_date="",  # run_date irrelevant for the per-fund projection
        )["funds"][fund.id]
        health = (monitor_signal_health(projection, minimum_observations=min_obs,
                                        stale_days=_NAV_STALE_DAYS),)
        gates.append(apply_eval_gate(view.signal, health=health,
                                     gating_stages=GATING_STAGES_M0))
    return tuple(gates)


def _write_eval_artifacts(
    out: Path, root: Path, funds: list[MonitorFund], views: list[FundView],
    bundles: list[FundTraceBundle], gates: tuple[GateDecision, ...], *, run_date: str,
) -> None:
    """EDGE: serialize eval_trace.json + append the forward ledger. Failures are
    logged and swallowed — the brief must still render."""
    try:
        trace = build_eval_trace(
            tuple(zip(funds, views, gates, bundles)),
            engine_version=_ENGINE_VERSION, run_date=run_date,
        )
        atomic_write_text(out / "eval_trace.json",
                          json.dumps(trace, ensure_ascii=False, indent=2))
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("eval_trace write failed", exc_info=True)
    try:
        written_at = _now_iso()
        rows = [
            ledger_row(
                run_date=run_date, fund_id=fund.id, written_at=written_at,
                signal=view.signal,
                nav_acc=(view.nav_series[-1][1] if view.nav_series else None),
                nav_unit=view.latest_nav, as_of_date=view.as_of_date,
                published_state=published_state(view.signal, gate), gate=gate,
                manifest_versions={"engine": _ENGINE_VERSION},
            )
            for fund, view, gate in zip(funds, views, gates)
        ]
        append_ledger(root / "data" / "monitor" / "forward_ledger.jsonl", rows)
    except Exception:  # noqa: BLE001 — append_ledger already swallows, this guards ledger_row
        _log.warning("forward ledger write failed", exc_info=True)
```

(d) Rewrite the body of `run_monitor` (lines 382-408) to collect bundles, compute gates, write
artifacts, then render. Replace from the loop through the end:

```python
def run_monitor(*, repo_root: str, today: str | None = None) -> int:
    """EDGE orchestrator for `irc monitor`."""
    root = Path(repo_root)
    _today = today or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    gate = preflight_gate(repo_root, "monitor")
    if gate != 0:
        return gate
    cfg = load_monitor_config(root)
    funds = resolve_funds(cfg)
    llm_config = load_yaml(root / "config/llm.yaml", root)
    views: list[FundView] = []
    bundles: list[FundTraceBundle] = []
    all_costs: list = []
    for fund in funds:
        view, costs, bundle = _process_fund(fund, cfg, root, llm_config)
        views.append(view)
        bundles.append(bundle)
        all_costs.extend(costs)
    gates = _compute_gates(list(funds), views, bundles,
                           min_obs=cfg.history.minimum_observations)
    prior = _read_prior_signal(root, _today)
    out = root / "outputs" / _today / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    _write_eval_artifacts(out, root, list(funds), views, bundles, gates, run_date=_today)
    _write_outputs(out, views, prior, gates)
    record_command_run(
        repo_root=root,
        history=all_costs,
        search_units={},
        today=datetime.fromisoformat(_today).date(),
    )
    return 0
```

NOTE: `_write_outputs` signature gains a `gates` parameter — implemented in Task 18. For THIS task,
update `_write_outputs` to accept and ignore `gates` so the wiring tests pass before the render work:

In `_write_outputs` (line 301), change the signature to:

```python
def _write_outputs(out: Path, views: list[FundView], prior: dict | None,
                   gates: tuple = ()) -> None:
```

(leave the body unchanged for now — Task 18 threads `gates` into `render_report`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verification — full monitor + eval test sweep (no regression)**

Run: `uv run pytest tests/commands/ tests/monitor/ tests/evals/ -q`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_eval_wiring.py
git commit -m "feat(monitor): wire eval gate + eval_trace + forward ledger into run_monitor"
```

---

## Task 18: Render — EVAL-GATED badge + validation chips + panel (AC #30, #31)

**Files:**
- Modify: `src/irc/monitor/render_html.py`
- Modify: `src/irc/commands/monitor_cmd.py` (thread `gates` into `render_report`)
- Test: `tests/monitor/test_render_html_eval.py` (new)

`render_report` gains a per-fund `gates` map so `_badge` can key off `published_state` and append the
validation chip; the Validation panel is appended from `panel.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/monitor/test_render_html_eval.py`:

```python
from __future__ import annotations
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.eval.types import GateDecision
from irc.monitor.eval.staleness import STALE_AFTER_DAYS  # noqa: F401 (import sanity)
from irc.monitor.types import SignalRecord, FactorContribution, NarrativeDoc

_NOW = "2026-06-16T09:00:00+08:00"


def _signal(status="ok", bias="ADD_BIAS"):
    return SignalRecord(fund_id="008986", status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                        divergence_codes=())


def _view(status="ok", bias="ADD_BIAS"):
    return FundView(fund_id="008986", name_cn="测试", latest_nav=2.0, as_of_date="2026-06-16",
                    nav_series=(("2026-06-15", 2.4), ("2026-06-16", 2.5)), signal=_signal(status, bias),
                    narrative=NarrativeDoc("008986", (), (), (), "ok"), evidence_pool=(),
                    return_table={}, factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=())


def _gate(badge="validated", suppressed=False, reason=""):
    return GateDecision("008986", suppressed, ("monitor_signal",) if suppressed else (),
                        badge, reason)


def _render(view, gate):
    from irc.monitor.render_html import render_report
    prov = Provenance("1", "1", "1", "")
    return render_report((view,), prov, prior_signal=None, now=_NOW,
                         gates={"008986": gate})


def test_eval_gated_badge_rendered():
    html = _render(_view(), _gate(badge="gated", suppressed=True, reason="nav_quality FAIL"))
    assert "eval-gated" in html
    assert "EVAL-GATED" in html


def test_validated_chip_on_published_bias():
    html = _render(_view(bias="ADD_BIAS"), _gate(badge="validated"))
    assert "ADD_BIAS" in html
    assert "✓" in html  # validated chip glyph


def test_caveated_chip_on_published_bias():
    html = _render(_view(bias="REDUCE_BIAS"), _gate(badge="caveated"))
    assert "REDUCE_BIAS" in html
    assert "⚠" in html  # caveated chip glyph


def test_no_call_not_eval_gated_when_status_not_ok():
    html = _render(_view(status="low_confidence", bias=None), _gate(badge="caveated"))
    assert "NO_CALL" in html
    assert "EVAL-GATED" not in html


def test_validation_panel_present_with_monitor_signal_row():
    html = _render(_view(), _gate(badge="validated"))
    assert "Validation" in html
    assert "monitor_signal" in html


def test_render_report_backwards_compatible_without_gates():
    # gates defaults to None → falls back to bare bias badge (no chip/panel crash)
    from irc.monitor.render_html import render_report
    prov = Provenance("1", "1", "1", "")
    html = render_report((_view(),), prov, prior_signal=None, now=_NOW)
    assert "ADD_BIAS" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_render_html_eval.py -v`
Expected: FAIL — `render_report` has no `gates` kwarg.

- [ ] **Step 3: Modify `render_html.py`**

(a) Add CSS classes inside `_CSS` (before the closing `"</style>"`):

```python
    ".eval-gated{background:#57606a;color:#fff}"
    ".val-chip{font-size:11px;margin-left:6px;padding:1px 4px;border-radius:3px}"
    ".val-validated{color:#1a7f37}"
    ".val-caveated{color:#bf8700}"
    ".validation-panel{margin:16px 0;padding:8px;border:1px solid #d0d7de;border-radius:6px}"
    ".validation{border-collapse:collapse;font-size:13px;margin:4px 0}"
    ".validation th,.validation td{border:1px solid #d0d7de;padding:3px 6px}"
```

(b) Add a published-state import and helpers at the top (after existing imports):

```python
from irc.monitor.eval.gate import published_state
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import GateDecision

_EVAL_GATED = "EVAL_GATED"
_CHIP = {"validated": ('val-validated', '✓ validated'),
         "caveated": ('val-caveated', '⚠ caveated')}
```

(c) Replace `_badge` (lines 41-44) with a gate-aware version:

```python
def _badge(view: FundView, gate: GateDecision | None) -> str:
    if gate is None:
        if view.signal.status != "ok":
            return f'<span class="badge no-call">{_NO_CALL}</span>'
        return f'<span class="badge {view.signal.bias.lower()}">{escape(view.signal.bias)}</span>'
    state = published_state(view.signal, gate)
    if state == _NO_CALL:
        return f'<span class="badge no-call">{_NO_CALL}</span>'
    if state == _EVAL_GATED:
        return f'<span class="badge eval-gated">EVAL-GATED 🛡</span>'
    chip = ""
    cls_label = _CHIP.get(gate.badge)
    if cls_label:
        cls, label = cls_label
        chip = f'<span class="val-chip {cls}">{label}</span>'
    return f'<span class="badge {state.lower()}">{escape(state)}</span>{chip}'
```

(d) Thread `gates` through `_summary_row`, `_card`, and `render_report`. Replace `_summary_row`
(58-70) and `_card` (73-85) signatures + their `_badge(view)` calls:

```python
def _summary_row(view: FundView, prior: dict | None, gate: GateDecision | None) -> str:
    changed = ""
    if prior is not None:
        prev = (prior.get(view.fund_id) or {}).get("bias")
        if prev != view.signal.bias:
            changed = '<span class="changed-since-yesterday" style="color:#bf8700">●</span>'
    return (
        f"<tr><td>{escape(view.name_cn)}</td>"
        f"<td>{view.latest_nav:.4f} @ {view.as_of_date}</td>"
        f"<td>{_badge(view, gate)}</td>"
        f"<td>C={view.signal.composite:+.4f}</td>"
        f"<td>{changed}</td></tr>"
    )


def _card(view: FundView, gate: GateDecision | None) -> str:
    chart = render_nav_chart(view.nav_series, markers=_markers(view))
    return (
        f'<section class="fund-card" id="fund-{view.fund_id}">'
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view, gate)}</h2>"
        f"{verdict_block_html(view.signal, view.narrative)}"
        f"{chart}"
        f"{returns_table_html(view.return_table)}"
        f"{factor_table_html(view.signal, view.factor_scores, view.factor_freshness)}"
        f"{narrative_sections_html(view.narrative)}"
        f"{risk_block_html(view.signal, view.narrative)}"
        "</section>"
    )
```

(e) Add a panel helper and update `render_report` (108-132):

```python
def _panel(views: tuple[FundView, ...], gates: dict[str, GateDecision] | None, now: str) -> str:
    if not gates:
        return ""
    from irc.monitor.eval.types import StageHealth
    counts: dict[str, int] = {}
    for v in views:
        g = gates.get(v.fund_id)
        if g is not None:
            counts[g.badge] = counts.get(g.badge, 0) + 1
    health = StageHealth("monitor_signal", "PASS", ())
    return validation_panel_html(stage_health=health, ran_at=now, badge_counts=counts)


def render_report(
    views: tuple[FundView, ...],
    provenance: Provenance,
    *,
    prior_signal: dict | None,
    now: str,
    gates: dict[str, GateDecision] | None = None,
) -> str:
    """PURE: self-contained HTML. No I/O, no JS, no remote refs."""
    header = (
        f'<header>as_of {now} · engine {provenance.engine_version} · '
        f'prompt {provenance.prompt_version} · schema {provenance.schema_version} · '
        f'{escape(provenance.spend_summary)}</header>'
    )
    g = gates or {}
    summary = (
        "<table class='summary'>"
        + "".join(_summary_row(v, prior_signal, g.get(v.fund_id)) for v in views)
        + "</table>"
    )
    cards = "".join(_card(v, g.get(v.fund_id)) for v in views)
    panel = _panel(views, gates, now)
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<title>irc monitor</title>" + _CSS + "</head><body>"
        + header + summary + cards + panel + _appendix(views) + "</body></html>"
    )
```

NOTE on panel health row: M0's panel shows a single `monitor_signal` row. The per-fund structural
health varies; the panel summarizes via badge counts (the per-fund verdicts), and the stage row's
`overall` is the worst-of badges proxy. For M0 simplicity the row status is rendered "PASS" with the
distribution conveyed by counts (a gated count > 0 is visible). This matches AC #30 ("per-fund badge
counts") and AC #31 (the staleness reason is visible via each fund's `EVAL-GATED` badge + reason in
the trace). The integration assertion in Task 17 already covers the EVAL_GATED published_state.

- [ ] **Step 4: Modify `monitor_cmd._write_outputs` to thread gates into render**

In `src/irc/commands/monitor_cmd.py`, update `_write_outputs` (the body) to build a gates map and
pass it to `render_report`:

```python
def _write_outputs(out: Path, views: list[FundView], prior: dict | None,
                   gates: tuple = ()) -> None:
    prov = Provenance(_ENGINE_VERSION, "1", "1", "")
    gate_map = {g.fund_id: g for g in gates}
    html = render_report(tuple(views), prov, prior_signal=prior, now=_now_iso(),
                         gates=gate_map or None)
    atomic_write_text(out / "report.html", html)
    atomic_write_text(
        out / "signal.json",
        json.dumps(_signal_dump(views), indent=2, sort_keys=True),
    )
    atomic_write_text(
        out / "impacts.json",
        json.dumps(_impacts_dump(views), indent=2, sort_keys=True),
    )
    atomic_write_text(
        out / "narrative.json",
        json.dumps(_narrative_dump(views), indent=2, sort_keys=True),
    )
    atomic_write_text(
        out / "monitor.json",
        json.dumps(_machine_summary(views), indent=2, sort_keys=True),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_render_html_eval.py tests/monitor/test_render_html.py -v`
Expected: PASS (new eval tests + existing render tests — the existing tests call `render_report`
without `gates`, which now defaults to `None` and uses the bare-bias badge path).

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/render_html.py src/irc/commands/monitor_cmd.py \
        tests/monitor/test_render_html_eval.py
git commit -m "feat(monitor): EVAL-GATED badge, validation chips, Validation panel"
```

---

## Task 19: Acceptance guard (AC #32, #31 stale-NAV end-to-end)

**Files:**
- Test: `tests/monitor/test_acceptance_eval.py` (new)

A grep-style acceptance + stale-NAV integration. Reuses the wiring harness from Task 17.

- [ ] **Step 1: Write the test**

Create `tests/monitor/test_acceptance_eval.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
from irc.commands import monitor_cmd
from irc.monitor.eval.types import FundTraceBundle
from irc.monitor.render_types import FundView
from irc.monitor.types import (
    MonitorFund, SignalRecord, FactorContribution, NarrativeDoc,
)


def _fund(fid="008986"):
    return MonitorFund(id=fid, name_cn="测试", market="CN", analysis_profile="gold_etf",
                       themes=("gold",), constituent_news=False, weights={"trend": 1.0},
                       bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5)


def _signal(fid):
    return SignalRecord(fund_id=fid, status="ok", bias="ADD_BIAS", composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                        divergence_codes=())


def _stale_view(fid="008986"):
    # NAV older than _NAV_STALE_DAYS (7) → nav_quality FAIL → EVAL_GATED
    return FundView(fund_id=fid, name_cn="测试", latest_nav=2.0, as_of_date="2000-01-02",
                    nav_series=(("2000-01-01", 2.4), ("2000-01-02", 2.5)), signal=_signal(fid),
                    narrative=NarrativeDoc(fid, (), (), (), "ok"), evidence_pool=(),
                    return_table={}, factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=())


def _patch(monkeypatch, funds, views):
    monkeypatch.setattr(monitor_cmd, "load_monitor_config", lambda root: object())
    monkeypatch.setattr(monitor_cmd, "resolve_funds", lambda cfg: funds)
    monkeypatch.setattr(monitor_cmd, "load_yaml", lambda *a, **k: object())
    monkeypatch.setattr(monitor_cmd, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(monitor_cmd, "record_command_run", lambda **k: None)
    monkeypatch.setattr(monitor_cmd, "_read_prior_signal", lambda root, today: None)
    it = iter(views)
    monkeypatch.setattr(monitor_cmd, "_process_fund",
                        lambda fund, cfg, root, llm: (next(it), [],
                                                      FundTraceBundle(fund.id, (), (), ())))


def test_eval_trace_emitted_and_ledger_uses_coalesce_basis(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json").exists()
    ledger = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert all(r["nav_basis"] == "coalesce(nav_acc,nav)" for r in rows)


def test_stale_nav_fund_is_eval_gated_and_panel_names_it(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    trace = json.loads(
        (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json")
        .read_text(encoding="utf-8"))
    f = trace["funds"]["008986"]
    assert f["published_state"] == "EVAL_GATED"
    assert f["validation_badge"] == "gated"
    assert "older than" in f["gate"]["reason"]
    html = (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").read_text(encoding="utf-8")
    assert "EVAL-GATED" in html and "Validation" in html
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_acceptance_eval.py -v`
Expected: PASS (2 passed). (These exercise the already-built wiring + render — they should pass
green immediately; if either fails, the wiring/render task has a gap to fix before proceeding.)

- [ ] **Step 3: Commit**

```bash
git add tests/monitor/test_acceptance_eval.py
git commit -m "test(monitor-eval): acceptance — eval_trace emitted, ledger basis, stale-NAV gated"
```

---

## Task 20: Full sweep + lint + final commit

**Files:** none (verification only)

- [ ] **Step 1: Run the full new-code test sweep**

Run:
```bash
uv run pytest tests/monitor/ tests/evals/ tests/commands/test_eval_cmd.py \
  tests/commands/test_gate_wiring.py tests/spend/test_scope.py \
  tests/commands/test_monitor_cmd_trace.py tests/commands/test_monitor_cmd_eval_wiring.py \
  tests/monitor/test_render_html_eval.py tests/monitor/test_acceptance_eval.py -q
```
Expected: PASS (all green).

- [ ] **Step 2: Lint**

Run: `uv run ruff check src tests evals`
Expected: `All checks passed!` (fix any line-length > 100 or unused-import findings; keep functions
small).

- [ ] **Step 3: Spot-check the legacy monitor dumps are unchanged (AC constraint)**

Run: `uv run pytest tests/monitor/test_render_html.py tests/commands/ -q`
Expected: PASS — the four legacy dumps (`signal.json`/`impacts.json`/`narrative.json`/`monitor.json`)
are untouched; `eval_trace.json` is strictly additive.

- [ ] **Step 4: Final verification commit (if any lint fixes were needed)**

```bash
git add -A
git commit -m "chore(monitor-eval): lint + final sweep for M0 eval spine"
```

(If Step 2 found nothing, skip this commit.)

---

## Self-review notes (spec coverage map)

| AC | Task |
|---|---|
| #1–#3 (trace artifact + schema + round-trip) | 6, 17 |
| #4–#5 (degradation-safe NAV → EVAL_GATED + ledger null) | 6, 17 |
| #6–#8 (FundTraceBundle, unified pool, constituent resolves) | 1, 6, 16 |
| #9 (types + naming guard) | 1 |
| #10 (structural) | 2 |
| #11 (staleness) | 3 |
| #12, #24 (latest_stage_report) | 11 |
| #13–#15 (gate + published_state + GATING_STAGES_M0) | 4 |
| #16–#18 (ledger row/append/latest_per_key) | 5 |
| #19–#20 (monitor_signal metrics + runner) | 12, 13 |
| #21 (status SKIPPED) | 8 |
| #22 (EVAL_RC_SKIPPED + skipped_report) | 9 |
| #23 (registry live_gated + placeholders) | 10 |
| #25, #27 (eval_cmd skip + gate-before-runner) | 15 |
| #26 (eval-live scope) | 14 |
| #28 (_process_fund → bundle) | 16 |
| #29 (run_monitor wiring) | 17 |
| #30 (badge + chips + panel) | 18 |
| #31 (stale-NAV EVAL_GATED end-to-end) | 19 |
| #32 (acceptance grep) | 19 |

**Out of scope (NOT built — M1/M2-M4):** `cases/`, `metrics_impact.py`, `metrics_narrative.py`,
`evals/monitor_impact/runner.py`, `evals/monitor_narrative/runner.py`, `GATING_STAGES_M1`, the
ledger scorer, retro backtest, the ADR. The M0 surface lands only the `eval-live` *scope*, the
registry *placeholders*, and the `eval_cmd` gate/skip *path* (spec Non-goals).

**Judgment calls made (flag for reviewer):**
- **Task 17 two-pass gate computation.** Spec §2.8 wiring computes `health` from a "trace_fund"
  projection then builds the real trace with the gate. To avoid duplicating the projection logic, I
  reuse `build_eval_trace` with a stub gate to produce the per-fund projection that `monitor_signal_health`
  reads, then re-serialize the final trace with the real gate. This keeps one serialization code path
  (DRY) at the cost of building the trace dict twice; acceptable for 7 funds. (Spec §2.8 step 1-2.)
- **Task 18 panel stage-row status.** AC #30 specifies "per-fund badge counts" but does not pin the
  single stage row's `overall` value when funds disagree. I render the row label as the static
  `monitor_signal` stage with badge-count distribution; a gated fund is visible via its count and its
  per-card EVAL-GATED badge. (Spec §2.8 panel bullet — "per-fund badge counts".)
- **`render_report` `gates` kwarg defaults to `None`** for backward compatibility with the existing
  `tests/monitor/test_render_html.py` (which calls `render_report` without gates). The live path
  always passes a populated map. (Not spec-pinned; preserves the locked legacy-dump-unchanged
  constraint and existing test contract.)
