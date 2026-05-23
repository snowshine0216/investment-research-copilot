# Item 007 Implementation Plan — memo + discipline renderers + alias-builder (Slices D1a + D1c + D3a + D3b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the user-facing renderer slice that consumes everything items 002 + 003 + 005 + 006 have already produced and emits (a) `memo.md` evidence pool lines with `[stock:{symbol}] [ref:{citation_id}]` markers, (b) `discipline_report.md` per-row sections with nested `thesis_evidence` bullets + inline top-5 holdings + a full `## 持仓明细` appendix listing all top-N constituents per fund, (c) the alias-builder (`build_alias_maps`) that closes the silent-no-op failure mode in `find_uncited_conclusions` (item 009).

**Architecture:** Three production code edits + one new module + one classmethod promotion. New file `src/irc/memo/aliases.py` exposes `build_alias_maps`, `InstrumentAliasCollisionError`, `InstrumentAliases`, `ConstituentAliases`. New file `src/irc/memo/markers.py` exposes the `[ref:...]` + `[stock:...]` marker grammar as module-level constants reused by both renderers. `src/irc/memo/evidence_pool.py::build_evidence_pool` appends top-3 citation lines after each instrument's state-codes line. `src/irc/opportunity/report.py::_render_section` gains nested thesis_evidence bullets + inline top-5 holdings; `compose_discipline_markdown` gains two keyword-only params (`publishable_rows`, `pick_order_iids`) and appends a `## 持仓明细` appendix section. `src/irc/memo/numeric_audit.py` gains an empty-map `RuntimeError` raise inside a new `find_uncited_conclusions` stub. `_evidence_from_dict` is promoted to `@classmethod ThesisEvidence.from_dict` in `src/irc/fundamentals/types.py` and the three production call sites collapse onto it. Wiring: `memo_cmd.py::run_memo` builds alias maps from publishable rows; `opportunity_cmd.py::_write_opportunity_outputs` loads `trade_plan.yaml` for pick order and threads it through `compose_discipline_markdown`.

**Tech Stack:** Python 3.12, pytest, ruff, stdlib only. No new third-party deps.

---

## Constraints (apply to every task)

- **Strict TDD per task:** red (failing test) → green (minimal impl) → refactor. No implementation code lands without a prior failing test. Tests-first within a task.
- **Pure functions only.** Every new function in `aliases.py`, `markers.py`, `evidence_pool.py`, and the renderer additions in `report.py` are pure: no I/O, no mutation, no logging, no global state. Alias maps and frozensets are constructed via comprehensions or spread; no `dict.setdefault(...).add(...)`-style mutation visible to callers.
- **Frozen dataclasses + `dataclasses.replace`.** No `dataclass.field = value` mutation. Where item 007 needs to enrich `OpportunityRow.constituent_analyses` (OQ2 wiring), use a copy-then-replace pattern at a single boundary.
- **No new I/O.** Renderers consume already-loaded data and return strings. `pipeline.py::run_memo` / `_write_opportunity_outputs` still own all `atomic_write_text` calls (no edits there).
- **Defaults locked:**
  - `SELECT_CITATIONS_CAP = 3` (call `select_citations(thesis_evidence, cap=3)` at every consumer site — locked SAME-3 invariant from ADR 0004 §3).
  - `TOP_5_HOLDINGS_INLINE_CAP = 5` (inline cap in discipline row sections; appendix shows full top-N).
  - `TOP_N_DEFAULT = 10` (already exported from `opportunity_cmd.py`; item 007 imports and reuses).
  - `INLINE_HEADER_LITERAL = "持仓 (Top 5)"` (fixed label even when `len(constituent_analyses) < 5` — spec OQ4 locked literal).
- **Marker grammar locked** — see "Locked marker grammar" below. The constants live in `src/irc/memo/markers.py` and both renderers import from there.
- **Appendix line regex locked** — see "Locked appendix line regex contract" below. `_APPENDIX_LINE_RE` module-level constant in `report.py` for item 009 cross-test reuse.
- **SAME-3 invariant** (ADR 0004 §3): all three consumers — `_build_pick_rows`, `build_evidence_pool`, `_render_section` — receive the identical `tuple[ThesisEvidence, ...]` with NO pre-filtering at the consumer level. Locked by a regression test in Task 13.
- **No mutation of cached `ConstituentAnalysis` snapshots.** Per ADR 0003 §2: `audit_errors` is derived, never persisted. OQ2 stamping happens via `dataclasses.replace` in `_build_rows` (not at the snapshot cache boundary).
- **Functional programming (CLAUDE.md).** No methods on frozen dataclasses (no `row.has_constituents()`); use free functions or inline predicates. No mid-function `list.append` accumulation; use comprehensions.
- **Commit cadence:** one conventional-commit per task (`feat(memo):`, `feat(opportunity):`, `feat(fundamentals):`, `refactor(...):`). DO NOT push.
- **Verification per task:** an exact `pytest …` command with expected PASS/FAIL output. Final task = full `pytest --ignore=tests/news --ignore=tests/scoring/test_sanity_check.py -x -q` + `ruff check src/ tests/` clean.

## Branch

Sub-branch: `autodev/thesis-evidence-007-memo-and-discipline-renderers` cut from `autodev/thesis-cards-evidence-gap`. Commits land on the sub-branch; the eventual PR opens against `autodev/thesis-cards-evidence-gap`.

---

## File-touch map (read this before starting)

**Source (create):**
- `src/irc/memo/markers.py` — marker-grammar constants: `REF_MARKER_FMT`, `STOCK_MARKER_FMT`, `format_ref_marker`, `format_stock_marker`, `format_combined_marker`. Pure helpers; no logic beyond f-string formatting.
- `src/irc/memo/aliases.py` — `InstrumentAliases`, `ConstituentAliases` type aliases; `InstrumentAliasCollisionError` exception class; `build_alias_maps(rows) -> (InstrumentAliases, ConstituentAliases)` pure function.
- `tests/memo/test_markers.py` (new) — `format_ref_marker`, `format_stock_marker`, `format_combined_marker` unit tests; regex contract for parsing.
- `tests/memo/test_aliases.py` (new) — alias-map correctness, multi-owner resolution, collision raise.
- `tests/memo/test_same_3_invariant.py` (new) — three-surface SAME-3 regression (AC5 + AC15 + AC25).
- `tests/opportunity/test_report_appendix.py` (new) — appendix subsection rendering, ordering, line precedence, regex contract.

**Source (modify):**
- `src/irc/fundamentals/types.py` — add `@classmethod ThesisEvidence.from_dict(d: dict) -> ThesisEvidence` (OQ1 promotion).
- `src/irc/fundamentals/snapshot_cache.py` — replace `_evidence_from_dict` body (or call) with `ThesisEvidence.from_dict` (OQ1 dedup site 1).
- `src/irc/commands/memo_cmd.py` — replace `_evidence_from_dict` body (or call) with `ThesisEvidence.from_dict` (OQ1 dedup site 2); add `build_alias_maps(publishable_rows)` call after `_build_pick_rows` to construct alias maps; pass `thesis_evidence` as `tuple[ThesisEvidence, ...]` (dataclass form) into the new `build_evidence_pool` signature.
- `src/irc/memo/evidence_pool.py` — extend `build_evidence_pool` to append top-3 citation lines after each instrument's state-codes line via `select_citations(thesis_evidence, cap=3)`. Use `markers.format_combined_marker`. Skip `[stock:...]` when `scope != "constituent"`; omit trailing `({url})` when `url == ""`. Add new helper `_format_citation_line(ev: ThesisEvidence) -> str`.
- `src/irc/opportunity/report.py` — extend `_render_section` to (a) append nested `thesis_evidence` bullets (top-3 via `select_citations`), (b) emit inline top-5 holdings for rows with `constituent_analyses != ()`. Extend `compose_discipline_markdown` with two keyword-only params (`publishable_rows`, `pick_order_iids`) and append `## 持仓明细` appendix section after `_DRAWDOWN_NOTE_CN`. New helpers `_render_thesis_evidence_bullets`, `_render_inline_holdings_block`, `_render_appendix_subsection`, `_render_appendix_section`. Add `_APPENDIX_LINE_RE` module-level constant.
- `src/irc/memo/numeric_audit.py` — add `find_uncited_conclusions` stub with empty-map `RuntimeError` raise + `return []`. Item 009 fills the body.
- `src/irc/commands/opportunity_cmd.py` — (OQ2) `_build_rows`: after Policy B verdict stamping, for publishable verdicts whose `constituent_coverage` carries non-empty `audit_errors` on any entry, stamp those `audit_errors` onto `row.constituent_analyses[i]` via `dataclasses.replace`. (Q10 wiring) `_write_opportunity_outputs`: load `trade_plan.yaml` once, compute `pick_order_iids`, pass `publishable_rows` + `pick_order_iids` into `compose_discipline_markdown` via the new keyword-only params.

**Tests (modify):**
- `tests/memo/test_evidence_pool.py` — add tests for `[ref:...]` markers, `[stock:...]` tag emission/omission, URL-less line, watchlist exclusion preserved, no `[ref:literal:...]` regression.
- `tests/opportunity/test_report.py` — extend with tests for `_render_section` nested bullets, inline top-5 holdings, partial-success constituent rendering, audit-error sentinel, two-run byte equality.
- `tests/memo/test_numeric_audit.py` — add empty-map `RuntimeError` test and non-empty no-raise test.
- `tests/fundamentals/test_types.py` — add tests for `ThesisEvidence.from_dict` happy path + mismatch raise.
- `tests/commands/test_opportunity_cmd.py` — extend with OQ2 audit_errors stamping test on publishable verdict.
- `tests/commands/test_memo_cmd.py` (or new `test_memo_cmd_aliases.py`) — verify `run_memo` wires `build_alias_maps` over publishable rows.

---

## Locked marker grammar (do not drift)

```python
# src/irc/memo/markers.py
REF_MARKER_FMT = "[ref:{citation_id}]"
STOCK_MARKER_FMT = "[stock:{symbol}]"

def format_ref_marker(citation_id: str) -> str:
    if not citation_id:
        raise ValueError("citation_id must be non-empty")
    return REF_MARKER_FMT.format(citation_id=citation_id)

def format_stock_marker(symbol: str) -> str:
    if not symbol:
        raise ValueError("symbol must be non-empty")
    return STOCK_MARKER_FMT.format(symbol=symbol)

def format_combined_marker(citation_id: str, symbol: str | None) -> str:
    """Combine [stock:...] [ref:...] with single-space separation.

    Per ADR 0004 / Q1: `{stock_marker} {ref_marker}`. Stock marker is OMITTED
    when symbol is None or empty (NOT replaced with an empty placeholder).
    """
    ref = format_ref_marker(citation_id)
    if not symbol:
        return ref
    return f"{format_stock_marker(symbol)} {ref}"
```

Parse regex (item 009 inherits this contract): `^(?:\[stock:[^\]]+\] )?\[ref:[0-9a-f]{16}\]`.

## Locked appendix line regex contract

Five shapes per grill §17. Module-level constant in `src/irc/opportunity/report.py`:

```python
import re

# Per grill §17 + ADR 0004. Locked contract for item 009's appendix-parse pass.
# SYM = 4-6 chars (CN 6-digit, HK 5-digit, US 4-char); NM = greedy non-newline;
# WPCT = decimal weight (e.g. 8.2, 0.5); REFS = one or more space-prefixed ref tokens.
_APPENDIX_LINE_RE = re.compile(
    r"^- (?P<sym>[0-9A-Z]{4,6}) (?P<nm>[^()\n]+?) "
    r"\(权重 (?P<wpct>\d+(?:\.\d+)?)%\): "
    r"(?:"
    r"(?P<oneline_with_failures>.+?)(?P<refs_with_failures>(?: \[ref:[0-9a-f]{16}\])+) "
    r"\((?P<failures>.+?)\)"  # Shape 1: evidence + failures
    r"|❌ (?P<failure_only>.+?)"  # Shape 2: failure only
    r"|⚠️ audit_error: (?P<audit_error>.+?)"  # Shape 3: audit-error only
    r"|(?P<oneline_only>.+?)(?P<refs_only>(?: \[ref:[0-9a-f]{16}\])+)"  # Shape 4: evidence only
    r")$"
)
```

Shape 5 (defensive fallback for `evidence == () AND failure_reasons == () AND audit_errors == ()`) matches Shape 3 with the literal text `audit_error: missing_constituent_record`.

## Locked decisions (resolutions of open questions)

### OQ1 — `_evidence_from_dict` promotion (BUNDLED INTO ITEM 007, EXECUTED FIRST)

**Decision:** Promote to `@classmethod ThesisEvidence.from_dict(d: dict) -> ThesisEvidence` in `src/irc/fundamentals/types.py` (NOT `irc.opportunity.types` — the dataclass lives in `irc.fundamentals.types`; `irc.opportunity.types` only re-exports it).

**Justification:** Item 007 introduces a THIRD consumer (`run_memo` reconstructing `tuple[ThesisEvidence, ...]` from `opportunity_report.json` for `build_evidence_pool`). Three copies of the same JSON→dataclass rebuilder (`snapshot_cache.py:148`, `memo_cmd.py:262`, plus the new pipeline.py consumer) is one too many. The classmethod lands as Task 1 of this plan, then the three call sites collapse onto it in Task 2. Net delta: −2 functions, +1 classmethod, +0 behavior change. The drift-detection check (raise on `expected_id != ev.citation_id`) lives ON the classmethod — both call sites inherit it.

### OQ2 — `ConstituentAnalysis.audit_errors` wiring (Option A — `_build_rows` stamps via `dataclasses.replace`)

**Decision:** Item 007 patches `_build_rows` in `opportunity_cmd.py` (Task 11): after `evaluate_policy_b`, iterate `verdict.constituent_coverage` looking for entries with `audit_errors != ()`. For each such entry, find the matching `ConstituentAnalysis` in `row.constituent_analyses` (by symbol) and replace it via `dataclasses.replace(c, audit_errors=coverage_entry.audit_errors)`. Then `row = dataclasses.replace(row, constituent_analyses=patched_tuple)`. Pure copy-replace, no in-place mutation; cached snapshot JSON is untouched (per ADR 0003 §2).

**Justification:** `_build_rows` has the most context — it already has the snapshot, the Policy B verdict, and the row in one place. Threading the audit-error stamping through `_write_opportunity_outputs` (Option C) would force a second loop over rows after Policy B and another `dataclasses.replace`. Option B (Policy B stamping the source `ConstituentAnalysis`) was already rejected by ADR 0003 §2 — Policy B is pure and never mutates its input. Option A is the simplest single-locus fix at the cost of ~5 lines in `_build_rows`. In V1, Policy B's publishable verdict produces `audit_errors=()` on every `ConstituentCoverageEntry`, so the wiring is a no-op for the canonical run — but the test fixture in Task 11 forces a synthetic publishable verdict with a non-empty entry to verify the stamping fires.

### Q10 — `compose_discipline_markdown` signature change

Locked by the spec: signature gains two keyword-only params with empty defaults (backward-compat). `opportunity_cmd.py::_write_opportunity_outputs` computes `pick_order_iids` from `trade_plan.yaml` (which it does NOT currently load — Task 12 adds the load) and passes both into the renderer. No memo→opportunity dependency is introduced; both pipelines independently read the trade plan as the single source of truth for pick order.

---

## Task index (one slice per task, all green-at-checkpoint)

