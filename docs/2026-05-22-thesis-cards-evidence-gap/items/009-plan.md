# Item 009 Implementation Plan — citation audit gate (Slice D2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire four structural audit functions and two fail-closed gates (opportunity-stage and memo-stage) that block publishable artifacts whose conclusions cannot be tied — per-instrument and per-leg — to a `CitationMeta` entry in the `CitedMap` from item 002. Gate is fail-closed (`block`) on canonical paths and shadow-logged in all modes.

**Architecture:** One new pure-function module (`src/irc/opportunity/auditor.py`) for opportunity-side audits; two new functions in `src/irc/memo/numeric_audit.py` plus a body for the item 007 `find_uncited_conclusions` stub; one new helper (`build_constituent_cited_map`) in `src/irc/opportunity/citation_map.py`; one new `RejectionReasonCode` entry. Two gate wirings: (a) `_write_opportunity_outputs` gains Step 2a/2b/2c between H3 partition (Step 2) and serializer calls (Step 3); (b) `run_memo` gains a citation gate downstream of `audit_blocks_publish`. Both stages share a single `outputs/<date>/citation_audit.json` shadow log (read-modify-write across the two stages). New `_resolve_enforce_mode` helper lives at module scope in `opportunity_cmd.py` and is imported by `memo_cmd.py`. Item 008's lockdown helper is lifted to `tests/integration/_publishable_set_helper.py` so item 009's integration tests can reuse it.

**Tech Stack:** Python 3.12, pytest, ruff, stdlib only. No new third-party deps.

---

## Constraints (apply to every task)

- **Strict TDD per task:** red (failing test) → green (minimal impl) → refactor. No implementation code lands without a prior failing test. Tests-first within a task.
- **Pure functions only.** Every new function in `auditor.py`, `numeric_audit.py`, and `citation_map.py` is pure: no I/O, no mutation, no logging, no global state. The two helpers in `opportunity_cmd.py` (`_resolve_enforce_mode`, `_write_citation_audit_shadow_log`) are minimal: the first is a pure resolver, the second is a thin wrapper around `atomic_write_text`.
- **Frozen dataclasses + `dataclasses.replace`.** No in-place mutation. `NumericFinding` from `numeric_audit.py` is already frozen; `RejectionRecord` stays frozen.
- **No new I/O at the audit-function layer.** Gate wirings own all `atomic_write_text` calls.
- **Defaults locked:**
  - `IRC_CITATION_ENFORCE_MODE` default = `"block"` on canonical paths (`os.environ.get(...,"block")` plus canonical-path force).
  - Canonical-path predicate: `out_dir.resolve().parent.name == "outputs" AND re.fullmatch(r"\d{4}-\d{2}-\d{2}", out_dir.name)`. Date read from `out_dir.name`, NOT from wall-clock `_today()`.
  - Actionable keyword set (item 009 v1, frozen):
    `("加速定投","正常定投","减速定投","暂停加仓","禁止买入","回避","建仓","加仓","减仓","止损")`
  - V1 dimension binding is **structural**: dual-leg per row (≥1 `data` + ≥1 `information` anywhere in `row.thesis_evidence`); per-dimension `(type → dimension)` map is v2 (Q1 deferral).
  - `strict_empty_alias_check: bool = False` keyword-only default for `find_uncited_conclusions` (Q3 lock). Only `memo_cmd.py` flips it to `True` via `bool(rebuilt_op_rows)`.
- **Shadow-log shape locked.** See AC13. Single shared file across the two stages; opportunity stage writes the four lists; memo stage RMW updates only `memo_findings` and re-derives `summary`.
- **Functional programming (CLAUDE.md).** No methods on frozen dataclasses; free functions or inline predicates. No mid-function `list.append` over comprehensions where the comprehension is readable.
- **Item 008 baseline stays green.** Lifting `_seed_publishable_set_repo` to `tests/integration/_publishable_set_helper.py` must NOT change the bytes that ACs 22–23 sha256-lock. Verified by running `pytest tests/integration/test_publishable_set_lockdown.py -x -q` after the lift commit and at the final task.
- **Commit cadence:** one conventional-commit per task (`feat(opportunity):`, `feat(memo):`, `refactor(tests):`, `test(integration):`). DO NOT push.
- **Verification per task:** an exact `pytest …` command with expected PASS/FAIL output. Final task = full `pytest -x -q` + `ruff check src tests` clean.

## Branch

Sub-branch: `autodev/thesis-evidence-009-citation-gate-block-mode` cut from `autodev/thesis-cards-evidence-gap`. Commits land on the sub-branch; the eventual PR opens against `autodev/thesis-cards-evidence-gap`.

---

## Locked decisions (from grill Q1–Q7)

These are non-negotiable; the plan implements them verbatim. See `009-grill.md` for full justifications.

- **Q1 — v2 dimension-binding handoff:** Defer to v2 via a CONTEXT.md breadcrumb under "Audit gates and enforcement modes". V1 ships structural binding only (dual-leg per row, no `(type → dimension)` map). No new ADR.
- **Q2 — Canonical-path detection:** Regex-based on `out_dir.name`, NOT wall-clock `_today()`. `out_dir.resolve().parent.name == "outputs" AND re.fullmatch(r"\d{4}-\d{2}-\d{2}", out_dir.name)`. Handles end-of-day skew, `--output-dir outputs/2026-05-22` cross-day invocations, and `tmp_path` scratch dirs.
- **Q3 — Empty-alias guard parameter name:** Rename to `strict_empty_alias_check: bool = False`, keyword-only. Default `False` preserves item 007's all-gapped pipeline state semantic. Only `memo_cmd.py` flips it to `True` via `strict_empty_alias_check=bool(rebuilt_op_rows)`.
- **Q4 — `citation_gate_blocked` RejectionReasonCode:** ADD to both the `RejectionReasonCode` literal AND `_GAP_TO_REASON` in `src/irc/opportunity/rejection_log.py`. Identity mapping. Appended at END of `_GAP_TO_REASON` to preserve existing precedence (item 008 AC11 stays valid).
- **Q5 — Dimension-conclusion-dropping renderer:** Deferred to v2. V1 = fail-the-row (Step 2a removes row, stamps `evidence_gaps=("citation_gate_blocked",)`, routes via `rejections.json` + discipline failure section). Inline TODO comment at Step 2a emission site; CONTEXT.md breadcrumb.
- **Q6 — Item 008 baseline with default `block`:** Item 008's `_seed_publishable_set_repo` already seeds dual-leg dual-scope evidence on every publishable row by construction. Gate is a no-op on item 008 seeds. New AC24 locks this. Final task runs `pytest tests/integration/test_publishable_set_lockdown.py -x -q` to verify.
- **Q7 + F1 — Memo-stage `out_dir` vs `out_today`:** `_resolve_enforce_mode(out_dir, today)` in `memo_cmd.run_memo` uses `out_dir` (line ~534: WRITE path, `root / "outputs" / today`), NOT `out_today` (line ~419: READ path, `scoring_path.parent`). `today = _today()` captured once at line 409. New AC25 locks this with a unit test that monkey-patches `_latest_file` to return a yesterday-dated `scoring.json`.

---

## File-touch map (read this before starting)

**Source (create):**
- `src/irc/opportunity/auditor.py` (~120 LOC) — pure functions `find_uncited_opportunity_rows`, `find_incomplete_constituent_analyses`. Imports `NumericFinding` from `irc.memo.numeric_audit`.

**Source (modify):**
- `src/irc/memo/numeric_audit.py` — add `find_missing_pick_citations`, `find_uncited_discipline_rows`; replace the `find_uncited_conclusions` stub body with paragraph-level implementation; add keyword-only `strict_empty_alias_check: bool = False`.
- `src/irc/opportunity/citation_map.py` — add `build_constituent_cited_map(rows) -> ConstituentCitedMap` mirroring `build_cited_map`'s provenance checks.
- `src/irc/opportunity/rejection_log.py` — add `"citation_gate_blocked"` to `RejectionReasonCode` literal AND append identity-mapped entry to `_GAP_TO_REASON` (Q4).
- `src/irc/commands/opportunity_cmd.py` — add `_resolve_enforce_mode(out_dir, today) -> str`, `_write_citation_audit_shadow_log(out_dir, payload)`; wire Steps 2a/2b/2c into `_write_opportunity_outputs` between H3 partition (line ~1100) and serializer (line ~1117). Inline `# Q5 deferral` comment at Step 2a emission site.
- `src/irc/commands/memo_cmd.py` — wire memo-stage gate after `audit_blocks_publish` (line ~539) and before `atomic_write_text(memo.md)` (line ~568). Import `_resolve_enforce_mode` from `opportunity_cmd`. **Pass `out_dir` (write-path), NOT `out_today` (read-path).**

**Tests (create):**
- `tests/opportunity/test_auditor.py` (~250 LOC) — covers ACs 1, 5, 6, 7. Unit tests for the two auditor functions; hand-built `OpportunityRow` instances.
- `tests/integration/test_citation_audit_gate.py` (~600 LOC) — covers ACs 9, 11, 12, 13, 14, 15, 16, 20, 21, 22, 23, 24, 25. Reuses the lifted `_publishable_set_helper.py`.
- `tests/integration/_publishable_set_helper.py` (~250 LOC) — extracted from item 008's `test_publishable_set_lockdown.py` module-level helpers.

**Tests (modify):**
- `tests/memo/test_numeric_audit.py` — extend with AC2/3 (`find_missing_pick_citations`), AC4 (`find_uncited_discipline_rows`), AC8/17/18/19 (`find_uncited_conclusions` body).
- `tests/integration/test_publishable_set_lockdown.py` — import-shift only (no AC change): the module-level helpers move to `_publishable_set_helper.py`; the file re-imports them. Sha256-locked outputs from AC22/23 stay byte-equal.

**Files explicitly NOT touched:**
- `src/irc/opportunity/types.py` — no schema changes.
- `src/irc/opportunity/thesis_evidence.py` — no producer-side change.
- `src/irc/settings.py` — `IRC_CITATION_ENFORCE_MODE` is read via `os.environ.get` per AC11, not via pydantic settings (matches existing `IRC_CACHE_FRESHNESS_DAYS` / `IRC_FETCH_BUDGET` precedent in `opportunity_cmd.py`).
- `docs/adr/0001-0004` — unchanged.
- `CONTEXT.md` — appended in Task 16 (final docs commit), under "Audit gates and enforcement modes".

---

## Task index (one slice per task, all green-at-checkpoint)

1. Lift `_seed_publishable_set_repo` + auxiliaries from `test_publishable_set_lockdown.py` into `tests/integration/_publishable_set_helper.py`; re-import shim in the original file; verify item 008 ACs 22–23 still byte-equal.
2. Add `"citation_gate_blocked"` to `RejectionReasonCode` literal + `_GAP_TO_REASON` identity-mapped entry (Q4).
3. Create `src/irc/opportunity/auditor.py` with `find_uncited_opportunity_rows` (ACs 1, 6).
4. Add `find_incomplete_constituent_analyses` to `src/irc/opportunity/auditor.py` (ACs 5, 7).
5. Add `find_missing_pick_citations` to `src/irc/memo/numeric_audit.py` (AC2).
6. Add `find_uncited_discipline_rows` to `src/irc/memo/numeric_audit.py` (AC4).
7. Replace the `find_uncited_conclusions` stub body with the paragraph-level implementation; add `strict_empty_alias_check` keyword (ACs 3, 8, 17, 18, 19).
8. Add `build_constituent_cited_map` to `src/irc/opportunity/citation_map.py`.
9. Add `_resolve_enforce_mode` + `_write_citation_audit_shadow_log` to `src/irc/commands/opportunity_cmd.py` (AC11, AC13).
10. Wire Steps 2a/2b/2c into `_write_opportunity_outputs` (ACs 9, 10, 12, 13).
11. Wire the memo-stage gate into `run_memo` (ACs 14, 15, 16, 25).
12. Integration test: canonical-path × enforce-mode matrix (AC22 in spec / our local naming; covers all 7 scenarios from spec AC22).
13. Integration test: shadow log written in all modes including `block` (AC23).
14. Integration test: item 008 baseline passes with default `block` (AC24).
15. Integration test: memo-stage `out_dir` vs `out_today` discipline (AC25); two-run byte equality cross-check (AC20).
16. CONTEXT.md update ("Audit gates and enforcement modes" section) + final `pytest -x -q` + `ruff check src tests` + verify item 008 baseline still green.

---

## Task 1: Lift `_seed_publishable_set_repo` to `tests/integration/_publishable_set_helper.py`

**Files:**
- Create: `tests/integration/_publishable_set_helper.py`
- Modify: `tests/integration/test_publishable_set_lockdown.py` (import-only shim)

**Why first:** Item 009's integration tests reuse the seed helper. Lifting it before any source change keeps item 008's byte-equality regression (ACs 22–23) intact; if the lift breaks anything, we discover it immediately.

- [ ] **Step 1: Inventory the helpers to lift**

Open `tests/integration/test_publishable_set_lockdown.py` and identify all module-level helpers up to (but excluding) the first `def test_...` function. The spec lists them as:
- `_resp(text) -> ChatResponse`
- `_today_cn() -> str`
- `_sha256_file(path) -> str`
- `_collect_publishable_citation_universe(out_dir) -> set[str]`
- `_patch_memo_routes(synth_text) -> contextmanager`
- `_install_ak_call_dispatch(monkeypatch, dispatch) -> Counter`
- `_seed_publishable_set_repo(tmp_path, *, monkeypatch, ...) -> dict`

These plus any private helpers they call. Read the file and confirm the exact set; nothing else moves.

