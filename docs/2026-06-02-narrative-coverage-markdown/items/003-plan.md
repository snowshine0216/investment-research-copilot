# Item 003 — Markdown report enrichment (M1 evidence prose/citations + M2 product metrics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the narrative `.md` self-explaining — inline evidence prose, a per-fund resolvable citation footnote appendix + per-constituent prose, and product-quality driver metrics next to `质量={state}` — without touching any scorer, gate, or invariant.

**Architecture:** Thread two new (defaulted, frozen) carriers onto `NarrativeFundReport` (`constituent_analyses` — already on `card`/`row`, just stop dropping it; and a small `ProductMetrics` bundle built from `OpportunityInput` at the `analyze_fund` edge). `report.py` gains small pure render helpers that **mirror, not import**, the opportunity-report line shapes (RD-1: `narrative/report.py` is a display-only, non-SAME-3 surface). `.json` stays the full source of truth (additive only). Footnotes sort by `citation_id` ascending (RD-4 determinism); appendix constituents by weight-desc.

**Tech Stack:** Python 3.12, frozen dataclasses + keyword construction, `uv run pytest`, `uv run ruff check`. TDD throughout (red → green → refactor).

---

## Context the engineer must hold

**Files in play (all repo-relative):**
- `src/irc/narrative/schemas.py` — `NarrativeFundReport` (frozen dataclass; add fields with safe defaults). Add a frozen `ProductMetrics` value object here.
- `src/irc/narrative/analyze.py` — `_report_from_card(row, shortlist_row, *, role)` (today **drops** `card.constituent_analyses` and carries **no** product metrics). `analyze_fund(...)` builds `inp` (line 137) and calls `_report_from_card` (line 140).
- `src/irc/narrative/report.py` — `render_report_md`, `render_report_json`, `_evidence_bullets`, `_evidence_dict`, `_report_dict`. **< 200 lines budget** — extract helpers, keep each < 20 lines.
- `tests/narrative/test_report.py` — mirror existing fixture style (`_row`, `_evidence`, `_report`, `_REF_RE`).

**Read-only references (DO NOT modify):**
- `src/irc/opportunity/states.py:342-359` `classify_product_quality` — F-1 follow-up; surface drivers only, never re-classify.
- `src/irc/opportunity/report.py:289` `_format_appendix_constituent_line` (5-shape precedence, column-0 `- ` head) and `:196` `_render_thesis_evidence_bullets` (`- [ref:{id}] {type} · {source} · {date}`) — **mirror the shape, do NOT import** (RD-1/Approach-C rejected).
- `src/irc/opportunity/citation_selector.py` `select_citations(entries, cap=3)` — reuse as-is; add NO new consumer to SAME-3 surfaces.
- `src/irc/fundamentals/types.py` — `ThesisEvidence` (`type/source/url/date/summary/citation_id`); `ConstituentAnalysis` (`symbol/name_cn/weight_pct/evidence/failure_reasons/one_line_view/audit_errors`).
- `src/irc/opportunity/types.py:101-105` — product metrics on `OpportunityInput`: `expense_ratio`, `aum_cny`, `aum_stability_pct`, `tracking_error`, `manager_tenure_years`. `:170` `OpportunityRow.constituent_analyses`; `:198` `ThesisCard.constituent_analyses`.

**Real signatures (quoted verbatim — do not re-type from memory):**

```python
# src/irc/narrative/report.py — TODAY
def _evidence_bullets(thesis_evidence: tuple[ThesisEvidence, ...]) -> list[str]:
    if not thesis_evidence:
        return []
    selected = select_citations(thesis_evidence, cap=3)
    return [
        f"  - [ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date}"
        for ev in selected
    ]

def render_report_md(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str: ...
def render_report_json(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str: ...

# src/irc/narrative/analyze.py — TODAY
def _report_from_card(
    row: OpportunityRow, shortlist_row: ShortlistRow, *, role: str,
) -> NarrativeFundReport: ...
# analyze_fund body, line 137-140:
#     inp = _build_input(score_row, instr, None, None, 0.0, set(), con, provider=provider)
#     ...
#     row = build_opportunity_row(inp, None, snapshot=snapshot, theme_report=None)
#     return _report_from_card(row, shortlist_row, role=role)

# src/irc/opportunity/states.py — READ-ONLY (F-1)
def classify_product_quality(inp: OpportunityInput) -> tuple[ProductQualityState, str]:
    if _is_active_fund(inp):
        if inp.manager_tenure_years is None or inp.aum_stability_pct is None:
            if inp.manager_tenure_years is None and inp.aum_stability_pct is None:
                return "evidence_insufficient", "主动基金缺少基金经理与AUM稳定性证据。"
            return "weak", "主动基金证据不足，未达可推荐水平。"   # ← the structural floor
        ...
```

**Invariants the engineer must not break:**
- Citation IDs are exactly 16-hex, read verbatim from `ev.citation_id` — never recompute/truncate. Markers match `\[ref:[0-9a-f]{16}\]` (ADR 0001).
- Renderer is pure (string in / string out); all I/O stays at the `analyze.py` edge.
- Determinism (ADR 0004): no `dict`/`set` iteration without an explicit sort; footnotes sorted by `citation_id` asc; constituents by weight-desc; no timestamps.
- `narrative/report.py` is **NOT** a SAME-3 surface (RD-1) — the appendix/footnotes are display-only and never enter any citation-set-equality check. Add NO new `select_citations` consumer to `_build_pick_rows` / `build_evidence_pool` / `_render_section`.
- New `NarrativeFundReport` fields are frozen with safe defaults (`() / None`), constructed by keyword. `error_report` and all existing constructors stay valid.
- Do NOT touch item 004's gapped-row triad suppression — leave the `机会 / dca / 风险` line exactly as-is.
- Files < 200 lines; helper funcs < 20 lines.