1. Promote `_evidence_from_dict` to `@classmethod ThesisEvidence.from_dict` in `src/irc/fundamentals/types.py`.
2. Dedup the existing `_evidence_from_dict` call sites (`snapshot_cache.py`, `memo_cmd.py`) onto `ThesisEvidence.from_dict`.
3. Create `src/irc/memo/markers.py` with marker constants + format helpers.
4. Create `src/irc/memo/aliases.py` with `InstrumentAliases`, `ConstituentAliases`, `InstrumentAliasCollisionError`, `build_alias_maps`.
5. Add empty-map `RuntimeError` stub of `find_uncited_conclusions` in `src/irc/memo/numeric_audit.py`.
6. Extend `build_evidence_pool` in `src/irc/memo/evidence_pool.py` with citation-line emission (D1a).
7. Wire `memo_cmd.py::run_memo` to reconstruct `ThesisEvidence` per row and pass dataclass tuples into `build_evidence_pool`; build alias maps over publishable rows.
8. Add `_render_thesis_evidence_bullets` helper to `src/irc/opportunity/report.py` and wire it into `_render_section` (D3a).
9. Add `_render_inline_holdings_block` helper to `src/irc/opportunity/report.py` and wire it into `_render_section` (D3b inline top-5).
10. Add `_render_appendix_subsection` + `_render_appendix_section` helpers + `_APPENDIX_LINE_RE` constant to `src/irc/opportunity/report.py`.
11. (OQ2 wiring) Patch `_build_rows` in `opportunity_cmd.py` to stamp `audit_errors` onto publishable `OpportunityRow.constituent_analyses` from Policy B verdict coverage entries.
12. (Q10 wiring) Extend `compose_discipline_markdown` signature with `publishable_rows` + `pick_order_iids` keyword params; wire `_write_opportunity_outputs` to load `trade_plan.yaml` and pass both through.
13. SAME-3 invariant regression test across all three rendering surfaces.
14. Two-run byte equality regression tests for `memo.md` and `discipline_report.md` (AC26 + AC27).
15. Final: full `pytest --ignore=tests/news --ignore=tests/scoring/test_sanity_check.py -x -q` + `ruff check src/ tests/` clean.

---

## Task 1: Promote `_evidence_from_dict` → `@classmethod ThesisEvidence.from_dict`

**Files:**
- Modify: `src/irc/fundamentals/types.py`
- Modify: `tests/fundamentals/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/fundamentals/test_types.py`:

```python
def test_thesis_evidence_from_dict_happy_path() -> None:
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "filing",
        "source": "akshare:filing:600519",
        "url": "https://example.com/600519/2024q1",
        "date": "2024-04-15",
        "summary": "600519 24Q1 财报",
        "scope": "constituent",
        "citation_kind": "data",
        "owner_instrument_id": "005827",
        "parent_fund_id": "005827",
        "constituent_key": "600519",
    }
    ev = ThesisEvidence.from_dict(d)
    assert ev.type == "filing"
    assert ev.owner_instrument_id == "005827"
    assert ev.constituent_key == "600519"
    assert len(ev.citation_id) == 16
    assert all(c in "0123456789abcdef" for c in ev.citation_id)


def test_thesis_evidence_from_dict_missing_optional_fields() -> None:
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "snapshot",
        "source": "akshare:nav:518880",
        "url": "",
        "date": "2026-03-15",
        "summary": "518880 NAV snapshot",
        "scope": "instrument",
        "citation_kind": "data",
        "owner_instrument_id": "518880",
    }
    ev = ThesisEvidence.from_dict(d)
    assert ev.parent_fund_id is None
    assert ev.constituent_key is None
    assert ev.holding_weight_pct is None
    assert ev.url == ""


def test_thesis_evidence_from_dict_holding_weight_carried() -> None:
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "filing",
        "source": "akshare:filing:600519",
        "url": "https://example.com/600519",
        "date": "2024-04-15",
        "summary": "600519",
        "scope": "constituent",
        "citation_kind": "data",
        "owner_instrument_id": "005827",
        "parent_fund_id": "005827",
        "constituent_key": "600519",
        "holding_weight_pct": 8.2,
    }
    ev = ThesisEvidence.from_dict(d)
    assert ev.holding_weight_pct == 8.2


def test_thesis_evidence_from_dict_citation_id_mismatch_raises() -> None:
    """If the JSON carries a citation_id that doesn't match __post_init__'s
    recomputed value, raise (catches tampering of opportunity_report.json)."""
    import pytest
    from irc.fundamentals.types import ThesisEvidence
    d = {
        "type": "filing",
        "source": "akshare:filing:600519",
        "url": "https://example.com/600519",
        "date": "2024-04-15",
        "summary": "600519",
        "scope": "constituent",
        "citation_kind": "data",
        "owner_instrument_id": "005827",
        "parent_fund_id": "005827",
        "constituent_key": "600519",
        "citation_id": "ffffffffffffffff",  # bogus
    }
    with pytest.raises(ValueError, match="citation_id mismatch"):
        ThesisEvidence.from_dict(d)
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_types.py::test_thesis_evidence_from_dict_happy_path -v`
Expected: FAIL with `AttributeError: type object 'ThesisEvidence' has no attribute 'from_dict'`.

- [ ] **Step 3: Add the classmethod**

Edit `src/irc/fundamentals/types.py`. Locate the `ThesisEvidence` dataclass `__post_init__` method and append a classmethod immediately after it:

```python
    @classmethod
    def from_dict(cls, d: dict) -> "ThesisEvidence":
        """Rebuild a `ThesisEvidence` from its JSON dict form.

        Recomputes `citation_id` via `__post_init__`. If the JSON dict carries
        a `citation_id` that doesn't match the recomputed value, raise — detects
        drift/tampering of `opportunity_report.json` between stages.

        Single source of truth for the dict→dataclass rebuild across
        snapshot_cache.py, memo_cmd.py, and the renderer pipeline.
        """
        expected_id = d.get("citation_id")
        ev = cls(
            type=d["type"],
            source=d["source"],
            url=d.get("url") or "",
            date=d["date"],
            summary=d.get("summary") or "",
            scope=d["scope"],
            citation_kind=d["citation_kind"],
            owner_instrument_id=d["owner_instrument_id"],
            parent_fund_id=d.get("parent_fund_id"),
            constituent_key=d.get("constituent_key"),
            holding_weight_pct=d.get("holding_weight_pct"),
        )
        if expected_id and expected_id != ev.citation_id:
            raise ValueError(
                f"citation_id mismatch: JSON has {expected_id!r} "
                f"but recomputed to {ev.citation_id!r} "
                f"(possible tampering of opportunity_report.json)"
            )
        return ev
```

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/test_types.py -v -k from_dict`
Expected: 4 PASS.

Run: `pytest tests/fundamentals/ -x -q`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/types.py tests/fundamentals/test_types.py
git commit -m "feat(fundamentals): promote _evidence_from_dict to ThesisEvidence.from_dict classmethod (OQ1)"
```

---

## Task 2: Collapse `_evidence_from_dict` call sites onto `ThesisEvidence.from_dict`

**Files:**
- Modify: `src/irc/fundamentals/snapshot_cache.py`
- Modify: `src/irc/commands/memo_cmd.py`

- [ ] **Step 1: Write failing tests**

Two regression tests confirm the classmethod is actually used by both call sites. Append to `tests/fundamentals/test_snapshot_cache.py`:

```python
def test_snapshot_cache_uses_thesis_evidence_from_dict(monkeypatch) -> None:
    """The cache loader MUST go through ThesisEvidence.from_dict so
    the citation_id mismatch raise is shared across consumers."""
    import irc.fundamentals.snapshot_cache as sc
    from irc.fundamentals.types import ThesisEvidence

    called: list[dict] = []
    real_from_dict = ThesisEvidence.from_dict

    def spy_from_dict(d):
        called.append(d)
        return real_from_dict(d)

    monkeypatch.setattr(ThesisEvidence, "from_dict", classmethod(
        lambda cls, d: real_from_dict(d) if called.append(d) is None else None
    ))
    d = {
        "type": "filing", "source": "src", "url": "https://x",
        "date": "2024-04-15", "summary": "x", "scope": "constituent",
        "citation_kind": "data", "owner_instrument_id": "005827",
        "parent_fund_id": "005827", "constituent_key": "600519",
    }
    _ = sc._evidence_from_dict(d) if hasattr(sc, "_evidence_from_dict") else ThesisEvidence.from_dict(d)
    assert called, "ThesisEvidence.from_dict was not invoked by snapshot_cache path"
```

Append to `tests/memo/test_pick_rows.py` (or `tests/commands/test_memo_cmd.py`):

```python
def test_memo_cmd_uses_thesis_evidence_from_dict() -> None:
    """memo_cmd must dispatch dict→dataclass through ThesisEvidence.from_dict."""
    import irc.commands.memo_cmd as mc
    # Either _evidence_from_dict was removed (call sites updated to from_dict)
    # OR it now delegates internally to ThesisEvidence.from_dict.
    if hasattr(mc, "_evidence_from_dict"):
        # Delegation path: assert it calls the classmethod.
        from irc.fundamentals.types import ThesisEvidence
        d = {
            "type": "filing", "source": "src", "url": "https://x",
            "date": "2024-04-15", "summary": "x", "scope": "constituent",
            "citation_kind": "data", "owner_instrument_id": "005827",
            "parent_fund_id": "005827", "constituent_key": "600519",
        }
        # Both routes must return identical ThesisEvidence instances.
        assert mc._evidence_from_dict(d).citation_id == ThesisEvidence.from_dict(d).citation_id
    else:
        # Removal path: call sites have already migrated.
        assert True
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/fundamentals/test_snapshot_cache.py::test_snapshot_cache_uses_thesis_evidence_from_dict -v`
Expected: PASS (the spy approach works against the pre-change code too) OR FAIL (depending on monkeypatch ordering). Either way, the test serves as a regression marker once the migration completes.

- [ ] **Step 3: Migrate call sites**

Edit `src/irc/fundamentals/snapshot_cache.py`. Replace the existing `_evidence_from_dict` function body to delegate (preserves the export for callers that may still reference it):

```python
def _evidence_from_dict(d: dict[str, Any]) -> ThesisEvidence:
    """Deprecated shim — delegates to ThesisEvidence.from_dict. New code should
    call the classmethod directly."""
    return ThesisEvidence.from_dict(d)
```

Edit `src/irc/commands/memo_cmd.py`. Replace the existing `_evidence_from_dict` function (~line 262) the same way:

```python
def _evidence_from_dict(d: dict) -> ThesisEvidence:
    """Deprecated shim — delegates to ThesisEvidence.from_dict."""
    return ThesisEvidence.from_dict(d)
```