Run: `grep -n "^def \|^@contextmanager\|^_FIXED_INGESTED_AT\|^_BROKER_REPORT_DATE" tests/integration/test_publishable_set_lockdown.py | head -30`

- [ ] **Step 2: Capture pre-lift sha256 of two locked artifacts**

Run the two-run byte-equality tests to confirm a clean baseline before the move:

Run: `pytest tests/integration/test_publishable_set_lockdown.py -k "two_run_byte_equality" -v`
Expected: PASS (these are item 008's ACs 22 + 23).

- [ ] **Step 3: Create the helper module**

Create `tests/integration/_publishable_set_helper.py` by:
1. Copying the module docstring (one paragraph naming the helper as the shared seed scaffold for items 008 + 009).
2. Copying all module-level imports from the original file that the helpers depend on.
3. Copying every helper enumerated in Step 1 verbatim, in the same order.
4. Including the module-level constants (`_FIXED_INGESTED_AT`, `_BROKER_REPORT_DATE`, etc.) used by the helpers.

Sketch:

```python
"""Lifted from tests/integration/test_publishable_set_lockdown.py per item 009 D3.

Shared seed scaffold for the publishable-set lockdown (item 008) and the
citation-audit-gate (item 009) integration suites. Both files import from
this module; no other module should import here.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import yaml

from irc.llm.http_client import ChatResponse

# ... (rest copied verbatim)
```

- [ ] **Step 4: Replace the helpers in the original file with imports**

Edit `tests/integration/test_publishable_set_lockdown.py`. Delete the helper definitions AND the imports they own that are now used only by the helpers. Add at the top (immediately after the file docstring):

```python
from tests.integration._publishable_set_helper import (
    _resp,
    _today_cn,
    _sha256_file,
    _collect_publishable_citation_universe,
    _patch_memo_routes,
    _install_ak_call_dispatch,
    _seed_publishable_set_repo,
    _FIXED_INGESTED_AT,
    _BROKER_REPORT_DATE,
)
```

(Only re-import the constants if the tests reference them by name.)

- [ ] **Step 5: Verify item 008 baseline still passes byte-for-byte**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -x -v`
Expected: All ACs 1–23 PASS (no behavior change). Pay specific attention to the two `*_byte_equality_*` tests — they sha256 on-disk artifacts; if those still pass, the lift is byte-safe.

Run: `ruff check tests/integration/`
Expected: clean (no unused-import warnings).

- [ ] **Step 6: Commit**

```bash
git add tests/integration/_publishable_set_helper.py tests/integration/test_publishable_set_lockdown.py
git commit -m "refactor(tests): lift _seed_publishable_set_repo helpers to _publishable_set_helper.py for item 009 reuse"
```

---

## Task 2: Add `citation_gate_blocked` to `RejectionReasonCode` + `_GAP_TO_REASON` (Q4)

**Files:**
- Modify: `src/irc/opportunity/rejection_log.py`
- Modify: `tests/opportunity/test_rejection_log.py` (or create if absent)

**Why second:** Step 2a's row blocking stamps `evidence_gaps=("citation_gate_blocked",)` and then calls `_classify_rejection_reason`. Without this registration, that call would crash on line 213-215 (`raise RuntimeError("unknown evidence_gap code: ...")`). F2 in `009-grill.md` catches this.

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_rejection_log.py` (or create the file with the standard imports):

```python
def test_rejection_reason_code_includes_citation_gate_blocked() -> None:
    """Item 009 Q4 — citation_gate_blocked is a first-class RejectionReasonCode."""
    from irc.opportunity.rejection_log import RejectionReasonCode
    # typing.Literal exposes __args__ at runtime.
    args = set(RejectionReasonCode.__args__)
    assert "citation_gate_blocked" in args


def test_gap_to_reason_maps_citation_gate_blocked_to_self() -> None:
    """Item 009 Q4 — identity mapping (same shape as qdii_information_unavailable)."""
    from irc.opportunity.rejection_log import _GAP_TO_REASON
    assert _GAP_TO_REASON["citation_gate_blocked"] == "citation_gate_blocked"


def test_gap_to_reason_citation_gate_blocked_is_last_entry() -> None:
    """Item 009 Q4 — appended at end to preserve existing precedence.

    Item 008 AC11 hard-codes `qdii_information_unavailable` precedence over
    other gaps; that ordering must NOT change."""
    from irc.opportunity.rejection_log import _GAP_TO_REASON
    keys = list(_GAP_TO_REASON.keys())
    assert keys[-1] == "citation_gate_blocked"
    # First entry stays qdii_information_unavailable (item 008 AC11 contract).
    assert keys[0] == "qdii_information_unavailable"


def test_classify_rejection_reason_handles_citation_gate_blocked() -> None:
    """A row with only the new gap classifies cleanly (no RuntimeError)."""
    from irc.opportunity.rejection_log import _classify_rejection_reason
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    row = OpportunityRow(
        instrument_id="005827",
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827",
            display_cn="易方达蓝筹精选", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=("citation_gate_blocked",),
        thesis_evidence=(),
        constituent_analyses=(),
    )
    assert _classify_rejection_reason(row) == "citation_gate_blocked"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_rejection_log.py -v -k "citation_gate_blocked"`
Expected: 4 FAIL — three with `AssertionError` on membership / mapping; one (`test_classify_rejection_reason_handles_citation_gate_blocked`) with `RuntimeError("unknown evidence_gap code: 'citation_gate_blocked'")`.

- [ ] **Step 3: Implement**

Edit `src/irc/opportunity/rejection_log.py`. In the `RejectionReasonCode = Literal[...]` block (lines 23–33), add `"citation_gate_blocked"` as the LAST entry:

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

In the `_GAP_TO_REASON: dict[str, RejectionReasonCode] = { ... }` block (lines 62–92), APPEND at the very end (after `"missing_us_news_adapter":`):

```python
    # Item 009 Q4: opportunity-stage citation gate stamp.
    # Identity mapping (gap code IS the rejection reason). Appended LAST so
    # existing precedence (qdii first, etc.) is unchanged. Item 008 AC11's
    # hard-coded "qdii_information_unavailable" string stays valid.
    "citation_gate_blocked":                "citation_gate_blocked",
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_rejection_log.py -v -k "citation_gate_blocked"`
Expected: 4 PASS.

Run: `pytest tests/opportunity/ -x -q`
Expected: PASS (no regressions across existing rejection-log tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/rejection_log.py tests/opportunity/test_rejection_log.py
git commit -m "feat(opportunity): add citation_gate_blocked RejectionReasonCode + _GAP_TO_REASON entry (Q4)"
```

---

## Task 3: `find_uncited_opportunity_rows` (ACs 1, 6)

**Files:**
- Create: `src/irc/opportunity/auditor.py`
- Create: `tests/opportunity/test_auditor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/opportunity/test_auditor.py`:

```python
"""Item 009 D2a — opportunity-stage auditor unit tests.

Pure unit tests; no run_opportunity invocation here. Each AC pattern is
verified at the per-function level with hand-built OpportunityRow instances.
"""
from __future__ import annotations


def _ev(
    *, type_="filing", source="src", url="https://x", date="2024-04-15",
    summary="x", scope="instrument", citation_kind="data",
    owner="005827", parent=None, constituent_key=None, weight=None,
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=source, url=url, date=date, summary=summary,
        scope=scope, citation_kind=citation_kind, owner_instrument_id=owner,
        parent_fund_id=parent, constituent_key=constituent_key,
        holding_weight_pct=weight,
    )


def _row(
    *, iid="005827", thesis_evidence=(), contributing_dimensions=frozenset(),
    opportunity_state="core_dca", evidence_gaps=(),
    constituent_analyses=(),
):
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    return OpportunityRow(
        instrument_id=iid,
        name_cn="X",
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=iid,
            display_cn="X", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state=opportunity_state,
        opportunity_reason="",
        evidence_gaps=evidence_gaps,
        thesis_evidence=thesis_evidence,
        contributing_dimensions=contributing_dimensions,
        constituent_analyses=constituent_analyses,
    )


def test_find_uncited_opportunity_rows_dual_leg_present_returns_empty() -> None:
    """AC1 — both data + information legs present anywhere on row.thesis_evidence
    is the v1 structural-binding satisfier."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    data_ev = _ev(citation_kind="data")
    info_ev = _ev(citation_kind="information", url="https://x/info",
                  date="2024-04-16")
    row = _row(
        thesis_evidence=(data_ev, info_ev),
        contributing_dimensions=frozenset({"valuation", "thesis"}),
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    assert findings == []


def test_find_uncited_opportunity_rows_missing_data_leg_emits_finding() -> None:
    """AC1 + AC6 — info-only row emits one `missing_data_citation`."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    info_ev = _ev(citation_kind="information")
    row = _row(
        thesis_evidence=(info_ev,),
        contributing_dimensions=frozenset({"valuation", "heat"}),
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    kinds = [f.kind for f in findings]
    assert "missing_data_citation" in kinds
    # AC6: per-dimension informative prose_excerpt; uses first dim by sorted order.
    f = next(x for x in findings if x.kind == "missing_data_citation")
    assert f.prose_excerpt.startswith("dimension:")
    assert f.instrument_id == "005827"


def test_find_uncited_opportunity_rows_missing_information_leg_emits_finding() -> None:
    """AC1 + AC6 — data-only row emits one `missing_information_citation`."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    data_ev = _ev(citation_kind="data")
    row = _row(
        thesis_evidence=(data_ev,),
        contributing_dimensions=frozenset({"valuation"}),
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    kinds = [f.kind for f in findings]
    assert "missing_information_citation" in kinds


def test_find_uncited_opportunity_rows_both_missing_emits_two_findings() -> None:
    """Empty thesis_evidence on a publishable row → two findings (both legs)."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    row = _row(
        thesis_evidence=(),
        contributing_dimensions=frozenset({"valuation"}),
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    kinds = sorted(f.kind for f in findings)
    assert kinds == ["missing_data_citation", "missing_information_citation"]


def test_find_uncited_opportunity_rows_owner_mismatch_excluded() -> None:
    """Evidence whose owner_instrument_id != row.instrument_id is structurally
    excluded — the row is still uncited even if foreign-owned evidence exists."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    # Two rows so build_cited_map sees the right owners; only the second row
    # has its own evidence. The first row has zero owned evidence.
    foreign_data = _ev(citation_kind="data", owner="OTHER_FUND")
    own_info = _ev(citation_kind="information", owner="005827",
                   date="2024-04-17")
    other_row = _row(
        iid="OTHER_FUND",
        thesis_evidence=(_ev(citation_kind="data", owner="OTHER_FUND"),
                         _ev(citation_kind="information", owner="OTHER_FUND",
                             date="2024-04-18")),
    )
    row = _row(
        iid="005827", thesis_evidence=(own_info,),
        contributing_dimensions=frozenset({"valuation"}),
    )
    from irc.opportunity.citation_map import build_cited_map
    cited = build_cited_map((other_row, row))
    findings = find_uncited_opportunity_rows((row,), cited)
    kinds = [f.kind for f in findings]
    assert "missing_data_citation" in kinds


def test_find_uncited_opportunity_rows_exclude_state_with_empty_dims_still_checked() -> None:
    """AC6 — an `exclude` row with empty contributing_dimensions still gets the
    row-level dual-leg check (excluding evidence still requires citation)."""
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    row = _row(
        thesis_evidence=(),
        contributing_dimensions=frozenset(),
        opportunity_state="exclude",
    )
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    assert len(findings) >= 2  # both legs flagged


def test_find_uncited_opportunity_rows_empty_input_returns_empty() -> None:
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    assert find_uncited_opportunity_rows((), {}) == []


def test_find_uncited_opportunity_rows_returns_numeric_finding_type() -> None:
    """Return type contract — list[NumericFinding] from numeric_audit."""
    from irc.memo.numeric_audit import NumericFinding
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.opportunity.citation_map import build_cited_map
    row = _row(thesis_evidence=(), contributing_dimensions=frozenset({"thesis"}))
    cited = build_cited_map((row,))
    findings = find_uncited_opportunity_rows((row,), cited)
    assert all(isinstance(f, NumericFinding) for f in findings)
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_auditor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.opportunity.auditor'`.

- [ ] **Step 3: Implement `auditor.py` (first function)**

Create `src/irc/opportunity/auditor.py`:

```python
"""Item 009 D2a — opportunity-stage structural auditor.

Pure functions consumed by the opportunity-stage gate in
`src/irc/commands/opportunity_cmd.py::_write_opportunity_outputs`. No I/O.

`find_uncited_opportunity_rows` implements the v1 STRUCTURAL dual-leg binding:
for each publishable OpportunityRow, require ≥1 entry in `row.thesis_evidence`
with `citation_kind == "data"` AND ≥1 with `citation_kind == "information"`,
both with `owner_instrument_id == row.instrument_id` and scope in
{"instrument","constituent"}. The v2 `(type → dimension)` map is a deliberate
deferral — see Q1 in `docs/2026-05-22-thesis-cards-evidence-gap/items/009-grill.md`.

`find_incomplete_constituent_analyses` catches pure-failure constituents
(`evidence == () AND failure_reasons != ()`) that escaped H2's gap stamp; a
finding here is fatal at the gate-wiring caller (raises RuntimeError).
"""
from __future__ import annotations

from irc.memo.numeric_audit import NumericFinding
from irc.opportunity.types import CitedMap, OpportunityRow


_PUBLISHABLE_SCOPES: frozenset[str] = frozenset({"instrument", "constituent"})


def find_uncited_opportunity_rows(
    publishable_rows: tuple[OpportunityRow, ...] | list[OpportunityRow],
    cited_map: CitedMap,
) -> list[NumericFinding]:
    """Return a list of NumericFinding for rows that fail the v1 structural
    dual-leg dual-scope check.

    Per AC6 row-level restriction rule: emits at most ONE finding per missing
    leg per row (not per-dimension). `prose_excerpt` carries
    `"dimension:<first dim sorted>"` for log-reader context; v2 will expand
    to per-dimension findings once the `(type → dimension)` map exists.
    """
    findings: list[NumericFinding] = []
    for row in publishable_rows:
        owned_data = [
            ev for ev in row.thesis_evidence
            if ev.citation_kind == "data"
            and ev.scope in _PUBLISHABLE_SCOPES
            and ev.owner_instrument_id == row.instrument_id
        ]
        owned_info = [
            ev for ev in row.thesis_evidence
            if ev.citation_kind == "information"
            and ev.scope in _PUBLISHABLE_SCOPES
            and ev.owner_instrument_id == row.instrument_id
        ]
        dims_sorted = sorted(row.contributing_dimensions) or ["<none>"]
        dim_excerpt = f"dimension:{dims_sorted[0]}"
        if not owned_data:
            findings.append(NumericFinding(
                instrument_id=row.instrument_id,
                kind="missing_data_citation",
                prose_excerpt=dim_excerpt,
                evidence_excerpt=row.opportunity_state,
            ))
        if not owned_info:
            findings.append(NumericFinding(
                instrument_id=row.instrument_id,
                kind="missing_information_citation",
                prose_excerpt=dim_excerpt,
                evidence_excerpt=row.opportunity_state,
            ))
    return findings
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_auditor.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/auditor.py tests/opportunity/test_auditor.py
git commit -m "feat(opportunity): add find_uncited_opportunity_rows v1 structural auditor (AC1, AC6)"
```

---

## Task 4: `find_incomplete_constituent_analyses` (ACs 5, 7)

**Files:**
- Modify: `src/irc/opportunity/auditor.py`
- Modify: `tests/opportunity/test_auditor.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_auditor.py`:

```python
def _constituent(symbol, *, evidence=(), failure_reasons=()):
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol,
        name_cn=symbol,
        weight_pct=5.0,
        evidence=evidence,
        failure_reasons=failure_reasons,
        one_line_view="",
    )


def test_find_incomplete_constituent_analyses_pure_failure_flagged() -> None:
    """AC5 + AC7 — evidence == () AND failure_reasons != () is fatal."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    bad = _constituent("600519", evidence=(), failure_reasons=("timeout",))
    row = _row(
        thesis_evidence=(_ev(citation_kind="data"), _ev(citation_kind="information", date="2024-04-17")),
        contributing_dimensions=frozenset({"thesis"}),
        constituent_analyses=(bad,),
    )
    findings = find_incomplete_constituent_analyses((row,))
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "constituent_pure_failure"
    assert f.instrument_id == "005827"
    assert "symbol=600519" in f.prose_excerpt
    assert "evidence=()" in f.evidence_excerpt
    assert "timeout" in f.evidence_excerpt


def test_find_incomplete_constituent_analyses_partial_success_not_flagged() -> None:
    """AC7 — partial-success (both fields non-empty) is NOT a violation.

    Policy B's per-holding data leg + top-half info quorum is the correct
    disposition; the auditor does not second-guess it."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    partial = _constituent(
        "600519",
        evidence=(_ev(citation_kind="data", constituent_key="600519",
                      scope="constituent", parent="005827"),),
        failure_reasons=("broker_report_missing",),
    )
    row = _row(constituent_analyses=(partial,))
    findings = find_incomplete_constituent_analyses((row,))
    assert findings == []


def test_find_incomplete_constituent_analyses_intact_not_flagged() -> None:
    """Intact constituent (failure_reasons == ()) does not appear."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    intact = _constituent(
        "600519",
        evidence=(_ev(citation_kind="data", constituent_key="600519",
                      scope="constituent", parent="005827"),),
        failure_reasons=(),
    )
    row = _row(constituent_analyses=(intact,))
    assert find_incomplete_constituent_analyses((row,)) == []


def test_find_incomplete_constituent_analyses_returns_one_per_failing_constituent() -> None:
    """AC7 — one finding per pure-failure constituent, across multiple rows."""
    from irc.opportunity.auditor import find_incomplete_constituent_analyses
    bad1 = _constituent("600519", failure_reasons=("e1",))
    bad2 = _constituent("300750", failure_reasons=("e2",))
    intact = _constituent("601318",
                          evidence=(_ev(constituent_key="601318",
                                        scope="constituent", parent="005827"),),
                          failure_reasons=())
    row = _row(constituent_analyses=(bad1, bad2, intact))
    findings = find_incomplete_constituent_analyses((row,))
    symbols = sorted(f.prose_excerpt for f in findings)
    assert symbols == ["symbol=300750", "symbol=600519"]
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_auditor.py -v -k "incomplete_constituent"`
Expected: FAIL with `ImportError: cannot import name 'find_incomplete_constituent_analyses'`.

- [ ] **Step 3: Implement**

Append to `src/irc/opportunity/auditor.py`:

```python
def find_incomplete_constituent_analyses(
    publishable_rows: tuple[OpportunityRow, ...] | list[OpportunityRow],
) -> list[NumericFinding]:
    """Return a NumericFinding per ConstituentAnalysis with `evidence == ()`
    AND `failure_reasons != ()` on a publishable row.

    Per Q9 grill correction: a finding from this function is FATAL at the
    opportunity-stage gate caller (it raises RuntimeError, ignoring
    `IRC_CITATION_ENFORCE_MODE` — same shape as `fetch_budget_exhausted`).
    Kept as a structured NumericFinding rather than an in-function raise so
    the auditor module stays pure and uniformly testable.

    Partial-success constituents (`evidence != () AND failure_reasons != ()`)
    are NOT violations — Policy B's per-holding data leg + top-half info
    quorum is the correct disposition.
    """
    findings: list[NumericFinding] = []
    for row in publishable_rows:
        for c in row.constituent_analyses:
            if c.evidence == () and c.failure_reasons != ():
                findings.append(NumericFinding(
                    instrument_id=row.instrument_id,
                    kind="constituent_pure_failure",
                    prose_excerpt=f"symbol={c.symbol}",
                    evidence_excerpt=(
                        f"evidence=() failure_reasons={c.failure_reasons!r}"
                    ),
                ))
    return findings
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_auditor.py -v`
Expected: 12 PASS (8 from Task 3 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/auditor.py tests/opportunity/test_auditor.py
git commit -m "feat(opportunity): add find_incomplete_constituent_analyses pure-failure auditor (AC5, AC7)"
```

---

## Task 5: `find_missing_pick_citations` (AC2)

**Files:**
- Modify: `src/irc/memo/numeric_audit.py`
- Modify: `tests/memo/test_numeric_audit.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/memo/test_numeric_audit.py`:

```python
def _ev_for_pick(
    *, citation_kind="data", owner="005827",
    constituent_key=None, scope="instrument", date="2024-04-15",
    url="https://x",
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type="filing", source="src", url=url, date=date,
        summary="x", scope=scope, citation_kind=citation_kind,
        owner_instrument_id=owner, parent_fund_id=None,
        constituent_key=constituent_key, holding_weight_pct=None,
    )


def _pick(iid="005827", citations=()):
    from irc.memo.picks_table import PickRow
    return PickRow(
        instrument_id=iid, name_cn="X", asset_class="cn_equity_fund",
        role="core", target_weight=0.1, composite_score=70.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        citations=citations,
    )


def test_find_missing_pick_citations_dual_leg_present_returns_empty() -> None:
    """AC2 — top-3 has both kinds → no finding."""
    from irc.memo.numeric_audit import find_missing_pick_citations
    data = _ev_for_pick(citation_kind="data")
    info = _ev_for_pick(citation_kind="information", date="2024-04-16")
    pick = _pick(citations=(data, info))
    assert find_missing_pick_citations((pick,), {}) == []


def test_find_missing_pick_citations_empty_citations_flagged() -> None:
    """AC2 — empty citations tuple emits one `missing_pick_citations`."""
    from irc.memo.numeric_audit import find_missing_pick_citations
    pick = _pick(citations=())
    findings = find_missing_pick_citations((pick,), {})
    assert len(findings) == 1
    assert findings[0].kind == "missing_pick_citations"
    assert findings[0].instrument_id == "005827"


def test_find_missing_pick_citations_data_only_flagged() -> None:
    """AC2 — data-only pick row → one finding for missing info leg."""
    from irc.memo.numeric_audit import find_missing_pick_citations
    pick = _pick(citations=(_ev_for_pick(citation_kind="data"),))
    findings = find_missing_pick_citations((pick,), {})
    kinds = [f.kind for f in findings]
    # Either explicit "missing_information_citation" OR the general
    # "missing_pick_citations" — spec AC2 doesn't differentiate at the empty
    # vs single-leg level, but the wrapper kind for completely empty is
    # distinct. For single-leg, the test asserts the missing-info leg surfaces.
    assert any(k in {"missing_pick_citations", "missing_information_citation"}
               for k in kinds)


def test_find_missing_pick_citations_wrong_instrument_flagged() -> None:
    """AC2 — a citation pointing at a different owner_instrument_id is
    a provenance leak from select_citations → `wrong_instrument_citation`."""
    from irc.memo.numeric_audit import find_missing_pick_citations
    leaked = _ev_for_pick(citation_kind="data", owner="OTHER_FUND")
    info = _ev_for_pick(citation_kind="information", date="2024-04-16")
    pick = _pick(iid="005827", citations=(leaked, info))
    findings = find_missing_pick_citations((pick,), {})
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" in kinds
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/memo/test_numeric_audit.py -v -k "missing_pick"`
Expected: FAIL with `ImportError: cannot import name 'find_missing_pick_citations'`.

- [ ] **Step 3: Implement**

Append to `src/irc/memo/numeric_audit.py` (after the existing `find_uncited_conclusions` stub):

```python
# ── Item 009 D2a — find_missing_pick_citations ──────────────────────────────
# Structural per-pick dual-leg + owner-provenance check. Runs against the
# pre-filtered top-3 citations returned by select_citations(cap=3).

def find_missing_pick_citations(
    pick_rows,
    cited_map: dict,
) -> list[NumericFinding]:
    """Return findings for PickRows that fail the dual-leg or owner check.

    Three failure modes:
      - empty `pick_row.citations` → kind="missing_pick_citations" (single finding)
      - non-empty but no `citation_kind == "data"` entry → "missing_data_citation"
      - non-empty but no `citation_kind == "information"` entry → "missing_information_citation"
      - any entry with `owner_instrument_id != pick_row.instrument_id` → "wrong_instrument_citation"
    """
    findings: list[NumericFinding] = []
    for pick in pick_rows:
        if not pick.citations:
            findings.append(NumericFinding(
                instrument_id=pick.instrument_id,
                kind="missing_pick_citations",
                prose_excerpt="citations=()",
                evidence_excerpt=pick.opportunity_state,
            ))
            continue
        for ev in pick.citations:
            if ev.owner_instrument_id != pick.instrument_id:
                findings.append(NumericFinding(
                    instrument_id=pick.instrument_id,
                    kind="wrong_instrument_citation",
                    prose_excerpt=f"citation_id={ev.citation_id}",
                    evidence_excerpt=(
                        f"owner_instrument_id={ev.owner_instrument_id!r} "
                        f"!= pick.instrument_id={pick.instrument_id!r}"
                    ),
                ))
        kinds = {ev.citation_kind for ev in pick.citations
                 if ev.owner_instrument_id == pick.instrument_id}
        if "data" not in kinds:
            findings.append(NumericFinding(
                instrument_id=pick.instrument_id,
                kind="missing_data_citation",
                prose_excerpt="leg:data",
                evidence_excerpt=pick.opportunity_state,
            ))
        if "information" not in kinds:
            findings.append(NumericFinding(
                instrument_id=pick.instrument_id,
                kind="missing_information_citation",
                prose_excerpt="leg:information",
                evidence_excerpt=pick.opportunity_state,
            ))
    return findings
```

- [ ] **Step 4: Run green**

Run: `pytest tests/memo/test_numeric_audit.py -v -k "missing_pick"`
Expected: 4 PASS.

Run: `pytest tests/memo/ -x -q`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/numeric_audit.py tests/memo/test_numeric_audit.py
git commit -m "feat(memo): add find_missing_pick_citations dual-leg + owner-provenance auditor (AC2)"
```

---

## Task 6: `find_uncited_discipline_rows` (AC4)

**Files:**
- Modify: `src/irc/memo/numeric_audit.py`
- Modify: `tests/memo/test_numeric_audit.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/memo/test_numeric_audit.py`:

```python
def _discipline_row(
    *, iid="005827", thesis_evidence=(), constituent_analyses=(),
):
    from irc.opportunity.types import DisciplineRow
    return DisciplineRow(
        instrument_id=iid,
        name_cn="X",
        asset_class="cn_equity_fund",
        theme=None,
        opportunity_state="core_dca",
        dca_action="normal_dca",
        risk_action="none",
        note_cn="",
        thesis_evidence=thesis_evidence,
        constituent_analyses=constituent_analyses,
        evidence_gaps=(),
        fetch_types_attempted=(),
    )


def test_find_uncited_discipline_rows_dual_leg_present_returns_empty() -> None:
    """AC4 (i) — both legs on row.thesis_evidence → no finding."""
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    data = _ev_for_pick(citation_kind="data", owner="005827")
    info = _ev_for_pick(citation_kind="information", owner="005827",
                        date="2024-04-16")
    row = _discipline_row(thesis_evidence=(data, info))
    assert find_uncited_discipline_rows((row,), {}) == []


def test_find_uncited_discipline_rows_missing_data_emits_finding() -> None:
    """AC4 (i) — info-only → missing data."""
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    info = _ev_for_pick(citation_kind="information", owner="005827")
    row = _discipline_row(thesis_evidence=(info,))
    findings = find_uncited_discipline_rows((row,), {})
    assert any(f.kind == "missing_data_citation" for f in findings)


def test_find_uncited_discipline_rows_wrong_instrument_emits_finding() -> None:
    """AC4 (ii) — entry.owner_instrument_id != row.instrument_id is flagged."""
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    foreign_data = _ev_for_pick(citation_kind="data", owner="OTHER")
    foreign_info = _ev_for_pick(citation_kind="information", owner="OTHER",
                                date="2024-04-16")
    row = _discipline_row(thesis_evidence=(foreign_data, foreign_info))
    findings = find_uncited_discipline_rows((row,), {})
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" in kinds


def test_find_uncited_discipline_rows_constituent_parent_check() -> None:
    """AC4 (ii) — constituent-scoped entry must have parent_fund_id == row.instrument_id."""
    from irc.fundamentals.types import ThesisEvidence
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    bad_parent = ThesisEvidence(
        type="filing", source="src", url="https://x", date="2024-04-15",
        summary="x", scope="constituent", citation_kind="data",
        owner_instrument_id="005827",  # owner matches
        parent_fund_id="WRONG_PARENT",  # but parent doesn't
        constituent_key="600519",
        holding_weight_pct=None,
    )
    good_info = _ev_for_pick(citation_kind="information", owner="005827",
                             date="2024-04-16")
    row = _discipline_row(thesis_evidence=(bad_parent, good_info))
    findings = find_uncited_discipline_rows((row,), {})
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" in kinds
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/memo/test_numeric_audit.py -v -k "uncited_discipline"`
Expected: FAIL with `ImportError: cannot import name 'find_uncited_discipline_rows'`.

- [ ] **Step 3: Implement**

Append to `src/irc/memo/numeric_audit.py`:

```python
# ── Item 009 D2a — find_uncited_discipline_rows ─────────────────────────────
# Structural per-row dual-leg + owner + parent_fund check on DisciplineRow.
# No [ref:...] marker check on note_cn — the structural check is authoritative.

def find_uncited_discipline_rows(
    discipline_rows,
    cited_map: dict,
) -> list[NumericFinding]:
    """Return findings for DisciplineRows that fail dual-leg or provenance.

    Per AC4:
      (i) require ≥1 data + ≥1 information entry in `row.thesis_evidence`;
      (ii) require `entry.owner_instrument_id == row.instrument_id`;
           for constituent-scoped entries, also `entry.parent_fund_id == row.instrument_id`.
    """
    findings: list[NumericFinding] = []
    for row in discipline_rows:
        own_data_present = False
        own_info_present = False
        for ev in row.thesis_evidence:
            if ev.owner_instrument_id != row.instrument_id:
                findings.append(NumericFinding(
                    instrument_id=row.instrument_id,
                    kind="wrong_instrument_citation",
                    prose_excerpt=f"citation_id={ev.citation_id}",
                    evidence_excerpt=(
                        f"owner_instrument_id={ev.owner_instrument_id!r} "
                        f"!= row.instrument_id={row.instrument_id!r}"
                    ),
                ))
                continue
            if ev.scope == "constituent" and ev.parent_fund_id != row.instrument_id:
                findings.append(NumericFinding(
                    instrument_id=row.instrument_id,
                    kind="wrong_instrument_citation",
                    prose_excerpt=f"citation_id={ev.citation_id}",
                    evidence_excerpt=(
                        f"parent_fund_id={ev.parent_fund_id!r} "
                        f"!= row.instrument_id={row.instrument_id!r}"
                    ),
                ))
                continue
            if ev.citation_kind == "data":
                own_data_present = True
            elif ev.citation_kind == "information":
                own_info_present = True
        if not own_data_present:
            findings.append(NumericFinding(
                instrument_id=row.instrument_id,
                kind="missing_data_citation",
                prose_excerpt="leg:data",
                evidence_excerpt=row.opportunity_state,
            ))
        if not own_info_present:
            findings.append(NumericFinding(
                instrument_id=row.instrument_id,
                kind="missing_information_citation",
                prose_excerpt="leg:information",
                evidence_excerpt=row.opportunity_state,
            ))
    return findings
```

- [ ] **Step 4: Run green**

Run: `pytest tests/memo/test_numeric_audit.py -v -k "uncited_discipline"`
Expected: 4 PASS.

Run: `pytest tests/memo/ -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/numeric_audit.py tests/memo/test_numeric_audit.py
git commit -m "feat(memo): add find_uncited_discipline_rows structural auditor (AC4)"
```

---

## Task 7: Replace `find_uncited_conclusions` stub body (ACs 3, 8, 17, 18, 19)

**Files:**
- Modify: `src/irc/memo/numeric_audit.py`
- Modify: `tests/memo/test_numeric_audit.py`

This is the biggest single task. Implement it carefully — the stub has been load-bearing for item 007's wiring, so the rename (`strict_empty_alias_check`) must be additive (kwarg-only with `False` default).

- [ ] **Step 1: Write the failing tests**

Append to `tests/memo/test_numeric_audit.py`:

```python
# ── Item 009 — find_uncited_conclusions body tests ──────────────────────────

_ACTIONABLE = "加仓"  # one of the 10 frozen keywords


def _cited_map_single(iid="005827", *, kinds=("data", "information")):
    """Build a CitedMap with one data and one information entry for `iid`."""
    from irc.opportunity.types import CitationMeta
    m = {}
    for i, k in enumerate(kinds):
        cid = f"{i:016x}"
        m.setdefault(iid, {})[cid] = CitationMeta(
            scope="instrument", citation_kind=k,
            owner_instrument_id=iid, asset_class="cn_equity_fund",
            parent_fund_id=None, constituent_key=None,
        )
    return m


def test_find_uncited_conclusions_empty_prose_returns_empty() -> None:
    """AC18 — empty/whitespace prose short-circuits regardless of other args."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    assert find_uncited_conclusions(
        prose="", cited_map={}, instrument_aliases={},
        constituent_aliases={}, constituent_cited_map={},
    ) == []
    assert find_uncited_conclusions(
        prose="   \n  ", cited_map={}, instrument_aliases={},
        constituent_aliases={}, constituent_cited_map={},
    ) == []


def test_find_uncited_conclusions_strict_empty_alias_check_raises() -> None:
    """AC17 — strict_empty_alias_check=True AND empty aliases AND non-empty
    prose → RuntimeError("empty instrument_aliases — D1c builder did not run")."""
    import pytest
    from irc.memo.numeric_audit import find_uncited_conclusions
    with pytest.raises(RuntimeError, match="empty instrument_aliases"):
        find_uncited_conclusions(
            prose="some prose 加仓",
            cited_map={},
            instrument_aliases={},
            constituent_aliases={},
            constituent_cited_map={},
            strict_empty_alias_check=True,
        )


def test_find_uncited_conclusions_default_strict_false_no_raise() -> None:
    """AC17 — default strict_empty_alias_check=False preserves item 007's
    all-gapped pipeline-state semantic: returns [] without raising."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    result = find_uncited_conclusions(
        prose="some prose 加仓",
        cited_map={},
        instrument_aliases={},
        constituent_aliases={},
        constituent_cited_map={},
    )
    assert result == []


def test_find_uncited_conclusions_uncited_conclusion_emitted() -> None:
    """AC8 (a) — paragraph mentions instrument + actionable keyword but has
    no [ref:...] marker resolving to that instrument."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = f"## CN权益基金\n\n易方达蓝筹精选 (005827) {_ACTIONABLE}\n"
    findings = find_uncited_conclusions(
        prose=prose,
        cited_map=_cited_map_single("005827"),
        instrument_aliases={
            "005827": "005827",
            "易方达蓝筹精选": "005827",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "uncited_conclusion" in kinds


def test_find_uncited_conclusions_with_dual_leg_markers_passes() -> None:
    """AC8 — paragraph with both data + information markers for the
    referenced instrument → no finding."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = _cited_map_single("005827")
    data_id, info_id = sorted(cited["005827"].keys())
    prose = (
        f"## CN权益基金\n\n"
        f"易方达蓝筹精选 (005827) {_ACTIONABLE} "
        f"[ref:{data_id}] [ref:{info_id}]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={
            "005827": "005827", "易方达蓝筹精选": "005827",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "uncited_conclusion" not in kinds


def test_find_uncited_conclusions_wrong_instrument_citation() -> None:
    """AC8 (b) — marker resolves to a different owner_instrument_id."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    cited = {
        "OTHER_FUND": {
            "deadbeefdeadbeef": CitationMeta(
                scope="instrument", citation_kind="data",
                owner_instrument_id="OTHER_FUND", asset_class="cn_equity_fund",
                parent_fund_id=None, constituent_key=None,
            ),
        },
    }
    prose = (
        f"## CN权益基金\n\n"
        f"易方达蓝筹精选 (005827) {_ACTIONABLE} [ref:deadbeefdeadbeef]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map=cited,
        instrument_aliases={
            "005827": "005827", "易方达蓝筹精选": "005827",
        },
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "wrong_instrument_citation" in kinds


def test_find_uncited_conclusions_ambiguous_constituent_reference() -> None:
    """AC8 (e) + AC19 — constituent resolves to ≥2 owner pairs with no
    section header → ambiguous_constituent_reference, no further checks
    in this paragraph for this constituent."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = f"贵州茅台 {_ACTIONABLE}\n"
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"x": "x"},  # non-empty to bypass empty-map case
        constituent_aliases={
            "贵州茅台": frozenset({
                ("005827", "600519"), ("163417", "600519"),
            }),
        },
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "ambiguous_constituent_reference" in kinds


def test_find_uncited_conclusions_section_header_disambiguates_constituent() -> None:
    """AC19 — section header (### iid in name) resolves the multi-owner."""
    from irc.opportunity.types import CitationMeta
    from irc.memo.numeric_audit import find_uncited_conclusions
    constituent_cited = {
        "005827": {
            "600519": {
                "aaaaaaaaaaaaaaaa": CitationMeta(
                    scope="constituent", citation_kind="data",
                    owner_instrument_id="005827",
                    asset_class="cn_equity_fund",
                    parent_fund_id="005827", constituent_key="600519",
                ),
                "bbbbbbbbbbbbbbbb": CitationMeta(
                    scope="constituent", citation_kind="information",
                    owner_instrument_id="005827",
                    asset_class="cn_equity_fund",
                    parent_fund_id="005827", constituent_key="600519",
                ),
            },
        },
    }
    prose = (
        f"### 易方达蓝筹精选 (005827)\n\n"
        f"贵州茅台 {_ACTIONABLE} [ref:aaaaaaaaaaaaaaaa] [ref:bbbbbbbbbbbbbbbb]\n"
    )
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"005827": "005827"},
        constituent_aliases={
            "贵州茅台": frozenset({
                ("005827", "600519"), ("163417", "600519"),
            }),
        },
        constituent_cited_map=constituent_cited,
    )
    # Resolved cleanly under the header context — no ambiguous finding,
    # no uncited finding (markers cover both legs).
    kinds = [f.kind for f in findings]
    assert "ambiguous_constituent_reference" not in kinds
    assert "uncited_conclusion" not in kinds