---

## AC → Test mapping (all 11)

| AC | Test(s) |
|---|---|
| AC1 inline cap=3 + `· {summary}` | `test_report_md_inline_bullet_has_summary_suffix`, `test_report_md_inline_caps_at_three_with_summary` |
| AC2 16-hex inline prefix unchanged | `test_report_md_emits_ref_from_thesis_evidence` (existing, unchanged) |
| AC3 active-fund constituent appendix prose | `test_report_md_appendix_renders_constituent_one_line_view`, `test_report_md_appendix_constituent_failure_only_no_oneline` |
| AC4 every inline `[ref:hex]` resolves | `test_report_md_every_inline_ref_resolves_to_footnote` |
| AC5 footnote determinism (byte-identical, id-sorted) | `test_report_md_footnote_table_is_byte_identical_two_calls`, `test_report_md_footnotes_sorted_by_citation_id_asc` |
| AC6 product drivers rendered, `—` for None | `test_report_md_renders_product_drivers`, `test_report_md_none_metric_renders_em_dash` |
| AC7 genuine-weak vs metadata-floored visible | `test_report_md_metadata_floored_weak_shows_all_em_dash`, `test_report_md_genuine_weak_shows_real_numbers` |
| AC8 `.json` round-trips + additive new fields | `test_report_json_round_trips_states_and_evidence` (existing), `test_report_json_includes_product_metrics_and_constituents` |
| AC9 existing renderer tests pass | full `tests/narrative/test_report.py` (5 existing tests unchanged) |
| AC10 SAME-3 + opportunity/memo determinism green | scope run `tests/memo/test_same_3_invariant.py` + `tests/opportunity` |
| AC11 no scorer/state change | `git diff --name-only` inspection step (no file under `states.py`/`thesis_evidence.py`/`risk.py`/any classifier) |

---

## Task 0: Baseline (no code change)

**Files:** none.

- [ ] **Step 1: Confirm branch and green baseline**

Run:
```bash
git branch --show-current
uv run pytest tests/narrative/test_report.py -q
ITEM003_BASE=$(git rev-parse HEAD); echo "$ITEM003_BASE"   # capture for AC11
```
Expected: branch `autodev/narrative-coverage-markdown-feature`; `7 passed`. Record `$ITEM003_BASE` (the pre-item-003 HEAD) for the AC11 scope-diff in Task 8.

---

## Task 1: Add `ProductMetrics` + new `NarrativeFundReport` fields (schema)

**Files:**
- Modify: `src/irc/narrative/schemas.py`
- Test: `tests/narrative/test_schemas.py` (create if absent) — but schema is exercised through `test_report.py`; a dedicated construct-default test goes here.

- [ ] **Step 1: Write the failing test** — append to `tests/narrative/test_report.py` (top, after imports):

```python
from irc.narrative.schemas import ProductMetrics  # NEW import


def test_product_metrics_defaults_are_none() -> None:
    pm = ProductMetrics()
    assert pm.expense_ratio is None
    assert pm.aum_cny is None
    assert pm.manager_tenure_years is None
    assert pm.tracking_error is None


def test_narrative_fund_report_new_fields_default_empty() -> None:
    # Existing _report() constructor must still be valid (no new required args).
    r = _report("A")
    assert r.constituent_analyses == ()
    assert r.product_metrics is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_report.py::test_product_metrics_defaults_are_none -v`
Expected: FAIL — `ImportError: cannot import name 'ProductMetrics'`.

- [ ] **Step 3: Add the schema** — in `src/irc/narrative/schemas.py`, add the import and the value object, and extend `NarrativeFundReport`.

Add to the import block at the top (alongside the existing `ConstituentAnalysis`-bearing module):

```python
from irc.fundamentals.types import ConstituentAnalysis, ThesisEvidence
```

(Replace the current `from irc.fundamentals.types import ThesisEvidence` line with the line above.)

Add the value object before `NarrativeFundReport`:

```python
@dataclass(frozen=True)
class ProductMetrics:
    """M2 product-quality drivers, projected from OpportunityInput at the
    analyze edge. Display-only — no classifier reads it (RD-7). `None` means
    'unprovidable / not ingested' and renders as `—`. `tracking_error` is
    populated for passive vehicles only."""

    expense_ratio: float | None = None
    aum_cny: float | None = None
    manager_tenure_years: float | None = None
    tracking_error: float | None = None
```

Extend `NarrativeFundReport` (append two defaulted fields AFTER `thesis_evidence`, preserving its `= ()` default position):

```python
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    # Item 003: display-only carriers. constituent_analyses is threaded from
    # card/row (the renderer stopped dropping it); product_metrics is built from
    # OpportunityInput. Neither feeds any gate/classifier (RD-5, RD-7).
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
    product_metrics: ProductMetrics | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/narrative/test_report.py::test_product_metrics_defaults_are_none tests/narrative/test_report.py::test_narrative_fund_report_new_fields_default_empty -v`
Expected: 2 passed.

- [ ] **Step 5: Confirm existing suite still green (defaults are backward-compatible)**