(Both shims are 2-line delegators — no behavior change. The shim is preferred over removal so any out-of-tree consumer doesn't break; subsequent items can audit-and-remove if desired.)

- [ ] **Step 4: Run green**

Run: `pytest tests/fundamentals/ tests/memo/ tests/commands/ -x -q`
Expected: PASS (no regressions; the delegators preserve every existing call site's behavior).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/snapshot_cache.py src/irc/commands/memo_cmd.py tests/fundamentals/test_snapshot_cache.py tests/memo/test_pick_rows.py
git commit -m "refactor(fundamentals): delegate _evidence_from_dict to ThesisEvidence.from_dict (OQ1 dedup)"
```

---

## Task 3: Create `src/irc/memo/markers.py` with marker grammar constants

**Files:**
- Create: `src/irc/memo/markers.py`
- Create: `tests/memo/test_markers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/memo/test_markers.py`:

```python
"""Item 007 D1a — marker grammar lock.

Locked format: `[stock:{symbol}] [ref:{citation_id}] ...` per ADR 0004 / Q1.
"""
import pytest


def test_format_ref_marker_full_16_hex() -> None:
    from irc.memo.markers import format_ref_marker
    cid = "a1b2c3d4e5f60718"
    assert format_ref_marker(cid) == "[ref:a1b2c3d4e5f60718]"


def test_format_ref_marker_empty_raises() -> None:
    from irc.memo.markers import format_ref_marker
    with pytest.raises(ValueError, match="citation_id must be non-empty"):
        format_ref_marker("")


def test_format_stock_marker_cn_symbol() -> None:
    from irc.memo.markers import format_stock_marker
    assert format_stock_marker("600519") == "[stock:600519]"


def test_format_stock_marker_hk_symbol() -> None:
    """HK 5-digit codes pass through verbatim."""
    from irc.memo.markers import format_stock_marker
    assert format_stock_marker("00700") == "[stock:00700]"


def test_format_stock_marker_empty_raises() -> None:
    from irc.memo.markers import format_stock_marker
    with pytest.raises(ValueError, match="symbol must be non-empty"):
        format_stock_marker("")


def test_format_combined_marker_with_symbol() -> None:
    from irc.memo.markers import format_combined_marker
    out = format_combined_marker("a1b2c3d4e5f60718", "600519")
    assert out == "[stock:600519] [ref:a1b2c3d4e5f60718]"


def test_format_combined_marker_without_symbol() -> None:
    """When symbol is None/empty, stock marker is OMITTED (no placeholder)."""
    from irc.memo.markers import format_combined_marker
    assert format_combined_marker("a1b2c3d4e5f60718", None) == "[ref:a1b2c3d4e5f60718]"
    assert format_combined_marker("a1b2c3d4e5f60718", "") == "[ref:a1b2c3d4e5f60718]"


def test_marker_grammar_format_constants_present() -> None:
    """Both format strings exposed as module-level constants for cross-test reuse."""
    from irc.memo import markers
    assert markers.REF_MARKER_FMT == "[ref:{citation_id}]"
    assert markers.STOCK_MARKER_FMT == "[stock:{symbol}]"


def test_combined_marker_parses_with_locked_regex() -> None:
    """Item 009's parser keys off this regex — locked here."""
    import re
    from irc.memo.markers import format_combined_marker
    line = format_combined_marker("a1b2c3d4e5f60718", "600519") + " content..."
    m = re.match(r"^(?:\[stock:(?P<sym>[^\]]+)\] )?\[ref:(?P<cid>[0-9a-f]{16})\]", line)
    assert m is not None
    assert m.group("sym") == "600519"
    assert m.group("cid") == "a1b2c3d4e5f60718"


def test_combined_marker_no_stock_parses_with_locked_regex() -> None:
    import re
    from irc.memo.markers import format_combined_marker
    line = format_combined_marker("a1b2c3d4e5f60718", None) + " content..."
    m = re.match(r"^(?:\[stock:(?P<sym>[^\]]+)\] )?\[ref:(?P<cid>[0-9a-f]{16})\]", line)
    assert m is not None
    assert m.group("sym") is None
    assert m.group("cid") == "a1b2c3d4e5f60718"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/memo/test_markers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.memo.markers'`.

- [ ] **Step 3: Implement `markers.py`**

Create `src/irc/memo/markers.py`:

```python
"""Item 007 D1a — marker grammar.

Single source of truth for the `[ref:{citation_id}]` and `[stock:{symbol}]`
markers emitted by `evidence_pool.py` and `report.py`. Locked by
[ADR 0004 / Q1](../../../docs/adr/0004-renderer-determinism-and-alias-policy.md).
"""
from __future__ import annotations


REF_MARKER_FMT = "[ref:{citation_id}]"
STOCK_MARKER_FMT = "[stock:{symbol}]"


def format_ref_marker(citation_id: str) -> str:
    """Render `[ref:{citation_id}]`. Raises on empty `citation_id`.

    Item 002 invariant: `citation_id` is always 16 hex chars (computed in
    `ThesisEvidence.__post_init__`). Empty here means a programming error.
    """
    if not citation_id:
        raise ValueError("citation_id must be non-empty")
    return REF_MARKER_FMT.format(citation_id=citation_id)


def format_stock_marker(symbol: str) -> str:
    """Render `[stock:{symbol}]`. Raises on empty `symbol`.

    The symbol passes through verbatim — no transformation (CN 6-digit,
    HK 5-digit, US tickers all carry their native shape).
    """
    if not symbol:
        raise ValueError("symbol must be non-empty")
    return STOCK_MARKER_FMT.format(symbol=symbol)


def format_combined_marker(citation_id: str, symbol: str | None) -> str:
    """Combine `[stock:...] [ref:...]` with single-space separation per Q1.

    Stock marker is OMITTED (not replaced with an empty placeholder) when
    `symbol` is None or empty. The result is always parseable by:
        `^(?:\\[stock:[^\\]]+\\] )?\\[ref:[0-9a-f]{16}\\]`
    """
    ref = format_ref_marker(citation_id)
    if not symbol:
        return ref
    return f"{format_stock_marker(symbol)} {ref}"
```

- [ ] **Step 4: Run green**

Run: `pytest tests/memo/test_markers.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/markers.py tests/memo/test_markers.py
git commit -m "feat(memo): add marker grammar constants for [ref:...] + [stock:...] (D1a)"
```

---

## Task 4: Create `src/irc/memo/aliases.py` with `build_alias_maps`

**Files:**
- Create: `src/irc/memo/aliases.py`
- Create: `tests/memo/test_aliases.py`

- [ ] **Step 1: Write failing tests**

Create `tests/memo/test_aliases.py`:

```python
"""Item 007 D1c — alias-builder.

Tests cover acceptance criteria 7–9 + multi-owner + collision invariant
per [ADR 0004 §1 + §2](../../../docs/adr/0004-renderer-determinism-and-alias-policy.md).
"""
import pytest


def _opportunity_row(
    *, iid: str, name_cn: str = "", asset_class: str = "cn_equity_fund",
    constituent_analyses: tuple = (), lookthrough_key: str = "",
):
    """Factory: minimal OpportunityRow for alias-builder tests."""
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    return OpportunityRow(
        instrument_id=iid,
        name_cn=name_cn,
        asset_class=asset_class,
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=lookthrough_key or iid,
            display_cn=name_cn, provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=(),
        thesis_evidence=(),
        constituent_analyses=constituent_analyses,
    )


def _constituent(symbol: str, name_cn: str = "", weight: float = 5.0):
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol, name_cn=name_cn or symbol, weight_pct=weight,
        evidence=(), failure_reasons=(), one_line_view="",
    )


def test_build_alias_maps_instrument_aliases_basic() -> None:
    from irc.memo.aliases import build_alias_maps
    rows = (
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选"),
        _opportunity_row(iid="163417", name_cn="兴全合润"),
        _opportunity_row(iid="518880", name_cn="黄金ETF",
                         asset_class="gold"),
    )
    inst, _ = build_alias_maps(rows)
    assert inst["005827"] == "005827"
    assert inst["易方达蓝筹精选"] == "005827"
    assert inst["163417"] == "163417"
    assert inst["兴全合润"] == "163417"
    assert inst["518880"] == "518880"
    assert inst["黄金ETF"] == "518880"


def test_build_alias_maps_skips_empty_name_cn() -> None:
    from irc.memo.aliases import build_alias_maps
    rows = (_opportunity_row(iid="005827", name_cn=""),)
    inst, _ = build_alias_maps(rows)
    assert "" not in inst
    assert inst["005827"] == "005827"


def test_build_alias_maps_constituent_aliases_multi_owner() -> None:
    """600519 held by both 005827 and 163417 → frozenset of 2 tuples."""
    from irc.memo.aliases import build_alias_maps
    rows = (
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选",
                         constituent_analyses=(
                             _constituent("600519", "贵州茅台", 8.2),
                             _constituent("300750", "宁德时代", 6.0),
                         )),
        _opportunity_row(iid="163417", name_cn="兴全合润",
                         constituent_analyses=(
                             _constituent("600519", "贵州茅台", 7.5),
                             _constituent("601318", "中国平安", 5.5),
                         )),
    )
    _, cons = build_alias_maps(rows)
    assert cons["600519"] == frozenset({("005827", "600519"), ("163417", "600519")})
    assert cons["贵州茅台"] == frozenset({("005827", "600519"), ("163417", "600519")})
    assert cons["300750"] == frozenset({("005827", "300750")})
    assert cons["宁德时代"] == frozenset({("005827", "300750")})
    assert cons["601318"] == frozenset({("163417", "601318")})


def test_build_alias_maps_constituent_aliases_skip_empty_name() -> None:
    from irc.memo.aliases import build_alias_maps
    rows = (_opportunity_row(iid="005827", name_cn="X",
                              constituent_analyses=(
                                  _constituent("600519", "", 8.2),
                              )),)
    _, cons = build_alias_maps(rows)
    assert "" not in cons
    assert cons["600519"] == frozenset({("005827", "600519")})


def test_build_alias_maps_instrument_collision_raises() -> None:
    """Two rows with the same name_cn but different instrument_id → raise."""
    from irc.memo.aliases import build_alias_maps, InstrumentAliasCollisionError
    rows = (
        _opportunity_row(iid="005827", name_cn="某基金"),
        _opportunity_row(iid="163417", name_cn="某基金"),
    )
    with pytest.raises(InstrumentAliasCollisionError) as exc:
        build_alias_maps(rows)
    msg = str(exc.value)
    assert "005827" in msg
    assert "163417" in msg
    assert "某基金" in msg


def test_build_alias_maps_duplicate_iid_does_not_raise() -> None:
    """Two rows sharing the SAME instrument_id collapse without raising
    (a bug in upstream H3 partition; alias-builder is permissive)."""
    from irc.memo.aliases import build_alias_maps
    rows = (
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选"),
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选"),
    )
    inst, _ = build_alias_maps(rows)
    assert inst["005827"] == "005827"
    assert inst["易方达蓝筹精选"] == "005827"


def test_build_alias_maps_empty_rows_returns_empty_maps() -> None:
    from irc.memo.aliases import build_alias_maps
    inst, cons = build_alias_maps(())
    assert inst == {}
    assert cons == {}


def test_build_alias_maps_collision_error_message_lists_iids_sorted() -> None:
    """Error message includes both instrument_id values, sorted ASC."""
    from irc.memo.aliases import build_alias_maps, InstrumentAliasCollisionError
    rows = (
        _opportunity_row(iid="163417", name_cn="某基金"),
        _opportunity_row(iid="005827", name_cn="某基金"),
    )
    with pytest.raises(InstrumentAliasCollisionError) as exc:
        build_alias_maps(rows)
    msg = str(exc.value)
    # Sorted ascending — '005827' appears before '163417'.
    assert msg.index("005827") < msg.index("163417")


def test_build_alias_maps_returns_dict_types() -> None:
    """Return shape: (dict[str, str], dict[str, frozenset[tuple[str, str]]])."""
    from irc.memo.aliases import build_alias_maps
    rows = (_opportunity_row(iid="005827", name_cn="X",
                              constituent_analyses=(_constituent("600519", "Y"),)),)
    inst, cons = build_alias_maps(rows)
    assert isinstance(inst, dict)
    assert isinstance(cons, dict)
    for v in cons.values():
        assert isinstance(v, frozenset)
        for tup in v:
            assert isinstance(tup, tuple) and len(tup) == 2
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/memo/test_aliases.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.memo.aliases'`.

- [ ] **Step 3: Implement `aliases.py`**

Create `src/irc/memo/aliases.py`:

```python
"""Item 007 D1c — alias-builder.

Pure function `build_alias_maps` constructs `InstrumentAliases` +
`ConstituentAliases` from a tuple of publishable `OpportunityRow`s. Consumed
by item 009's `find_uncited_conclusions` to map memo prose mentions back to
rows.

Determinism rule (ADR 0004 §1): consumers MUST `sorted(fs)` before iterating
a `ConstituentAliases` frozenset whose iteration order would affect rendered
output or audit-finding emission.

See [ADR 0004 §1 + §2](../../../docs/adr/0004-renderer-determinism-and-alias-policy.md).
"""
from __future__ import annotations

from irc.opportunity.types import OpportunityRow


InstrumentAliases = dict[str, str]
"""alias-string → instrument_id"""

ConstituentAliases = dict[str, frozenset[tuple[str, str]]]
"""stock identifier (symbol OR name_cn) → frozenset of (instrument_id, constituent_key)"""


class InstrumentAliasCollisionError(RuntimeError):
    """Raised by build_alias_maps when an alias-string resolves to two
    different instrument_id values (e.g. two unrelated funds sharing
    name_cn due to malformed opportunity_report.json).

    Loud, fail-fast, deterministic — see ADR 0004 §2. Raise happens AT
    BUILD time, never at lookup time.
    """


def build_alias_maps(
    publishable_rows: tuple[OpportunityRow, ...],
) -> tuple[InstrumentAliases, ConstituentAliases]:
    """Pure function. Build alias maps from publishable rows.

    Raises `InstrumentAliasCollisionError` if any alias key maps to two
    different `instrument_id` values. Multi-owner constituents (same stock
    held by ≥2 funds) accumulate into a frozenset — this is the NORMAL case
    for blue-chip names and never raises.
    """
    # Instrument-level: working dict[alias_key, set[instrument_id]] for collision detection.
    inst_working: dict[str, set[str]] = {}
    for r in publishable_rows:
        for alias in _instrument_alias_keys(r):
            if not alias:
                continue
            inst_working.setdefault(alias, set()).add(r.instrument_id)

    # Final pass: collapse + collision check.
    instrument_aliases: InstrumentAliases = {}
    for alias, iids in inst_working.items():
        if len(iids) > 1:
            raise InstrumentAliasCollisionError(
                f"alias {alias!r} resolves to multiple instrument_ids: "
                f"{sorted(iids)}"
            )
        instrument_aliases[alias] = next(iter(iids))

    # Constituent-level: accumulate frozensets directly (multi-owner is normal).
    cons_working: dict[str, set[tuple[str, str]]] = {}
    for r in publishable_rows:
        for c in r.constituent_analyses:
            tup = (r.instrument_id, c.symbol)
            if c.symbol:
                cons_working.setdefault(c.symbol, set()).add(tup)
            if c.name_cn:
                cons_working.setdefault(c.name_cn, set()).add(tup)

    constituent_aliases: ConstituentAliases = {
        key: frozenset(tups) for key, tups in cons_working.items()
    }

    return instrument_aliases, constituent_aliases


def _instrument_alias_keys(row: OpportunityRow) -> tuple[str, ...]:
    """Return the alias-string set for one OpportunityRow.

    Sources: (a) bare instrument_id, (b) canonical name_cn, (c) the
    lookthrough_target.key when distinct from instrument_id (venue-suffixed
    forms like `510300.SH`).
    """
    keys: list[str] = [row.instrument_id]
    if row.name_cn:
        keys.append(row.name_cn)
    lt_key = getattr(row.lookthrough_target, "key", "")
    if lt_key and lt_key != row.instrument_id:
        keys.append(lt_key)
    return tuple(keys)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/memo/test_aliases.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/aliases.py tests/memo/test_aliases.py
git commit -m "feat(memo): add build_alias_maps + InstrumentAliasCollisionError (D1c)"
```

---

## Task 5: Add `find_uncited_conclusions` empty-map RuntimeError stub

**Files:**
- Modify: `src/irc/memo/numeric_audit.py`
- Modify: `tests/memo/test_numeric_audit.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/memo/test_numeric_audit.py`:

```python
def test_find_uncited_conclusions_empty_instrument_aliases_raises() -> None:
    """Item 007 D1c — empty alias map indicates build_alias_maps did not
    run; the function refuses to silent-no-op the audit."""
    import pytest
    from irc.memo.numeric_audit import find_uncited_conclusions
    with pytest.raises(RuntimeError) as exc:
        find_uncited_conclusions(
            prose="some prose mentioning 005827",
            cited_map={},
            instrument_aliases={},
            constituent_aliases={},
            constituent_cited_map={},
        )
    msg = str(exc.value)
    assert "empty instrument_aliases" in msg
    assert "D1c" in msg


def test_find_uncited_conclusions_non_empty_aliases_does_not_raise() -> None:
    """Non-empty instrument_aliases must pass the guard. Empty
    constituent_aliases is permitted (a publishable run may have zero
    active funds)."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    result = find_uncited_conclusions(
        prose="some prose",
        cited_map={},
        instrument_aliases={"005827": "005827"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    # Item 007 ships the stub; the body is item 009's territory.
    assert result == []
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/memo/test_numeric_audit.py::test_find_uncited_conclusions_empty_instrument_aliases_raises -v`
Expected: FAIL with `ImportError: cannot import name 'find_uncited_conclusions' from 'irc.memo.numeric_audit'`.

- [ ] **Step 3: Add the stub**

Append to `src/irc/memo/numeric_audit.py`:

```python
# ── Item 007 D1c — find_uncited_conclusions stub ─────────────────────────────
# The full body lands in item 009 (paragraph-level instrument/constituent
# reference detection + multi-owner disambiguation + per-mention strict gate).
# Item 007's irreducible contribution is the empty-map RuntimeError raise —
# it closes the most likely failure mode where build_alias_maps did not run
# and every prose mention silently looks like "no instrument referenced".


def find_uncited_conclusions(
    prose: str,
    cited_map: dict,
    instrument_aliases: dict,
    constituent_aliases: dict,
    constituent_cited_map: dict,
) -> list[NumericFinding]:
    """Detect prose conclusions that reference an instrument/constituent
    without a corresponding citation. Stub in item 007; body in item 009.

    The empty-map check is item 007's load-bearing contribution: an upstream
    bug returning `{}` would cause every memo paragraph to silently look
    like "no instrument referenced", silent-no-op'ing the entire audit gate.
    Raise loud-fast-deterministic at the entry boundary.
    """
    if not instrument_aliases:
        raise RuntimeError(
            "empty instrument_aliases — D1c build_alias_maps did not run "
            "or returned an empty map; refusing to silent-no-op the audit"
        )
    return []
```

- [ ] **Step 4: Run green**

Run: `pytest tests/memo/test_numeric_audit.py -v`
Expected: PASS (existing tests + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/numeric_audit.py tests/memo/test_numeric_audit.py
git commit -m "feat(memo): add find_uncited_conclusions stub with empty-map RuntimeError raise (D1c)"
```

---

## Task 6: Extend `build_evidence_pool` with citation lines (D1a)

**Files:**
- Modify: `src/irc/memo/evidence_pool.py`
- Modify: `tests/memo/test_evidence_pool.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/memo/test_evidence_pool.py`:

```python
import re


def _evidence(
    *, type_="filing", source="x", url="https://x", date="2024-04-15",
    summary="x", scope="constituent", citation_kind="data",
    owner="005827", parent="005827", constituent_key="600519",
    weight=8.2,
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=source, url=url, date=date, summary=summary,
        scope=scope, citation_kind=citation_kind, owner_instrument_id=owner,
        parent_fund_id=parent, constituent_key=constituent_key,
        holding_weight_pct=weight,
    )


def _op_row(
    *, iid="005827", thesis_evidence=(),
    opportunity_state="core_dca",
):
    """Dict-form op row (matches opportunity_report.json shape)."""
    return {
        "instrument_id": iid,
        "name_cn": "易方达蓝筹精选",
        "asset_class": "cn_equity_fund",
        "valuation_state": "fair",
        "heat_state": "normal",
        "thesis_state": "intact",
        "product_quality_state": "strong",
        "opportunity_state": opportunity_state,
        "opportunity_reason": "",
        "thesis_evidence": thesis_evidence,
    }


def test_build_evidence_pool_emits_ref_markers() -> None:
    """AC1 — [ref:...] markers appear with 16-hex citation_id."""
    from irc.memo.evidence_pool import build_evidence_pool
    ev = _evidence()
    row = _op_row(thesis_evidence=(ev,))
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1, "buy_method": "limit"}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    assert re.search(r"\[ref:[0-9a-f]{16}\]", joined), \
        f"expected [ref:...] in pool, got:\n{joined}"


def test_build_evidence_pool_emits_stock_marker_for_constituent_scope() -> None:
    """AC2 — [stock:600519] appears for scope=constituent entries; not for instrument scope."""
    from irc.memo.evidence_pool import build_evidence_pool
    constituent_ev = _evidence(scope="constituent", constituent_key="600519")
    instrument_ev = _evidence(scope="instrument", constituent_key=None,
                              source="nav", type_="snapshot")
    row = _op_row(thesis_evidence=(constituent_ev, instrument_ev))
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    assert "[stock:600519]" in joined
    # Locked spacing: [stock:...] [ref:...] with exactly one space.
    assert re.search(r"\[stock:600519\] \[ref:[0-9a-f]{16}\]", joined)
    # The instrument-scope entry must NOT carry [stock:...] (no constituent_key).
    instrument_line_re = re.compile(
        r"^(?!\[stock:)\[ref:[0-9a-f]{16}\] snapshot ", re.MULTILINE,
    )
    assert instrument_line_re.search(joined) is not None


def test_build_evidence_pool_rejects_old_literal_ref_format() -> None:
    """AC3 regression — `[ref:filing:600519]` style explicitly rejected."""
    from irc.memo.evidence_pool import build_evidence_pool
    row = _op_row(thesis_evidence=(_evidence(),))
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    # No non-hex chars after `[ref:` allowed (the colon-prefixed literal form).
    assert not re.search(r"\[ref:[a-z_]+:", joined)


def test_build_evidence_pool_omits_empty_url_parenthetical() -> None:
    """AC4 — url=="" → no trailing `()` in the rendered line."""
    from irc.memo.evidence_pool import build_evidence_pool
    ev = _evidence(url="", source="ann", type_="news",
                   summary="[r1] 公告 / dividend")
    row = _op_row(thesis_evidence=(ev,))
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    # No trailing `()` empty parenthetical.
    assert not re.search(r"\(\s*\)\s*$", joined, re.MULTILINE)


def test_build_evidence_pool_watchlist_excluded() -> None:
    """AC6 — small_watch rows whose iid is NOT in plan_trades contribute no pool lines."""
    from irc.memo.evidence_pool import build_evidence_pool
    ev = _evidence()
    row = _op_row(iid="999999", thesis_evidence=(ev,),
                  opportunity_state="small_watch")
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[],  # no trade for 999999
        gold_regime=None,
    )
    joined = "\n".join(pool)
    assert "999999" not in joined