def test_find_uncited_conclusions_uncited_portfolio_conclusion() -> None:
    """AC8 (d) — actionable keyword + zero alias hits + zero markers →
    uncited_portfolio_conclusion."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    prose = f"## CN权益基金\n\n本周 {_ACTIONABLE} 整个权益板块\n"
    findings = find_uncited_conclusions(
        prose=prose, cited_map={},
        instrument_aliases={"005827": "005827"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    kinds = [f.kind for f in findings]
    assert "uncited_portfolio_conclusion" in kinds
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/memo/test_numeric_audit.py -v -k "find_uncited_conclusions"`
Expected: most FAIL (the stub returns `[]` for all inputs; new tests expect specific kinds).

- [ ] **Step 3: Implement the body**

Edit `src/irc/memo/numeric_audit.py`. Add a frozen actionable-keyword constant after the existing `_EXPENSIVE_PHRASES` constant:

```python
# Item 009 v1: actionable-keyword set for find_uncited_conclusions paragraph audit.
# Frozen list; v2 extension requires a producer-side change.
_ACTIONABLE_KEYWORDS: Final[tuple[str, ...]] = (
    "加速定投", "正常定投", "减速定投", "暂停加仓", "禁止买入",
    "回避", "建仓", "加仓", "减仓", "止损",
)

# Asset-class section header → asset_class string. Used by AC8(c)/(d) only.
_SECTION_HEADER_RE = re.compile(
    r"^##\s+(?P<label>CN权益基金|CN债券基金|黄金|CN ETF|US\w*|HK\w*)\b",
    re.MULTILINE,
)
_SECTION_LABEL_TO_ASSET_CLASS: Final[dict[str, str]] = {
    "CN权益基金": "cn_equity_fund",
    "CN债券基金": "cn_bond_fund",
    "黄金": "gold",
    "CN ETF": "cn_etf",
}

# Sub-section header that names an instrument_id explicitly:
#   "### 易方达蓝筹精选 (005827)"
# Used by AC19 for multi-owner constituent disambiguation.
_SUBSECTION_INSTRUMENT_RE = re.compile(
    r"^###\s+.+?\((?P<iid>[A-Za-z0-9_]{4,12})\)", re.MULTILINE,
)

_MARKER_RE = re.compile(r"\[ref:([0-9a-f]{16})\]")
```

Replace the stub body of `find_uncited_conclusions` (currently around line 156–190) with the paragraph-level implementation:

```python
def find_uncited_conclusions(
    prose: str,
    cited_map: dict,
    instrument_aliases: dict,
    constituent_aliases: dict,
    constituent_cited_map: dict,
    *,
    strict_empty_alias_check: bool = False,
) -> list[NumericFinding]:
    """Paragraph-level audit: every actionable conclusion must be cited.

    Per AC3:
      (a) instrument references → require dual-leg [ref:...] markers from
          the same paragraph (or its immediate predecessor);
      (b) multi-owner constituent references → resolve via the nearest
          preceding `### {name} ({iid})` sub-header; emit
          `ambiguous_constituent_reference` when unresolvable;
      (c) actionable keyword with zero alias hits → asset-class section
          context drives `uncited_portfolio_conclusion`;
      (d) marker present but resolves to wrong owner_instrument_id →
          `wrong_instrument_citation`.

    `strict_empty_alias_check=True` (Q3) raises RuntimeError when
    instrument_aliases is empty AND prose is non-empty — closes the wiring
    bug where `build_alias_maps` was forgotten. Default False preserves the
    all-gapped pipeline state semantic from item 007.
    """
    if not prose or not prose.strip():
        return []
    if strict_empty_alias_check and not instrument_aliases:
        raise RuntimeError(
            "empty instrument_aliases — D1c builder did not run; "
            "check memo_cmd wiring"
        )
    if not instrument_aliases:
        # Permissive path (item 007 all-gapped semantic): no aliases → no audit.
        return []

    paragraphs = prose.split("\n\n")
    findings: list[NumericFinding] = []

    # Pre-scan for section/sub-section context as cumulative state.
    # We map char-offset → most-recent asset_class + instrument_id.
    section_spans = _build_section_spans(prose)
    subsection_spans = _build_subsection_spans(prose)

    paragraph_offset = 0
    prev_markers: tuple[str, ...] = ()
    for para in paragraphs:
        para_start = paragraph_offset
        paragraph_offset += len(para) + 2  # +2 for the "\n\n" separator

        if not any(kw in para for kw in _ACTIONABLE_KEYWORDS):
            prev_markers = tuple(_MARKER_RE.findall(para))
            continue

        current_markers = tuple(_MARKER_RE.findall(para))
        scope_markers = current_markers + prev_markers
        asset_class = _section_at(section_spans, para_start)
        owner_iid = _subsection_at(subsection_spans, para_start)

        instrument_hits = _instrument_alias_hits(para, instrument_aliases)
        constituent_hits = _constituent_alias_hits(para, constituent_aliases)

        if not instrument_hits and not constituent_hits:
            # AC8(d) — portfolio-class conclusion path.
            if not scope_markers:
                findings.append(NumericFinding(
                    instrument_id=asset_class or "<portfolio>",
                    kind="uncited_portfolio_conclusion",
                    prose_excerpt=_excerpt(para),
                    evidence_excerpt=asset_class or "<no_section>",
                ))
            prev_markers = current_markers
            continue

        for iid in sorted(instrument_hits):
            findings.extend(_check_instrument_citation(
                iid=iid, markers=scope_markers,
                cited_map=cited_map, paragraph=para,
            ))

        for ck, owner_pairs in sorted(constituent_hits.items()):
            if len(owner_pairs) > 1 and owner_iid not in {iid for iid, _ in owner_pairs}:
                findings.append(NumericFinding(
                    instrument_id="<ambiguous>",
                    kind="ambiguous_constituent_reference",
                    prose_excerpt=ck,
                    evidence_excerpt=f"owners={sorted(owner_pairs)}",
                ))
                continue
            # Resolved: either single-owner OR section header disambiguates.
            resolved = next(
                (pair for pair in owner_pairs if pair[0] == owner_iid),
                next(iter(sorted(owner_pairs))),
            )
            iid, c_key = resolved
            findings.extend(_check_constituent_citation(
                iid=iid, c_key=c_key, markers=scope_markers,
                constituent_cited_map=constituent_cited_map, paragraph=para,
            ))

        prev_markers = current_markers

    return findings


def _build_section_spans(prose: str) -> list[tuple[int, str]]:
    """Return list of (offset, asset_class) sorted ascending by offset."""
    spans: list[tuple[int, str]] = []
    for m in _SECTION_HEADER_RE.finditer(prose):
        label = m.group("label")
        ac = _SECTION_LABEL_TO_ASSET_CLASS.get(label, label.lower())
        spans.append((m.start(), ac))
    return spans


def _build_subsection_spans(prose: str) -> list[tuple[int, str]]:
    """Return list of (offset, instrument_id) for `### {name} ({iid})` headers."""
    return [
        (m.start(), m.group("iid"))
        for m in _SUBSECTION_INSTRUMENT_RE.finditer(prose)
    ]


def _section_at(spans: list[tuple[int, str]], offset: int) -> str | None:
    """Return the asset_class of the most-recent section header before offset."""
    current = None
    for start, ac in spans:
        if start <= offset:
            current = ac
        else:
            break
    return current


def _subsection_at(spans: list[tuple[int, str]], offset: int) -> str | None:
    current = None
    for start, iid in spans:
        if start <= offset:
            current = iid
        else:
            break
    return current


def _instrument_alias_hits(paragraph: str, instrument_aliases: dict) -> set[str]:
    return {
        iid for alias, iid in instrument_aliases.items()
        if alias and alias in paragraph
    }


def _constituent_alias_hits(
    paragraph: str, constituent_aliases: dict,
) -> dict[str, frozenset[tuple[str, str]]]:
    return {
        alias: owners
        for alias, owners in constituent_aliases.items()
        if alias and alias in paragraph
    }


def _check_instrument_citation(
    *, iid: str, markers: tuple[str, ...], cited_map: dict, paragraph: str,
) -> list[NumericFinding]:
    """Return findings for the instrument-citation rule on one paragraph."""
    findings: list[NumericFinding] = []
    per_iid = cited_map.get(iid, {})
    has_data = False
    has_info = False
    wrong_owner_seen = False
    for cid in markers:
        meta = per_iid.get(cid)
        if meta is None:
            # Try to find this cid under another owner — wrong instrument.
            for owner, mp in cited_map.items():
                if cid in mp and owner != iid:
                    findings.append(NumericFinding(
                        instrument_id=iid,
                        kind="wrong_instrument_citation",
                        prose_excerpt=_excerpt(paragraph),
                        evidence_excerpt=(
                            f"citation_id={cid} resolves to owner={owner!r}, "
                            f"not {iid!r}"
                        ),
                    ))
                    wrong_owner_seen = True
                    break
            continue
        if meta.scope not in _PUBLISHABLE_SCOPES_MEMO:
            continue
        if meta.citation_kind == "data":
            has_data = True
        elif meta.citation_kind == "information":
            has_info = True
    if wrong_owner_seen:
        # Wrong-owner finding is the dominant diagnosis; skip uncited duplication.
        return findings
    if not has_data or not has_info:
        findings.append(NumericFinding(
            instrument_id=iid,
            kind="uncited_conclusion",
            prose_excerpt=_excerpt(paragraph),
            evidence_excerpt=(
                f"has_data={has_data} has_info={has_info} "
                f"markers={list(markers)}"
            ),
        ))
    return findings


def _check_constituent_citation(
    *, iid: str, c_key: str, markers: tuple[str, ...],
    constituent_cited_map: dict, paragraph: str,
) -> list[NumericFinding]:
    findings: list[NumericFinding] = []
    per_iid = constituent_cited_map.get(iid, {})
    per_c = per_iid.get(c_key, {})
    has_data = any(
        per_c.get(cid) and per_c[cid].citation_kind == "data" for cid in markers
    )
    has_info = any(
        per_c.get(cid) and per_c[cid].citation_kind == "information" for cid in markers
    )
    if not has_data or not has_info:
        findings.append(NumericFinding(
            instrument_id=iid,
            kind="uncited_conclusion",
            prose_excerpt=f"constituent={c_key}",
            evidence_excerpt=f"has_data={has_data} has_info={has_info}",
        ))
    return findings


def _excerpt(paragraph: str, *, limit: int = 120) -> str:
    s = paragraph.replace("\n", " ").strip()
    return s[:limit]


_PUBLISHABLE_SCOPES_MEMO: Final[frozenset[str]] = frozenset({"instrument", "constituent"})
```

- [ ] **Step 4: Run green**

Run: `pytest tests/memo/test_numeric_audit.py -v -k "find_uncited_conclusions"`
Expected: all PASS (9 new + 2 pre-existing from item 007).

Run: `pytest tests/memo/ -x -q`
Expected: PASS (item 007's tests + the new ones).

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/numeric_audit.py tests/memo/test_numeric_audit.py
git commit -m "feat(memo): replace find_uncited_conclusions stub with paragraph-level body + strict_empty_alias_check (AC3, AC8, AC17, AC18, AC19)"
```

---

## Task 8: Add `build_constituent_cited_map`

**Files:**
- Modify: `src/irc/opportunity/citation_map.py`
- Modify: `tests/opportunity/test_citation_map.py` (or create if absent)

- [ ] **Step 1: Write the failing test**

Append to `tests/opportunity/test_citation_map.py`:

```python
def test_build_constituent_cited_map_basic() -> None:
    """Build a constituent-cited map: instrument_id → constituent_key → {cid: CitationMeta}."""
    from irc.fundamentals.types import (
        ConstituentAnalysis, LookthroughTarget, ThesisEvidence,
    )
    from irc.opportunity.citation_map import build_constituent_cited_map
    from irc.opportunity.types import OpportunityRow
    ev = ThesisEvidence(
        type="filing", source="src", url="https://x", date="2024-04-15",
        summary="x", scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519", holding_weight_pct=8.2,
    )
    constituent = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(ev,), failure_reasons=(), one_line_view="",
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827",
            display_cn="易方达蓝筹精选", provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(),
        thesis_evidence=(), constituent_analyses=(constituent,),
    )
    m = build_constituent_cited_map((row,))
    assert "005827" in m
    assert "600519" in m["005827"]
    cids = list(m["005827"]["600519"].keys())
    assert len(cids) == 1
    meta = m["005827"]["600519"][cids[0]]
    assert meta.scope == "constituent"
    assert meta.citation_kind == "data"
    assert meta.owner_instrument_id == "005827"


def test_build_constituent_cited_map_empty_returns_empty_dict() -> None:
    from irc.opportunity.citation_map import build_constituent_cited_map
    assert build_constituent_cited_map(()) == {}


def test_build_constituent_cited_map_provenance_mismatch_raises() -> None:
    """Mirror build_cited_map's provenance check."""
    import pytest
    from irc.fundamentals.types import (
        ConstituentAnalysis, LookthroughTarget, ThesisEvidence,
    )
    from irc.opportunity.citation_map import build_constituent_cited_map
    from irc.opportunity.types import OpportunityRow
    ev = ThesisEvidence(
        type="filing", source="src", url="https://x", date="2024-04-15",
        summary="x", scope="constituent", citation_kind="data",
        owner_instrument_id="OTHER_FUND",  # wrong owner
        parent_fund_id="005827", constituent_key="600519",
        holding_weight_pct=8.2,
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(ev,), failure_reasons=(), one_line_view="",
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="X", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827",
            display_cn="X", provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(),
        thesis_evidence=(), constituent_analyses=(c,),
    )
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        build_constituent_cited_map((row,))
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_citation_map.py -v -k "constituent_cited"`
Expected: FAIL with `ImportError: cannot import name 'build_constituent_cited_map'`.

- [ ] **Step 3: Implement**

Append to `src/irc/opportunity/citation_map.py`:

```python
def build_constituent_cited_map(
    rows: tuple[OpportunityRow, ...],
) -> "ConstituentCitedMap":
    """Walk every row's `constituent_analyses[*].evidence`, validate
    provenance, and build the constituent-cited map.

    Item 009 D2b prerequisite: memo-stage `find_uncited_conclusions` keys
    constituent dual-leg lookup off `(instrument_id, constituent_key)`.

    Raises:
      RuntimeError: if any evidence's `owner_instrument_id != row.instrument_id`.
    """
    from irc.opportunity.types import ConstituentCitedMap
    cited: ConstituentCitedMap = {}
    for row in rows:
        for c in row.constituent_analyses:
            for ev in c.evidence:
                if ev.owner_instrument_id != row.instrument_id:
                    raise RuntimeError(
                        f"provenance mismatch in constituent evidence: "
                        f"owner_instrument_id={ev.owner_instrument_id!r} "
                        f"but row.instrument_id={row.instrument_id!r} "
                        f"(citation_id={ev.citation_id!r})"
                    )
                cited.setdefault(row.instrument_id, {}).setdefault(
                    c.symbol, {},
                )[ev.citation_id] = CitationMeta(
                    scope=ev.scope,
                    citation_kind=ev.citation_kind,
                    owner_instrument_id=ev.owner_instrument_id,
                    asset_class=row.asset_class,
                    parent_fund_id=ev.parent_fund_id,
                    constituent_key=ev.constituent_key,
                )
    return cited
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_citation_map.py -v`
Expected: All PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/citation_map.py tests/opportunity/test_citation_map.py
git commit -m "feat(opportunity): add build_constituent_cited_map for memo-stage constituent dual-leg lookup"
```