Run: `uv run pytest tests/narrative/test_report.py -q`
Expected: all pass (the 5 original + 2 new).

- [ ] **Step 6: Commit**

```bash
git add src/irc/narrative/schemas.py tests/narrative/test_report.py
git commit -m "feat(003): add ProductMetrics + display-only fields to NarrativeFundReport"
```

---

## Task 2: Thread `constituent_analyses` + `ProductMetrics` through `_report_from_card`

**Files:**
- Modify: `src/irc/narrative/analyze.py` (`_report_from_card`, `analyze_fund`)
- Test: `tests/narrative/test_analyze.py` (existing — verify; create the two tests below)

> The unit test builds an `OpportunityRow` + `OpportunityInput` directly (no DuckDB/provider) and calls `_report_from_card`, so it stays a pure unit test. Confirm fixtures by reading the existing `tests/narrative/test_analyze.py` for the established `OpportunityRow` builder before writing — reuse it.

- [ ] **Step 1: Write the failing test** — in `tests/narrative/test_analyze.py`:

```python
from irc.fundamentals.types import ConstituentAnalysis, ThesisEvidence
from irc.narrative.analyze import _report_from_card
from irc.narrative.schemas import OverlapResult, ShortlistRow
from irc.opportunity.types import OpportunityInput, OpportunityRow


def _ev(iid: str) -> ThesisEvidence:
    return ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary="s", scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
    )


def _ca() -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol="601899", name_cn="紫金矿业", weight_pct=8.5,
        evidence=(_ev("601899"),), failure_reasons=(),
        one_line_view="紫金矿业 2026Q1 营收同比 +20%", audit_errors=(),
    )


def _row(iid: str) -> OpportunityRow:
    # Reuse the existing OpportunityRow builder in this test module if one
    # exists; otherwise construct the minimum-valid row with constituent_analyses.
    ...  # build a valid OpportunityRow with constituent_analyses=(_ca(),)


def _shortlist(iid: str) -> ShortlistRow:
    ov = OverlapResult(basket_weight_pct=10.0, overlap_count=1,
                       matched_symbols=("601899",), industry_credit_symbols=())
    return ShortlistRow(instrument_id=iid, name_cn=f"fund-{iid}",
                        asset_class="cn_equity_fund", overlap=ov, holdings=())


def test_report_from_card_carries_constituent_analyses() -> None:
    inp = OpportunityInput(...)  # minimal valid input, see existing test fixtures
    rpt = _report_from_card(_row("A"), _shortlist("A"), inp=inp, role="satellite")
    assert rpt.constituent_analyses != ()
    assert rpt.constituent_analyses[0].one_line_view == "紫金矿业 2026Q1 营收同比 +20%"


def test_report_from_card_carries_product_metrics_from_input() -> None:
    inp = OpportunityInput(... , expense_ratio=0.005, aum_cny=5.0e8,
                           manager_tenure_years=7.0, tracking_error=None)
    rpt = _report_from_card(_row("A"), _shortlist("A"), inp=inp, role="satellite")
    assert rpt.product_metrics is not None
    assert rpt.product_metrics.expense_ratio == 0.005
    assert rpt.product_metrics.aum_cny == 5.0e8
    assert rpt.product_metrics.manager_tenure_years == 7.0
    assert rpt.product_metrics.tracking_error is None
```