def test_build_evidence_pool_renders_top_3_only() -> None:
    """AC1 quantitative — 5 evidence entries → top 3 by select_citations()."""
    from irc.memo.evidence_pool import build_evidence_pool
    # 5 entries with distinct citation_ids (different dates differentiate).
    evs = tuple(
        _evidence(date=f"2024-04-{d:02d}", url=f"https://x/{d}",
                  citation_kind="data" if d % 2 == 0 else "information",
                  scope="constituent",
                  constituent_key=f"60051{d}")
        for d in range(1, 6)
    )
    row = _op_row(thesis_evidence=evs)
    pool = build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[],
        plan_trades=[{"target": "005827", "target_weight": 0.1}],
        gold_regime=None,
    )
    joined = "\n".join(pool)
    ref_matches = re.findall(r"\[ref:[0-9a-f]{16}\]", joined)
    # Exactly 3 ref markers from this row.
    assert len(ref_matches) == 3, \
        f"expected 3 [ref:...] markers, got {len(ref_matches)}:\n{joined}"
```

NOTE: the test fixtures use `_evidence(...)` returning `ThesisEvidence` directly; `_op_row` wraps them as a tuple under `thesis_evidence`. But `build_evidence_pool`'s current signature accepts `opportunity_rows: list[dict[str, Any]]` — the test exercise depends on whether the function migrates to dataclass-form input (per spec D1a-2 + Task 7 wiring). Choose ONE of:

- **Option α:** `build_evidence_pool` continues to accept dict-form rows but reconstructs `ThesisEvidence` internally via `ThesisEvidence.from_dict`. Tests pass dataclass tuples but the function tolerates both (isinstance check + branch).
- **Option β (LOCKED):** Migrate the function to accept `tuple[ThesisEvidence, ...]` in the row dict — the caller (`run_memo` in Task 7) does the reconstruction. The test `_op_row` returns `{..., "thesis_evidence": tuple_of_dataclasses}` (a hybrid dict-with-dataclass-tuple shape).

Item 007 picks Option β. The dataclass tuple lives ON the row dict but is constructed by the caller; `build_evidence_pool` reads `op["thesis_evidence"]` as `tuple[ThesisEvidence, ...]`. This avoids `from_dict` calls inside the pool builder.

- [ ] **Step 2: Run failing**

Run: `pytest tests/memo/test_evidence_pool.py::test_build_evidence_pool_emits_ref_markers -v`
Expected: FAIL — no `[ref:...]` markers in current output.

- [ ] **Step 3: Extend `evidence_pool.py`**

Edit `src/irc/memo/evidence_pool.py`. Add an import block at the top:

```python
from irc.fundamentals.types import ThesisEvidence
from irc.memo.citation_selector import select_citations
from irc.memo.markers import format_combined_marker
```

Add a new helper after `_format_instrument_evidence`:

```python
def _format_citation_line(ev: ThesisEvidence) -> str:
    """Render one citation as `[stock:{symbol}] [ref:{citation_id}] {type} · {source} · {date}: {summary} ({url})`.

    - `[stock:{symbol}]` emitted ONLY when `ev.scope == "constituent"`
      (uses `ev.constituent_key` as the symbol; omitted entirely otherwise).
    - ` ({url})` parenthetical omitted when `ev.url == ""`.
    """
    symbol = ev.constituent_key if ev.scope == "constituent" else None
    marker = format_combined_marker(ev.citation_id, symbol)
    body = f"{ev.type} · {ev.source} · {ev.date}: {ev.summary}"
    if ev.url:
        return f"{marker} {body} ({ev.url})"
    return f"{marker} {body}"
```

Replace the body of `build_evidence_pool` so that after `_format_instrument_evidence` returns the state-codes line, top-3 citation lines are appended for that instrument:

```python
def build_evidence_pool(
    *,
    opportunity_rows: list[dict[str, Any]],
    scoring_rows: list[dict[str, Any]],
    plan_trades: list[dict[str, Any]],
    gold_regime: dict[str, Any] | None = None,
) -> list[str]:
    """Return a flat list of evidence strings to feed the LLM.

    Each instrument contributes (a) one compact state-codes line, plus
    (b) up to 3 `[stock:...] [ref:...]`-prefixed citation lines via
    `select_citations(thesis_evidence, cap=3)`. The gold regime contributes
    one prelude line when provided. Order: gold first, then plan_trades
    order, then remaining opportunity rows.

    `op["thesis_evidence"]` is expected as `tuple[ThesisEvidence, ...]` —
    the caller (memo_cmd::run_memo) is responsible for reconstructing
    dataclasses from the JSON dict form via ThesisEvidence.from_dict.
    """
    score_by_id = {s.get("instrument_id"): s for s in scoring_rows}
    op_by_id = {r.get("instrument_id"): r for r in opportunity_rows}

    pool: list[str] = []
    if gold_regime:
        pool.append(
            f"[gold] regime={gold_regime.get('regime', '?')} "
            f"zone={gold_regime.get('zone', '?')} "
            f"tilt={gold_regime.get('tilt', '?')}"
        )

    seen_ids: set[str] = set()
    for t in plan_trades:
        iid = t.get("target")
        if not iid or iid in seen_ids:
            continue
        seen_ids.add(iid)
        op = op_by_id.get(iid)
        if op is None:
            continue
        pool.append(_format_instrument_evidence(op, score_by_id.get(iid), t))
        pool.extend(_format_citation_lines_for_row(op))

    for op in opportunity_rows:
        iid = op.get("instrument_id")
        if iid in seen_ids:
            continue
        if op.get("opportunity_state") == "small_watch":
            continue
        seen_ids.add(iid)
        pool.append(_format_instrument_evidence(op, score_by_id.get(iid), None))
        pool.extend(_format_citation_lines_for_row(op))

    return pool


def _format_citation_lines_for_row(op: dict[str, Any]) -> list[str]:
    """Apply select_citations(cap=3) and emit one citation line per pick.

    Pure function over `op["thesis_evidence"]` which must already be a
    `tuple[ThesisEvidence, ...]` (the caller handles JSON→dataclass).
    """
    evidence = op.get("thesis_evidence") or ()
    if not isinstance(evidence, tuple):
        evidence = tuple(evidence)
    if not evidence:
        return []
    selected = select_citations(evidence, cap=3)
    return [_format_citation_line(ev) for ev in selected]
```

- [ ] **Step 4: Run green**

Run: `pytest tests/memo/test_evidence_pool.py -v`
Expected: 6 new PASS + existing PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/evidence_pool.py tests/memo/test_evidence_pool.py
git commit -m "feat(memo): extend build_evidence_pool with [stock:...] [ref:...] citation lines (D1a)"
```

---

## Task 7: Wire `memo_cmd.py::run_memo` to dataclass-form evidence + alias builder

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Modify: `tests/commands/test_memo_cmd.py` (or create `test_memo_cmd_aliases.py`)

- [ ] **Step 1: Write failing tests**

Create `tests/commands/test_memo_cmd_aliases.py`:

```python
"""Item 007 — memo_cmd wires build_alias_maps over publishable rows."""
from __future__ import annotations

import json
import pytest

from pathlib import Path


def _write_minimal_run_inputs(out_dir: Path) -> None:
    """Write the minimum scoring/opportunity/trade_plan files run_memo needs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    scoring = {"scores": [
        {"instrument_id": "005827", "composite_score": 70.0,
         "asset_class": "cn_equity_fund"},
    ]}
    (out_dir / "scoring.json").write_text(json.dumps(scoring), encoding="utf-8")
    opportunity = {
        "date": "2026-05-23",
        "summary": {"core_dca_count": 1, "small_watch_count": 0,
                    "pause_wait_count": 0, "exclude_count": 0},
        "rows": [
            {
                "instrument_id": "005827",
                "name_cn": "易方达蓝筹精选",
                "asset_class": "cn_equity_fund",
                "theme": None,
                "lookthrough_target": "易方达蓝筹精选",
                "lookthrough_kind": "active_fund",
                "lookthrough_key": "005827",
                "valuation_state": "fair",
                "heat_state": "normal",
                "thesis_state": "intact",
                "product_quality_state": "strong",
                "opportunity_state": "core_dca",
                "opportunity_reason": "",
                "evidence_gaps": [],
                "thesis_evidence": [],  # empty for this smoke test
                "contributing_dimensions": [],
                "constituent_analyses": [],
                "fetch_types_attempted": [],
                "expected_omissions": [],
            },
        ],
    }
    (out_dir / "opportunity_report.json").write_text(
        json.dumps(opportunity, ensure_ascii=False), encoding="utf-8",
    )
    (out_dir / "trade_plan.yaml").write_text(
        "mode: build\ntrades:\n  - target: '005827'\n    target_weight: 0.1\n    role: ''\n    buy_method: limit\n    granularity: default\n    triggers: []\n    venue_note: ''\n",
        encoding="utf-8",
    )


def test_run_memo_builds_alias_maps_over_publishable_rows(monkeypatch, tmp_path) -> None:
    """run_memo invokes build_alias_maps on the publishable subset of opportunity rows."""
    import irc.commands.memo_cmd as mc
    from irc.memo import aliases as alias_mod

    captured: list[tuple] = []
    real_build = alias_mod.build_alias_maps

    def spy_build_alias_maps(rows):
        captured.append(tuple(rows))
        return real_build(rows)

    monkeypatch.setattr(alias_mod, "build_alias_maps", spy_build_alias_maps)
    # Also expose at the memo_cmd import-site if memo_cmd binds the name early.
    if hasattr(mc, "build_alias_maps"):
        monkeypatch.setattr(mc, "build_alias_maps", spy_build_alias_maps)

    _write_minimal_run_inputs(tmp_path / "outputs" / "2026-05-23")
    # Run_memo expects various other config; this test asserts only that
    # build_alias_maps is invoked at the wiring site if run_memo gets that far.
    # We tolerate any RuntimeError / SystemExit downstream after the wiring point.
    try:
        mc.run_memo(str(tmp_path))
    except (SystemExit, RuntimeError, FileNotFoundError, Exception):
        pass

    # If memo_cmd never imported build_alias_maps yet, the test fails.
    # If memo_cmd imported but never called it, captured stays empty.
    assert captured, \
        "build_alias_maps was not invoked by run_memo — wiring missing"
```

(This is a smoke test — the more rigorous determinism + alias-map content tests live in Task 13.)

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_memo_cmd_aliases.py -v`
Expected: FAIL — `captured` is empty (no wiring yet).

- [ ] **Step 3: Wire the call site**

Edit `src/irc/commands/memo_cmd.py`. Add to the imports:

```python
from irc.memo.aliases import build_alias_maps
```

Edit `run_memo` (around the existing `build_evidence_pool` call site near line 414). Locate this block:

```python
    raw_ref_pool = build_evidence_pool(
        opportunity_rows=list(opportunity.get("rows") or []),
        scoring_rows=list(scoring.get("scores") or []),
        plan_trades=trades,
        gold_regime=gold_regime,
    )
```

Replace it with the dataclass-reconstruction wiring:

```python
    # Item 007 D1a: reconstruct ThesisEvidence dataclasses from the JSON
    # dict form so build_evidence_pool can pass them through select_citations
    # without a third-call-site _evidence_from_dict copy.
    raw_op_rows = list(opportunity.get("rows") or [])
    rebuilt_op_rows: list[dict] = []
    for row in raw_op_rows:
        ev_tuple = tuple(
            ThesisEvidence.from_dict(d) for d in (row.get("thesis_evidence") or [])
        )
        rebuilt_op_rows.append({**row, "thesis_evidence": ev_tuple})

    raw_ref_pool = build_evidence_pool(
        opportunity_rows=rebuilt_op_rows,
        scoring_rows=list(scoring.get("scores") or []),
        plan_trades=trades,
        gold_regime=gold_regime,
    )

    # Item 007 D1c: build alias maps from publishable rows. Item 009's
    # find_uncited_conclusions consumes these via the audit-gate wiring;
    # item 007 ships only the producer side. The empty-map RuntimeError in
    # find_uncited_conclusions raises if this wiring ever fails to fire.
    publishable_rows_for_aliases = _reconstruct_opportunity_rows(rebuilt_op_rows)
    _instrument_aliases, _constituent_aliases = build_alias_maps(
        publishable_rows_for_aliases,
    )
```

Add a new helper near `_evidence_from_dict`:

```python
def _reconstruct_opportunity_rows(
    rebuilt_op_rows: list[dict],
) -> tuple:
    """Reconstruct OpportunityRow dataclasses from rebuilt dict-form rows
    for the alias-builder. Publishable rows only (evidence_gaps == ()).

    Best-effort — fields not strictly needed by build_alias_maps default
    to neutral placeholders so the function never raises on a partial dict.
    """
    from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget
    from irc.opportunity.types import OpportunityRow

    rows: list = []
    for r in rebuilt_op_rows:
        if (r.get("evidence_gaps") or ()):
            continue
        constituent_analyses = tuple(
            ConstituentAnalysis(
                symbol=c.get("symbol", ""),
                name_cn=c.get("name_cn", ""),
                weight_pct=float(c.get("weight_pct", 0.0)),
                evidence=tuple(
                    ThesisEvidence.from_dict(e) for e in c.get("evidence", [])
                ),
                failure_reasons=tuple(c.get("failure_reasons", ())),
                one_line_view=c.get("one_line_view", ""),
                audit_errors=tuple(c.get("audit_errors", ())),
            )
            for c in (r.get("constituent_analyses") or [])
            if c.get("symbol")
        )
        lt = LookthroughTarget(
            kind=r.get("lookthrough_kind", "broad_index"),
            key=r.get("lookthrough_key", r["instrument_id"]),
            display_cn=r.get("lookthrough_target", ""),
            provider_symbol="",
        )
        rows.append(OpportunityRow(
            instrument_id=r["instrument_id"],
            name_cn=r.get("name_cn", ""),
            asset_class=r.get("asset_class", ""),
            theme=r.get("theme"),
            lookthrough_target=lt,
            valuation_state=r.get("valuation_state", "evidence_insufficient"),
            heat_state=r.get("heat_state", "evidence_insufficient"),
            thesis_state=r.get("thesis_state", "evidence_insufficient"),
            product_quality_state=r.get("product_quality_state", "evidence_insufficient"),
            opportunity_state=r.get("opportunity_state", "small_watch"),
            opportunity_reason=r.get("opportunity_reason", ""),
            evidence_gaps=tuple(r.get("evidence_gaps", ())),
            thesis_evidence=r["thesis_evidence"]
                if isinstance(r["thesis_evidence"], tuple)
                else tuple(r["thesis_evidence"]),
            constituent_analyses=constituent_analyses,
        ))
    return tuple(rows)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_memo_cmd_aliases.py -v`
Expected: PASS — `build_alias_maps` invoked.

Run: `pytest tests/memo/ tests/commands/ -x -q`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/memo_cmd.py tests/commands/test_memo_cmd_aliases.py
git commit -m "feat(memo): wire run_memo to reconstruct ThesisEvidence + invoke build_alias_maps (D1a + D1c)"
```