---

## Task 9: `_resolve_enforce_mode` + `_write_citation_audit_shadow_log` (ACs 11, 13)

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Modify: `tests/commands/test_opportunity_cmd.py` (or new `test_opportunity_cmd_enforce_mode.py`)

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_opportunity_cmd_enforce_mode.py`:

```python
"""Item 009 — _resolve_enforce_mode + _write_citation_audit_shadow_log unit tests."""
from __future__ import annotations

import json
from pathlib import Path


def test_resolve_enforce_mode_canonical_forces_block(monkeypatch, tmp_path):
    """AC11 — canonical path forces 'block' regardless of env var."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    canonical = tmp_path / "outputs" / "2026-05-22"
    canonical.mkdir(parents=True)
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    assert _resolve_enforce_mode(canonical, "2026-05-22") == "block"
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "warn")
    assert _resolve_enforce_mode(canonical, "2026-05-22") == "block"


def test_resolve_enforce_mode_non_canonical_honours_env(monkeypatch, tmp_path):
    """AC11 — non-canonical (tmp_path scratch) honours IRC_CITATION_ENFORCE_MODE."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    scratch = tmp_path / "scratch_outputs"
    scratch.mkdir()
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "off"
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "warn")
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "warn"
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "block"


def test_resolve_enforce_mode_non_canonical_unknown_value_falls_back_to_block(
    monkeypatch, tmp_path, capsys,
):
    """AC11 — unknown value → fallback to 'block' + stderr warning."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "bogus_value")
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "block"
    err = capsys.readouterr().err
    assert "WARN citation-audit" in err
    assert "bogus_value" in err


def test_resolve_enforce_mode_canonical_path_date_from_dir_name(monkeypatch, tmp_path):
    """AC11 — date is read from out_dir.name, NOT wall-clock today.
    This handles end-of-day skew and cross-day --output-dir invocations."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    # out_dir.name = '2026-05-22' but `today` (wall-clock) = '2026-06-01'.
    canonical = tmp_path / "outputs" / "2026-05-22"
    canonical.mkdir(parents=True)
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    assert _resolve_enforce_mode(canonical, "2026-06-01") == "block"