(Fill the `...` from the existing `tests/narrative/test_analyze.py` fixtures — read that file first; reuse its `OpportunityRow`/`OpportunityInput` builders verbatim rather than re-inventing required fields.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_analyze.py::test_report_from_card_carries_constituent_analyses -v`
Expected: FAIL — `_report_from_card() got an unexpected keyword argument 'inp'`.

- [ ] **Step 3: Add the `ProductMetrics` builder + change the signature** — in `src/irc/narrative/analyze.py`.

Add the import (extend the existing schemas import):

```python
from irc.narrative.schemas import (
    NarrativeFundReport,
    ProductMetrics,
    RiskEvalView,
    ShortlistRow,
)
```

Add a pure builder helper (above `_report_from_card`):

```python
def _product_metrics_from_input(inp: OpportunityInput) -> ProductMetrics:
    """Project the four display-only product-quality drivers (RD-5). Pure."""
    return ProductMetrics(
        expense_ratio=inp.expense_ratio,
        aum_cny=inp.aum_cny,
        manager_tenure_years=inp.manager_tenure_years,
        tracking_error=inp.tracking_error,
    )
```

Change `_report_from_card` to receive `inp` and thread both new carriers:

```python
def _report_from_card(
    row: OpportunityRow, shortlist_row: ShortlistRow, *, inp: OpportunityInput, role: str,
) -> NarrativeFundReport:
    entry_reason = row.opportunity_reason.split("；")[0].split(";")[0]
    card = build_thesis_card(row, _PROSPECTIVE_POSITION, role, entry_reason)
    view = _risk_view_from_row(row, shortlist_row)
    level, rationale, drivers = derive_position_risk_level(view, shortlist_row.overlap, {})
    return NarrativeFundReport(
        instrument_id=card.instrument_id, name_cn=card.name_cn,
        position_risk_level=level, risk_rationale=rationale, risk_drivers=drivers,
        valuation_state=card.valuation_state, heat_state=card.heat_state,
        thesis_state=card.thesis_state, product_quality_state=card.product_quality_state,
        opportunity_state=card.opportunity_state, dca_action=card.dca_action,
        risk_action=card.risk_action,
        falsification_triggers=card.falsification_triggers,
        trim_triggers=card.trim_triggers, review_cadence=card.review_cadence,
        evidence_gaps=card.evidence_gaps, thesis_evidence=card.thesis_evidence,
        constituent_analyses=card.constituent_analyses,
        product_metrics=_product_metrics_from_input(inp),
    )
```

- [ ] **Step 4: Update the `analyze_fund` call site** — `src/irc/narrative/analyze.py:140`:

```python
    return _report_from_card(row, shortlist_row, inp=inp, role=role)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_analyze.py -v`
Expected: all pass (incl. the 2 new). If a pre-existing analyze test called `_report_from_card` positionally without `inp`, update it to pass `inp=` — that is the only allowed test churn (signature change).

- [ ] **Step 6: Commit**

```bash
git add src/irc/narrative/analyze.py tests/narrative/test_analyze.py
git commit -m "feat(003): thread constituent_analyses + ProductMetrics onto NarrativeFundReport"
```

---

## Task 3: M1 — inline evidence bullet gains `· {summary}` (AC1, AC2)

**Files:**
- Modify: `src/irc/narrative/report.py` (`_evidence_bullets`)
- Test: `tests/narrative/test_report.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_report_md_inline_bullet_has_summary_suffix() -> None:
    ev = _evidence("A")  # summary = "601899 2026Q1 财报已披露（口径未核实）"
    md = render_report_md("算力金属", (_report("A", evidence=(ev,)),))
    assert (
        f"- [ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date} · {ev.summary}"
        in md
    )


def test_report_md_inline_caps_at_three_with_summary() -> None:
    evs = tuple(
        ThesisEvidence(
            type="news", source=f"src{i}", url="", date=f"2026-03-0{i}",
            summary=f"headline-{i}", scope="instrument", citation_kind="information",
            owner_instrument_id="A", parent_fund_id=None, constituent_key=None,
        )
        for i in range(1, 6)  # 5 records
    )
    md = render_report_md("算力金属", (_report("A", evidence=evs),))
    # Inline cell still capped at 3 distinct inline bullets (the `证据 / evidence:` block).
    inline = md.split("证据 / evidence:")[1].split("\n\n")[0]
    assert inline.count("[ref:") == 3
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/narrative/test_report.py::test_report_md_inline_bullet_has_summary_suffix -v`
Expected: FAIL — current bullet ends at `{ev.date}`, no ` · {summary}`.

- [ ] **Step 3: Append `· {summary}` in `_evidence_bullets`** — `src/irc/narrative/report.py`:

```python
def _evidence_bullets(thesis_evidence: tuple[ThesisEvidence, ...]) -> list[str]:
    """Inline cell: locked `- [ref:{id}] {type} · {source} · {date}` prefix
    (opportunity/report.py:210, mirrored not imported) with a trailing
    ` · {summary}` prose segment (AC1). Capped at 3 via select_citations."""
    if not thesis_evidence:
        return []
    selected = select_citations(thesis_evidence, cap=3)
    return [
        f"  - [ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date} · {ev.summary}"
        for ev in selected
    ]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/narrative/test_report.py::test_report_md_inline_bullet_has_summary_suffix tests/narrative/test_report.py::test_report_md_inline_caps_at_three_with_summary tests/narrative/test_report.py::test_report_md_emits_ref_from_thesis_evidence -v`
Expected: 3 passed. AC2's existing test still asserts the prefix `... {ev.date}` substring, which is unchanged (summary is appended) → still green.

- [ ] **Step 5: Commit**

```bash
git add src/irc/narrative/report.py tests/narrative/test_report.py
git commit -m "feat(003): inline evidence bullet carries ThesisEvidence.summary prose (AC1)"
```

---

## Task 4: M1 — footnote appendix that resolves every inline `[ref:hex]` (AC4, AC5)

**Files:**
- Modify: `src/irc/narrative/report.py` (new `_footnote_lines`, wire into `render_report_md`)
- Test: `tests/narrative/test_report.py`

- [ ] **Step 1: Write the failing tests**

```python
def _multi(iid: str) -> tuple[ThesisEvidence, ...]:
    return tuple(
        ThesisEvidence(
            type="news", source=f"src{i}", url=("" if i % 2 else f"http://u/{i}"),
            date=f"2026-03-0{i}", summary=f"headline-{i}",
            scope="instrument", citation_kind="information",
            owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
        )
        for i in range(1, 6)
    )


def test_report_md_every_inline_ref_resolves_to_footnote() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=_multi("A")),))
    block = md.split("## A ")[1]
    inline_ids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", block))
    # Footnote section header present + each inline id has exactly one footnote line.
    assert "证据明细" in block
    for cid in inline_ids:
        footnote = [ln for ln in block.splitlines()
                    if ln.startswith(f"[ref:{cid}]")]
        assert len(footnote) == 1, f"{cid} resolved {len(footnote)} times"


def test_report_md_footnote_table_is_byte_identical_two_calls() -> None:
    reports = (_report("A", evidence=_multi("A")),)
    assert render_report_md("算力金属", reports) == render_report_md("算力金属", reports)


def test_report_md_footnotes_sorted_by_citation_id_asc() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=_multi("A")),))
    footnotes = [ln[len("[ref:"):len("[ref:") + 16]
                 for ln in md.splitlines() if ln.startswith("[ref:")]
    assert footnotes == sorted(footnotes)