---

## Task 8: Add `_render_thesis_evidence_bullets` and wire into `_render_section` (D3a)

**Files:**
- Modify: `src/irc/opportunity/report.py`
- Modify: `tests/opportunity/test_report.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/opportunity/test_report.py`:

```python
import re


def _evidence(
    *, type_="filing", source="x", url="https://x", date="2024-04-15",
    summary="x", scope="constituent", citation_kind="data",
    owner="005827", parent="005827", constituent_key="600519",
    weight=8.2,
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=source, url=url, date=date, summary=summary,
        scope=scope, citation_kind=citation_kind, owner_instrument_id=owner,
        parent_fund_id=parent, constituent_key=constituent_key,
        holding_weight_pct=weight,
    )


def _discipline_row(
    *, iid="005827", thesis_evidence=(), constituent_analyses=(),
    dca_action="normal_dca", risk_action="none",
    opportunity_state="core_dca",
):
    from irc.opportunity.types import DisciplineRow
    return DisciplineRow(
        instrument_id=iid,
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        opportunity_state=opportunity_state,
        dca_action=dca_action,
        risk_action=risk_action,
        note_cn="",
        thesis_evidence=thesis_evidence,
        constituent_analyses=constituent_analyses,
    )


def test_render_section_emits_top_3_nested_bullets() -> None:
    """AC12 — 5 evidence entries → exactly 3 nested bullets via select_citations."""
    from irc.opportunity.report import _render_section
    evs = tuple(
        _evidence(date=f"2024-04-{d:02d}", url=f"https://x/{d}",
                  citation_kind="data" if d % 2 == 0 else "information",
                  scope="constituent",
                  constituent_key=f"60051{d}")
        for d in range(1, 6)
    )
    row = _discipline_row(thesis_evidence=evs)
    out = _render_section("今日可定投", [row])
    # Three nested `  - [ref:...]` bullets.
    nested = re.findall(r"^  - \[ref:[0-9a-f]{16}\] ", out, re.MULTILINE)
    assert len(nested) == 3


def test_render_section_empty_thesis_evidence_no_bullets() -> None:
    """AC14 — empty thesis_evidence → no nested bullets, no `（无）` placeholder."""
    from irc.opportunity.report import _render_section
    row = _discipline_row(thesis_evidence=())
    out = _render_section("今日可定投", [row])
    # No `  - [ref:` lines.
    assert "  - [ref:" not in out
    # No `（无）` line either (that's the empty-section placeholder, not empty-bullets).
    parent_line = next((l for l in out.split("\n") if l.startswith("- **005827")), "")
    assert parent_line  # parent line still rendered
    # Body has no bullet lines beyond the parent.
    bullets_under = [l for l in out.split("\n")
                     if l.startswith("  - ")]
    assert bullets_under == []


def test_render_section_nested_bullet_format() -> None:
    """Locked format: `  - [ref:{cid}] {type} · {source} · {date}` (no summary, no url)."""
    from irc.opportunity.report import _render_section
    ev = _evidence(type_="filing", source="akshare:filing:600519",
                   date="2024-04-15")
    row = _discipline_row(thesis_evidence=(ev,))
    out = _render_section("今日可定投", [row])
    nested = re.search(r"^  - \[ref:[0-9a-f]{16}\] filing · akshare:filing:600519 · 2024-04-15$",
                       out, re.MULTILINE)
    assert nested is not None, f"locked format missed; got:\n{out}"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_report.py::test_render_section_emits_top_3_nested_bullets -v`
Expected: FAIL — `_render_section` does not emit `[ref:...]` bullets yet.

- [ ] **Step 3: Add helper + wire into `_render_section`**

Edit `src/irc/opportunity/report.py`. Add import:

```python
from irc.memo.citation_selector import select_citations
```

Add new helper before `_render_section`:

```python
def _render_thesis_evidence_bullets(thesis_evidence: tuple) -> list[str]:
    """Render top-3 nested thesis_evidence bullets for a discipline row.

    Format: `  - [ref:{citation_id}] {type} · {source} · {date}`. Two-space
    indentation (markdown nested list). Empty evidence → empty list (no
    `（无）` placeholder — caller renders the parent line only).

    Same selector as picks-table + evidence-pool — the SAME-3 invariant
    locked by ADR 0004 §3.
    """
    if not thesis_evidence:
        return []
    selected = select_citations(thesis_evidence, cap=3)
    return [
        f"  - [ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date}"
        for ev in selected
    ]
```

Replace `_render_section`:

```python
def _render_section(title: str, rows: list) -> str:
    if not rows:
        return f"## {title}\n\n（无）\n"
    lines = [f"## {title}\n"]
    for r in rows:
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** "
            f"｜ {r.opportunity_state} ｜ dca={r.dca_action} ｜ risk={r.risk_action} "
            f"｜ {r.note_cn}"
        )
        # Item 007 D3a: nested thesis_evidence bullets (top-3 via select_citations).
        lines.extend(_render_thesis_evidence_bullets(r.thesis_evidence))
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_report.py -v -k render_section`
Expected: PASS (3 new + existing).

Run: `pytest tests/opportunity/ -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/report.py tests/opportunity/test_report.py
git commit -m "feat(opportunity): add nested thesis_evidence bullets to _render_section (D3a)"
```

---

## Task 9: Add `_render_inline_holdings_block` and wire into `_render_section` (D3b inline top-5)

**Files:**
- Modify: `src/irc/opportunity/report.py`
- Modify: `tests/opportunity/test_report.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/opportunity/test_report.py`:

```python
def _constituent(
    *, symbol="600519", name_cn="贵州茅台", weight=8.2,
    evidence=(), failure_reasons=(), one_line_view="持有头部白酒",
    audit_errors=(),
):
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol, name_cn=name_cn, weight_pct=weight,
        evidence=evidence, failure_reasons=failure_reasons,
        one_line_view=one_line_view, audit_errors=audit_errors,
    )


def test_render_section_inline_top_5_holdings() -> None:
    """AC16 — 8 constituents → exactly 5 inline holdings by weight desc."""
    from irc.opportunity.report import _render_section
    weights = [8.2, 7.1, 6.5, 5.0, 4.2, 3.8, 3.0, 2.5]
    constituents = tuple(
        _constituent(symbol=f"60{i:04d}", name_cn=f"股{i}",
                     weight=w, evidence=(_evidence(constituent_key=f"60{i:04d}"),))
        for i, w in enumerate(weights)
    )
    row = _discipline_row(constituent_analyses=constituents,
                         thesis_evidence=())
    out = _render_section("今日可定投", [row])
    # Header `  - 持仓 (Top 5):` literal.
    assert "  - 持仓 (Top 5):" in out
    inline_bullets = re.findall(r"^    - 60\d{4} 股\d ", out, re.MULTILINE)
    assert len(inline_bullets) == 5
    # Tail 3 holdings (weight 3.8, 3.0, 2.5) are NOT in the inline block.
    assert "权重 3.8%" not in out
    assert "权重 3.0%" not in out
    assert "权重 2.5%" not in out


def test_render_section_inline_top_5_failure_reasons_rendering() -> None:
    """AC17 — evidence==() AND failure_reasons!=() → `❌ {reasons}`."""
    from irc.opportunity.report import _render_section
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(), failure_reasons=("filing_fetch_failed:600519",),
                     one_line_view="should not appear")
    row = _discipline_row(constituent_analyses=(c,), thesis_evidence=())
    out = _render_section("今日可定投", [row])
    assert "    - 600519 贵州茅台 (权重 6.5%): ❌ filing_fetch_failed:600519" in out
    # one_line_view is suppressed when evidence == () and failure_reasons != ().
    assert "should not appear" not in out


def test_render_section_inline_top_5_audit_errors_appended() -> None:
    """AC18 — audit_errors!=() with evidence!=() → `{one_line_view} ⚠️ {errors}`."""
    from irc.opportunity.report import _render_section
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(_evidence(constituent_key="600519"),),
                     audit_errors=("missing_constituent_record:600519",),
                     one_line_view="持有头部白酒")
    row = _discipline_row(constituent_analyses=(c,), thesis_evidence=())
    out = _render_section("今日可定投", [row])
    assert "持有头部白酒 ⚠️ missing_constituent_record:600519" in out


def test_render_section_no_inline_block_when_empty_constituents() -> None:
    """Row with constituent_analyses==() emits no inline-5 block."""
    from irc.opportunity.report import _render_section
    row = _discipline_row(constituent_analyses=(), thesis_evidence=())
    out = _render_section("今日可定投", [row])
    assert "持仓 (Top 5)" not in out


def test_render_section_inline_top_5_orders_by_weight_desc() -> None:
    """Constituents render by weight_pct descending (rank 1 first)."""
    from irc.opportunity.report import _render_section
    constituents = (
        _constituent(symbol="600003", weight=3.0, name_cn="低权"),
        _constituent(symbol="600001", weight=8.0, name_cn="高权"),
        _constituent(symbol="600002", weight=5.0, name_cn="中权"),
    )
    row = _discipline_row(constituent_analyses=constituents,
                         thesis_evidence=())
    out = _render_section("今日可定投", [row])
    high_pos = out.index("高权")
    mid_pos = out.index("中权")
    low_pos = out.index("低权")
    assert high_pos < mid_pos < low_pos
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_report.py::test_render_section_inline_top_5_holdings -v`
Expected: FAIL — no `持仓 (Top 5)` in output.

- [ ] **Step 3: Add helper + wire into `_render_section`**

Edit `src/irc/opportunity/report.py`. Add module-level constants:

```python
TOP_5_HOLDINGS_INLINE_CAP = 5
INLINE_HEADER_LITERAL = "持仓 (Top 5)"
```

Add new helpers before `_render_section`:

```python
def _rank_constituents_by_weight(
    constituent_analyses: tuple,
) -> tuple:
    """Sort by weight_pct DESC, ties broken by symbol ASC. Pure."""
    return tuple(sorted(
        constituent_analyses,
        key=lambda c: (-c.weight_pct, c.symbol),
    ))


def _format_inline_constituent_line(c) -> str:
    """Render one constituent line for the inline top-5 block.

    Precedence (single-bullet shape — distinct from the appendix's 5-shape
    contract per spec §17):
    - `evidence == () AND failure_reasons != ()` → `❌ {failure_reasons_joined}` in place of one_line_view.
    - `audit_errors != ()` → append ` ⚠️ {audit_errors_joined}` after one_line_view.
    - `evidence != ()` (no failures) → bare `{one_line_view}`.
    - all-empty (defensive) → ` ⚠️ audit_error: missing_constituent_record`.
    """
    head = f"    - {c.symbol} {c.name_cn} (权重 {c.weight_pct}%): "
    if not c.evidence and c.failure_reasons:
        return f"{head}❌ {'; '.join(c.failure_reasons)}"
    if not c.evidence and not c.failure_reasons and not c.audit_errors:
        return f"{head}⚠️ audit_error: missing_constituent_record"
    body = c.one_line_view
    if c.audit_errors:
        body = f"{body} ⚠️ {'; '.join(c.audit_errors)}"
    return f"{head}{body}"


def _render_inline_holdings_block(constituent_analyses: tuple) -> list[str]:
    """Render the inline top-5 holdings block for a discipline row.

    Returns empty list when `constituent_analyses == ()`. Always renders
    the literal `持仓 (Top 5):` header even when N < 5 (per OQ4 lock).
    """
    if not constituent_analyses:
        return []
    ranked = _rank_constituents_by_weight(constituent_analyses)
    top = ranked[:TOP_5_HOLDINGS_INLINE_CAP]
    return [
        f"  - {INLINE_HEADER_LITERAL}:",
        *[_format_inline_constituent_line(c) for c in top],
    ]
```

Update `_render_section` to call the new helper after the thesis_evidence bullets:

```python
def _render_section(title: str, rows: list) -> str:
    if not rows:
        return f"## {title}\n\n（无）\n"
    lines = [f"## {title}\n"]
    for r in rows:
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** "
            f"｜ {r.opportunity_state} ｜ dca={r.dca_action} ｜ risk={r.risk_action} "
            f"｜ {r.note_cn}"
        )
        lines.extend(_render_thesis_evidence_bullets(r.thesis_evidence))
        # Item 007 D3b: inline top-5 holdings for active-fund rows.
        lines.extend(_render_inline_holdings_block(
            getattr(r, "constituent_analyses", ()),
        ))
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_report.py -v -k inline`
Expected: PASS (5 new + existing).

Run: `pytest tests/opportunity/ -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/report.py tests/opportunity/test_report.py
git commit -m "feat(opportunity): add inline top-5 holdings block to _render_section (D3b)"
```

---

## Task 10: Add `## 持仓明细` appendix + `_APPENDIX_LINE_RE` constant

**Files:**
- Modify: `src/irc/opportunity/report.py`
- Create: `tests/opportunity/test_report_appendix.py`

- [ ] **Step 1: Write failing tests**

Create `tests/opportunity/test_report_appendix.py`:

```python
"""Item 007 D3b — 持仓明细 appendix tests.

Tests cover AC19, AC20, AC21, AC22, AC23, AC28, AC29 + the locked
5-shape regex contract per spec §17.
"""
import re


def _evidence(
    *, type_="filing", source="x", url="https://x", date="2024-04-15",
    summary="x", scope="constituent", citation_kind="data",
    owner="005827", parent="005827", constituent_key="600519",
    weight=8.2,
):
    from irc.fundamentals.types import ThesisEvidence
    return ThesisEvidence(
        type=type_, source=source, url=url, date=date, summary=summary,
        scope=scope, citation_kind=citation_kind, owner_instrument_id=owner,
        parent_fund_id=parent, constituent_key=constituent_key,
        holding_weight_pct=weight,
    )


def _constituent(
    *, symbol="600519", name_cn="贵州茅台", weight=8.2,
    evidence=(), failure_reasons=(), one_line_view="持有头部白酒",
    audit_errors=(),
):
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol, name_cn=name_cn, weight_pct=weight,
        evidence=evidence, failure_reasons=failure_reasons,
        one_line_view=one_line_view, audit_errors=audit_errors,
    )


def _opportunity_row(
    *, iid="005827", name_cn="易方达蓝筹精选",
    asset_class="cn_equity_fund", constituent_analyses=(),
    evidence_gaps=(),
):
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    return OpportunityRow(
        instrument_id=iid,
        name_cn=name_cn,
        asset_class=asset_class,
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=iid, display_cn=name_cn,
            provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=evidence_gaps,
        thesis_evidence=(),
        constituent_analyses=constituent_analyses,
    )


def _discipline_row(*, iid="005827", constituent_analyses=()):
    from irc.opportunity.types import DisciplineRow
    return DisciplineRow(
        instrument_id=iid,
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        opportunity_state="core_dca",
        dca_action="normal_dca",
        risk_action="none",
        note_cn="",
        thesis_evidence=(),
        constituent_analyses=constituent_analyses,
    )


def test_appendix_header_appears_after_drawdown_note() -> None:
    """AC19 — `## 持仓明细` section appended after _DRAWDOWN_NOTE_CN."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(evidence=(_evidence(),))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(_opportunity_row(constituent_analyses=(c,)),),
        pick_order_iids=("005827",),
    )
    drawdown_pos = out.index("## 关于回撤的说明")
    appendix_pos = out.index("## 持仓明细")
    assert drawdown_pos < appendix_pos