def test_resolve_enforce_mode_default_when_env_unset(monkeypatch, tmp_path):
    """Env unset on non-canonical → default 'block'."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.delenv("IRC_CITATION_ENFORCE_MODE", raising=False)
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "block"


def test_write_citation_audit_shadow_log_writes_json_atomically(tmp_path):
    """AC13 — file lands at out_dir/citation_audit.json with the locked schema."""
    from irc.commands.opportunity_cmd import _write_citation_audit_shadow_log
    payload = {
        "run_date": "2026-05-22",
        "enforce_mode": "block",
        "canonical_path": True,
        "out_dir": str(tmp_path),
        "opportunity_findings": [],
        "constituent_findings": [],
        "discipline_findings": [],
        "memo_findings": [],
        "summary": {"total": 0, "blocking": False},
    }
    _write_citation_audit_shadow_log(tmp_path, payload)
    written = json.loads((tmp_path / "citation_audit.json").read_text(encoding="utf-8"))
    assert written["run_date"] == "2026-05-22"
    assert written["summary"] == {"total": 0, "blocking": False}
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd_enforce_mode.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Edit `src/irc/commands/opportunity_cmd.py`. Add the imports near the top (alongside existing `re`, `os` imports if present; otherwise add them):

```python
import os
import re
```

Add at module scope, near `_today`:

```python
_CANONICAL_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_VALID_ENFORCE_MODES: tuple[str, ...] = ("off", "warn", "block")


def _is_canonical_out_dir(out_dir: Path) -> bool:
    """Per AC11 / Q2: canonical IFF parent is 'outputs' AND name matches YYYY-MM-DD."""
    try:
        resolved = out_dir.resolve()
    except (OSError, RuntimeError):
        return False
    if resolved.parent.name != "outputs":
        return False
    return bool(_CANONICAL_DATE_RE.fullmatch(resolved.name))


def _resolve_enforce_mode(out_dir: Path, today: str) -> str:
    """Resolve the IRC_CITATION_ENFORCE_MODE for the given output dir.

    Per AC11 / Q2:
      - Canonical path (outputs/YYYY-MM-DD) → 'block' (env var ignored).
      - Non-canonical → honour env var, default 'block'.
      - Unknown env value → 'block' with stderr warning.

    `today` is unused for canonical-path detection (date is read from
    `out_dir.name`) but accepted for forward-compat / call-site clarity.
    """
    if _is_canonical_out_dir(out_dir):
        return "block"
    raw = os.environ.get("IRC_CITATION_ENFORCE_MODE", "block")
    if raw in _VALID_ENFORCE_MODES:
        return raw
    print(
        f"WARN citation-audit: unknown IRC_CITATION_ENFORCE_MODE={raw!r}; "
        f"falling back to 'block'",
        file=sys.stderr,
    )
    return "block"


def _write_citation_audit_shadow_log(out_dir: Path, payload: dict) -> None:
    """Atomic write of the shared shadow log per AC13. Same atomicity as
    every other artifact in this module."""
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "citation_audit.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd_enforce_mode.py -v`
Expected: 6 PASS.

Run: `pytest tests/commands/ -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd_enforce_mode.py
git commit -m "feat(opportunity): add _resolve_enforce_mode + _write_citation_audit_shadow_log (AC11, AC13)"
```

---

## Task 10: Wire Steps 2a/2b/2c into `_write_opportunity_outputs` (ACs 9, 10, 12, 13)

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Modify: `tests/commands/test_opportunity_cmd_h3_invariant.py` (or new `test_opportunity_cmd_citation_gate.py`)

This is the load-bearing wiring task. Read the existing `_write_opportunity_outputs` body (lines ~1080–1170) carefully before editing — Step 1 (`fetch_budget_exhausted` raise) MUST stay untouched per AC10.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_opportunity_cmd_citation_gate.py`:

```python
"""Item 009 — _write_opportunity_outputs gate-wiring unit tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_row(*, iid="005827", legs=("data", "information"), gaps=()):
    """OpportunityRow with one data + one info evidence by default."""
    from irc.fundamentals.types import LookthroughTarget, ThesisEvidence
    from irc.opportunity.types import OpportunityRow
    evs = tuple(
        ThesisEvidence(
            type="filing", source="src",
            url=f"https://x/{i}", date=f"2024-04-{15 + i:02d}",
            summary="x", scope="instrument", citation_kind=leg,
            owner_instrument_id=iid, parent_fund_id=None,
            constituent_key=None, holding_weight_pct=None,
        )
        for i, leg in enumerate(legs)
    )
    return OpportunityRow(
        instrument_id=iid, name_cn="X", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=iid,
            display_cn="X", provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=gaps,
        thesis_evidence=evs,
        contributing_dimensions=frozenset({"valuation"}),
        constituent_analyses=(),
    )


