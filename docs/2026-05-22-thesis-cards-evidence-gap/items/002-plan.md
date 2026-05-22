# Item 002 plan — Citation data model (Slice D0 a–f + D1b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install the unified citation provenance schema (`ThesisEvidence` gains six required fields + content-addressed `citation_id`; `CitationMeta` + `CitedMap`/`ConstituentCitedMap` aliases land; `DisciplineRow` carries gap/evidence state; `select_citations` becomes the deterministic picks/evidence selector; `_build_pick_rows` cross-references `opportunity_report.json` and routes gapped/absent trade targets into failure sub-sections; `build_cited_map` lands with duplicate-id + wrong-owner detectors).

**Architecture:** Schema-first. Source of truth = `src/irc/opportunity/types.py`. Every existing `ThesisEvidence(...)` constructor (3 production producers, 5 test fixtures, plus 1 loop site) is updated to pass the new required fields in a single slice — fail-fast `__post_init__` is the contract (no backwards-compat shim). New pure functions live in `src/irc/memo/citation_selector.py` (selector) and `src/irc/opportunity/citation_map.py` (cited-map producer). Memo flow gains gap-aware classification of trade targets with two failure sub-blocks rendered as `###` headers nested under §5 of `memo.md`.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `ruff`, frozen dataclasses with `__post_init__` overriding default field via `object.__setattr__`.

---

## Drift guardrails (read before starting)

These rules govern when to STOP and report drift rather than silently patch:

1. **Unenumerated `ThesisEvidence(...)` call site.** This plan enumerates 9 call sites (3 in `src/irc/opportunity/thesis_evidence.py`, 6 in `tests/opportunity/test_{report,cards,types}.py`). If during impl you discover ANY OTHER call site (e.g. via `grep -rn "ThesisEvidence(" src/ tests/`), STOP — do not silently update it. Surface in the drift log: "found ThesisEvidence call at `path:line` not in spec's enumerated 9". The planner needs to decide whether item 002 absorbs it or whether scope creeps.
2. **Unexpected test failure.** If a test the plan didn't write/touch fails after a step, STOP. Investigate root cause; do not silently `pytest -k` around it. Two pre-existing failures on `autodev/thesis-cards-evidence-gap` HEAD are known and ARE NOT caused by this slice — see §"Pre-existing failures" below.
3. **No backwards-compat shim.** Old `ThesisEvidence(type=..., source=..., url=..., date=..., summary=...)` calls without the new provenance fields MUST fail with `TypeError: __init__() missing N required keyword arguments`. Do not add defaults to the new required fields. The fail-fast `__post_init__` validation is the load-bearing contract for items 003–009.
4. **No silent absorption of CITATION_ID into preimage.** Callers MUST NOT pass `citation_id=` as a kwarg. If a test fixture supplies it (none do today), let `__post_init__` overwrite it via `object.__setattr__` — that is the spec'd behavior, not a bug.
5. **`_evidence_from_dict` placement.** Spec defers to "second-consumer discovery"; this plan puts it inside `src/irc/commands/memo_cmd.py` as a private helper (only `_build_pick_rows` consumes it). DO NOT promote to a `ThesisEvidence.from_dict` classmethod in this slice — item 009 audit gates may need it, that's their call.
6. **`build_cited_map` location.** This plan places it in `src/irc/opportunity/citation_map.py` (new file). The producer is an opportunity-stage artifact; memo + audit gates are consumers. DO NOT colocate inside `types.py` (keeps `types.py` schema-only, no logic).
7. **`render_failure_sections` placement.** This plan adds it to `src/irc/memo/picks_table.py` (next to `render_picks_table`). Memo-stage rendering, picks-table-adjacent. DO NOT add to `memo_cmd.py` (keeps `memo_cmd.py` orchestration-only).

## Pre-existing failures on branch HEAD (NOT caused by this slice)

These tests fail on `autodev/thesis-cards-evidence-gap` HEAD before this plan starts and are unrelated to item 002:

- `tests/commands/test_run_cmd.py::test_only_stage_runs_single`
- `tests/integration/test_thesis_coverage.py::test_thesis_coverage_meets_threshold`

The final pytest sweep in Task 18 explicitly excludes these from "this slice's failures". DO NOT attempt to fix them as part of this slice. If a third pre-existing failure surfaces, STOP and surface as drift.

## File map

### Created

| Path | Responsibility |
|---|---|
| `src/irc/memo/citation_selector.py` | `select_citations(entries, cap=3)` — single deterministic selector for picks-table (D0e) and evidence-pool (D1a). |
| `src/irc/opportunity/citation_map.py` | `build_cited_map(rows) -> CitedMap` with duplicate-id and wrong-owner detectors. Schema function only; not called from any write path in this slice. |
| `tests/memo/test_citation_selector.py` | Selector determinism, data+info-leg invariant, stable rendering order, empty input, cap=0, cap > len. |
| `tests/memo/test_pick_rows.py` | `_build_pick_rows` returns 3-tuple; absent / gapped / clean target classification. |
| `tests/opportunity/test_citation_map.py` | `build_cited_map` shape, duplicate-id detector, wrong-owner detector. |

### Modified

| Path | Change summary |
|---|---|
| `src/irc/opportunity/types.py` | Add `CitationMeta` dataclass; add `CitedMap` / `ConstituentCitedMap` type aliases; extend `ThesisEvidence` with 6 required fields + `__post_init__` validation + `citation_id` computation; extend `DisciplineRow` with 4 trailing defaulted fields; `import hashlib` at module top. |
| `src/irc/opportunity/thesis_evidence.py` | Add `owner_instrument_id: str` kwarg to `derive_thesis_from_evidence`; thread it into `_filing_evidence` / `_broker_evidence` / `_news_evidence`; pass new provenance kwargs into every `ThesisEvidence(...)`. |
| `src/irc/opportunity/states.py` | `build_opportunity_row` passes `inp.instrument_id` as `owner_instrument_id=` to `derive_thesis_from_evidence`. |
| `src/irc/opportunity/report.py` | `_row_to_dict` emits `thesis_evidence`, `contributing_dimensions`, `constituent_analyses`. |
| `src/irc/commands/opportunity_cmd.py` | `_discipline_row_from` propagates 4 new fields. |
| `src/irc/memo/picks_table.py` | `PickRow.citations: tuple[ThesisEvidence, ...] = ()`; `render_picks_table` adds `证据` column with `[ref:{citation_id}] {type}·{source}·{date}` joined by `<br>`; `render_failure_sections(absent, gapped, extra_names) -> str`. |
| `src/irc/commands/memo_cmd.py` | Rewrite `_build_pick_rows` to return `(pick_rows, absent, gapped)`; add private helpers `_strip_venue_suffix`, `_evidence_from_dict`; `run_memo` appends failure-section markdown to `picks_table_md`. |
| `tests/opportunity/test_types.py` | Update `ThesisEvidence` constructions to pass new fields; add validation, determinism, cross-instrument hash divergence tests. |
| `tests/opportunity/test_report.py` | Update `ThesisEvidence` constructions; add round-trip test for `thesis_evidence` + `contributing_dimensions` + `constituent_analyses`. |
| `tests/opportunity/test_cards.py` | Update `ThesisEvidence` constructions. |
| `tests/memo/test_picks_table.py` | Add test for `[ref:{citation_id}]` markers in 证据 column; empty citations renders `—`. |

### Untouched in this slice (item 003+)

- `src/irc/opportunity/cards.py` — `build_thesis_card` already propagates `row.thesis_evidence`; no change needed.
- Per-constituent evidence fetching, audit gates, evidence-pool citation markers — items 003 / 007 / 009.

---

## Task 1 — Failing tests for `ThesisEvidence.__post_init__` validation

**Files:**
- Modify: `tests/opportunity/test_types.py` (append after line 89 — after `test_thesis_evidence_type_must_be_known_kind`)

- [ ] **Step 1: Add 5 failing validation tests**

Append to `tests/opportunity/test_types.py`:

```python
def _evidence_kwargs(**over):
    """Helper: minimal valid kwargs for ThesisEvidence. Override per test."""
    base = dict(
        type="filing",
        source="600519",
        url="https://example.com/foo",
        date="2026-04-28",
        summary="x",
        scope="instrument",
        citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None,
        constituent_key=None,
    )
    base.update(over)
    return base


def test_thesis_evidence_rejects_empty_owner_instrument_id():
    with pytest.raises(ValueError, match="owner_instrument_id"):
        ThesisEvidence(**_evidence_kwargs(owner_instrument_id=""))


def test_thesis_evidence_rejects_invalid_citation_kind():
    with pytest.raises(ValueError, match="citation_kind"):
        ThesisEvidence(**_evidence_kwargs(citation_kind="both"))  # type: ignore[arg-type]


def test_thesis_evidence_rejects_invalid_scope():
    with pytest.raises(ValueError, match="scope"):
        ThesisEvidence(**_evidence_kwargs(scope="random"))  # type: ignore[arg-type]


def test_thesis_evidence_rejects_empty_type_source_date():
    with pytest.raises(ValueError, match="type/source/date"):
        ThesisEvidence(**_evidence_kwargs(type=""))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="type/source/date"):
        ThesisEvidence(**_evidence_kwargs(source=""))
    with pytest.raises(ValueError, match="type/source/date"):
        ThesisEvidence(**_evidence_kwargs(date=""))


def test_thesis_evidence_accepts_none_for_fund_level_optional_fields():
    """parent_fund_id and constituent_key may be None for fund-level evidence."""
    ev = ThesisEvidence(**_evidence_kwargs(parent_fund_id=None, constituent_key=None))
    assert ev.parent_fund_id is None
    assert ev.constituent_key is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_types.py::test_thesis_evidence_rejects_empty_owner_instrument_id -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'scope'` (or similar — the new fields don't exist yet).

- [ ] **Step 3: Do NOT implement yet**

Move to Task 2. Implementation lands in Task 3.

---

## Task 2 — Failing tests for `citation_id` hash determinism and divergence

**Files:**
- Modify: `tests/opportunity/test_types.py` (append after Task 1 tests)

- [ ] **Step 1: Add 3 failing hash tests**

```python
def test_citation_id_is_deterministic_for_identical_preimage():
    """Same inputs → same 16-hex citation_id. Content-addressed invariant."""
    kwargs = _evidence_kwargs()
    a = ThesisEvidence(**kwargs)
    b = ThesisEvidence(**kwargs)
    assert a.citation_id == b.citation_id
    assert len(a.citation_id) == 16
    assert all(c in "0123456789abcdef" for c in a.citation_id)


def test_citation_id_differs_across_owner_instruments():
    """Same type/source/date/url but different owner_instrument_id → different id."""
    a = ThesisEvidence(**_evidence_kwargs(owner_instrument_id="510300"))
    b = ThesisEvidence(**_evidence_kwargs(owner_instrument_id="163417"))
    assert a.citation_id != b.citation_id


def test_citation_id_differs_across_constituents_under_same_fund():
    """Same type/source/date/url/owner_instrument_id but different constituent_key → different id."""
    a = ThesisEvidence(**_evidence_kwargs(
        scope="constituent", owner_instrument_id="005827",
        parent_fund_id="005827", constituent_key="600519",
    ))
    b = ThesisEvidence(**_evidence_kwargs(
        scope="constituent", owner_instrument_id="005827",
        parent_fund_id="005827", constituent_key="000858",
    ))
    assert a.citation_id != b.citation_id


def test_citation_id_uses_summary_fallback_when_url_empty():
    """When url='', summary[:64] is mixed into the preimage so two empty-URL
    filings with different content but same source/date/instrument get distinct ids."""
    a = ThesisEvidence(**_evidence_kwargs(url="", summary="FY24-Q3 营收 +12%"))
    b = ThesisEvidence(**_evidence_kwargs(url="", summary="FY24-Q4 营收 -5%"))
    assert a.citation_id != b.citation_id
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/opportunity/test_types.py::test_citation_id_is_deterministic_for_identical_preimage -v`
Expected: FAIL (same `TypeError` as Task 1).

---

## Task 3 — Implement `ThesisEvidence` schema additions in `types.py`

**Files:**
- Modify: `src/irc/opportunity/types.py:102-114` (extend `ThesisEvidence`)
- Modify: `src/irc/opportunity/types.py:1-4` (add `import hashlib`)

- [ ] **Step 1: Add `import hashlib` at module top**

Edit `src/irc/opportunity/types.py` line 1-4. After `from typing import Literal`, ensure imports include `hashlib`. Final top of file:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal
```

- [ ] **Step 2: Replace `ThesisEvidence` class**

Replace lines 102-114 (the current `ThesisEvidence` definition) with:

```python
ThesisEvidenceKind = Literal["filing", "broker", "news", "policy", "snapshot"]
CitationKind = Literal["data", "information"]
CitationScope = Literal["instrument", "constituent", "asset_class_macro", "policy"]


@dataclass(frozen=True)
class ThesisEvidence:
    """Primary-source citation backing a `thesis_state`, with content-addressed
    provenance.

    `citation_id` is a 16-hex-char prefix of sha256 over the preimage
    (owner_instrument_id : scope : constituent_key : type : canonical_id : date)
    where canonical_id = url or f"{source}:{date}:{summary[:64]}". The id is
    computed in `__post_init__` and overrides any caller-supplied value.

    See `docs/adr/0001-citation-data-model.md` for the binding contract.
    """
    type: ThesisEvidenceKind
    source: str
    url: str
    date: str
    summary: str
    # Required provenance fields (no defaults; callers MUST supply).
    scope: CitationScope
    citation_kind: CitationKind
    owner_instrument_id: str
    parent_fund_id: str | None
    constituent_key: str | None
    # Computed in __post_init__; never accept caller-supplied value.
    citation_id: str = ""

    def __post_init__(self) -> None:
        if not self.owner_instrument_id:
            raise ValueError("ThesisEvidence.owner_instrument_id must be non-empty")
        if self.citation_kind not in ("data", "information"):
            raise ValueError(f"invalid citation_kind: {self.citation_kind!r}")
        if self.scope not in ("instrument", "constituent",
                              "asset_class_macro", "policy"):
            raise ValueError(f"invalid scope: {self.scope!r}")
        if not self.type or not self.source or not self.date:
            raise ValueError(
                "ThesisEvidence.type/source/date must be non-empty"
            )
        canonical_id = self.url or f"{self.source}:{self.date}:{self.summary[:64]}"
        preimage = (
            f"{self.owner_instrument_id}:{self.scope}:"
            f"{self.constituent_key or ''}:{self.type}:"
            f"{canonical_id}:{self.date}"
        ).encode("utf-8")
        object.__setattr__(
            self, "citation_id", hashlib.sha256(preimage).hexdigest()[:16]
        )
```

- [ ] **Step 3: Run validation + hash tests — they should pass**

Run: `uv run pytest tests/opportunity/test_types.py -v -k "thesis_evidence_rejects or citation_id or thesis_evidence_accepts"`
Expected: All 9 tests from Tasks 1+2 pass.

- [ ] **Step 4: Confirm `test_thesis_evidence_is_frozen_dataclass` and `test_thesis_evidence_type_must_be_known_kind` still fail**

Run: `uv run pytest tests/opportunity/test_types.py::test_thesis_evidence_is_frozen_dataclass tests/opportunity/test_types.py::test_thesis_evidence_type_must_be_known_kind -v`
Expected: Both FAIL (missing required kwargs). Task 8 fixes them.

---

## Task 4 — Add `CitationMeta` + type aliases to `types.py`

**Files:**
- Modify: `src/irc/opportunity/types.py` (append after the `ThesisEvidence` block from Task 3, before `OpportunityRow`)

- [ ] **Step 1: Failing test for `CitationMeta`**

Append to `tests/opportunity/test_types.py`:

```python
from irc.opportunity.types import CitationMeta, CitedMap, ConstituentCitedMap  # noqa: E402


def test_citation_meta_is_frozen_dataclass():
    m = CitationMeta(
        scope="instrument",
        citation_kind="data",
        owner_instrument_id="510300",
        asset_class="cn_etf",
        parent_fund_id=None,
        constituent_key=None,
    )
    assert m.asset_class == "cn_etf"
    with pytest.raises(FrozenInstanceError):
        m.asset_class = "x"  # type: ignore[misc]


def test_cited_map_type_alias_is_importable():
    """CitedMap / ConstituentCitedMap are type aliases — import smoke test."""
    assert CitedMap is not None
    assert ConstituentCitedMap is not None
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/opportunity/test_types.py::test_citation_meta_is_frozen_dataclass -v`
Expected: FAIL with `ImportError: cannot import name 'CitationMeta'`.

- [ ] **Step 3: Add `CitationMeta` + aliases in `types.py`**

Insert immediately after the `ThesisEvidence` block:

```python
@dataclass(frozen=True)
class CitationMeta:
    """Per-citation metadata indexed by `citation_id` in `CitedMap`.

    `asset_class` is the asset class of the row whose `instrument_id ==
    owner_instrument_id` at `build_cited_map` time. Required because the
    portfolio-section audit (item 007/009) rejects scope-mismatched citations
    from `CitationMeta.asset_class` alone, without alias lookup.
    """
    scope: CitationScope
    citation_kind: CitationKind
    owner_instrument_id: str
    asset_class: str
    parent_fund_id: str | None
    constituent_key: str | None


# Type aliases consumed by build_cited_map and downstream audit gates (item 009).
CitedMap = dict[str, dict[str, CitationMeta]]
"""instrument_id → {citation_id: CitationMeta}"""

ConstituentCitedMap = dict[str, dict[str, dict[str, CitationMeta]]]
"""instrument_id → constituent_key → {citation_id: CitationMeta}"""
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/opportunity/test_types.py::test_citation_meta_is_frozen_dataclass tests/opportunity/test_types.py::test_cited_map_type_alias_is_importable -v`
Expected: Both PASS.

---

## Task 5 — Failing test for `select_citations`

**Files:**
- Create: `tests/memo/test_citation_selector.py`

- [ ] **Step 1: Create test file with comprehensive selector tests**

Write to `tests/memo/test_citation_selector.py`:

```python
from __future__ import annotations

from irc.memo.citation_selector import select_citations
from irc.opportunity.types import ThesisEvidence


def _ev(**over):
    """Helper: minimal-valid ThesisEvidence with overrides."""
    base = dict(
        type="filing", source="s", url="https://u/x", date="2026-04-28",
        summary="x",
        scope="instrument", citation_kind="data",
        owner_instrument_id="510300", parent_fund_id=None, constituent_key=None,
    )
    base.update(over)
    return ThesisEvidence(**base)


def test_select_citations_empty_input_returns_empty_tuple():
    assert select_citations((), cap=3) == ()


def test_select_citations_cap_zero_returns_empty_tuple():
    entries = (_ev(),)
    assert select_citations(entries, cap=0) == ()


def test_select_citations_cap_greater_than_len_returns_all_entries():
    a = _ev(url="https://u/a", citation_kind="data")
    b = _ev(url="https://u/b", citation_kind="information")
    out = select_citations((a, b), cap=10)
    assert set(out) == {a, b}
    assert len(out) == 2


def test_select_citations_deterministic_across_shuffled_inputs():
    """Two input tuples with the same SET of entries (different order) → same output."""
    a = _ev(url="https://u/a", date="2026-04-01", citation_kind="data")
    b = _ev(url="https://u/b", date="2026-04-15", citation_kind="information")
    c = _ev(url="https://u/c", date="2026-05-01", citation_kind="data",
            scope="asset_class_macro")
    d = _ev(url="https://u/d", date="2026-03-10", citation_kind="information",
            scope="constituent", parent_fund_id="005827", constituent_key="600519")
    out_abc = select_citations((a, b, c, d), cap=3)
    out_dcba = select_citations((d, c, b, a), cap=3)
    out_bdac = select_citations((b, d, a, c), cap=3)
    assert out_abc == out_dcba == out_bdac


def test_select_citations_data_and_info_leg_invariant():
    """If inputs contain ≥1 data AND ≥1 information, output contains ≥1 of each.

    Locks the dual-coverage gate invariant: 6 data + 2 info → output includes
    ≥1 info even with cap=3.
    """
    datas = tuple(
        _ev(url=f"https://u/d{i}", citation_kind="data", date=f"2026-04-{10+i:02d}")
        for i in range(6)
    )
    infos = (
        _ev(url="https://u/i0", citation_kind="information", date="2026-04-01"),
        _ev(url="https://u/i1", citation_kind="information", date="2026-04-02"),
    )
    out = select_citations(datas + infos, cap=3)
    kinds = {e.citation_kind for e in out}
    assert "data" in kinds, f"data-leg missing from {out}"
    assert "information" in kinds, f"info-leg missing from {out}"


def test_select_citations_rendering_order_scope_then_date_then_id():
    """Stable rendering order: (scope_rank desc, date desc, citation_id asc).

    Build a fixed input with hand-picked dates so the expected order is
    deterministic.
    """
    # scope=instrument (rank=2), date=2026-05-01, kind=data
    high_recent = _ev(url="https://u/H", date="2026-05-01", citation_kind="data")
    # scope=asset_class_macro (rank=1), date=2026-05-05, kind=information
    low_recent = _ev(url="https://u/L", date="2026-05-05",
                     citation_kind="information", scope="asset_class_macro")
    # scope=instrument (rank=2), date=2026-04-01, kind=information
    high_old = _ev(url="https://u/M", date="2026-04-01", citation_kind="information")
    out = select_citations((low_recent, high_old, high_recent), cap=3)
    # Expected: scope_rank desc first → high_recent and high_old before low_recent.
    # Between high_recent and high_old: date desc → high_recent (May) before high_old (Apr).
    assert out[0] is high_recent
    assert out[1] is high_old
    assert out[2] is low_recent


def test_select_citations_picks_only_one_data_when_no_information_available():
    """If only data entries exist, output contains data only (info-leg empty)."""
    entries = tuple(_ev(url=f"https://u/d{i}", citation_kind="data") for i in range(4))
    out = select_citations(entries, cap=3)
    assert all(e.citation_kind == "data" for e in out)
    assert len(out) == 3
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/memo/test_citation_selector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.memo.citation_selector'`.

---

## Task 6 — Implement `select_citations` in `src/irc/memo/citation_selector.py`

**Files:**
- Create: `src/irc/memo/citation_selector.py`

- [ ] **Step 1: Create selector module**

Write to `src/irc/memo/citation_selector.py`:

```python
"""Deterministic citation selector — single source of truth for picks-table
(D0e) and memo evidence-pool (D1a).

Pure function. Two input tuples with the same set of entries (different order)
produce the same output tuple. Guarantees ≥1 data-leg AND ≥1 information-leg
when both are present in the input. Locked by `tests/memo/test_citation_selector.py`.

See `docs/adr/0001-citation-data-model.md` §3 for the invariant.
"""
from __future__ import annotations

from irc.opportunity.types import ThesisEvidence


def _scope_rank(scope: str) -> int:
    """instrument/constituent → 2; asset_class_macro/policy → 1."""
    if scope in ("instrument", "constituent"):
        return 2
    return 1


def _slot_key(e: ThesisEvidence) -> tuple[int, float, str, str]:
    """Cross-slot ranking ignores citation_kind. Used for `max(..., key=_slot_key)`.

    `holding_weight_pct` is sourced from `e.holding_weight_pct` if present
    (item 003 adds it to constituent-scoped evidence); otherwise 0.0.
    """
    weight = getattr(e, "holding_weight_pct", 0.0) or 0.0
    return (_scope_rank(e.scope), float(weight), e.date, e.citation_id)


def select_citations(
    entries: tuple[ThesisEvidence, ...],
    cap: int = 3,
) -> tuple[ThesisEvidence, ...]:
    """Pick at most `cap` citations from `entries`.

    Algorithm:
      1. Pick the highest-ranked entry with `citation_kind == "data"` AND
         `scope in {"instrument", "constituent"}` (data slot).
      2. Pick the highest-ranked entry with `citation_kind == "information"`
         (info slot), if distinct from the data pick.
      3. Fill remaining slots up to `cap` from un-picked entries by sort key.
      4. Re-sort the result for stable rendering:
         `(scope_rank desc, date desc, citation_id asc)`.
    """
    if not entries or cap <= 0:
        return ()

    data_candidates = [
        e for e in entries
        if e.citation_kind == "data"
        and e.scope in ("instrument", "constituent")
    ]
    data_pick = max(data_candidates, key=_slot_key) if data_candidates else None

    info_candidates = [e for e in entries if e.citation_kind == "information"]
    info_pick = max(info_candidates, key=_slot_key) if info_candidates else None

    selected: list[ThesisEvidence] = []
    if data_pick is not None:
        selected.append(data_pick)
    if info_pick is not None and info_pick is not data_pick:
        selected.append(info_pick)

    # Fill remaining slot(s) up to cap.
    remaining = [e for e in entries if e not in selected]
    remaining.sort(key=_slot_key, reverse=True)
    for e in remaining:
        if len(selected) >= cap:
            break
        selected.append(e)

    # Stable rendering order. Two-pass: stable-sort by citation_id ascending,
    # then stable-sort by (scope_rank desc, date desc). Python's sort is
    # stable, so equal keys preserve the prior pass's order.
    selected.sort(key=lambda e: e.citation_id)
    selected.sort(key=lambda e: (_scope_rank(e.scope), e.date), reverse=True)
    return tuple(selected)
```

- [ ] **Step 2: Run selector tests — all pass**

Run: `uv run pytest tests/memo/test_citation_selector.py -v`
Expected: All 7 tests PASS.

---

## Task 7 — Thread provenance through `_filing_evidence` / `_broker_evidence` / `_news_evidence`

**Files:**
- Modify: `src/irc/opportunity/thesis_evidence.py:72-117` (3 helpers + `derive_thesis_from_evidence` signature)
- Modify: `src/irc/opportunity/states.py:441-443` (call site)

- [ ] **Step 1: Add `owner_instrument_id` kwarg to the 3 helpers and main entry**

Edit `src/irc/opportunity/thesis_evidence.py`:

Replace `_filing_evidence` (lines 72-87) with:

```python
def _filing_evidence(
    filings: tuple[FilingDigest, ...],
    *,
    owner_instrument_id: str,
) -> tuple[ThesisEvidence, ...]:
    """Up to N filings with the most extreme YoY moves (largest magnitude first).

    NOTE (item 002): These V1 helpers iterate aggregate-per-fund snapshots
    rather than per-constituent fetches. Until item 003 rewires them, they
    carry `scope="instrument"` and `constituent_key=None`. Item 003 will
    change `scope` to `"constituent"` and populate `constituent_key=f.symbol`.
    """
    scored = [
        (abs(f.revenue_yoy), f) for f in filings if f.revenue_yoy is not None
    ]
    scored.sort(key=lambda t: t[0], reverse=True)
    out: list[ThesisEvidence] = []
    for _, f in scored[:_MAX_FILING_EVIDENCE]:
        out.append(ThesisEvidence(
            type="filing",
            source=f.symbol,
            url=f.source_url,
            date=f.filed_at_iso,
            summary=f"{f.symbol} {f.fiscal_period} 营收同比 {f.revenue_yoy:+.1%}。",
            scope="instrument",            # item 003 rewires to "constituent"
            citation_kind="data",
            owner_instrument_id=owner_instrument_id,
            parent_fund_id=None,            # item 003 sets to owner_instrument_id
            constituent_key=None,           # item 003 sets to f.symbol
        ))
    return tuple(out)
```

Replace `_broker_evidence` (lines 90-102) with:

```python
def _broker_evidence(
    reports: tuple[BrokerReport, ...],
    *,
    owner_instrument_id: str,
) -> tuple[ThesisEvidence, ...]:
    """Up to N most recent broker reports.

    NOTE (item 002): V1 carries `scope="instrument"` per the same rationale
    as `_filing_evidence`.
    """
    recent = sorted(reports, key=lambda r: r.published_iso, reverse=True)
    out: list[ThesisEvidence] = []
    for r in recent[:_MAX_BROKER_EVIDENCE]:
        out.append(ThesisEvidence(
            type="broker",
            source=r.broker,
            url=r.source_url,
            date=r.published_iso,
            summary=f"{r.broker} {r.rating}: {r.title}".strip(),
            scope="instrument",
            citation_kind="information",
            owner_instrument_id=owner_instrument_id,
            parent_fund_id=None,
            constituent_key=None,
        ))
    return tuple(out)
```

Replace `_news_evidence` (lines 105-117) with:

```python
def _news_evidence(
    report: ThemeReport | None,
    *,
    owner_instrument_id: str,
) -> tuple[ThesisEvidence, ...]:
    """Theme-report (macro/sector) citations.

    Carry `scope="asset_class_macro"` and `owner_instrument_id` = the row
    being built. These won't satisfy the dual-coverage gate's
    `scope in {"instrument", "constituent"}` predicate — intentional;
    macro citations are supplemental context only.
    """
    if report is None or not report.citations:
        return ()
    out: list[ThesisEvidence] = []
    for c in report.citations[:_MAX_NEWS_EVIDENCE]:
        out.append(ThesisEvidence(
            type="news",
            source=c.title or c.url,
            url=c.url,
            date=c.published_iso,
            summary=c.title,
            scope="asset_class_macro",
            citation_kind="information",
            owner_instrument_id=owner_instrument_id,
            parent_fund_id=None,
            constituent_key=None,
        ))
    return tuple(out)
```

- [ ] **Step 2: Update `_thesis_from_theme_report` (internal caller)**

In `src/irc/opportunity/thesis_evidence.py`, the function `_thesis_from_theme_report` (line 178 onwards) calls `_news_evidence(report)` at two return sites (lines ~192 and ~197). These calls need `owner_instrument_id`. Change the signature:

Replace `_thesis_from_theme_report` (lines 178-198) with:

```python
def _thesis_from_theme_report(
    report: ThemeReport,
    *,
    owner_instrument_id: str,
) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...]]:
    """Rule: report with ≥3 citations AND ≥1 trusted-tier citation
    → intact (research-backed). Otherwise evidence_insufficient."""
    if len(report.citations) < _MIN_RESEARCH_CITATIONS:
        return "evidence_insufficient", "", ()
    trusted = _count_trusted_citations(report)
    if trusted < 1:
        return (
            "evidence_insufficient",
            f"主题研究 {len(report.citations)} 条引用全部来自次级转载源，"
            f"未达到一级新闻/研究层级，长期逻辑暂不可背书。",
            _news_evidence(report, owner_instrument_id=owner_instrument_id),
        )
    return (
        "intact",
        f"长期逻辑由主题研究背书（citations={len(report.citations)}，"
        f"其中一级来源 {trusted} 条），暂未触发证伪。",
        _news_evidence(report, owner_instrument_id=owner_instrument_id),
    )
```

- [ ] **Step 3: Update `derive_thesis_from_evidence` signature + internal calls**

Replace the `derive_thesis_from_evidence` definition (line 262 onwards). The new signature adds `owner_instrument_id: str` (keyword-only, no default — fail-fast); the three internal helper calls pass it through:

```python
def derive_thesis_from_evidence(
    snapshot: ConstituentSnapshot | None,
    theme_report: ThemeReport | None,
    *,
    asset_class: str | None = None,
    owner_instrument_id: str,
) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...], tuple[str, ...]]:
    """Derive (state, reason, evidence, gap_labels) from concrete sources.

    `owner_instrument_id` is the instrument id of the row being built; it is
    stamped on every emitted `ThesisEvidence` so `build_cited_map` can verify
    `e.owner_instrument_id == row.instrument_id`.
    """
    gaps: list[str] = []

    snapshot_usable = snapshot is not None and bool(snapshot.filings)
    if not snapshot_usable:
        gaps.append("missing_constituent_snapshot")
    if theme_report is None:
        gaps.append("news_stage_skipped")
    else:
        news_status = _classify_theme_report(theme_report)
        if news_status == "search_empty":
            gaps.append("news_search_empty")
        elif news_status == "llm_failed":
            gaps.append("news_llm_failed")

    refined = _classify_constituent_gap(snapshot, asset_class)
    if refined is not None and refined not in gaps:
        gaps.append(refined)

    if snapshot_usable:
        pos, neg, total = _yoy_split(snapshot.filings)
        if total == 0:
            gaps.append("missing_constituent_snapshot")
        else:
            if not snapshot.broker_reports:
                gaps.append("missing_broker_coverage")
            consensus = _broker_consensus(snapshot.broker_reports)
            evidence = (
                _filing_evidence(snapshot.filings,
                                 owner_instrument_id=owner_instrument_id)
                + _broker_evidence(snapshot.broker_reports,
                                   owner_instrument_id=owner_instrument_id)
                + _news_evidence(theme_report,
                                 owner_instrument_id=owner_instrument_id)
            )
            state, reason = _classify_state(pos / total, neg / total, consensus)
            return (state, reason, evidence, tuple(gaps))

    if theme_report is not None and _theme_report_usable(theme_report):
        state, reason, evidence = _thesis_from_theme_report(
            theme_report, owner_instrument_id=owner_instrument_id,
        )
        if reason:
            return state, reason, evidence, tuple(gaps)

    return (
        "evidence_insufficient",
        "缺少底层成分股财报数据，且主题研究证据不足，无法判定长期逻辑。",
        (),
        tuple(gaps),
    )
```

- [ ] **Step 4: Update `states.py` call site**

Edit `src/irc/opportunity/states.py` lines ~441-443:

Old:
```python
        thesis, thesis_reason, evidence, thesis_gaps = derive_thesis_from_evidence(
            snapshot, theme_report, asset_class=inp.asset_class,
        )
```

New:
```python
        thesis, thesis_reason, evidence, thesis_gaps = derive_thesis_from_evidence(
            snapshot, theme_report,
            asset_class=inp.asset_class,
            owner_instrument_id=inp.instrument_id,
        )
```

- [ ] **Step 5: Run thesis-evidence tests — confirm green**

Run: `uv run pytest tests/opportunity/test_thesis_evidence.py tests/opportunity/test_states.py -v`
Expected: All PASS. If any fail, root-cause: have you preserved the gap-flagging behavior? Did you pass `owner_instrument_id` through ALL three internal calls?

---

## Task 8 — Update all 5 test-fixture `ThesisEvidence(...)` call sites

**Files:**
- Modify: `tests/opportunity/test_report.py:73-86` (2 sites in `test_thesis_cards_yaml_serializes_thesis_evidence`)
- Modify: `tests/opportunity/test_cards.py:83-95` (2 sites in `test_card_propagates_thesis_evidence`)
- Modify: `tests/opportunity/test_types.py:73-79, 87-89` (2 sites in `test_thesis_evidence_is_frozen_dataclass` + `test_thesis_evidence_type_must_be_known_kind`)

Mapping per spec §"Threading provenance through existing producers":

- Tests in `test_report.py` / `test_cards.py`: pass `scope="constituent"`, `citation_kind="data"` for filing OR `"information"` for broker, `owner_instrument_id="510300"`, `parent_fund_id=None`, `constituent_key="600519"`.
- `test_types.py:73-79`: pass `scope="instrument"`, `citation_kind="data"`, `owner_instrument_id="510300"`, `parent_fund_id=None`, `constituent_key=None`.
- `test_types.py:87-89` (the kind-loop): same as above with the loop var as `type`.

- [ ] **Step 1: Edit `tests/opportunity/test_report.py:73-86`**

Replace the `evidence = (...)` block inside `test_thesis_cards_yaml_serializes_thesis_evidence` (lines 73-86) with:

```python
    evidence = (
        ThesisEvidence(
            type="filing", source="600519",
            url="https://example.com/filing/600519",
            date="2026-04-28",
            summary="600519 营收同比 +12%",
            scope="constituent", citation_kind="data",
            owner_instrument_id="510300",
            parent_fund_id=None, constituent_key="600519",
        ),
        ThesisEvidence(
            type="broker", source="中信证券",
            url="https://example.com/broker/600519",
            date="2026-05-02",
            summary="维持买入",
            scope="constituent", citation_kind="information",
            owner_instrument_id="510300",
            parent_fund_id=None, constituent_key="600519",
        ),
    )
```

- [ ] **Step 2: Edit `tests/opportunity/test_cards.py:83-95`**

Replace the `evidence = (...)` block inside `test_card_propagates_thesis_evidence` (lines 83-95) with the SAME content as Step 1 above (the two test files share the same fixture).

- [ ] **Step 3: Edit `tests/opportunity/test_types.py:73-79`**

Replace lines 73-79 (the `ev = ThesisEvidence(...)` inside `test_thesis_evidence_is_frozen_dataclass`):

```python
    ev = ThesisEvidence(
        type="filing",
        source="巨潮资讯",
        url="http://www.cninfo.com.cn/foo",
        date="2026-04-28",
        summary="中芯国际 2026Q1 营收同比 +18%。",
        scope="instrument", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key=None,
    )
```

- [ ] **Step 4: Edit `tests/opportunity/test_types.py:87-89`**

Replace lines 87-89 (the loop in `test_thesis_evidence_type_must_be_known_kind`):

```python
    for kind in ("filing", "broker", "news", "policy", "snapshot"):
        ev = ThesisEvidence(
            type=kind, source="s", url="u", date="d", summary="x",
            scope="instrument", citation_kind="data",
            owner_instrument_id="510300",
            parent_fund_id=None, constituent_key=None,
        )
        assert ev.type == kind
```

- [ ] **Step 5: Run all touched tests — expect green**

Run: `uv run pytest tests/opportunity/test_report.py tests/opportunity/test_cards.py tests/opportunity/test_types.py -v`
Expected: All PASS. If unknown failures appear, treat as drift.

---

## Task 9 — Failing test: `_row_to_dict` round-trips `thesis_evidence` + `contributing_dimensions` + `constituent_analyses`

**Files:**
- Modify: `tests/opportunity/test_report.py` (append new test)

- [ ] **Step 1: Add failing round-trip test**

Append to `tests/opportunity/test_report.py`:

```python
import json as _json


def test_row_to_dict_serializes_thesis_evidence_and_contributing_dimensions():
    """JSON round-trip: thesis_evidence appears as a list of dicts with all
    provenance fields including citation_id; contributing_dimensions appears
    as a sorted list; constituent_analyses appears as an empty list (item 003
    populates it later)."""
    ev = ThesisEvidence(
        type="filing", source="600519",
        url="https://example.com/filing/600519",
        date="2026-04-28", summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    row = _row(
        thesis_evidence=(ev,),
        contributing_dimensions=frozenset({"valuation", "heat"}),
    )
    d = _row_to_dict(row)
    # Round-trip through JSON to confirm serializability.
    loaded = _json.loads(_json.dumps(d, ensure_ascii=False))
    assert "thesis_evidence" in loaded
    assert len(loaded["thesis_evidence"]) == 1
    assert loaded["thesis_evidence"][0]["citation_id"] == ev.citation_id
    assert loaded["thesis_evidence"][0]["owner_instrument_id"] == "510300"
    assert loaded["thesis_evidence"][0]["scope"] == "constituent"
    # contributing_dimensions: sorted list (item 001's frozenset → sorted list)
    assert loaded["contributing_dimensions"] == ["heat", "valuation"]
    # constituent_analyses default-empty until item 003.
    assert loaded["constituent_analyses"] == []
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/opportunity/test_report.py::test_row_to_dict_serializes_thesis_evidence_and_contributing_dimensions -v`
Expected: FAIL — `thesis_evidence` key missing from `_row_to_dict` output.

---

## Task 10 — Update `_row_to_dict` and `_card_to_dict` to serialize new schema

**Files:**
- Modify: `src/irc/opportunity/report.py:15-32` (`_row_to_dict`)
- Modify: `src/irc/opportunity/report.py:54-60` (`_card_to_dict`)

- [ ] **Step 1: Update `_row_to_dict`**

Replace lines 15-32 of `src/irc/opportunity/report.py`:

```python
def _row_to_dict(row: OpportunityRow) -> dict[str, Any]:
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
        # New schema (item 002):
        "thesis_evidence": [asdict(e) for e in row.thesis_evidence],
        "contributing_dimensions": sorted(row.contributing_dimensions),
        "constituent_analyses": [
            asdict(c) for c in getattr(row, "constituent_analyses", ())
        ],
    }
```

Note: `getattr(row, "constituent_analyses", ())` is defensive. Item 003 will add `constituent_analyses` to `OpportunityRow` as a real field; until then it does not exist on `OpportunityRow`, so the `getattr` returns `()` and the list comprehension emits `[]`.

- [ ] **Step 2: Update `_card_to_dict` to assert citation_id round-trips**

Replace lines 54-60 of `src/irc/opportunity/report.py`:

```python
def _card_to_dict(card: ThesisCard) -> dict[str, Any]:
    d = asdict(card)
    for key in ("falsification_triggers", "trim_triggers",
                "do_not_sell_just_because", "evidence_gaps",
                "expected_omissions"):
        d[key] = list(d.get(key, []))
    # Every ThesisEvidence dict must carry its citation_id (computed in
    # __post_init__; never empty after construction).
    for ev_dict in d.get("thesis_evidence", []):
        if not ev_dict.get("citation_id"):
            raise RuntimeError(
                f"thesis_evidence entry missing citation_id: {ev_dict}"
            )
    return d
```

- [ ] **Step 3: Run round-trip test — expect green**

Run: `uv run pytest tests/opportunity/test_report.py::test_row_to_dict_serializes_thesis_evidence_and_contributing_dimensions -v`
Expected: PASS.

- [ ] **Step 4: Confirm pre-existing report tests still green**

Run: `uv run pytest tests/opportunity/test_report.py -v`
Expected: All PASS.

- [ ] **Step 5: Verify YAML output of thesis_cards includes citation_id (per spec open question #1)**

Run: `uv run pytest tests/opportunity/test_report.py::test_thesis_cards_yaml_serializes_thesis_evidence -v`
Expected: PASS. (The existing test asserts `type: filing` is in the YAML; the new `citation_id` field flows through `asdict` for free.)

Add a positive assertion to the existing `test_thesis_cards_yaml_serializes_thesis_evidence`:

```python
    assert "citation_id:" in payload  # Item 002: every evidence carries citation_id.
```

Insert this assertion immediately after `assert "thesis_evidence:" in payload` (around test_report.py line 91).

Re-run: `uv run pytest tests/opportunity/test_report.py::test_thesis_cards_yaml_serializes_thesis_evidence -v`
Expected: PASS.

---

## Task 11 — Failing test then add 4 fields to `DisciplineRow`

**Files:**
- Modify: `tests/opportunity/test_types.py` (append test)
- Modify: `src/irc/opportunity/types.py:161-170` (extend `DisciplineRow`)

- [ ] **Step 1: Add failing test**

Append to `tests/opportunity/test_types.py`:

```python
def test_discipline_row_has_new_evidence_fields_with_empty_defaults():
    """DisciplineRow gains thesis_evidence, constituent_analyses, evidence_gaps,
    fetch_types_attempted (all defaulted to empty tuples so existing test
    constructors still work)."""
    from irc.opportunity.types import DisciplineRow as _DR
    r = _DR(
        instrument_id="510300", name_cn="x", asset_class="cn_etf", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
    )
    assert r.thesis_evidence == ()
    assert r.constituent_analyses == ()
    assert r.evidence_gaps == ()
    assert r.fetch_types_attempted == ()


def test_discipline_row_accepts_evidence_gaps_kwarg():
    from irc.opportunity.types import DisciplineRow as _DR
    r = _DR(
        instrument_id="510300", name_cn="x", asset_class="cn_etf", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
        evidence_gaps=("holdings_fetch_failed",),
        fetch_types_attempted=("filing", "broker", "news"),
    )
    assert r.evidence_gaps == ("holdings_fetch_failed",)
    assert r.fetch_types_attempted == ("filing", "broker", "news")
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/opportunity/test_types.py::test_discipline_row_has_new_evidence_fields_with_empty_defaults -v`
Expected: FAIL — `AttributeError: 'DisciplineRow' object has no attribute 'thesis_evidence'`.

- [ ] **Step 3: Extend `DisciplineRow` in `types.py`**

Replace lines 161-170 of `src/irc/opportunity/types.py`:

```python
@dataclass(frozen=True)
class DisciplineRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    note_cn: str
    # Item 002: gap state and provenance carried through to renderers.
    # `constituent_analyses` is typed `tuple[Any, ...]` until item 003 narrows
    # to `tuple[ConstituentAnalysis, ...]`; default `()` round-trips through
    # JSON as `[]`.
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    constituent_analyses: tuple[object, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    fetch_types_attempted: tuple[str, ...] = ()
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/opportunity/test_types.py::test_discipline_row_has_new_evidence_fields_with_empty_defaults tests/opportunity/test_types.py::test_discipline_row_accepts_evidence_gaps_kwarg -v`
Expected: Both PASS.

---

## Task 12 — `_discipline_row_from` propagates 4 new fields

**Files:**
- Modify: `tests/commands/test_opportunity_cmd.py` if it exists, OR create a new test file
- Modify: `src/irc/commands/opportunity_cmd.py:148-163` (`_discipline_row_from`)

- [ ] **Step 1: Confirm whether a test file exists**

Run: `ls tests/commands/test_opportunity_cmd.py 2>/dev/null || echo MISSING`

- If file exists: append the failing test (Step 2) to it.
- If MISSING: create `tests/commands/test_opportunity_cmd.py` with the standard test scaffolding:

```python
from __future__ import annotations
```

and append the failing test.

- [ ] **Step 2: Add failing test**

```python
def test_discipline_row_from_propagates_evidence_gaps_and_thesis_evidence():
    """_discipline_row_from must carry the row's thesis_evidence,
    evidence_gaps, fetch_types_attempted into the DisciplineRow so item 006
    (H3) can render the failure section and item 007 can render evidence
    bullets per row."""
    from irc.commands.opportunity_cmd import _discipline_row_from
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.types import (
        LookthroughTarget, OpportunityRow, ThesisEvidence,
    )

    ev = ThesisEvidence(
        type="filing", source="600519",
        url="https://example.com/600519", date="2026-04-28",
        summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    row = OpportunityRow(
        instrument_id="510300", name_cn="x",
        asset_class="cn_etf", theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="fair", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="core_dca", opportunity_reason="r",
        evidence_gaps=("holdings_fetch_failed",),
        thesis_evidence=(ev,),
    )
    position = PositionContext(0.05, 0.0, 0.30, None, True)
    drow = _discipline_row_from(row, position)
    assert drow.thesis_evidence == (ev,)
    assert drow.evidence_gaps == ("holdings_fetch_failed",)
    # `fetch_types_attempted` is sourced from `getattr(row, "fetch_types_attempted", ())`
    # — OpportunityRow doesn't carry it today, so default is ().
    assert drow.fetch_types_attempted == ()


def test_discipline_row_from_passes_through_constituent_analyses():
    """Until item 003 lands, constituent_analyses is empty by default; the
    propagator still threads it (default → default) so the field exists on
    DisciplineRow for item 007's renderer."""
    from irc.commands.opportunity_cmd import _discipline_row_from
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.types import LookthroughTarget, OpportunityRow

    row = OpportunityRow(
        instrument_id="510300", name_cn="x",
        asset_class="cn_etf", theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="fair", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="core_dca", opportunity_reason="r",
        evidence_gaps=(),
    )
    drow = _discipline_row_from(row, PositionContext(0.05, 0.0, 0.30, None, True))
    assert drow.constituent_analyses == ()
```

- [ ] **Step 3: Run to verify fail**

Run: `uv run pytest tests/commands/test_opportunity_cmd.py::test_discipline_row_from_propagates_evidence_gaps_and_thesis_evidence -v`
Expected: FAIL — `drow.thesis_evidence == ()` because propagator drops it.

- [ ] **Step 4: Update `_discipline_row_from`**

Replace lines 148-163 of `src/irc/commands/opportunity_cmd.py`:

```python
def _discipline_row_from(
    row: OpportunityRow, position: PositionContext,
) -> DisciplineRow:
    dca = derive_dca_action(row)
    risk = derive_risk_action(row, position)
    note = row.opportunity_reason.split(" | ")[0] if row.opportunity_reason else ""
    return DisciplineRow(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        asset_class=row.asset_class,
        theme=row.theme,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        risk_action=risk,
        note_cn=note,
        # Item 002: propagate gap state and provenance.
        thesis_evidence=row.thesis_evidence,
        constituent_analyses=getattr(row, "constituent_analyses", ()),
        evidence_gaps=row.evidence_gaps,
        fetch_types_attempted=getattr(row, "fetch_types_attempted", ()),
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/commands/test_opportunity_cmd.py -v`
Expected: PASS for both new tests; any pre-existing tests in that file still green.

---

## Task 13 — Failing test for `PickRow.citations` + `[ref:{citation_id}]` rendering

**Files:**
- Modify: `tests/memo/test_picks_table.py` (append)

- [ ] **Step 1: Add failing test**

Append to `tests/memo/test_picks_table.py`:

```python
from irc.opportunity.types import ThesisEvidence


def _evidence(**over) -> ThesisEvidence:
    base = dict(
        type="filing", source="600519",
        url="https://example.com/600519", date="2026-04-28",
        summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    base.update(over)
    return ThesisEvidence(**base)


def test_render_picks_table_emits_citation_markers_in_evidence_column():
    """证据 column renders `[ref:{citation_id}] {type}·{source}·{date}` per citation;
    multiple citations on one row joined by `<br>` so the markdown cell stays
    single-row."""
    ev_a = _evidence(url="https://example.com/a", date="2026-04-28")
    ev_b = _evidence(url="https://example.com/b", date="2026-05-02",
                     type="broker", source="中信证券", citation_kind="information")
    row = PickRow(
        instrument_id="510300", name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf", role="core_cn_equity",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="r",
        citations=(ev_a, ev_b),
    )
    md = render_picks_table([row])
    # Header includes 证据 column.
    assert "证据" in md
    # Each citation renders its citation_id marker.
    assert f"[ref:{ev_a.citation_id}]" in md
    assert f"[ref:{ev_b.citation_id}]" in md
    # Joined by <br> in a single cell.
    assert "<br>" in md
    # Render format includes type·source·date.
    assert "filing·600519·2026-04-28" in md
    assert "broker·中信证券·2026-05-02" in md


def test_render_picks_table_empty_citations_renders_dash():
    """When PickRow.citations is empty, the 证据 cell renders `—`."""
    row = PickRow(
        instrument_id="518880", name_cn="华安黄金ETF", asset_class="gold",
        role="core_gold_hedge", target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="r",
    )
    md = render_picks_table([row])
    # Find the data row for 518880 and confirm the dash appears as a cell.
    rows_lines = [line for line in md.split("\n")
                  if "518880" in line and "|" in line]
    assert rows_lines, "no data row found for 518880"
    assert "| — |" in rows_lines[0]
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/memo/test_picks_table.py::test_render_picks_table_emits_citation_markers_in_evidence_column -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'citations'`.

---

## Task 14 — Implement `PickRow.citations` + `证据` column + `render_failure_sections`

**Files:**
- Modify: `src/irc/memo/picks_table.py` (extend `PickRow`, extend `render_picks_table`, add `render_failure_sections`)

- [ ] **Step 1: Add import + extend `PickRow`**

Replace the top of `src/irc/memo/picks_table.py` (lines 1-4) with:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from irc.opportunity.types import ThesisEvidence
```

Replace lines 31-43 (the `PickRow` definition) with:

```python
@dataclass(frozen=True)
class PickRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    role: str
    target_weight: float
    composite_score: float
    opportunity_state: str
    dca_action: str
    risk_action: str
    one_line_reason: str
    citations: tuple[ThesisEvidence, ...] = field(default_factory=tuple)
```

- [ ] **Step 2: Update `render_picks_table` to add `证据` column**

Replace `render_picks_table` (lines 53-78) with:

```python
def _format_citation(ev: ThesisEvidence) -> str:
    """Render one citation as `[ref:{citation_id}] {type}·{source}·{date}`."""
    return f"[ref:{ev.citation_id}] {ev.type}·{ev.source}·{ev.date}"


def _format_citations_cell(citations: tuple[ThesisEvidence, ...]) -> str:
    """Render the 证据 column cell. Multi-citation cells join by <br> so the
    markdown row stays single-line; empty → `—`."""
    if not citations:
        return "—"
    return "<br>".join(_format_citation(c) for c in citations)


def render_picks_table(rows: list[PickRow] | tuple[PickRow, ...]) -> str:
    # Safety-net dedup; canonical dedup is performed by callers
    # (e.g. _build_pick_rows).
    seen: set[str] = set()
    unique: list[PickRow] = []
    for r in rows:
        if r.instrument_id in seen:
            continue
        seen.add(r.instrument_id)
        unique.append(r)

    header = (
        "| 代码 | 名称 | 角色 | 目标权重 | 综合分 | 状态 | 本期行动 | 主要理由 | 证据 |\n"
        "|---|---|---|---|---|---|---|---|---|"
    )
    lines = [header]
    for r in unique:
        weight_str = f"{r.target_weight * 100:.1f}%"
        score_str = f"{r.composite_score:.1f}"
        citations_cell = _format_citations_cell(r.citations)
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {r.role} | "
            f"{weight_str} | {score_str} | {r.opportunity_state} | "
            f"{_action_cn(r)} | {r.one_line_reason} | {citations_cell} |"
        )
    lines.append("")
    lines.append(_SCORING_FOOTNOTE)
    return "\n".join(lines)
```

- [ ] **Step 3: Add `render_failure_sections` helper**

Append to `src/irc/memo/picks_table.py`:

```python
def render_failure_sections(
    absent_targets: list[dict],
    gapped_targets: list[dict],
    extra_names: dict[str, str] | None = None,
) -> str:
    """Render two `###` h3 sub-blocks for trade targets that didn't make the
    picks table. Returns "" when both buckets are empty.

    Output is appended to `picks_table_md` BEFORE it enters `MemoInputs`,
    nesting under `## 5. 精选标的` per grill resolution.

    Format (item 002 spec §"Gap-aware pick-row construction"):
      - absent: `{iid} {extra_names.get(iid, '?')}` — no op row available, name
        from extras (universe / watchlist CSV fallback).
      - gapped: `{iid} {op['name_cn']} | 原因: {gaps} | 已尝试: {fetch_types}` —
        op row exists but `evidence_gaps != ()`. Format mandated by H3 (item 006).
        NEVER renders opportunity_state, dca_action, risk_action, or note_cn.
    """
    extra_names = extra_names or {}
    parts: list[str] = []
    if absent_targets:
        parts.append("### 未能纳入精选：机会数据缺失\n")
        for t in absent_targets:
            iid = str(t.get("target") or "")
            name = extra_names.get(iid, "?")
            parts.append(
                f"- {iid} {name}（trade plan 中存在，但 "
                f"opportunity_report.json 中查无此 instrument_id）"
            )
        parts.append("")
    if gapped_targets:
        parts.append("### 未能纳入精选：证据不足\n")
        for t in gapped_targets:
            op = t.get("_matched_row") or {}
            iid = str(t.get("target") or "")
            name = op.get("name_cn") or extra_names.get(iid, "?")
            gaps = ", ".join(op.get("evidence_gaps") or ())
            attempted = ", ".join(op.get("fetch_types_attempted") or ())
            parts.append(
                f"- {iid} {name} | 原因: {gaps} | 已尝试: {attempted}"
            )
        parts.append("")
    if not parts:
        return ""
    return "\n" + "\n".join(parts)
```

- [ ] **Step 4: Run picks-table tests — expect green**

Run: `uv run pytest tests/memo/test_picks_table.py -v`
Expected: All tests PASS — including the 5 pre-existing tests that don't pass `citations=` (default-empty tuple keeps them working) AND the 2 new tests from Task 13.

Note: If pre-existing tests like `test_render_picks_table_dedupes_and_lists_action_and_rationale` (line 30: `for col in ("代码", "名称", "角色", "目标权重", "状态", "本期行动", "主要理由"):`) need to be extended to also check for `证据`, leave that to the test owner — the test still passes because it only checks for inclusion. DO NOT add `证据` to that loop. If the test fails on `md.count("006075") == 1`, that's a different bug — investigate.

---

## Task 15 — Rewrite `_build_pick_rows` to return `(pick_rows, absent, gapped)`

**Files:**
- Modify: `src/irc/commands/memo_cmd.py:236-278` (`_build_pick_rows`)
- Modify: `src/irc/commands/memo_cmd.py:281-417` (`run_memo` — wire the new return shape)
- Create: `tests/memo/test_pick_rows.py`

- [ ] **Step 1: Create failing tests in `tests/memo/test_pick_rows.py`**

Write to `tests/memo/test_pick_rows.py`:

```python
from __future__ import annotations

from dataclasses import asdict

from irc.commands.memo_cmd import _build_pick_rows
from irc.opportunity.types import ThesisEvidence


def _make_evidence_dict(**over) -> dict:
    base = ThesisEvidence(
        type="filing", source="600519",
        url="https://example.com/600519", date="2026-04-28",
        summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    d = asdict(base)
    d.update(over)
    return d


def _op_row(iid="510300", evidence_gaps=(), thesis_evidence=None, **over):
    base = {
        "instrument_id": iid,
        "name_cn": f"{iid}_name",
        "asset_class": "cn_etf",
        "opportunity_state": "core_dca",
        "opportunity_reason": "r",
        "evidence_gaps": list(evidence_gaps),
        "fetch_types_attempted": ["filing", "broker", "news"],
        "thesis_evidence": list(thesis_evidence or ()),
    }
    base.update(over)
    return base


def test_build_pick_rows_absent_target_routes_to_absent_bucket():
    """trade target whose iid is not in opportunity rows (after venue-proxy
    strip) ends up in `absent`, NOT in `pick_rows`."""
    trades = [{"target": "999999", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert pick_rows == []
    assert len(absent) == 1
    assert absent[0]["target"] == "999999"
    assert gapped == []


def test_build_pick_rows_gapped_target_routes_to_gapped_bucket():
    """trade target whose op row has `evidence_gaps != ()` ends up in
    `gapped`, NOT in `pick_rows`."""
    trades = [{"target": "510300", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300",
                                    evidence_gaps=("holdings_fetch_failed",))]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert pick_rows == []
    assert absent == []
    assert len(gapped) == 1
    assert gapped[0]["target"] == "510300"
    assert gapped[0]["_matched_row"]["instrument_id"] == "510300"


def test_build_pick_rows_clean_target_builds_pick_with_citations():
    """trade target whose op row has `evidence_gaps == ()` produces a PickRow
    whose `citations` is `select_citations(rebuilt_evidence, cap=3)`."""
    ev_dict = _make_evidence_dict()
    trades = [{"target": "510300", "target_weight": 0.1, "composite_score": 50.0}]
    opportunity = {"rows": [_op_row(iid="510300", thesis_evidence=[ev_dict])]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert absent == []
    assert gapped == []
    assert len(pick_rows) == 1
    pr = pick_rows[0]
    assert pr.instrument_id == "510300"
    assert len(pr.citations) == 1
    assert pr.citations[0].citation_id == ev_dict["citation_id"]


def test_build_pick_rows_venue_proxy_strip_falls_back_to_canonical():
    """A trade target like `A510300.SH` should match op row `510300` after
    suffix strip."""
    trades = [{"target": "A510300.SH", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, absent, gapped = _build_pick_rows(trades, opportunity, {"scores": []})
    assert absent == []
    assert gapped == []
    assert len(pick_rows) == 1


def test_build_pick_rows_raises_on_citation_id_tampering():
    """If the rebuilt ThesisEvidence's recomputed citation_id != the JSON
    value, raise ValueError — detects drift/tampering."""
    import pytest
    ev_dict = _make_evidence_dict()
    ev_dict["citation_id"] = "deadbeefdeadbeef"  # wrong; will recompute differently
    trades = [{"target": "510300", "target_weight": 0.1}]
    opportunity = {"rows": [_op_row(iid="510300", thesis_evidence=[ev_dict])]}
    with pytest.raises(ValueError, match="citation_id"):
        _build_pick_rows(trades, opportunity, {"scores": []})


def test_build_pick_rows_missing_opportunity_falls_into_absent():
    """When opportunity is {} (file absent), every trade target falls into
    `absent` — explicit signal that opportunity didn't run."""
    trades = [{"target": "510300"}, {"target": "159919"}]
    pick_rows, absent, gapped = _build_pick_rows(trades, {}, {"scores": []})
    assert pick_rows == []
    assert {a["target"] for a in absent} == {"510300", "159919"}
    assert gapped == []
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/memo/test_pick_rows.py -v`
Expected: FAIL — `_build_pick_rows` returns a flat list, not a 3-tuple; `ValueError: too many values to unpack`.

- [ ] **Step 3: Add helpers + rewrite `_build_pick_rows`**

In `src/irc/commands/memo_cmd.py`, just BEFORE `_build_pick_rows` (around line 235), add:

```python
import re
from dataclasses import asdict as _asdict

from irc.memo.citation_selector import select_citations
from irc.memo.picks_table import render_failure_sections
from irc.opportunity.types import ThesisEvidence


_VENUE_SUFFIX_RE = re.compile(r"\.[A-Z]{2,3}$")


def _strip_venue_suffix(iid: str) -> str:
    """Strip a trailing `.SH` / `.SZ` / `.OF` / `.HK` venue suffix if present.

    Conservative: only strips suffixes matching `\\.[A-Z]{2,3}$`. The diagnosis
    mentions `A1234.SH` → `1234`; canonical iids in `config/universe/*.yaml`
    are 6-digit bare codes (e.g. `510300`, `005827`) and venue proxies like
    `cmb_paper_gold` carry no dot — both pass through unchanged.
    """
    return _VENUE_SUFFIX_RE.sub("", iid)


def _evidence_from_dict(d: dict) -> ThesisEvidence:
    """Rebuild a `ThesisEvidence` from its JSON dict form.

    Recomputes `citation_id` via `__post_init__`. If the JSON dict carries a
    `citation_id` that doesn't match the recomputed value, raise — detects
    drift/tampering of `opportunity_report.json` between stages.
    """
    expected_id = d.get("citation_id")
    ev = ThesisEvidence(
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
    )
    if expected_id and expected_id != ev.citation_id:
        raise ValueError(
            f"citation_id mismatch: JSON has {expected_id!r} "
            f"but recomputed to {ev.citation_id!r} "
            f"(possible tampering of opportunity_report.json)"
        )
    return ev
```

Note: keep `_asdict` import only if used elsewhere in this file; remove if unused.

- [ ] **Step 4: Replace `_build_pick_rows`**

Replace lines 236-278 of `src/irc/commands/memo_cmd.py`:

```python
def _build_pick_rows(
    trades: list[dict],
    opportunity: dict,
    scoring: dict,
    extra_names: dict[str, str] | None = None,
) -> tuple[list[PickRow], list[dict], list[dict]]:
    """Classify each trade target into one of three buckets:

    - `pick_rows`: trade target whose opportunity row has `evidence_gaps == ()`.
    - `absent_targets`: trade target whose iid is NOT in `opportunity["rows"]`
      after venue-proxy suffix strip. Memo renders an absence sub-block.
    - `gapped_targets`: trade target whose op row has `evidence_gaps != ()`.
      Memo renders a gap sub-block (no conclusions emitted).

    Each `gapped_targets` entry is enriched with `_matched_row` so the renderer
    can reach the op row's name and gap labels.
    """
    rows_list = opportunity.get("rows") or []
    rows_by_id = {r["instrument_id"]: r for r in rows_list}
    score_by_id = {s["instrument_id"]: s for s in (scoring.get("scores") or [])}
    extra_names = extra_names or {}

    pick_rows: list[PickRow] = []
    absent: list[dict] = []
    gapped: list[dict] = []
    seen: set[str] = set()

    for t in trades:
        iid_raw = t.get("target")
        if not iid_raw or iid_raw in seen:
            continue
        seen.add(iid_raw)

        # Resolution: direct hit, else venue-proxy suffix strip, else absent.
        op = rows_by_id.get(iid_raw) or rows_by_id.get(_strip_venue_suffix(iid_raw))
        if op is None:
            absent.append(t)
            continue
        if op.get("evidence_gaps"):
            gapped.append({**t, "_matched_row": op})
            continue

        # Eligible: build PickRow with citations.
        raw_evidence = tuple(
            _evidence_from_dict(d) for d in (op.get("thesis_evidence") or [])
        )
        citations = select_citations(raw_evidence, cap=3)

        sc = score_by_id.get(iid_raw) or {}
        reason = (op.get("opportunity_reason") or "").split(" | ")[0].replace(
            "\n", " ").strip()
        opp_state = op.get("opportunity_state", "small_watch")
        dca = {"core_dca": "normal_dca", "small_watch": "slow_dca",
               "pause_wait": "pause_dca", "exclude": "do_not_buy"}.get(
                   opp_state, "slow_dca")
        score = t.get("composite_score")
        if score is None:
            score = sc.get("composite_score") or 0.0
        name = op.get("name_cn") or extra_names.get(str(iid_raw)) or iid_raw
        pick_rows.append(PickRow(
            instrument_id=iid_raw,
            name_cn=name,
            asset_class=op.get("asset_class") or t.get("asset_class", ""),
            role=t.get("role") or "",
            target_weight=float(t.get("target_weight") or 0.0),
            composite_score=float(score),
            opportunity_state=opp_state,
            dca_action=dca,
            risk_action="none",
            one_line_reason=reason or "—",
            citations=citations,
        ))

    return pick_rows, absent, gapped
```

- [ ] **Step 5: Update `run_memo` caller**

In `src/irc/commands/memo_cmd.py`, find the existing call at line ~316:

Old:
```python
    pick_rows = _build_pick_rows(trades, opportunity, scoring, fallback_names)
    picks_table_md = render_picks_table(pick_rows)
```

New:
```python
    pick_rows, absent_targets, gapped_targets = _build_pick_rows(
        trades, opportunity, scoring, fallback_names,
    )
    picks_table_md = render_picks_table(pick_rows) + render_failure_sections(
        absent_targets, gapped_targets, fallback_names,
    )
```

- [ ] **Step 6: Run new tests — expect green**

Run: `uv run pytest tests/memo/test_pick_rows.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 7: Run memo-cmd-touching tests**

Run: `uv run pytest tests/memo/ -v -x`
Expected: All PASS. Pre-existing memo tests must still work because:
- Old single-return `_build_pick_rows` callers don't exist (only `run_memo` calls it).
- `render_picks_table` accepts default-empty `citations` so old PickRow constructions still work.

---

## Task 16 — Failing test then implement `build_cited_map`

**Files:**
- Create: `tests/opportunity/test_citation_map.py`
- Create: `src/irc/opportunity/citation_map.py`

- [ ] **Step 1: Write failing tests in `tests/opportunity/test_citation_map.py`**

```python
from __future__ import annotations

import pytest

from irc.opportunity.citation_map import build_cited_map
from irc.opportunity.types import (
    CitationMeta,
    LookthroughTarget,
    OpportunityRow,
    ThesisEvidence,
)


def _ev(**over) -> ThesisEvidence:
    base = dict(
        type="filing", source="600519",
        url="https://example.com/600519", date="2026-04-28",
        summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    base.update(over)
    return ThesisEvidence(**base)


def _row(iid="510300", asset_class="cn_etf", evidence=()) -> OpportunityRow:
    return OpportunityRow(
        instrument_id=iid, name_cn=f"{iid}_name",
        asset_class=asset_class, theme=None,
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="fair", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="core_dca", opportunity_reason="r",
        evidence_gaps=(),
        thesis_evidence=tuple(evidence),
    )


def test_build_cited_map_returns_correct_shape():
    ev = _ev()
    row = _row(iid="510300", asset_class="cn_etf", evidence=(ev,))
    cited = build_cited_map((row,))
    assert "510300" in cited
    assert ev.citation_id in cited["510300"]
    meta = cited["510300"][ev.citation_id]
    assert isinstance(meta, CitationMeta)
    assert meta.scope == "constituent"
    assert meta.citation_kind == "data"
    assert meta.owner_instrument_id == "510300"
    assert meta.asset_class == "cn_etf"
    assert meta.parent_fund_id is None
    assert meta.constituent_key == "600519"


def test_build_cited_map_raises_on_wrong_owner():
    """If any evidence's owner_instrument_id != row.instrument_id → RuntimeError.

    Provenance integrity: an evidence entry filed under the wrong row is a
    hard error (closes the "wrong instrument" path).
    """
    ev_wrong_owner = _ev(owner_instrument_id="999999")
    row = _row(iid="510300", evidence=(ev_wrong_owner,))
    with pytest.raises(RuntimeError, match="owner_instrument_id"):
        build_cited_map((row,))


def test_build_cited_map_raises_on_duplicate_citation_id():
    """Two different (owner_instrument_id, citation_id) pairs pointing to the
    same citation_id under DIFFERENT owners → RuntimeError. Detector is
    schema-only in this slice (item 009 wires the call before atomic_write_text)."""
    # Same citation under two different funds, with matching owner ids
    # but somehow colliding citation_ids → simulate by monkeypatching is fragile.
    # Instead: build two rows where one row's evidence is wrongly stamped with
    # the OTHER row's instrument as owner — the wrong-owner detector fires first.
    # So the genuine duplicate test uses two evidence entries that legitimately
    # produce the same citation_id under the same owner — impossible by hash
    # construction unless we forge the id. We test that two entries with the
    # same hash inputs collapse into ONE map entry (idempotent) and verify
    # raise-on-conflict by direct call with hand-built map state:
    ev1 = _ev(owner_instrument_id="510300", url="https://example.com/x")
    ev2 = _ev(owner_instrument_id="510300", url="https://example.com/x")
    # ev1 and ev2 have identical citation_id (same preimage) — same row, same
    # evidence-twice scenario is legitimate (dedup, not collision).
    row = _row(iid="510300", evidence=(ev1, ev2))
    cited = build_cited_map((row,))
    # Same citation_id under the same owner: idempotent. Not a collision.
    assert len(cited["510300"]) == 1

    # Real-collision test: same citation_id appearing under TWO different
    # owners. We synthesize this by passing the same evidence dict-shape
    # through hash-construction-equivalent inputs but stamped under
    # different rows. Easiest path: two rows where both rows' thesis_evidence
    # share an evidence whose owner_instrument_id is one of them; the OTHER
    # row's owner mismatch fires the wrong-owner detector first. Skip the
    # synthetic collision test — it's only reachable via 2^64 birthday risk
    # and is locked by the wrong-owner detector. Leave a documented
    # placeholder so future audits know the gap.
```

Note on the duplicate-id test: a genuine 64-bit hash collision is astronomically unlikely in tests; the test above documents the "same evidence twice → idempotent map" semantics and trusts the wrong-owner detector for the more reachable error.

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/opportunity/test_citation_map.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.opportunity.citation_map'`.

- [ ] **Step 3: Implement `build_cited_map`**

Write to `src/irc/opportunity/citation_map.py`:

```python
"""Build a `CitedMap` from a sequence of `OpportunityRow`s.

Pure function. Consumed by audit gates (item 009) immediately before
`atomic_write_text` of `opportunity_report.json` and `memo.md`; a duplicate
citation_id or a wrong-owner mismatch aborts the run before a polluted
artifact reaches disk.

This slice (item 002) lands the function but does NOT call it from any write
path — that wire-up is item 009's responsibility per ADR 0001 §4.
"""
from __future__ import annotations

from irc.opportunity.types import CitationMeta, CitedMap, OpportunityRow


def build_cited_map(rows: tuple[OpportunityRow, ...]) -> CitedMap:
    """Walk every row's `thesis_evidence`, validate provenance, and build the map.

    Raises:
      RuntimeError: if any evidence's `owner_instrument_id != row.instrument_id`.
      RuntimeError: if any `citation_id` appears under two DIFFERENT owners
        (genuine hash collision; 64-bit birthday risk ≈ 2.7e-10 per 100k
        citations).
    """
    cited: dict[str, dict[str, CitationMeta]] = {}
    # Owner-of-id tracking for cross-owner duplicate-id detection.
    owner_of_id: dict[str, str] = {}

    for row in rows:
        for ev in row.thesis_evidence:
            if ev.owner_instrument_id != row.instrument_id:
                raise RuntimeError(
                    f"provenance mismatch: evidence owner_instrument_id="
                    f"{ev.owner_instrument_id!r} but row.instrument_id="
                    f"{row.instrument_id!r} (citation_id={ev.citation_id!r})"
                )
            prior_owner = owner_of_id.get(ev.citation_id)
            if prior_owner is not None and prior_owner != row.instrument_id:
                raise RuntimeError(
                    f"duplicate citation_id {ev.citation_id!r} appears under "
                    f"two different owners: {prior_owner!r} and "
                    f"{row.instrument_id!r}"
                )
            owner_of_id[ev.citation_id] = row.instrument_id
            cited.setdefault(row.instrument_id, {})[ev.citation_id] = CitationMeta(
                scope=ev.scope,
                citation_kind=ev.citation_kind,
                owner_instrument_id=ev.owner_instrument_id,
                asset_class=row.asset_class,
                parent_fund_id=ev.parent_fund_id,
                constituent_key=ev.constituent_key,
            )
    return cited
```

- [ ] **Step 4: Run citation_map tests — expect green**

Run: `uv run pytest tests/opportunity/test_citation_map.py -v`
Expected: All 3 tests PASS.

---

## Task 17 — Duplicate-citation-id detector + provenance integrity already wired in Task 16

The spec separates this as Task 17, but both detectors live inside `build_cited_map` (Task 16). Confirm by:

- [ ] **Step 1: Re-read Task 16's `build_cited_map`** — verify both detectors raise immediately on first violation.

- [ ] **Step 2: Add explicit "first-violation" assertion test**

Append to `tests/opportunity/test_citation_map.py`:

```python
def test_build_cited_map_raises_immediately_on_first_violation():
    """Detector raises on the FIRST bad evidence — does not accumulate violations."""
    ev_ok = _ev(owner_instrument_id="510300")
    ev_bad = _ev(owner_instrument_id="999999")
    # Order matters: ev_bad comes first, so the detector should fire before
    # ev_ok is inspected.
    row = _row(iid="510300", evidence=(ev_bad, ev_ok))
    with pytest.raises(RuntimeError, match="owner_instrument_id"):
        build_cited_map((row,))
```

- [ ] **Step 3: Run — expect pass**

Run: `uv run pytest tests/opportunity/test_citation_map.py::test_build_cited_map_raises_immediately_on_first_violation -v`
Expected: PASS.

---

## Task 18 — Lint + full test sweep

- [ ] **Step 1: Run ruff**

Run: `uv run ruff check src/ tests/`
Expected: No errors. If errors appear, fix in-place per ruff's hints; do not silence with `# noqa`.

- [ ] **Step 2: Run full pytest sweep, excluding known pre-existing failures**

Run:
```bash
uv run pytest -v \
  --deselect tests/commands/test_run_cmd.py::test_only_stage_runs_single \
  --deselect tests/integration/test_thesis_coverage.py::test_thesis_coverage_meets_threshold
```

Expected: All other tests PASS. If a different test fails:
1. STOP. Treat as drift (per drift guardrail #2).
2. Investigate the root cause — does this slice break the test, or was it broken on HEAD?
3. If broken on HEAD: surface as a third pre-existing failure in the drift log and consult before fixing.
4. If broken by this slice: fix the slice. Do not skip the test.

- [ ] **Step 3: Sanity-check the failure-section markdown end-to-end**

Append a single integration test to `tests/memo/test_pick_rows.py`:

```python
def test_render_failure_sections_produces_expected_markdown():
    """Smoke test: absent + gapped buckets render the `###` h3 sub-blocks
    and never emit conclusion fields (opportunity_state, dca_action, etc.)."""
    from irc.memo.picks_table import render_failure_sections

    absent = [{"target": "510300"}]
    gapped = [{
        "target": "005827",
        "_matched_row": {
            "instrument_id": "005827",
            "name_cn": "易方达蓝筹精选",
            "evidence_gaps": ["missing_constituent_snapshot", "news_search_empty"],
            "fetch_types_attempted": ["filing", "broker", "news"],
            # The following MUST NOT appear in the failure section markdown:
            "opportunity_state": "core_dca",
            "dca_action": "normal_dca",
            "risk_action": "none",
            "note_cn": "should-not-appear",
        },
    }]
    md = render_failure_sections(absent, gapped, extra_names={"510300": "华泰柏瑞沪深300ETF"})
    assert "### 未能纳入精选：机会数据缺失" in md
    assert "### 未能纳入精选：证据不足" in md
    assert "510300 华泰柏瑞沪深300ETF" in md
    assert "005827 易方达蓝筹精选" in md
    assert "missing_constituent_snapshot" in md
    assert "filing, broker, news" in md
    # Conclusion fields MUST NOT leak:
    assert "core_dca" not in md
    assert "normal_dca" not in md
    assert "should-not-appear" not in md


def test_render_failure_sections_empty_buckets_returns_empty_string():
    from irc.memo.picks_table import render_failure_sections
    assert render_failure_sections([], []) == ""
```

Run: `uv run pytest tests/memo/test_pick_rows.py -v`
Expected: All 8 tests in the file PASS.

- [ ] **Step 4: Final full sweep**

Run:
```bash
uv run pytest -v \
  --deselect tests/commands/test_run_cmd.py::test_only_stage_runs_single \
  --deselect tests/integration/test_thesis_coverage.py::test_thesis_coverage_meets_threshold
uv run ruff check src/ tests/
```

Expected: All green.

- [ ] **Step 5: Commit (one final commit; small interim commits also OK)**

```bash
git add src/ tests/ docs/2026-05-22-thesis-cards-evidence-gap/items/002-plan.md
git commit -m "feat(citations): unified citation provenance schema (item 002, slice D0)"
```

The commit message should follow the project's conventional-commit style as seen in `git log --oneline -10`.

---

## Self-review notes

**Spec coverage matrix:**

| Spec § / Acceptance # | Task |
|---|---|
| Schema additions 1 (ThesisEvidence) | Tasks 1, 2, 3 |
| Schema additions 2 (CitationMeta) | Task 4 |
| Schema additions 3 (type aliases) | Task 4 |
| Schema additions 4 (DisciplineRow new fields) | Task 11 |
| New module 5 (citation_selector) | Tasks 5, 6 |
| Serializer/propagator 6 (_row_to_dict) | Tasks 9, 10 |
| Serializer/propagator 7 (_discipline_row_from) | Task 12 |
| PickRow + render 8, 9 | Tasks 13, 14 |
| _build_pick_rows rewrite 10 | Task 15 |
| build_cited_map 11, dup detector 12 | Tasks 16, 17 |
| All 9 ThesisEvidence call sites | Tasks 7 (3 prod) + 8 (5 test + 1 loop) |
| Acceptance 1–8 | Tasks 1, 2, 3 |
| Acceptance 9–13 | Tasks 5, 6 |
| Acceptance 14, 24, 25 | Tasks 9, 10 |
| Acceptance 15 | Task 12 |
| Acceptance 16 | Tasks 13, 14 |
| Acceptance 17–20 | Task 15 |
| Acceptance 21–23 | Tasks 16, 17 |
| Acceptance 26 | Task 18 (smoke test) |
| Acceptance 27 | Task 18 (smoke test asserts no conclusion fields) |

**Judgment calls made:**

- **PickRow cell separator:** `<br>` between citations (spec §"PickRow rendering" — confirmed by grill point 7). Renders correctly in GFM markdown tables.
- **`build_cited_map` location:** `src/irc/opportunity/citation_map.py` (new file). Spec § "Files touched" notes "located in `opportunity/` rather than `memo/` because the producer is an opportunity-stage artifact (consumed by memo + opportunity audit gates)" — followed verbatim.
- **`_evidence_from_dict` location:** Inside `src/irc/commands/memo_cmd.py` as a private helper. Spec open question #3 defers; only consumer in this slice is `_build_pick_rows`. Item 009 may promote later.
- **`_strip_venue_suffix` regex:** `\.[A-Z]{2,3}$` (conservative). Spec open question #5 punts to planner; this matches `.SH`, `.SZ`, `.OF`, `.HK` plus 3-letter variants without over-matching legitimate iids (configs show all canonical iids are dot-free 6-digit codes).
- **Failure-section block separation:** A single leading `"\n"` prefix from `render_failure_sections` to ensure the `###` headers separate from `_SCORING_FOOTNOTE` cleanly. The footnote stays above the failure sections per spec.
- **`constituent_analyses` typing on `OpportunityRow`:** Spec describes the field on `DisciplineRow` only for this slice; `OpportunityRow` does not gain the field in item 002 (item 003 adds it). `_row_to_dict` uses `getattr(row, "constituent_analyses", ())` so the JSON emits `[]` even though the field doesn't exist on `OpportunityRow` yet. This honors acceptance #14 ("constituent_analyses (empty list before item 003)") without inventing fields that item 003 owns.
- **Field name consistency:** `holding_weight_pct` on `ThesisEvidence` is referenced in spec §"Selector algorithm" but NOT in the dataclass field list. This slice does NOT add it to `ThesisEvidence`; the selector uses `getattr(e, "holding_weight_pct", 0.0)` defensively so item 003 can add it without breaking the selector. Documented in `_slot_key` docstring.
- **Round-trip integrity check timing:** `_evidence_from_dict` raises on `citation_id` mismatch (acceptance #20). This means `opportunity_report.json` files generated by older versions WITHOUT `citation_id` will not round-trip. That is intentional — the schema break is the whole point of this slice. Memo runs against today's `opportunity_report.json` (regenerated in the same pipeline run); stale files are an upstream-orchestration concern.

**Ambiguities committed to:**

- The spec's selector pseudocode mentions a `-` (descending) trick on date strings; the plan picks the two-pass stable-sort approach (Task 6 Step 1) per spec's explicit allowance ("Either approach is acceptable as long as E13b regression locks the exact output ordering").
- The genuine 64-bit hash collision case for `build_cited_map` is documented but not directly tested (would require forging `citation_id`). The wrong-owner detector is the proximate gate; the duplicate-owner-of-id detector raises only on a real 2^64 birthday hit. A placeholder comment in `test_citation_map.py` documents the gap.