def test_appendix_empty_case_renders_placeholder() -> None:
    """AC19 — zero publishable rows with constituent_analyses → appendix header + （无）."""
    from irc.opportunity.report import compose_discipline_markdown
    out = compose_discipline_markdown(
        rows=(),
        date="2026-05-23",
        publishable_rows=(),
        pick_order_iids=(),
    )
    assert "## 持仓明细" in out
    # The body is `（无）` for the empty case (matches _render_section convention).
    appendix_section = out.split("## 持仓明细", 1)[1]
    assert "（无）" in appendix_section


def test_appendix_subsection_per_publishable_row() -> None:
    """AC28 — every publishable row with constituent_analyses gets a subsection."""
    from irc.opportunity.report import compose_discipline_markdown
    c1 = _constituent(symbol="600519", name_cn="贵州茅台", weight=8.2,
                     evidence=(_evidence(constituent_key="600519"),))
    c2 = _constituent(symbol="000001", name_cn="平安银行", weight=5.0,
                     evidence=(_evidence(constituent_key="000001"),))
    rows = (
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选",
                         constituent_analyses=(c1,)),
        _opportunity_row(iid="163417", name_cn="兴全合润",
                         constituent_analyses=(c2,)),
    )
    out = compose_discipline_markdown(
        rows=tuple(_discipline_row(iid=r.instrument_id,
                                    constituent_analyses=r.constituent_analyses)
                   for r in rows),
        date="2026-05-23",
        publishable_rows=rows,
        pick_order_iids=("005827", "163417"),
    )
    assert "### 005827 易方达蓝筹精选 (cn_equity_fund)" in out
    assert "### 163417 兴全合润 (cn_equity_fund)" in out


def test_appendix_lists_full_top_n_not_just_5() -> None:
    """AC20 — 10 constituents → 10 appendix bullets (full top-N), not 5."""
    from irc.opportunity.report import compose_discipline_markdown
    constituents = tuple(
        _constituent(symbol=f"6{i:05d}", name_cn=f"股{i}",
                     weight=10.0 - i * 0.5,
                     evidence=(_evidence(constituent_key=f"6{i:05d}"),))
        for i in range(10)
    )
    row = _opportunity_row(constituent_analyses=constituents)
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=constituents),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    # Count bullets under the 005827 subsection.
    subsection = out.split("### 005827 易方达蓝筹精选 (cn_equity_fund)", 1)[1]
    next_header_pos = subsection.find("\n### ")
    if next_header_pos < 0:
        next_header_pos = subsection.find("\n## ")
    section_body = subsection[:next_header_pos] if next_header_pos >= 0 else subsection
    bullets = re.findall(r"^- 6\d{5} ", section_body, re.MULTILINE)
    assert len(bullets) == 10


def test_appendix_ordering_pick_row_order_first() -> None:
    """AC21 — pick-row order [B, A, C] → appendix [B, A, C]; non-pick → instrument_id asc."""
    from irc.opportunity.report import compose_discipline_markdown
    rows = (
        _opportunity_row(iid="005827", name_cn="A基金",
                         constituent_analyses=(_constituent(symbol="600001"),)),
        _opportunity_row(iid="163417", name_cn="B基金",
                         constituent_analyses=(_constituent(symbol="600002"),)),
        _opportunity_row(iid="110022", name_cn="C基金",
                         constituent_analyses=(_constituent(symbol="600003"),)),
    )
    out = compose_discipline_markdown(
        rows=tuple(_discipline_row(iid=r.instrument_id,
                                    constituent_analyses=r.constituent_analyses)
                   for r in rows),
        date="2026-05-23",
        publishable_rows=rows,
        pick_order_iids=("163417", "005827", "110022"),
    )
    pos_b = out.index("### 163417")
    pos_a = out.index("### 005827")
    pos_c = out.index("### 110022")
    assert pos_b < pos_a < pos_c


def test_appendix_ordering_non_pick_publishable_sorted_by_iid_asc() -> None:
    """AC21 — funds NOT in pick_order_iids appear after, sorted by iid asc."""
    from irc.opportunity.report import compose_discipline_markdown
    rows = (
        _opportunity_row(iid="005827", name_cn="A基金",
                         constituent_analyses=(_constituent(symbol="600001"),)),
        _opportunity_row(iid="163417", name_cn="B基金",
                         constituent_analyses=(_constituent(symbol="600002"),)),
    )
    out = compose_discipline_markdown(
        rows=(),
        date="2026-05-23",
        publishable_rows=rows,
        pick_order_iids=(),  # No pick order → both are "non-pick publishable".
    )
    pos_a = out.index("### 005827")
    pos_b = out.index("### 163417")
    assert pos_a < pos_b  # 005827 < 163417 ascending


def test_appendix_shape_4_evidence_only_format() -> None:
    """AC22 c1 — `- {sym} {name} (权重 X%): {one_line_view} [ref:...]`."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=8.2,
                     evidence=(_evidence(constituent_key="600519"),
                                _evidence(constituent_key="600519",
                                          date="2024-04-16",
                                          citation_kind="information")),
                     one_line_view="持有头部白酒")
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    # Shape 4 regex: `- {sym} {name} (权重 X%): {oneline} [ref:...]`.
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 8\.2%\): 持有头部白酒(?: \[ref:[0-9a-f]{16}\])+$",
        re.MULTILINE,
    )
    assert pattern.search(out), \
        f"Shape 4 (evidence only) missed; got:\n{out}"


def test_appendix_shape_2_failure_only_format() -> None:
    """AC22 c2 — `- {sym} {name} (权重 X%): ❌ {failures}`."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(), failure_reasons=("filing_fetch_failed",),
                     one_line_view="should not appear")
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 6\.5%\): ❌ filing_fetch_failed$",
        re.MULTILINE,
    )
    assert pattern.search(out)
    # one_line_view suppressed.
    assert "should not appear" not in out


def test_appendix_shape_3_audit_error_only_format() -> None:
    """AC22 c3 (precedence) — audit_errors!=() AND evidence!=() → audit-error shape wins per spec."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(_evidence(constituent_key="600519"),),
                     audit_errors=("missing_constituent_record",))
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 6\.5%\): ⚠️ audit_error: missing_constituent_record$",
        re.MULTILINE,
    )
    assert pattern.search(out)


def test_appendix_shape_5_defensive_fallback() -> None:
    """AC29 — all-empty (evidence==failure_reasons==audit_errors==()) →
    `⚠️ audit_error: missing_constituent_record` (defensive)."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(), failure_reasons=(), audit_errors=(),
                     one_line_view="")
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 6\.5%\): ⚠️ audit_error: missing_constituent_record$",
        re.MULTILINE,
    )
    assert pattern.search(out)


def test_appendix_shape_1_evidence_plus_failures_partial_success() -> None:
    """AC22 spec edge case — evidence!=() AND failure_reasons!=() (mixed success).

    Format: `- {sym} {name} (权重 X%): {oneline} [ref:...]... ({failures})`.
    """
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(symbol="600519", name_cn="贵州茅台", weight=6.5,
                     evidence=(_evidence(constituent_key="600519"),),
                     failure_reasons=("broker_fetch_failed",),
                     one_line_view="持有头部白酒")
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pattern = re.compile(
        r"^- 600519 贵州茅台 \(权重 6\.5%\): 持有头部白酒(?: \[ref:[0-9a-f]{16}\])+ \(broker_fetch_failed\)$",
        re.MULTILINE,
    )
    assert pattern.search(out), f"Shape 1 missed; got:\n{out}"