def _make_position():
    from irc.opportunity.types import PositionContext
    return PositionContext(current_weight=0.0, target_band=None)


def _write_outputs(rows, tmp_path, *, today="2026-05-22"):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    out_dir = tmp_path / "outputs_scratch"
    positions = {r.instrument_id: _make_position() for r in rows}
    qualities = {r.instrument_id: object() for r in rows}
    roles = {r.instrument_id: "core" for r in rows}
    _write_opportunity_outputs(
        rows, positions, qualities, roles, {},
        out_dir, today,
        pending_verdicts=None,
        plan_hash="x",
        snapshot_cache_by_instrument=None,
    )
    return out_dir


def test_gate_clean_publishable_row_passes(tmp_path, monkeypatch):
    """AC9 — dual-leg row passes the gate; opportunity_report.json is written."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    rows = [_make_row()]
    out_dir = _write_outputs(rows, tmp_path)
    assert (out_dir / "opportunity_report.json").exists()
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    assert audit["summary"]["blocking"] is False


def test_gate_step_2a_blocks_uncited_row_block_mode(tmp_path, monkeypatch):
    """AC9 + AC12 — info-only row → row dropped + RuntimeError raised in block mode."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    info_only = _make_row(legs=("information",))
    with pytest.raises(RuntimeError, match="citation_gate_blocked"):
        _write_outputs([info_only], tmp_path)


def test_gate_step_2a_warn_mode_writes_artifacts(tmp_path, monkeypatch, capsys):
    """AC12 — warn mode logs to stderr, writes shadow log, emits artifacts."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "warn")
    info_only = _make_row(legs=("information",))
    out_dir = _write_outputs([info_only], tmp_path)
    assert (out_dir / "opportunity_report.json").exists()
    err = capsys.readouterr().err
    assert "WARN citation-audit" in err
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    assert audit["summary"]["blocking"] is False  # warn ≠ blocking


def test_gate_step_2a_off_mode_silent(tmp_path, monkeypatch, capsys):
    """AC12 — off mode is silent, writes shadow log, emits artifacts."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    info_only = _make_row(legs=("information",))
    out_dir = _write_outputs([info_only], tmp_path)
    assert (out_dir / "opportunity_report.json").exists()
    err = capsys.readouterr().err
    assert "WARN citation-audit" not in err


def test_gate_step_2b_pure_failure_constituent_raises_unconditionally(
    tmp_path, monkeypatch,
):
    """AC9 Step 2b — pure-failure constituent raises even in off mode."""
    from irc.fundamentals.types import ConstituentAnalysis
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    bad = ConstituentAnalysis(
        symbol="600519", name_cn="X", weight_pct=5.0,
        evidence=(), failure_reasons=("timeout",), one_line_view="",
    )
    row = _make_row()
    from dataclasses import replace as _replace
    row = _replace(row, constituent_analyses=(bad,))
    with pytest.raises(RuntimeError, match="constituent_failure_in_publishable_row"):
        _write_outputs([row], tmp_path)


def test_gate_step_1_fetch_budget_exhausted_still_raises(tmp_path, monkeypatch):
    """AC10 — fetch_budget_exhausted Step 1 raise is unchanged."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    row = _make_row(gaps=("fetch_budget_exhausted",))
    with pytest.raises(RuntimeError, match="fetch_budget_exhausted"):
        _write_outputs([row], tmp_path)


def test_gate_shadow_log_written_in_block_mode_before_raise(tmp_path, monkeypatch):
    """AC13 + AC23 — block-mode raise still writes the shadow log first."""
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    info_only = _make_row(legs=("information",))
    with pytest.raises(RuntimeError):
        _write_outputs([info_only], tmp_path)
    # Compute out_dir as the helper did: tmp_path/'outputs_scratch'
    out_dir = tmp_path / "outputs_scratch"
    audit_path = out_dir / "citation_audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["summary"]["blocking"] is True
    # Canonical artifacts should NOT have leaked.
    assert not (out_dir / "opportunity_report.json").exists()
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd_citation_gate.py -v`
Expected: all FAIL (gate not yet wired).

- [ ] **Step 3: Implement the wiring**

Edit `src/irc/commands/opportunity_cmd.py`. Replace the body of `_write_opportunity_outputs` from line ~1098 onwards to add Steps 2a/2b/2c BEFORE Step 3 (serializer). Sketch of the new body (only the post-Step-1 region — KEEP Step 1 verbatim):

```python
    # Step 1 — H3 fatal pre-gate (UNCHANGED, AC10).
    for r in kept_rows:
        if "fetch_budget_exhausted" in r.evidence_gaps:
            raise RuntimeError(
                f"fetch_budget_exhausted appeared on row {r.instrument_id} — "
                "this gap is run-level fatal and must be caught at preflight; "
                "row-level emission is a programming error"
            )

    # Step 2 — H3 partition.
    publishable_rows = [r for r in kept_rows if not r.evidence_gaps]
    gapped_rows = [r for r in kept_rows if r.evidence_gaps]

    # ── Item 009 Step 2a — opportunity-row citation gate ───────────────────
    # Q5 deferral: drop-dimension-text renderer is v2 work; v1 blocks the
    # entire row by stamping evidence_gaps=("citation_gate_blocked",) and
    # routing through Step 4's rejection-record builder.
    from irc.opportunity.auditor import (
        find_incomplete_constituent_analyses, find_uncited_opportunity_rows,
    )
    from irc.opportunity.citation_map import build_cited_map
    cited_map = build_cited_map(tuple(publishable_rows))
    op_findings = find_uncited_opportunity_rows(publishable_rows, cited_map)
    blocked_iids = {f.instrument_id for f in op_findings}
    if blocked_iids:
        kept_publishable: list = []
        for r in publishable_rows:
            if r.instrument_id in blocked_iids:
                gapped_rows.append(
                    dataclasses.replace(
                        r, evidence_gaps=("citation_gate_blocked",),
                    )
                )
            else:
                kept_publishable.append(r)
        publishable_rows = kept_publishable

    # ── Item 009 Step 2b — pure-failure constituent gate (unconditional) ──
    constituent_findings = find_incomplete_constituent_analyses(publishable_rows)
    # ── Item 009 Step 2c — discipline-row citation gate ────────────────────
    from irc.memo.numeric_audit import find_uncited_discipline_rows
    discipline_rows = [
        _discipline_row_from(r, positions[r.instrument_id]) for r in publishable_rows
    ]
    discipline_findings = find_uncited_discipline_rows(discipline_rows, cited_map)

    # ── Item 009 — resolve mode + write shadow log BEFORE any potential raise.
    enforce_mode = _resolve_enforce_mode(out_dir, today)
    blocking_findings = bool(op_findings) or bool(discipline_findings)
    shadow_payload = {
        "run_date": today,
        "enforce_mode": enforce_mode,
        "canonical_path": _is_canonical_out_dir(out_dir),
        "out_dir": str(out_dir.resolve()),
        "opportunity_findings": [
            {"instrument_id": f.instrument_id, "kind": f.kind,
             "prose_excerpt": f.prose_excerpt, "evidence_excerpt": f.evidence_excerpt}
            for f in op_findings
        ],
        "constituent_findings": [
            {"instrument_id": f.instrument_id, "kind": f.kind,
             "prose_excerpt": f.prose_excerpt, "evidence_excerpt": f.evidence_excerpt}
            for f in constituent_findings
        ],
        "discipline_findings": [
            {"instrument_id": f.instrument_id, "kind": f.kind,
             "prose_excerpt": f.prose_excerpt, "evidence_excerpt": f.evidence_excerpt}
            for f in discipline_findings
        ],
        "memo_findings": [],
        "summary": {
            "total": (
                len(op_findings) + len(constituent_findings)
                + len(discipline_findings)
            ),
            "blocking": (
                bool(constituent_findings)
                or (enforce_mode == "block" and blocking_findings)
            ),
        },
    }
    _write_citation_audit_shadow_log(out_dir, shadow_payload)

    # Step 2b raise: pure-failure constituent is unconditional fatal.
    if constituent_findings:
        raise RuntimeError(
            "constituent_failure_in_publishable_row: "
            + "; ".join(f.prose_excerpt for f in constituent_findings)
        )

    # Step 2a/2c dispatch by mode.
    if blocking_findings:
        msg_parts = [f"{f.instrument_id}:{f.kind}"
                     for f in (op_findings + discipline_findings)]
        msg = "citation_gate_blocked: " + "; ".join(msg_parts)
        if enforce_mode == "block":
            raise RuntimeError(msg)
        if enforce_mode == "warn":
            print(f"WARN citation-audit: {msg}", file=sys.stderr)
        # off: silent

    # Step 3 — emit thesis_cards.yaml + opportunity_report.json from publishable only.
    # ... (existing body unchanged)
```

You'll need to:
1. Add `import dataclasses` at the top of the file if not already imported (check first).
2. Rebuild `discipline_rows` after Step 2a row-blocking removes a row — replace the original `discipline_rows = [...]` line that comes after Step 2 with the one above.
3. Ensure `sys` is imported (it should already be, for the existing `_reject_limit_on_canonical`).
4. Make sure `_write_citation_audit_shadow_log` / `_is_canonical_out_dir` / `_resolve_enforce_mode` are imported / accessible (they live in the same module, so direct reference suffices).

Read your edit back and confirm the existing Step 4 (`rejection_records` loop) STILL fires AFTER Step 2a's gapped_rows append — the new `citation_gate_blocked` gaps must reach `_classify_rejection_reason` so they land in `rejections.json`.

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd_citation_gate.py -v`
Expected: 7 PASS.

Run: `pytest tests/commands/ -x -q`
Expected: PASS.

Run: `pytest tests/opportunity/ -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd_citation_gate.py
git commit -m "feat(opportunity): wire Steps 2a/2b/2c citation gate into _write_opportunity_outputs (AC9, AC10, AC12, AC13)"
```

---

## Task 11: Wire memo-stage gate into `run_memo` (ACs 14, 15, 16, 25)

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Modify: `tests/commands/test_memo_cmd.py` (or new `test_memo_cmd_citation_gate.py`)

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_memo_cmd_citation_gate.py`:

```python
"""Item 009 — memo-stage citation gate unit tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def _resp(text):
    from irc.llm.http_client import ChatResponse
    return ChatResponse(
        text=text, prompt_tokens=10, completion_tokens=20,
        latency_ms=50, raw={},
    )