def test_report_md_no_evidence_has_no_footnote_table() -> None:
    md = render_report_md("算力金属", (_report("A", evidence=()),))
    assert "证据明细" not in md
    assert not _REF_RE.search(md)
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/narrative/test_report.py::test_report_md_every_inline_ref_resolves_to_footnote -v`
Expected: FAIL — no `证据明细` section, footnotes absent.

- [ ] **Step 3: Add the footnote builder + appendix wiring** — `src/irc/narrative/report.py`.

```python
def _footnote_line(ev: ThesisEvidence) -> str:
    """One footnote resolving a [ref:hex]. 16-hex id read verbatim (ADR 0001).
    `· {url}` appended only when url is non-empty."""
    base = f"[ref:{ev.citation_id}] {ev.type} · {ev.source} · {ev.date} · {ev.summary}"
    return f"{base} · {ev.url}" if ev.url else base


def _footnote_lines(thesis_evidence: tuple[ThesisEvidence, ...]) -> list[str]:
    """Full-pool footnote table for one fund, deduped by citation_id, sorted by
    citation_id ASC (RD-4 determinism). Draws from the flattened r.thesis_evidence
    superset so every appendix/inline ref resolves (RD-6, AC4)."""
    if not thesis_evidence:
        return []
    by_id = {ev.citation_id: ev for ev in thesis_evidence}
    return [_footnote_line(by_id[cid]) for cid in sorted(by_id)]
```

> Note: building `by_id` from a tuple then iterating `sorted(by_id)` is deterministic — last-write-wins on a dup id is irrelevant because identical `citation_id` means identical preimage → identical fields. No `set` iteration without a sort (RD-4).

Wire into `render_report_md` (replace the current `bullets = _evidence_bullets(...)` tail of the per-fund loop):

```python
        bullets = _evidence_bullets(r.thesis_evidence)
        if bullets:
            lines.append("- 证据 / evidence:")
            lines.extend(bullets)
        appendix = _appendix_lines(r)  # added in Task 5; for now return [] (see below)
        lines.extend(appendix)
        footnotes = _footnote_lines(r.thesis_evidence)
        if footnotes:
            lines.append("")
            lines.append("### 证据明细 / Evidence appendix")
            lines.extend(footnotes)
        lines.append("")
```

> To keep Task 4 independently green BEFORE Task 5 lands, temporarily define a stub:
> ```python
> def _appendix_lines(r: NarrativeFundReport) -> list[str]:
>     return []  # constituent prose added in Task 5
> ```
> Task 5 replaces this stub body. (This is the only stub allowed — it is immediately superseded, not left dangling.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/narrative/test_report.py -k "footnote or resolves or no_evidence" -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/narrative/report.py tests/narrative/test_report.py
git commit -m "feat(003): per-fund footnote appendix resolving every inline ref, id-sorted (AC4/AC5)"
```

---

## Task 5: M1 — per-constituent appendix prose (AC3)

**Files:**
- Modify: `src/irc/narrative/report.py` (`_appendix_lines`, new `_appendix_constituent_line`)
- Test: `tests/narrative/test_report.py`

> The constituent line shape **mirrors** `opportunity/report.py::_format_appendix_constituent_line` — a self-contained copy, NOT an import (RD-1 / Approach-C rejected). Ordering: weight-desc, symbol-asc tiebreak (mirror `_rank_constituents_by_weight`).

- [ ] **Step 1: Write the failing tests**

```python
from irc.fundamentals.types import ConstituentAnalysis  # add to imports


def _ca(symbol: str, weight: float, *, evidence=(), failures=(),
        oneline="prose", audit=()) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn=f"co-{symbol}", weight_pct=weight,
        evidence=evidence, failure_reasons=failures,
        one_line_view=oneline, audit_errors=audit,
    )


def _report_with_constituents(iid: str, cas) -> NarrativeFundReport:
    base = _report(iid, evidence=tuple(e for c in cas for e in c.evidence))
    from dataclasses import replace
    return replace(base, constituent_analyses=cas)


def test_report_md_appendix_renders_constituent_one_line_view() -> None:
    ev = _evidence("601899")
    cas = (_ca("601899", 8.5, evidence=(ev,), oneline="紫金矿业 营收 +20%"),)
    md = render_report_md("算力金属", (_report_with_constituents("A", cas),))
    block = md.split("## A ")[1]
    assert "601899 co-601899 (权重 8.5%): 紫金矿业 营收 +20%" in block
    assert f"[ref:{ev.citation_id}]" in block  # constituent refs present


def test_report_md_appendix_constituent_failure_only_no_oneline() -> None:
    cas = (_ca("000060", 3.0, evidence=(), failures=("no_filing",), oneline="X"),)
    md = render_report_md("算力金属", (_report_with_constituents("A", cas),))
    block = md.split("## A ")[1]
    assert "000060 co-000060 (权重 3.0%): ❌ no_filing" in block
    assert "X" not in block.split("证据明细")[0]  # no fabricated one_line_view


def test_report_md_passive_fund_has_no_constituent_block_but_has_footnotes() -> None:
    md = render_report_md("黄金", (_report("G", evidence=(_evidence("G"),)),))
    block = md.split("## G ")[1]
    assert "（权重" not in block  # no per-constituent bullets
    assert "证据明细" in block    # footnotes still render
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/narrative/test_report.py::test_report_md_appendix_renders_constituent_one_line_view -v`
Expected: FAIL — `_appendix_lines` stub returns `[]`.