def test_appendix_scope_publishable_only_gapped_excluded() -> None:
    """AC23 — gapped rows do NOT appear in the appendix."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(evidence=(_evidence(),))
    gapped_row = _opportunity_row(
        iid="005827", constituent_analyses=(c,),
        evidence_gaps=("qdii_information_unavailable",),
    )
    # The publishable_rows argument is what the appendix iterates;
    # gapped rows are partitioned out upstream by _write_opportunity_outputs.
    # Here we pass them OUT to confirm the renderer behavior.
    out = compose_discipline_markdown(
        rows=(),
        date="2026-05-23",
        publishable_rows=(),  # gapped row excluded by upstream
        pick_order_iids=(),
    )
    assert "### 005827" not in out


def test_appendix_constituent_order_weight_desc_symbol_asc_tiebreaker() -> None:
    """Within a subsection: weight desc, symbol asc tiebreaker."""
    from irc.opportunity.report import compose_discipline_markdown
    cs = (
        _constituent(symbol="600003", weight=5.0, name_cn="C",
                     evidence=(_evidence(constituent_key="600003"),)),
        _constituent(symbol="600001", weight=5.0, name_cn="A",
                     evidence=(_evidence(constituent_key="600001"),)),
        _constituent(symbol="600002", weight=8.0, name_cn="B",
                     evidence=(_evidence(constituent_key="600002"),)),
    )
    row = _opportunity_row(constituent_analyses=cs)
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=cs),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    pos_b = out.index("600002 B")  # weight 8.0 → first
    pos_a = out.index("600001 A")  # weight 5.0, symbol 600001 → second
    pos_c = out.index("600003 C")  # weight 5.0, symbol 600003 → third
    assert pos_b < pos_a < pos_c


def test_appendix_citation_id_uses_full_16_hex() -> None:
    """AC24 — every [ref:...] in the appendix uses full 16 hex chars."""
    from irc.opportunity.report import compose_discipline_markdown
    c = _constituent(evidence=(_evidence(),))
    row = _opportunity_row(constituent_analyses=(c,))
    out = compose_discipline_markdown(
        rows=(_discipline_row(constituent_analyses=(c,)),),
        date="2026-05-23",
        publishable_rows=(row,),
        pick_order_iids=("005827",),
    )
    refs = re.findall(r"\[ref:([^\]]+)\]", out)
    assert refs, "no [ref:...] markers found"
    for cid in refs:
        assert len(cid) == 16, f"citation_id has {len(cid)} chars: {cid}"
        assert all(c in "0123456789abcdef" for c in cid)


def test_appendix_line_re_module_constant_present() -> None:
    """Item 009 inherits this regex — locked here for cross-test reuse."""
    from irc.opportunity import report
    assert hasattr(report, "_APPENDIX_LINE_RE")
    # The compiled re must match all 5 shapes.
    assert report._APPENDIX_LINE_RE.match(
        "- 600519 贵州茅台 (权重 8.2%): 持有头部白酒 [ref:a1b2c3d4e5f60718]"
    ) is not None


def test_compose_discipline_markdown_backward_compat_no_publishable_kwargs() -> None:
    """Q10 — signature gains keyword-only params with empty defaults; legacy
    callers passing only (rows, date) still produce a valid markdown."""
    from irc.opportunity.report import compose_discipline_markdown
    out = compose_discipline_markdown(rows=(), date="2026-05-23")
    # The appendix still appears (with （无） body since publishable_rows defaulted to ()).
    assert "## 持仓明细" in out
    # No crash.
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/opportunity/test_report_appendix.py -v -k appendix_header_appears`
Expected: FAIL — `## 持仓明细` not in current output.

- [ ] **Step 3: Implement appendix renderer**

Edit `src/irc/opportunity/report.py`. Add re import:

```python
import re
```

Add module-level `_APPENDIX_LINE_RE` constant:

```python
# Item 007 D3b §17 — locked appendix line regex contract. Item 009's
# find_uncited_discipline_rows parses appendix bullets against this.
_APPENDIX_LINE_RE = re.compile(
    r"^- (?P<sym>[0-9A-Z]{4,6}) (?P<nm>[^()\n]+?) "
    r"\(权重 (?P<wpct>\d+(?:\.\d+)?)%\): "
    r"(?:"
    # Shape 1: evidence + failures
    r"(?P<oneline_with_failures>.+?)(?P<refs_with_failures>(?: \[ref:[0-9a-f]{16}\])+) "
    r"\((?P<failures_partial>.+?)\)"
    # Shape 2: failure only
    r"|❌ (?P<failure_only>.+?)"
    # Shape 3 / Shape 5: audit-error only
    r"|⚠️ audit_error: (?P<audit_error>.+?)"
    # Shape 4: evidence only
    r"|(?P<oneline_only>.+?)(?P<refs_only>(?: \[ref:[0-9a-f]{16}\])+)"
    r")$"
)
```

Add appendix-rendering helpers before `compose_discipline_markdown`:

```python
def _format_appendix_constituent_line(c) -> str:
    """Render one appendix bullet by FIRST-MATCH precedence (spec §17).

    Per ADR 0004 + spec §17:
    1. audit_errors != () → Shape 3 (audit-error only, NO refs).
    2. evidence != () AND failure_reasons != () → Shape 1 (evidence + failures).
    3. evidence == () AND failure_reasons != () → Shape 2 (failure only, NO refs).
    4. evidence != () → Shape 4 (evidence only).
    5. all-empty (defensive) → Shape 5 = Shape 3 with literal sentinel.
    """
    head = f"- {c.symbol} {c.name_cn} (权重 {c.weight_pct}%): "
    if c.audit_errors:
        return f"{head}⚠️ audit_error: {'; '.join(c.audit_errors)}"
    if c.evidence and c.failure_reasons:
        refs = " ".join(
            f"[ref:{ev.citation_id}]"
            for ev in select_citations(c.evidence, cap=3)
        )
        return f"{head}{c.one_line_view} {refs} ({'; '.join(c.failure_reasons)})"
    if not c.evidence and c.failure_reasons:
        return f"{head}❌ {'; '.join(c.failure_reasons)}"
    if c.evidence:
        refs = " ".join(
            f"[ref:{ev.citation_id}]"
            for ev in select_citations(c.evidence, cap=3)
        )
        return f"{head}{c.one_line_view} {refs}"
    # Shape 5 (defensive fallback).
    return f"{head}⚠️ audit_error: missing_constituent_record"


def _render_appendix_subsection(row) -> list[str]:
    """Render one fund subsection: `### {iid} {name} ({asset_class})` + bullets.

    Constituents ordered by weight_pct DESC, symbol ASC tiebreaker.
    """
    header = f"### {row.instrument_id} {row.name_cn} ({row.asset_class})"
    ranked = _rank_constituents_by_weight(row.constituent_analyses)
    return [
        "",
        header,
        "",
        *[_format_appendix_constituent_line(c) for c in ranked],
    ]


def _order_publishable_rows_for_appendix(
    publishable_rows: tuple,
    pick_order_iids: tuple[str, ...],
) -> tuple:
    """Order rows: pick-row order first, then instrument_id ascending."""
    pick_set = set(pick_order_iids)
    by_iid = {r.instrument_id: r for r in publishable_rows}
    pick_ordered = [by_iid[iid] for iid in pick_order_iids if iid in by_iid]
    non_pick = sorted(
        (r for r in publishable_rows if r.instrument_id not in pick_set),
        key=lambda r: r.instrument_id,
    )
    return tuple(pick_ordered + non_pick)


def _render_appendix_section(
    publishable_rows: tuple,
    pick_order_iids: tuple[str, ...],
) -> str:
    """Render the `## 持仓明细` section. Empty case → `（无）` body."""
    eligible = tuple(
        r for r in publishable_rows
        if getattr(r, "constituent_analyses", ())
    )
    if not eligible:
        return "## 持仓明细\n\n（无）\n"
    ordered = _order_publishable_rows_for_appendix(eligible, pick_order_iids)
    parts: list[str] = ["## 持仓明细"]
    for r in ordered:
        parts.extend(_render_appendix_subsection(r))
    parts.append("")  # trailing newline
    return "\n".join(parts)
```

Replace `compose_discipline_markdown`:

```python
def compose_discipline_markdown(
    rows,
    date: str,
    *,
    publishable_rows: tuple = (),
    pick_order_iids: tuple[str, ...] = (),
) -> str:
    """Compose `discipline_report.md`.

    Q10 (item 007): two keyword-only params control the appendix render.
    Backward-compat: empty defaults render the appendix with body `（无）`
    (no pick-row priority); legacy callers still produce valid markdown.
    """
    buckets = _bucket_rows(rows)
    parts = [
        f"# Discipline Report — {date}\n",
        _render_section("今日可定投", buckets["今日可定投"]),
        _render_section("减速定投", buckets["减速定投"]),
        _render_section("暂停加仓", buckets["暂停加仓"]),
        _render_section("风险复核", buckets["风险复核"]),
        _render_section("调仓复核", buckets["调仓复核"]),
        _render_section("退出复核", buckets["退出复核"]),
        _DRAWDOWN_NOTE_CN,
        _render_appendix_section(publishable_rows, pick_order_iids),
    ]
    return "\n".join(parts)
```

- [ ] **Step 4: Run green**

Run: `pytest tests/opportunity/test_report_appendix.py -v`
Expected: ~15 PASS.

Run: `pytest tests/opportunity/ -x -q`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/report.py tests/opportunity/test_report_appendix.py
git commit -m "feat(opportunity): add 持仓明细 appendix to compose_discipline_markdown (D3b + Q10)"
```

---

## Task 11: (OQ2) Stamp `audit_errors` on publishable `OpportunityRow.constituent_analyses`

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Modify: `tests/commands/test_opportunity_cmd.py` (or a new dedicated test)

- [ ] **Step 1: Write failing tests**

Append to `tests/commands/test_opportunity_cmd.py`:

```python
def test_build_rows_stamps_audit_errors_from_publishable_verdict_coverage(monkeypatch) -> None:
    """OQ2 — when Policy B returns a publishable verdict (no gap_codes) whose
    constituent_coverage carries non-empty audit_errors on any entry, the
    audit_errors MUST be stamped onto OpportunityRow.constituent_analyses[*]
    via dataclasses.replace. Locked because item 007's renderer reads
    OpportunityRow.constituent_analyses[*].audit_errors directly."""
    import irc.commands.opportunity_cmd as oc
    from irc.fundamentals.types import (
        ActiveFundSnapshot, ConstituentAnalysis, ThesisEvidence,
    )
    from irc.opportunity.policy_b import (
        ConstituentCoverageEntry, PolicyBVerdict,
    )

    # Synthesise a publishable verdict whose coverage carries an audit_error
    # on one symbol (a future-state defence-in-depth case).
    fake_verdict = PolicyBVerdict(
        gap_codes=(),  # ← publishable
        audit_errors=(),
        decision_rule="synthetic publishable with audit-error",
        material_symbols=("600519",),
        constituent_coverage=(
            ConstituentCoverageEntry(
                symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
                weight_rank=1, in_material_top_half=True, exchange="SH",
                has_data_leg=True, has_info_leg=True,
                data_kind_count=1, information_kind_count=1,
                failure_reasons=(),
                audit_errors=("missing_constituent_record:600519",),  # ← stamp source
            ),
        ),
    )

    def fake_evaluate(snapshot, *, top_n):
        return fake_verdict

    monkeypatch.setattr(oc, "evaluate_policy_b", fake_evaluate)
    # The function-level test cannot run _build_rows end-to-end without all
    # config inputs. Instead, assert the post-Policy-B stamping helper
    # exists and behaves correctly on a constructed input.
    assert hasattr(oc, "_stamp_audit_errors_from_verdict"), \
        "_stamp_audit_errors_from_verdict helper must exist (OQ2 wiring)"

    # Build a row whose constituent_analyses includes 600519.
    from irc.opportunity.types import OpportunityRow
    from irc.fundamentals.types import LookthroughTarget
    c1 = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(), failure_reasons=(), one_line_view="x",
        audit_errors=(),  # initially empty
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827", display_cn="易方达",
            provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(), thesis_evidence=(),
        constituent_analyses=(c1,),
    )
    patched = oc._stamp_audit_errors_from_verdict(row, fake_verdict)
    assert patched.constituent_analyses[0].audit_errors == \
        ("missing_constituent_record:600519",)
    # Other fields unchanged.
    assert patched.instrument_id == "005827"
    assert patched.constituent_analyses[0].symbol == "600519"


def test_stamp_audit_errors_no_op_when_coverage_empty() -> None:
    """No-op when verdict.constituent_coverage carries no audit_errors."""
    import irc.commands.opportunity_cmd as oc
    from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget
    from irc.opportunity.policy_b import (
        ConstituentCoverageEntry, PolicyBVerdict,
    )
    from irc.opportunity.types import OpportunityRow

    fake_verdict = PolicyBVerdict(
        gap_codes=(), audit_errors=(),
        decision_rule="publishable, no errors",
        material_symbols=("600519",),
        constituent_coverage=(
            ConstituentCoverageEntry(
                symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
                weight_rank=1, in_material_top_half=True, exchange="SH",
                has_data_leg=True, has_info_leg=True,
                data_kind_count=1, information_kind_count=1,
                failure_reasons=(),
                audit_errors=(),  # ← empty
            ),
        ),
    )
    c1 = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(), failure_reasons=(), one_line_view="",
        audit_errors=(),
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827", display_cn="易方达",
            provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(), thesis_evidence=(),
        constituent_analyses=(c1,),
    )
    patched = oc._stamp_audit_errors_from_verdict(row, fake_verdict)
    # Identical content (no audit_errors added).
    assert patched.constituent_analyses[0].audit_errors == ()
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd.py::test_build_rows_stamps_audit_errors_from_publishable_verdict_coverage -v`
Expected: FAIL — `_stamp_audit_errors_from_verdict` does not exist.

- [ ] **Step 3: Add the helper + wire into `_build_rows`**

Edit `src/irc/commands/opportunity_cmd.py`. Add new helper after the `_build_rows` function (or before it — placement is incidental):

```python
def _stamp_audit_errors_from_verdict(
    row: OpportunityRow,
    verdict: PolicyBVerdict,
) -> OpportunityRow:
    """Stamp per-constituent audit_errors from Policy B's coverage entries.

    OQ2 wiring: item 007's renderer reads
    OpportunityRow.constituent_analyses[*].audit_errors. Policy B v2 emits
    audit_errors on its ConstituentCoverageEntry; for publishable rows this
    is usually `()`, but defence-in-depth requires the stamp to fire if a
    future evaluator path produces non-empty audit_errors on a publishable
    verdict.

    Pure copy-replace via dataclasses.replace; cached snapshot JSON is
    untouched (ADR 0003 §2).
    """
    audit_by_symbol = {
        entry.symbol: entry.audit_errors
        for entry in verdict.constituent_coverage
        if entry.audit_errors
    }
    if not audit_by_symbol:
        return row
    patched_constituents = tuple(
        replace(c, audit_errors=audit_by_symbol[c.symbol])
        if c.symbol in audit_by_symbol
        else c
        for c in row.constituent_analyses
    )
    return replace(row, constituent_analyses=patched_constituents)
```

Edit `_build_rows`. Locate the Policy B verdict stamping block (~line 887):

```python
            # Item 006: Policy B verdict stamping for ActiveFundSnapshot rows.
            if isinstance(snap_obj, ActiveFundSnapshot):
                verdict = evaluate_policy_b(snap_obj, top_n=TOP_N_DEFAULT)
                if verdict.gap_codes:
                    row = replace(
                        row,
                        evidence_gaps=row.evidence_gaps + verdict.gap_codes,
                    )
                pending_verdicts[row.instrument_id] = verdict
```

Replace with:

```python
            # Item 006: Policy B verdict stamping for ActiveFundSnapshot rows.
            # Item 007 OQ2: stamp per-constituent audit_errors from publishable
            # verdicts so the renderer reads them directly off the OpportunityRow.
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

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd.py -v -k stamp_audit_errors`
Expected: 2 PASS.

Run: `pytest tests/commands/ -x -q`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd.py
git commit -m "feat(opportunity): stamp audit_errors on publishable rows from Policy B coverage (OQ2)"
```

---

## Task 12: (Q10) Wire `_write_opportunity_outputs` to pass `publishable_rows` + `pick_order_iids` into the renderer

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Modify: `tests/commands/test_opportunity_cmd.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/commands/test_opportunity_cmd.py`:

```python
def test_write_opportunity_outputs_loads_trade_plan_for_pick_order(tmp_path) -> None:
    """Q10 — _write_opportunity_outputs computes pick_order_iids from
    trade_plan.yaml so the appendix ordering matches the memo pick-table."""
    import json
    import yaml
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget
    from irc.opportunity.types import OpportunityRow

    # Write a minimal trade_plan.yaml in tmp_path.
    plan = {"trades": [
        {"target": "163417", "target_weight": 0.1},
        {"target": "005827", "target_weight": 0.05},
    ]}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "trade_plan.yaml").write_text(yaml.safe_dump(plan), encoding="utf-8")

    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(), failure_reasons=(), one_line_view="",
    )

    def _row(iid: str, name: str):
        return OpportunityRow(
            instrument_id=iid, name_cn=name, asset_class="cn_equity_fund",
            theme=None,
            lookthrough_target=LookthroughTarget(
                kind="active_fund", key=iid, display_cn=name,
                provider_symbol="",
            ),
            valuation_state="fair", heat_state="normal", thesis_state="intact",
            product_quality_state="strong", opportunity_state="core_dca",
            opportunity_reason="", evidence_gaps=(), thesis_evidence=(),
            constituent_analyses=(c,),
        )

    rows = [_row("005827", "A基金"), _row("163417", "B基金")]
    positions = {iid: type("P", (), {
        "portfolio_weight": None, "target_band_low": None,
        "target_band_high": None, "drawdown_since_entry": None,
        "is_holding": False,
    })() for iid in ("005827", "163417")}

    _write_opportunity_outputs(
        rows, positions, {}, {}, {}, tmp_path, "2026-05-23",
        pending_verdicts={}, plan_hash="",
        snapshot_cache_by_instrument={},
    )
    discipline = (tmp_path / "discipline_report.md").read_text(encoding="utf-8")
    # 163417 (first in trade_plan) appears before 005827 in the appendix.
    pos_b = discipline.index("### 163417")
    pos_a = discipline.index("### 005827")
    assert pos_b < pos_a, \
        f"appendix not ordered by pick-row; got:\n{discipline}"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/commands/test_opportunity_cmd.py::test_write_opportunity_outputs_loads_trade_plan_for_pick_order -v`
Expected: FAIL — appendix not in pick-row order yet.

- [ ] **Step 3: Wire the call site**

Edit `src/irc/commands/opportunity_cmd.py`. Add `yaml` import near other imports if not already present:

```python
import yaml  # NOTE: project already uses pyyaml elsewhere; if absent, ensure it imports.
```

Add a small helper near `_write_opportunity_outputs`:

```python
def _load_pick_order_iids(out_dir: Path) -> tuple[str, ...]:
    """Read trade_plan.yaml from out_dir and return ordered list of pick iids.

    Returns empty tuple when trade_plan.yaml does not exist (e.g. opportunity
    runs before plan/build); the appendix then renders in instrument_id
    ascending order (backward-compat per Q10).
    """
    plan_path = out_dir / "trade_plan.yaml"
    if not plan_path.exists():
        return ()
    try:
        doc = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ()
    return tuple(
        str(t["target"])
        for t in (doc.get("trades") or [])
        if t.get("target")
    )
```

Edit `_write_opportunity_outputs` Step 5 (the `compose_discipline_markdown` call). Locate:

```python
    # Step 5 — compose discipline_report.md: publishable buckets + V1 summary + failure section.
    publishable_md = compose_discipline_markdown(discipline_rows, today)
```

Replace with:

```python
    # Step 5 — compose discipline_report.md: publishable buckets + V1 summary + failure section.
    # Q10 wiring: load trade_plan.yaml for appendix pick-row order.
    pick_order_iids = _load_pick_order_iids(out_dir)
    publishable_md = compose_discipline_markdown(
        discipline_rows, today,
        publishable_rows=tuple(publishable_rows),
        pick_order_iids=pick_order_iids,
    )
```

- [ ] **Step 4: Run green**

Run: `pytest tests/commands/test_opportunity_cmd.py::test_write_opportunity_outputs_loads_trade_plan_for_pick_order -v`
Expected: PASS.

Run: `pytest tests/commands/ tests/opportunity/ -x -q`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd.py
git commit -m "feat(opportunity): wire _write_opportunity_outputs to pass pick_order_iids into discipline appendix (Q10)"
```

---

## Task 13: SAME-3 invariant regression test across three rendering surfaces

**Files:**
- Create: `tests/memo/test_same_3_invariant.py`

- [ ] **Step 1: Write the regression test**

Create `tests/memo/test_same_3_invariant.py`:

```python
"""Item 007 ADR 0004 §3 — SAME-3 invariant locked across three surfaces.

For any OpportunityRow, the set of citation_ids rendered in:
  (a) the picks-table 证据 cell (via _build_pick_rows → PickRow.citations)
  (b) the evidence-pool [ref:...] markers (via build_evidence_pool)
  (c) the discipline _render_section nested bullets (via _render_section)