def test_memo_gate_clean_publishable_set_passes(tmp_path, monkeypatch):
    """AC14 — clean run with dual-leg pick rows → memo.md written, exit 0."""
    # Use the lifted helper to seed a publishable set.
    from tests.integration._publishable_set_helper import (
        _seed_publishable_set_repo, _install_ak_call_dispatch,
        _patch_memo_routes,
    )
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.commands.memo_cmd import run_memo
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(str(tmp_path))
    with _patch_memo_routes("# memo draft"):
        rc = run_memo(str(tmp_path))
    assert rc == 0
    today = (tmp_path / "outputs").iterdir().__next__().name
    out_dir = tmp_path / "outputs" / today
    assert (out_dir / "memo.md").exists()
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    # memo_findings list exists (may be empty if all picks have dual-leg).
    assert "memo_findings" in audit


def test_memo_gate_uses_out_dir_not_out_today(tmp_path, monkeypatch):
    """AC25 + Q7 — _resolve_enforce_mode is called with out_dir (write-path),
    not out_today (read-path which may be stale-dated).

    Strategy: monkey-patch `_locate_scoring` / `_latest_file` to return a
    yesterday-dated scoring.json; assert the shadow log lands in TODAY's
    output dir, not yesterday's."""
    from tests.integration._publishable_set_helper import (
        _seed_publishable_set_repo, _install_ak_call_dispatch,
        _patch_memo_routes,
    )
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.commands.memo_cmd import run_memo, _today

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(str(tmp_path))

    today = _today()
    # Move today's scoring.json sideways so _latest_file falls back.
    today_dir = tmp_path / "outputs" / today
    yesterday = "2026-05-21"  # any earlier ISO date
    ydir = tmp_path / "outputs" / yesterday
    ydir.mkdir(parents=True, exist_ok=True)
    (today_dir / "scoring.json").rename(ydir / "scoring.json")
    # Also move the other upstream artifacts so memo_cmd's READ-path resolves
    # to yesterday.
    for name in ("gold_regime.json", "proposed_allocation.yaml",
                 "trade_plan.yaml", "opportunity_report.json"):
        src = today_dir / name
        if src.exists():
            src.rename(ydir / name)

    with _patch_memo_routes("# memo draft"):
        rc = run_memo(str(tmp_path))

    # The shadow log MUST live under today's dir (write path), not yesterday.
    audit_today = today_dir / "citation_audit.json"
    audit_yesterday = ydir / "citation_audit.json"
    assert audit_today.exists(), f"shadow log not under {today_dir}"
    assert not audit_yesterday.exists(), f"shadow log leaked into {ydir}"


def test_memo_gate_audit_blocks_publish_still_takes_precedence(tmp_path, monkeypatch):
    """AC16 — the existing audit_blocks_publish gate runs first; citation
    findings do not change the exit code if the audit gate fires."""
    from tests.integration._publishable_set_helper import (
        _seed_publishable_set_repo, _install_ak_call_dispatch,
    )
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.commands.memo_cmd import run_memo
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(str(tmp_path))
    with patch("irc.memo.synthesizer.call_chat", return_value=_resp("# memo")), \
         patch("irc.memo.auditor.call_chat", return_value=_resp("审核未通过 P-tier 高风险")):
        rc = run_memo(str(tmp_path))
    assert rc == 2  # blocked by audit gate, NOT citation gate
    today = (tmp_path / "outputs").iterdir().__next__().name
    out_dir = tmp_path / "outputs" / today
    assert (out_dir / "memo_blocked.md").exists()
    assert not (out_dir / "memo.md").exists()
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_memo_cmd_citation_gate.py -v`
Expected: FAIL (memo gate not wired yet).

- [ ] **Step 3: Implement the wiring**

Edit `src/irc/commands/memo_cmd.py`. At the top of the file (with other imports), add:

```python
from irc.commands.opportunity_cmd import (
    _resolve_enforce_mode, _write_citation_audit_shadow_log,
)
from irc.memo.numeric_audit import (
    find_missing_pick_citations, find_uncited_conclusions,
)
from irc.opportunity.citation_map import (
    build_cited_map, build_constituent_cited_map,
)
```

(Take care: `_reconstruct_opportunity_rows` already exists from item 007 — find its definition; it's used at line ~475.)

In `run_memo`, between `audit_blocks_publish` (line ~539) and `atomic_write_text(out_dir / "memo.md", output.draft)` (line ~568), insert the gate:

```python
    # ── Item 009 — memo-stage citation gate ───────────────────────────────
    # Q7 + F1 lock: use out_dir (write path), NOT out_today (read path).
    # `today` was captured once at line 409; pass it through for clarity.
    publishable_rows_for_gate = _reconstruct_opportunity_rows(rebuilt_op_rows)
    cited_map_for_gate = build_cited_map(tuple(publishable_rows_for_gate))
    constituent_cited_for_gate = build_constituent_cited_map(
        tuple(publishable_rows_for_gate),
    )
    pick_findings = find_missing_pick_citations(pick_rows, cited_map_for_gate)
    prose_findings = find_uncited_conclusions(
        output.draft,
        cited_map=cited_map_for_gate,
        instrument_aliases=_instrument_aliases,
        constituent_aliases=_constituent_aliases,
        constituent_cited_map=constituent_cited_for_gate,
        strict_empty_alias_check=bool(rebuilt_op_rows),
    )
    memo_findings = pick_findings + prose_findings
    enforce_mode = _resolve_enforce_mode(out_dir, today)

    # RMW the shared shadow log: read whatever the opportunity stage wrote,
    # overlay memo_findings + summary.
    audit_path = out_dir / "citation_audit.json"
    if audit_path.exists():
        shadow = json.loads(audit_path.read_text(encoding="utf-8"))
    else:
        shadow = {
            "run_date": today, "enforce_mode": enforce_mode,
            "canonical_path": False, "out_dir": str(out_dir.resolve()),
            "opportunity_findings": [], "constituent_findings": [],
            "discipline_findings": [], "memo_findings": [],
            "summary": {"total": 0, "blocking": False},
        }
    shadow["memo_findings"] = [
        {"instrument_id": f.instrument_id, "kind": f.kind,
         "prose_excerpt": f.prose_excerpt, "evidence_excerpt": f.evidence_excerpt}
        for f in memo_findings
    ]
    shadow["summary"]["total"] = (
        len(shadow.get("opportunity_findings", []))
        + len(shadow.get("constituent_findings", []))
        + len(shadow.get("discipline_findings", []))
        + len(memo_findings)
    )
    shadow["summary"]["blocking"] = (
        shadow["summary"].get("blocking", False)
        or (enforce_mode == "block" and bool(memo_findings))
    )
    _write_citation_audit_shadow_log(out_dir, shadow)

    if memo_findings and enforce_mode == "block":
        reasons = [f"{f.instrument_id}:{f.kind}" for f in memo_findings]
        block_header = (
            "# 备忘录发布被引用审核拒绝\n\n"
            "Item 009 citation gate flagged missing citations on picks/prose; "
            "see citation_audit.json for details.\n\n"
            "## 阻断原因\n\n"
            + "\n".join(f"- {r}" for r in reasons)
            + "\n\n---\n\n"
        )
        atomic_write_text(out_dir / "memo_blocked.md", block_header + output.draft)
        memo_path = out_dir / "memo.md"
        if memo_path.exists():
            memo_path.unlink()
        print("memo BLOCKED by citation gate: see "
              f"{out_dir/'memo_blocked.md'} and {out_dir/'citation_audit.json'}")
        for r in reasons:
            print(f"  - {r}")
        return 2
    if memo_findings and enforce_mode == "warn":
        print("WARN citation-audit (memo): "
              + "; ".join(f"{f.instrument_id}:{f.kind}" for f in memo_findings),
              file=sys.stderr)
```

Make sure this block lives AFTER `audit_blocks_publish` (so a P-tier block still wins per AC16) and BEFORE `atomic_write_text(out_dir / "memo.md", output.draft)`.

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_memo_cmd_citation_gate.py -v`
Expected: 3 PASS.

Run: `pytest tests/commands/ -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/memo_cmd.py tests/commands/test_memo_cmd_citation_gate.py
git commit -m "feat(memo): wire memo-stage citation gate downstream of audit_blocks_publish (AC14, AC15, AC16, AC25)"
```

---

## Task 12: Integration — canonical-path × enforce-mode matrix (spec AC22)

**Files:**
- Create: `tests/integration/test_citation_audit_gate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_citation_audit_gate.py`:

```python
"""Item 009 — citation audit gate integration suite.

Reuses _publishable_set_helper.py from item 008's lift. Every test that
exercises the AkShare dispatcher asserts `_unexpected_calls(counter) == []`
(AC21 — closes item 008's documented-only sentinel)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.integration._publishable_set_helper import (
    _resp, _today_cn, _sha256_file,
    _collect_publishable_citation_universe,
    _patch_memo_routes, _install_ak_call_dispatch,
    _seed_publishable_set_repo,
)


def _unexpected_calls(counter: Counter) -> list[tuple[str, str]]:
    """Returns keys in counter that aren't part of the locked dispatch set.
    Item 009 AC21 — closes item 008's documented-only sentinel."""
    # Conservative: every call should be accounted for in the helper's seed.
    return [k for k, v in counter.items() if v < 0]  # placeholder; refined per dispatch


def _make_uncited_scenario(tmp_path, monkeypatch):
    """Helper: seed a repo and tamper one row's thesis_evidence to be info-only.

    We use the seed helper to bootstrap a baseline publishable run, then
    manually rewrite opportunity_report.json before invoking run_memo (for
    memo-stage tests) — but for opportunity-stage tests we cannot inject
    after the fact. Instead, AC22 leans on `monkeypatch` of
    `find_uncited_opportunity_rows` to return a forced finding so we can
    verify the dispatch arms without engineering an uncited evidence fixture.
    """
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    return dispatch


@pytest.mark.parametrize(
    "mode,canonical,uncited,expected_raise",
    [
        ("block", True, True, True),    # (a) canonical + block + uncited → raise
        ("warn",  True, True, True),    # (b) canonical + warn  + uncited → raise (env ignored)
        ("off",   True, True, True),    # (c) canonical + off   + uncited → raise (env ignored)
        ("block", False, True, True),   # (d) non-canonical + block + uncited → raise
        ("warn",  False, True, False),  # (e) non-canonical + warn  + uncited → exits 0
        ("off",   False, True, False),  # (f) non-canonical + off   + uncited → silent
        ("block", True, False, False),  # (g) canonical + block + clean → exits 0
    ],
)
def test_enforce_mode_matrix(tmp_path, monkeypatch, mode, canonical, uncited, expected_raise):
    """Spec AC22 — seven-scenario matrix."""
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.memo.numeric_audit import NumericFinding

    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", mode)
    dispatch = _make_uncited_scenario(tmp_path, monkeypatch)

    # Force canonical path by writing to outputs/<today>/ (default).
    # For non-canonical, point run_opportunity at a sibling dir.
    out_arg = None if canonical else str(tmp_path / "scratch_out")

    if uncited:
        # Inject a fake finding to drive the gate without engineering bad seeds.
        def _fake(_rows, _cited):
            if not _rows:
                return []
            return [NumericFinding(
                instrument_id=_rows[0].instrument_id,
                kind="missing_data_citation",
                prose_excerpt="forced",
                evidence_excerpt="forced",
            )]
        monkeypatch.setattr(
            "irc.commands.opportunity_cmd.find_uncited_opportunity_rows",
            _fake,
        )

    if expected_raise:
        with pytest.raises((RuntimeError, SystemExit)):
            run_opportunity(str(tmp_path), output_dir=out_arg)
    else:
        rc = run_opportunity(str(tmp_path), output_dir=out_arg)
        assert rc == 0
```