- [ ] **Step 3: Implement the constituent appendix** — replace the Task-4 stub in `src/irc/narrative/report.py`:

```python
def _rank_constituents(cas: tuple) -> tuple:
    """weight_pct DESC, symbol ASC tiebreak (mirrors opportunity/report.py:131)."""
    return tuple(sorted(cas, key=lambda c: (-c.weight_pct, c.symbol)))


def _appendix_constituent_line(c) -> str:
    """Self-contained mirror of opportunity/report.py:289
    _format_appendix_constituent_line (5-shape precedence). NOT imported (RD-1)."""
    head = f"- {c.symbol} {c.name_cn} (权重 {c.weight_pct}%): "
    if c.audit_errors:
        return f"{head}⚠️ audit_error: {'; '.join(c.audit_errors)}"
    if c.evidence and c.failure_reasons:
        refs = " ".join(f"[ref:{e.citation_id}]" for e in select_citations(c.evidence, cap=3))
        return f"{head}{c.one_line_view} {refs} ({'; '.join(c.failure_reasons)})"
    if c.failure_reasons:
        return f"{head}❌ {'; '.join(c.failure_reasons)}"
    if c.evidence:
        refs = " ".join(f"[ref:{e.citation_id}]" for e in select_citations(c.evidence, cap=3))
        return f"{head}{c.one_line_view} {refs}"
    return f"{head}⚠️ audit_error: missing_constituent_record"


def _appendix_lines(r: NarrativeFundReport) -> list[str]:
    """Per-constituent prose block (active funds only; passive → empty, AC/Q8)."""
    if not r.constituent_analyses:
        return []
    return ["", "#### 持仓明细 / Holdings",
            *[_appendix_constituent_line(c) for c in _rank_constituents(r.constituent_analyses)]]
```

> The footnote section header (`### 证据明细`) already renders in Task 4 from the fund's full `thesis_evidence`; the constituent refs in `_appendix_constituent_line` are drawn from `c.evidence`, which is flattened into `r.thesis_evidence` upstream (RD-6) → every constituent ref resolves to a footnote. The constituent block is nested one level (`####`) under the appendix conceptually but rendered before the footnote table; that ordering is fixed and deterministic.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/narrative/test_report.py -k "appendix or constituent or passive" -v`
Expected: all pass.

- [ ] **Step 5: Re-run AC4 resolution test (constituent refs must resolve too)**