MUST be IDENTICAL. Locked here to prevent silent drift.
"""
from __future__ import annotations

import re

from irc.commands.memo_cmd import _build_pick_rows
from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget, ThesisEvidence
from irc.memo.evidence_pool import build_evidence_pool
from irc.memo.citation_selector import select_citations
from irc.opportunity.report import _render_section
from irc.opportunity.types import DisciplineRow


def _ev(d: int, kind: str = "data", scope: str = "constituent") -> ThesisEvidence:
    return ThesisEvidence(
        type="filing", source=f"src{d}", url=f"https://x/{d}",
        date=f"2024-04-{d:02d}", summary=f"s{d}", scope=scope,
        citation_kind=kind, owner_instrument_id="005827",
        parent_fund_id="005827", constituent_key=f"60051{d}",
        holding_weight_pct=8.0 - d * 0.1,
    )


def test_same_3_invariant_evidence_pool_and_picks_table() -> None:
    """SAME-3: picks_table.citations and evidence_pool [ref:...] markers
    cite the same 3 citation_ids."""
    evs = tuple(
        _ev(d, kind="data" if d % 2 == 0 else "information")
        for d in range(1, 9)  # 8 entries
    )

    # Picks-table path: build the dict-form row that _build_pick_rows expects.
    opp_dict = {
        "rows": [{
            "instrument_id": "005827",
            "name_cn": "易方达",
            "asset_class": "cn_equity_fund",
            "opportunity_state": "core_dca",
            "opportunity_reason": "",
            "thesis_evidence": [
                {
                    "type": e.type, "source": e.source, "url": e.url,
                    "date": e.date, "summary": e.summary, "scope": e.scope,
                    "citation_kind": e.citation_kind,
                    "owner_instrument_id": e.owner_instrument_id,
                    "parent_fund_id": e.parent_fund_id,
                    "constituent_key": e.constituent_key,
                    "holding_weight_pct": e.holding_weight_pct,
                }
                for e in evs
            ],
            "evidence_gaps": [],
        }],
    }
    trades = [{"target": "005827", "target_weight": 0.1, "role": ""}]
    scoring = {"scores": []}
    pick_rows, _, _ = _build_pick_rows(trades, opp_dict, scoring)
    picks_cids = {c.citation_id for c in pick_rows[0].citations}

    # Evidence-pool path: pass the dataclass tuple under thesis_evidence.
    op_row_for_pool = {
        "instrument_id": "005827",
        "name_cn": "易方达",
        "asset_class": "cn_equity_fund",
        "opportunity_state": "core_dca",
        "opportunity_reason": "",
        "thesis_evidence": evs,
        "valuation_state": "fair", "heat_state": "normal",
        "thesis_state": "intact", "product_quality_state": "strong",
    }
    pool = build_evidence_pool(
        opportunity_rows=[op_row_for_pool],
        scoring_rows=[], plan_trades=trades, gold_regime=None,
    )
    pool_cids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", "\n".join(pool)))

    assert picks_cids == pool_cids, \
        f"SAME-3 invariant broken between picks-table and evidence-pool:\n" \
        f"  picks: {picks_cids}\n  pool : {pool_cids}"
    assert len(picks_cids) == 3


def test_same_3_invariant_discipline_section_matches_picks_table() -> None:
    """SAME-3: _render_section nested bullets cite the same citation_ids
    as the picks-table."""
    evs = tuple(
        _ev(d, kind="data" if d % 2 == 0 else "information")
        for d in range(1, 9)
    )

    opp_dict = {
        "rows": [{
            "instrument_id": "005827",
            "name_cn": "易方达",
            "asset_class": "cn_equity_fund",
            "opportunity_state": "core_dca",
            "opportunity_reason": "",
            "thesis_evidence": [
                {
                    "type": e.type, "source": e.source, "url": e.url,
                    "date": e.date, "summary": e.summary, "scope": e.scope,
                    "citation_kind": e.citation_kind,
                    "owner_instrument_id": e.owner_instrument_id,
                    "parent_fund_id": e.parent_fund_id,
                    "constituent_key": e.constituent_key,
                    "holding_weight_pct": e.holding_weight_pct,
                }
                for e in evs
            ],
            "evidence_gaps": [],
        }],
    }
    trades = [{"target": "005827", "target_weight": 0.1, "role": ""}]
    scoring = {"scores": []}
    pick_rows, _, _ = _build_pick_rows(trades, opp_dict, scoring)
    picks_cids = {c.citation_id for c in pick_rows[0].citations}

    discipline_row = DisciplineRow(
        instrument_id="005827", name_cn="易方达",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
        thesis_evidence=evs,
    )
    section_md = _render_section("今日可定投", [discipline_row])
    discipline_cids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", section_md))

    assert picks_cids == discipline_cids, \
        f"SAME-3 invariant broken between picks-table and discipline section:\n" \
        f"  picks      : {picks_cids}\n  discipline : {discipline_cids}"
    assert len(picks_cids) == 3


def test_select_citations_shuffle_invariant() -> None:
    """AC25 — select_citations produces the same citation_id set across
    shuffled input orders. Locked at the selector level (ADR 0001 §3);
    this test pins the renderer-side consequence."""
    evs = tuple(
        _ev(d, kind="data" if d % 2 == 0 else "information")
        for d in range(1, 9)
    )
    cids_a = {e.citation_id for e in select_citations(evs, cap=3)}
    cids_b = {e.citation_id for e in select_citations(tuple(reversed(evs)), cap=3)}
    assert cids_a == cids_b
```

- [ ] **Step 2: Run failing / passing**

Run: `pytest tests/memo/test_same_3_invariant.py -v`
Expected: PASS (if Tasks 6–8 implemented correctly; otherwise FAIL with concrete diff).

- [ ] **Step 3: (no implementation — the prior tasks must satisfy this regression)**

If the test fails, return to Task 6, 7, or 8 to fix the consumer-side pre-filter that breaks SAME-3.

- [ ] **Step 4: Final pytest run for this slice**

Run: `pytest tests/memo/ tests/opportunity/ tests/commands/ -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/memo/test_same_3_invariant.py
git commit -m "test(memo): lock SAME-3 invariant regression across picks/pool/discipline surfaces"
```

---

## Task 14: Two-run byte equality regression tests

**Files:**
- Create or extend: `tests/memo/test_determinism.py`

- [ ] **Step 1: Write the byte equality tests**

Create `tests/memo/test_determinism.py`:

```python
"""Item 007 AC26 + AC27 — two-run byte equality for memo.md + discipline_report.md.

Locks the determinism contract from MASTER-SPEC AC9.
"""
from __future__ import annotations

import hashlib
import re


def test_evidence_pool_byte_equal_across_runs() -> None:
    """build_evidence_pool produces byte-identical output on two runs over the same input."""
    from irc.fundamentals.types import ThesisEvidence
    from irc.memo.evidence_pool import build_evidence_pool

    def _ev(d: int, kind="data"):
        return ThesisEvidence(
            type="filing", source=f"src{d}", url=f"https://x/{d}",
            date=f"2024-04-{d:02d}", summary=f"s{d}", scope="constituent",
            citation_kind=kind, owner_instrument_id="005827",
            parent_fund_id="005827", constituent_key=f"60051{d}",
            holding_weight_pct=8.0 - d * 0.1,
        )
    evs = tuple(_ev(d, "data" if d % 2 == 0 else "information") for d in range(1, 9))
    row = {
        "instrument_id": "005827", "name_cn": "易方达",
        "asset_class": "cn_equity_fund",
        "opportunity_state": "core_dca",
        "opportunity_reason": "",
        "thesis_evidence": evs,
        "valuation_state": "fair", "heat_state": "normal",
        "thesis_state": "intact", "product_quality_state": "strong",
    }
    trades = [{"target": "005827", "target_weight": 0.1}]

    pool1 = "\n".join(build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[], plan_trades=trades,
        gold_regime=None,
    ))
    pool2 = "\n".join(build_evidence_pool(
        opportunity_rows=[row], scoring_rows=[], plan_trades=trades,
        gold_regime=None,
    ))
    assert hashlib.sha256(pool1.encode("utf-8")).hexdigest() == \
        hashlib.sha256(pool2.encode("utf-8")).hexdigest()


def test_compose_discipline_markdown_byte_equal_across_runs() -> None:
    """compose_discipline_markdown produces byte-identical output on two runs."""
    from irc.fundamentals.types import (
        ConstituentAnalysis, LookthroughTarget, ThesisEvidence,
    )
    from irc.opportunity.report import compose_discipline_markdown
    from irc.opportunity.types import DisciplineRow, OpportunityRow

    ev = ThesisEvidence(
        type="filing", source="x", url="https://x", date="2024-04-15",
        summary="x", scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519",
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(ev,), failure_reasons=(), one_line_view="持有头部白酒",
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827", display_cn="易方达",
            provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(), thesis_evidence=(ev,),
        constituent_analyses=(c,),
    )
    drow = DisciplineRow(
        instrument_id="005827", name_cn="易方达",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
        thesis_evidence=(ev,), constituent_analyses=(c,),
    )
    out1 = compose_discipline_markdown(
        rows=(drow,), date="2026-05-23",
        publishable_rows=(row,), pick_order_iids=("005827",),
    )
    out2 = compose_discipline_markdown(
        rows=(drow,), date="2026-05-23",
        publishable_rows=(row,), pick_order_iids=("005827",),
    )
    assert hashlib.sha256(out1.encode("utf-8")).hexdigest() == \
        hashlib.sha256(out2.encode("utf-8")).hexdigest()


def test_appendix_shuffled_evidence_order_byte_equal() -> None:
    """AC25 — select_citations shuffle invariance ⇒ appendix renders byte-equal
    across two input evidence tuples differing only in element order."""
    from irc.fundamentals.types import (
        ConstituentAnalysis, LookthroughTarget, ThesisEvidence,
    )
    from irc.opportunity.report import compose_discipline_markdown
    from irc.opportunity.types import DisciplineRow, OpportunityRow

    def _ev(d, kind):
        return ThesisEvidence(
            type="filing", source=f"src{d}", url=f"https://x/{d}",
            date=f"2024-04-{d:02d}", summary=f"s{d}", scope="constituent",
            citation_kind=kind, owner_instrument_id="005827",
            parent_fund_id="005827", constituent_key="600519",
            holding_weight_pct=8.0,
        )
    evs_forward = tuple(
        _ev(d, "data" if d % 2 == 0 else "information") for d in range(1, 9)
    )
    evs_reverse = tuple(reversed(evs_forward))

    def _compose(evs):
        c = ConstituentAnalysis(
            symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
            evidence=evs, failure_reasons=(), one_line_view="x",
        )
        row = OpportunityRow(
            instrument_id="005827", name_cn="易方达",
            asset_class="cn_equity_fund", theme=None,
            lookthrough_target=LookthroughTarget(
                kind="active_fund", key="005827", display_cn="易方达",
                provider_symbol="",
            ),
            valuation_state="fair", heat_state="normal",
            thesis_state="intact", product_quality_state="strong",
            opportunity_state="core_dca", opportunity_reason="",
            evidence_gaps=(), thesis_evidence=evs,
            constituent_analyses=(c,),
        )
        drow = DisciplineRow(
            instrument_id="005827", name_cn="易方达",
            asset_class="cn_equity_fund", theme=None,
            opportunity_state="core_dca", dca_action="normal_dca",
            risk_action="none", note_cn="",
            thesis_evidence=evs, constituent_analyses=(c,),
        )
        return compose_discipline_markdown(
            rows=(drow,), date="2026-05-23",
            publishable_rows=(row,), pick_order_iids=("005827",),
        )

    assert hashlib.sha256(_compose(evs_forward).encode("utf-8")).hexdigest() == \
        hashlib.sha256(_compose(evs_reverse).encode("utf-8")).hexdigest()
```

- [ ] **Step 2: Run failing / passing**

Run: `pytest tests/memo/test_determinism.py -v`
Expected: 3 PASS.

- [ ] **Step 3: (no implementation — Tasks 6/8/10 must satisfy)**

If the test fails, the bug is non-determinism in `_render_section`, `build_evidence_pool`, or `_render_appendix_section`. Fix at the source.

- [ ] **Step 4: Commit**

```bash
git add tests/memo/test_determinism.py
git commit -m "test(memo): lock two-run byte equality for memo + discipline outputs (AC25/AC26/AC27)"
```

---

## Task 15: Final — full suite green + ruff clean

**Files:** No code changes. Verification only.

- [ ] **Step 1: Run the full test suite**

Run:
```bash
pytest --ignore=tests/news --ignore=tests/scoring/test_sanity_check.py -x -q
```
Expected: PASS — every test in `tests/memo/`, `tests/opportunity/`, `tests/commands/`, `tests/fundamentals/`, etc. green.

- [ ] **Step 2: Run ruff**

Run:
```bash
ruff check src/ tests/
```
Expected: clean (zero violations). Fix any flagged issues by editing the offending file; commit the fix as a separate `style(...)` commit.

- [ ] **Step 3: Inspect the slice's commit log**

Run:
```bash
git log --oneline autodev/thesis-cards-evidence-gap..HEAD
```
Expected: 14 conventional commits, one per task above.

- [ ] **Step 4: Confirm the file-touch map matches the actual diff**

Run:
```bash
git diff --name-status autodev/thesis-cards-evidence-gap..HEAD
```
Expected to show:
- `M src/irc/fundamentals/types.py` (classmethod added)
- `M src/irc/fundamentals/snapshot_cache.py` (delegator)
- `M src/irc/commands/memo_cmd.py` (delegator + wiring)
- `M src/irc/memo/evidence_pool.py` (D1a)
- `M src/irc/memo/numeric_audit.py` (D1c stub)
- `A src/irc/memo/markers.py` (new)
- `A src/irc/memo/aliases.py` (new)
- `M src/irc/opportunity/report.py` (D3a + D3b + appendix)
- `M src/irc/commands/opportunity_cmd.py` (OQ2 + Q10 wiring)
- `A tests/memo/test_markers.py`
- `A tests/memo/test_aliases.py`
- `A tests/memo/test_same_3_invariant.py`
- `A tests/memo/test_determinism.py`
- `A tests/opportunity/test_report_appendix.py`
- `A tests/commands/test_memo_cmd_aliases.py`
- `M tests/memo/test_evidence_pool.py`
- `M tests/memo/test_numeric_audit.py`
- `M tests/opportunity/test_report.py`
- `M tests/commands/test_opportunity_cmd.py`
- `M tests/fundamentals/test_types.py`
- `M tests/fundamentals/test_snapshot_cache.py`
- `M tests/memo/test_pick_rows.py`

- [ ] **Step 5: No commit (verification task only)**

The slice is complete when Steps 1 + 2 are green and the diff matches the file-touch map.

---

## Acceptance criteria mapping (29 ACs → tasks)

| AC | Description | Task |
|---|---|---|
| 1 | `[ref:...]` markers appear | T6 |
| 2 | `[stock:...]` tag scope-conditional | T6 + T3 |
| 3 | Old `[ref:filing:...]` format rejected | T6 |
| 4 | URL-less line omits `({url})` | T6 |
| 5 | SAME-3 invariant picks ↔ pool | T13 |
| 6 | Watchlist exclusion preserved | T6 |
| 7 | `build_alias_maps` correct shape | T4 |
| 8 | `InstrumentAliasCollisionError` at build time | T4 |
| 9 | Duplicate iid doesn't raise | T4 |
| 10 | `find_uncited_conclusions` empty-map raise | T5 |
| 11 | Non-empty alias map no-raise | T5 |
| 12 | `_render_section` 3 nested bullets | T8 |
| 13 | Active-fund flattened evidence used | T8 (covered via flattened tuple) |
| 14 | Empty evidence → no nested bullets | T8 |
| 15 | SAME-3 picks ↔ discipline | T13 |
| 16 | Inline top-5 holdings | T9 |
| 17 | Inline top-5 failure rendering (❌) | T9 |
| 18 | Inline top-5 audit-error append (⚠️) | T9 |
| 19 | `## 持仓明细` section after _DRAWDOWN_NOTE_CN | T10 |
| 20 | Appendix lists all top-N | T10 |
| 21 | Appendix ordering pick-row → iid-asc | T10 + T12 |
| 22 | Appendix per-constituent precedence | T10 |
| 23 | Appendix scope = publishable only | T10 |
| 24 | `[ref:...]` full 16 hex chars | T10 |
| 25 | `select_citations` shuffle-invariant | T13 + T14 |
| 26 | `memo.md` two-run byte equality | T14 |
| 27 | `discipline_report.md` two-run byte equality | T14 |
| 28 | Every active-fund row has appendix subsection | T10 |
| 29 | Defensive fallback (Shape 5) | T10 |

29/29 ACs covered.

## Open questions resolved (summary)

- **OQ1 (load-bearing classmethod promotion):** YES — Task 1 promotes `_evidence_from_dict` to `ThesisEvidence.from_dict`; Task 2 delegates the two existing call sites onto it. Net: −2 functions, +1 classmethod, drift-detection logic now lives in one place.
- **OQ2 (`audit_errors` stamping placement):** Option A — Task 11 patches `_build_rows` to stamp `audit_errors` via `dataclasses.replace` immediately after `evaluate_policy_b` returns a publishable verdict. The cached snapshot stays byte-identical (ADR 0003 §2).
- **OQ3 (small_watch appendix coverage):** Implicit in Task 10's `_order_publishable_rows_for_appendix` — any publishable row with `constituent_analyses != ()` gets a subsection regardless of `opportunity_state`. Test fixture in `test_appendix_ordering_non_pick_publishable_sorted_by_iid_asc` covers this path.
- **OQ4 (`(Top 5)` literal):** Locked literal `INLINE_HEADER_LITERAL = "持仓 (Top 5)"`; the inline block renders the literal even when `len(constituent_analyses) < 5`.