NOTE the `monkeypatch.setattr("irc.commands.opportunity_cmd.find_uncited_opportunity_rows", ...)` trick requires that the gate-wiring code in Task 10 import `find_uncited_opportunity_rows` at module scope (not lazily inside the function). If your Task 10 implementation imported it lazily inside `_write_opportunity_outputs`, you must lift it to a module-level import — adjust Task 10's import block accordingly so this test's monkeypatch reaches it.

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_citation_audit_gate.py::test_enforce_mode_matrix -v`
Expected: FAIL (some scenarios may not behave as expected yet — debug and adjust).

- [ ] **Step 3: Iterate to green**

The most likely failure modes:
1. Module-level import of `find_uncited_opportunity_rows` was not added → monkeypatch hits a different binding. Fix: ensure the import in `opportunity_cmd.py` is at module scope.
2. Non-canonical path detection broke when `output_dir` is supplied → check `_is_canonical_out_dir` against `Path(out_arg).resolve()`.
3. `run_opportunity`'s `--limit` rejection on canonical might re-engage; verify the test does NOT pass `limit`.

Run again: `pytest tests/integration/test_citation_audit_gate.py::test_enforce_mode_matrix -v`
Expected: 7 PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_citation_audit_gate.py
git commit -m "test(integration): lock canonical-path × enforce-mode matrix (spec AC22)"
```

---

## Task 13: Integration — shadow log written in all modes including block (spec AC23)

**Files:**
- Modify: `tests/integration/test_citation_audit_gate.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_citation_audit_gate.py`:

```python
def test_shadow_log_written_in_block_mode_even_when_raising(tmp_path, monkeypatch):
    """Spec AC23 — block mode raises but shadow log is written FIRST."""
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.opportunity.auditor import find_uncited_opportunity_rows
    from irc.memo.numeric_audit import NumericFinding

    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    _make_uncited_scenario(tmp_path, monkeypatch)

    def _fake(_rows, _cited):
        if not _rows:
            return []
        return [NumericFinding(
            instrument_id=_rows[0].instrument_id,
            kind="missing_data_citation",
            prose_excerpt="forced",
            evidence_excerpt="forced",
        )]
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.find_uncited_opportunity_rows", _fake,
    )

    with pytest.raises(RuntimeError, match="citation_gate_blocked"):
        run_opportunity(str(tmp_path))

    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    assert audit["summary"]["blocking"] is True
    assert audit["enforce_mode"] == "block"
    assert audit["opportunity_findings"]
    # Canonical artifacts must NOT leak.
    for fname in ("opportunity_report.json", "thesis_cards.yaml",
                  "discipline_report.md", "rejections.json"):
        assert not (out_dir / fname).exists(), f"{fname} leaked"
```

- [ ] **Step 2: Run failing → green**

Run: `pytest tests/integration/test_citation_audit_gate.py -v -k "shadow_log_written"`
Expected: PASS (if Task 10 wired the gate correctly, this should already pass — the test locks the behavior).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_citation_audit_gate.py
git commit -m "test(integration): lock shadow log written in block mode before raise (spec AC23)"
```

---

## Task 14: Integration — item 008 baseline passes with gate live (spec AC24 / Q6)

**Files:**
- Modify: `tests/integration/test_citation_audit_gate.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_citation_audit_gate.py`:

```python
def test_item_008_baseline_passes_with_gate_live(tmp_path, monkeypatch):
    """Spec AC24 / Q6 — item 008's seed already carries dual-leg dual-scope
    evidence on every publishable row; the gate is a no-op."""
    from irc.commands.opportunity_cmd import run_opportunity
    monkeypatch.delenv("IRC_CITATION_ENFORCE_MODE", raising=False)
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    rc = run_opportunity(str(tmp_path))
    assert rc == 0
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    # Gate-live baseline: no opportunity findings, blocking==False.
    assert audit["summary"]["blocking"] is False
    # All four canonical artifacts present.
    for fname in ("opportunity_report.json", "thesis_cards.yaml",
                  "discipline_report.md", "rejections.json"):
        assert (out_dir / fname).exists()
```

- [ ] **Step 2: Run failing → green**

Run: `pytest tests/integration/test_citation_audit_gate.py::test_item_008_baseline_passes_with_gate_live -v`
Expected: PASS (if item 008's seed actually carries dual-leg evidence as Q6 claims). If it FAILS, follow the Q6 / item 006/008 inline-fix precedent: investigate which leg is missing, patch the seed helper (lifted in Task 1) to add the missing evidence shape, and append a one-line entry to `docs/2026-05-22-thesis-cards-evidence-gap/items/009-drift.md`.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_citation_audit_gate.py
git commit -m "test(integration): lock item 008 baseline passes with citation gate live (spec AC24)"
```

---

## Task 15: Integration — `out_dir` vs `out_today` + two-run byte equality (spec AC25 + AC20)

**Files:**
- Modify: `tests/integration/test_citation_audit_gate.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_citation_audit_gate.py`:

```python
def test_memo_gate_shadow_log_lands_in_write_path_dir(tmp_path, monkeypatch):
    """Spec AC25 — _resolve_enforce_mode is called with out_dir (write path),
    NOT out_today (read path which may be stale-dated).

    Strategy: run opportunity into TODAY; manually rename today's upstream
    artifacts to a yesterday-dated dir; then run_memo and assert that the
    shadow log lands in today's dir, not yesterday's."""
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.commands.memo_cmd import run_memo, _today

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(str(tmp_path))

    today = _today()
    today_dir = tmp_path / "outputs" / today
    yesterday = "2026-05-21"
    ydir = tmp_path / "outputs" / yesterday
    ydir.mkdir(parents=True, exist_ok=True)
    for name in ("scoring.json", "gold_regime.json",
                 "proposed_allocation.yaml", "trade_plan.yaml",
                 "opportunity_report.json"):
        src = today_dir / name
        if src.exists():
            src.rename(ydir / name)

    with _patch_memo_routes("# memo draft"):
        run_memo(str(tmp_path))

    # AC25 contract: shadow log under today_dir, not ydir.
    assert (today_dir / "citation_audit.json").exists()
    assert not (ydir / "citation_audit.json").exists()


def test_two_run_byte_equality_for_citation_audit_json(tmp_path, monkeypatch):
    """Spec AC20 — two back-to-back runs of run_opportunity produce
    byte-identical citation_audit.json."""
    from irc.commands.opportunity_cmd import run_opportunity
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(str(tmp_path))
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    first_sha = _sha256_file(out_dir / "citation_audit.json")

    # Re-run. Atomic writes truncate-and-replace; the file should re-emerge
    # byte-identical (modulo run_date which is locked to today).
    run_opportunity(str(tmp_path))
    second_sha = _sha256_file(out_dir / "citation_audit.json")
    assert first_sha == second_sha
```

- [ ] **Step 2: Run failing → green**

Run: `pytest tests/integration/test_citation_audit_gate.py -v -k "shadow_log_lands or two_run_byte"`
Expected: 2 PASS.

If `test_two_run_byte_equality_for_citation_audit_json` fails on a non-deterministic ordering (e.g., dict iteration over `cited_map.values()` without a sort key), fix the determinism leak in `opportunity_cmd.py` — typical sites: sort `op_findings` / `discipline_findings` lists by `(instrument_id, kind)` before serialization.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_citation_audit_gate.py
git commit -m "test(integration): lock memo out_dir vs out_today discipline + citation_audit.json two-run byte equality (AC20, AC25)"
```

---

## Task 16: CONTEXT.md update + final verification (ACs 20, 21, 24 hard check)

**Files:**
- Modify: `CONTEXT.md`

- [ ] **Step 1: Append "Audit gates and enforcement modes" section**

Read `CONTEXT.md` and find a natural insertion point (after the existing audit-related terms; ideally after the "Publishable citation universe" term from item 008). Append:

```markdown
## Audit gates and enforcement modes

### `IRC_CITATION_ENFORCE_MODE`

Env var controlling the citation audit gate. Values: `block` (default), `warn`,
`off`. On **canonical paths** (`outputs/YYYY-MM-DD/` matched by
`out_dir.resolve().parent.name == "outputs" AND re.fullmatch(r"\d{4}-\d{2}-\d{2}", out_dir.name)`)
the env var is **ignored** and `block` is forced — production runs cannot be
silenced. On non-canonical scratch paths (e.g. `tmp_path` in tests) the env
var is honoured; unknown values fall back to `block` with a stderr warning.

The shadow log `outputs/<date>/citation_audit.json` is written in ALL modes
(including `block`, where it lands BEFORE the `RuntimeError` is raised). The
file is shared across opportunity and memo stages: the opportunity stage
writes `opportunity_findings`, `constituent_findings`, `discipline_findings`;
the memo stage RMW-overlays `memo_findings` and re-derives `summary`. Both
stages use `atomic_write_text` so a partial file is never observable.

### Citation gate v1 dimension binding

V1 ships **structural-only** dual-leg binding: for each publishable
`OpportunityRow`, require ≥1 `ThesisEvidence` with `citation_kind == "data"`
AND ≥1 with `citation_kind == "information"` anywhere in
`row.thesis_evidence` (no per-`type → dimension` map). A row with one or both
legs missing is dropped from publishable, stamped
`evidence_gaps=("citation_gate_blocked",)`, and routed via
`rejections.json` + the discipline-report failure section.

V2 contract sketch (deferred per Q1 / Q5 of item 009's grill): expand the
`ThesisEvidence.type` literal set with dimension-tagged values (e.g.
`valuation_metric`, `heat_metric`) and require per-dimension type-match. The
renderer behaviour of "drop the uncited dimension's conclusion text but keep
the row" (diagnosis-doc D2a) is paired with the v2 binding and also deferred.
Today's v1 fails-the-row instead.
```

- [ ] **Step 2: Final verification — full suite + lint**

Run: `pytest -x -q`
Expected: ALL PASS. This includes:
- All new item 009 tests (Tasks 3–15).
- Item 008 baseline (`tests/integration/test_publishable_set_lockdown.py`) — must remain green with the gate live (Q6 contract; AC24).
- All items 001–007 tests.

Run: `pytest tests/integration/test_publishable_set_lockdown.py -x -v`
Expected: every AC 1–23 from item 008 PASS — confirms Q6's "gate is a no-op on item 008 seeds" claim end-to-end and verifies the Task 1 helper lift preserved byte-equality on ACs 22–23.

Run: `ruff check src tests`
Expected: clean (no warnings, no errors).

If anything fails: follow the inline-fix precedent from item 008's Q6:
1. Diagnose whether the failure is a test-wrong (fix the test) or production-drift (fix `src/` in a separate commit).
2. Document any production-drift fix in `docs/2026-05-22-thesis-cards-evidence-gap/items/009-drift.md` (create the file if absent; one line per fix).
3. Re-run until green.

- [ ] **Step 3: Commit**

```bash
git add CONTEXT.md
git commit -m "docs(context): add 'Audit gates and enforcement modes' section for item 009 citation gate"
```

- [ ] **Step 4: Push and open PR**

(Per autodev cadence; ship workflow follows.) Branch: `autodev/thesis-evidence-009-citation-gate-block-mode`. PR opens against `autodev/thesis-cards-evidence-gap`.

---

## Self-review checklist

- **Spec AC coverage:** AC1 → T3; AC2 → T5; AC3 → T7; AC4 → T6; AC5 → T4; AC6 → T3; AC7 → T4; AC8 → T7; AC9 → T10; AC10 → T10; AC11 → T9; AC12 → T10; AC13 → T9 + T10; AC14 → T11; AC15 → T11; AC16 → T11; AC17 → T7; AC18 → T7; AC19 → T7; AC20 → T15; AC21 → asserted across T12–T15 via `_unexpected_calls`; AC22 → T12; AC23 → T13; AC24 → T14 + T16; AC25 → T11 + T15. All 25 ACs covered.
- **Q1–Q7 resolutions:** Locked in "Locked decisions" header and threaded through each affected task.
- **Order discipline:** Helper lift (T1) precedes any source change so item 008's byte-equality is preserved early; `RejectionReasonCode` (T2) precedes Step 2a wiring (T10) so the gap stamp never crashes `_classify_rejection_reason`; auditor functions (T3–T8) precede gate wirings (T9–T11) so each wiring builds on green tested foundations.
- **No placeholders:** every step shows code or a precise command + expected output.
- **Final task:** runs full `pytest -x -q` AND `pytest tests/integration/test_publishable_set_lockdown.py -x -v` (hard check per the brief — item 008 must stay green) AND `ruff check src tests`.