Run: `uv run pytest tests/narrative/test_report.py::test_report_md_every_inline_ref_resolves_to_footnote -v`
Expected: PASS. (If a constituent ref is NOT in `r.thesis_evidence` in a hand-built test fixture, the test fixture must flatten `c.evidence` into the report's `thesis_evidence` — `_report_with_constituents` already does this via the comprehension; production flattens upstream per RD-6.)

- [ ] **Step 6: Commit**

```bash
git add src/irc/narrative/report.py tests/narrative/test_report.py
git commit -m "feat(003): per-constituent appendix prose mirroring opportunity shape (AC3)"
```

---

## Task 6: M2 — product-quality drivers next to `质量={state}` (AC6, AC7)

**Files:**
- Modify: `src/irc/narrative/report.py` (new `_product_drivers_segment`, wire into the sub-state line in `render_report_md`)
- Test: `tests/narrative/test_report.py`

> The driver string is appended to the existing `- 子状态:` line (or an adjacent line). `None` → `—`. The renderer NEVER re-classifies (F-1). For a metadata-floored weak fund, all gating metrics render `—`, making the floor visible (AC7).

- [ ] **Step 1: Write the failing tests**

```python
from irc.narrative.schemas import ProductMetrics


def _report_pm(iid: str, pm: ProductMetrics, *, quality="weak") -> NarrativeFundReport:
    from dataclasses import replace
    base = _report(iid)
    return replace(base, product_quality_state=quality, product_metrics=pm)


def test_report_md_renders_product_drivers() -> None:
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8,
                        manager_tenure_years=7.0, tracking_error=0.002)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    assert "质量=weak" in block
    assert "费率=0.005" in block
    assert "规模=" in block       # aum formatted, not None
    assert "任职=7.0" in block
    assert "跟踪误差=0.002" in block


def test_report_md_none_metric_renders_em_dash() -> None:
    pm = ProductMetrics(expense_ratio=None, aum_cny=None,
                        manager_tenure_years=7.0, tracking_error=None)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    assert "费率=—" in block
    assert "规模=—" in block
    assert "任职=7.0" in block


def test_report_md_metadata_floored_weak_shows_all_em_dash() -> None:
    pm = ProductMetrics()  # all None — the metadata-thin floor case (RD-2)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    assert "质量=weak" in block
    assert "费率=— 规模=— 任职=—" in block  # visibly floored, not real signal


def test_report_md_genuine_weak_shows_real_numbers() -> None:
    pm = ProductMetrics(expense_ratio=0.02, aum_cny=1.0e7, manager_tenure_years=1.0)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    assert "—" not in block.split("质量=weak")[1].split("\n")[0]  # all real on the drivers line


def test_report_md_no_product_metrics_renders_em_dash_drivers() -> None:
    md = render_report_md("算力金属", (_report("A"),))  # product_metrics is None
    block = md.split("## A ")[1]
    assert "费率=—" in block  # None bundle → all em-dash, never crashes
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/narrative/test_report.py::test_report_md_renders_product_drivers -v`
Expected: FAIL — no `费率=` in output.

- [ ] **Step 3: Implement the driver segment** — `src/irc/narrative/report.py`:

```python
def _fmt_metric(v: float | None) -> str:
    """`—` for None (AC6); plain float otherwise. No locale/dict leak (ADR 0004)."""
    return "—" if v is None else f"{v}"


def _product_drivers_segment(pm) -> str:
    """M2 drivers next to 质量 (AC6/AC7). pm may be None (→ all —). Passive's
    tracking_error renders when present; — otherwise. Never re-classifies (F-1)."""
    expense = _fmt_metric(pm.expense_ratio if pm else None)
    aum = _fmt_metric(pm.aum_cny if pm else None)
    tenure = _fmt_metric(pm.manager_tenure_years if pm else None)
    track = _fmt_metric(pm.tracking_error if pm else None)
    return f"费率={expense} 规模={aum} 任职={tenure} 跟踪误差={track}"
```

Wire it into the sub-state line in `render_report_md` (append the drivers to the existing `子状态` line, after `质量={...}`):

```python
        lines.append(
            f"- 子状态: 估值={r.valuation_state} 热度={r.heat_state} "
            f"逻辑={r.thesis_state} 质量={r.product_quality_state} "
            f"｜ 产品驱动: {_product_drivers_segment(r.product_metrics)}"
        )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/narrative/test_report.py -k "driver or em_dash or floored or genuine_weak" -v`
Expected: all pass.

> If `test_report_md_genuine_weak_shows_real_numbers` flakes on `跟踪误差=—` (tenure-set active fund with no tracking_error), tighten the assertion to the three providable drivers (`费率/规模/任职`) rather than the whole line — passive `tracking_error` is legitimately `—` for an active fund. Adjust the test to slice only the `费率=…任职=…` span. The intent (AC7) is: genuine-weak shows real numbers on the *gating* drivers.

- [ ] **Step 5: Commit**

```bash
git add src/irc/narrative/report.py tests/narrative/test_report.py
git commit -m "feat(003): surface product-quality drivers next to 质量 with — for None (AC6/AC7)"
```

---

## Task 7: AC8 — `.json` stays the full source of truth (additive only)

**Files:**
- Modify: `src/irc/narrative/report.py` (`_report_dict`)
- Test: `tests/narrative/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
def test_report_json_includes_product_metrics_and_constituents() -> None:
    from dataclasses import replace
    ev = _evidence("601899")
    ca = ConstituentAnalysis(
        symbol="601899", name_cn="紫金矿业", weight_pct=8.5,
        evidence=(ev,), failure_reasons=(), one_line_view="紫金 +20%", audit_errors=(),
    )
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8,
                        manager_tenure_years=7.0, tracking_error=None)
    r = replace(_report("A", evidence=(ev,)), constituent_analyses=(ca,), product_metrics=pm)
    doc = json.loads(render_report_json("算力金属", (r,)))
    fund = doc["funds"][0]
    # additive — every existing key still present (round-trip AC8)
    assert fund["thesis_evidence"][0]["citation_id"] == ev.citation_id
    assert fund["product_metrics"]["expense_ratio"] == 0.005
    assert fund["product_metrics"]["tracking_error"] is None
    assert fund["constituent_analyses"][0]["symbol"] == "601899"
    assert fund["constituent_analyses"][0]["one_line_view"] == "紫金 +20%"


def test_report_json_two_calls_byte_identical() -> None:
    from dataclasses import replace
    ev = _evidence("A")
    pm = ProductMetrics(expense_ratio=0.005)
    r = replace(_report("A", evidence=(ev,)), product_metrics=pm)
    assert render_report_json("算力金属", (r,)) == render_report_json("算力金属", (r,))
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/narrative/test_report.py::test_report_json_includes_product_metrics_and_constituents -v`
Expected: FAIL — `KeyError: 'product_metrics'`.

- [ ] **Step 3: Extend `_report_dict` additively** — `src/irc/narrative/report.py`:

```python
def _product_metrics_dict(pm) -> dict | None:
    if pm is None:
        return None
    return {
        "expense_ratio": pm.expense_ratio,
        "aum_cny": pm.aum_cny,
        "manager_tenure_years": pm.manager_tenure_years,
        "tracking_error": pm.tracking_error,
    }


def _constituent_dict(c) -> dict:
    return {
        "symbol": c.symbol,
        "name_cn": c.name_cn,
        "weight_pct": c.weight_pct,
        "one_line_view": c.one_line_view,
        "failure_reasons": list(c.failure_reasons),
        "audit_errors": list(c.audit_errors),
        "evidence": [_evidence_dict(e) for e in c.evidence],
    }
```

Append to the dict returned by `_report_dict` (after `thesis_evidence`):

```python
        "thesis_evidence": [_evidence_dict(ev) for ev in r.thesis_evidence],
        "product_metrics": _product_metrics_dict(r.product_metrics),
        "constituent_analyses": [_constituent_dict(c) for c in r.constituent_analyses],
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/narrative/test_report.py -k "json" -v`
Expected: all pass (incl. the existing `test_report_json_round_trips_states_and_evidence`).

- [ ] **Step 5: Commit**

```bash
git add src/irc/narrative/report.py tests/narrative/test_report.py
git commit -m "feat(003): additively serialize product_metrics + constituent_analyses in .json (AC8)"
```

---

## Task 8: AC9/AC10/AC11 — full-suite verification + scorer-untouched proof

**Files:** none (verification only).

- [ ] **Step 1: AC9 — existing renderer tests pass unchanged**

Run: `uv run pytest tests/narrative/test_report.py -q`
Expected: all pass. Specifically confirm `test_report_md_emits_ref_from_thesis_evidence`, `test_report_md_renders_risk_and_action_fields`, `test_report_md_no_evidence_has_no_ref`, `test_report_json_round_trips_states_and_evidence`, `test_shortlist_*`, `test_diagnostics_*` are green.

- [ ] **Step 2: AC10 — SAME-3 + opportunity/memo determinism green**

Run:
```bash
uv run pytest tests/memo/test_same_3_invariant.py tests/memo/test_evidence_pool.py tests/opportunity -q
```
Expected: all pass — item 003 touched no SAME-3-bound surface (`_build_pick_rows` / `build_evidence_pool` / `_render_section`).

- [ ] **Step 3: AC11 — no scorer/state change**

> NOTE: items 001+002 are already merged into this feature branch, so a raw
> `main...HEAD` diff includes their files too. Scope AC11 to **item-003 commits
> only** — diff against the commit that was HEAD at the start of item 003
> (capture it in Task 0 as `git rev-parse HEAD`, call it `$ITEM003_BASE`).

Run:
```bash
git diff --name-only $ITEM003_BASE..HEAD
```
Expected: changed files are ONLY under `src/irc/narrative/` (`schemas.py`, `analyze.py`, `report.py`, optionally `report_appendix.py`), `tests/narrative/`, and `docs/2026-06-02-narrative-coverage-markdown/`. Assert NO file under `src/irc/opportunity/states.py`, `src/irc/fundamentals/types.py` (no `ThesisEvidence` change), `src/irc/narrative/risk.py`, or any classifier appears.

Also run the literal-grep guard to confirm no forbidden classifier edit slipped in:
```bash
git diff $ITEM003_BASE..HEAD -- src/irc/opportunity/states.py src/irc/narrative/risk.py | head
```
Expected: empty output.

- [ ] **Step 4: Scope run — full narrative suite + lint**

Run:
```bash
uv run pytest tests/narrative -q
uv run ruff check src tests
```
Expected: all pass; `All checks passed!`.

- [ ] **Step 5: Size-budget check**

Run:
```bash
wc -l src/irc/narrative/report.py src/irc/narrative/schemas.py src/irc/narrative/analyze.py
```
Expected: `report.py` < 200 lines. If it exceeds, extract the footnote/appendix helpers into `src/irc/narrative/report_appendix.py` (pure module, no I/O) and import them — note this in the commit. (Plan budgets for this: the helpers are self-contained pure functions.)

- [ ] **Step 6: Commit (if any refactor/extraction happened in Step 5)**

```bash
git add src/irc/narrative/
git commit -m "refactor(003): extract appendix/footnote helpers to keep report.py < 200 lines"
```

---

## Self-Review (run before handing off)

**Spec coverage:** AC1 (Task 3), AC2 (Task 3 + existing test), AC3 (Task 5), AC4 (Tasks 4+5), AC5 (Task 4), AC6 (Task 6), AC7 (Task 6), AC8 (Task 7), AC9 (Task 8 Step 1), AC10 (Task 8 Step 2), AC11 (Task 8 Step 3). All 11 mapped. M1 = Tasks 3-5; M2 = Task 6; threading = Tasks 1-2; JSON SoT = Task 7.

**Placeholder scan:** The only `...` placeholders are in Task 2's test fixtures (`OpportunityRow`/`OpportunityInput` builders) — explicitly flagged "read existing `tests/narrative/test_analyze.py` and reuse its builders verbatim." This is intentional: the real builder has ~20 required fields and must be copied from the live test module, not invented here. The Task-4 `_appendix_lines` stub is the only code stub, immediately superseded in Task 5.

**Type consistency:** `ProductMetrics` (4 fields) used identically in Task 1 (def), Task 2 (`_product_metrics_from_input`), Task 6 (`_product_drivers_segment`), Task 7 (`_product_metrics_dict`). `_appendix_lines(r)` signature is consistent between the Task-4 stub and Task-5 implementation. `_footnote_lines` / `_footnote_line` / `_appendix_constituent_line` / `_rank_constituents` names are stable across tasks.

**Determinism:** footnotes `sorted(by_id)` (citation_id asc, RD-4); constituents `_rank_constituents` (weight-desc, symbol-asc); no `set` iteration without a sort; no timestamps. AC5 two-call byte-equality test locks it.

**Spec-gap judgment calls (none blocking):**
1. *Section naming.* Spec offers `### 证据明细 / Evidence appendix` "(or equivalently-named)". I used `### 证据明细 / Evidence appendix` for the footnote table and a nested `#### 持仓明细 / Holdings` for the per-constituent prose, since the spec lists them as two sub-parts of the appendix (003-spec.md §M1.2). Tests assert on `证据明细` + the constituent head substring, not exact heading text, to stay robust.
2. *Driver label format.* Spec doesn't fix the exact `费率=/规模=/任职=/跟踪误差=` labels; I chose CN labels matching the existing `子状态:` line style. Tests assert these literals — change both together if a reviewer prefers different labels.
3. *`_fmt_metric` numeric format.* Spec says "formatted value" without a precision lock; I render the raw float (`f"{v}"`) to avoid inventing a rounding policy that could drift from the `.json`. AC6 only requires "not None, not 0" — raw float satisfies it and stays deterministic.
