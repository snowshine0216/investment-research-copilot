# Item 004 — Suppress action-triad / triggers / sub-states on `insufficient` narrative rows (H3 discipline) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On `position_risk_level == "insufficient"` narrative `.md` rows, suppress every earned-conclusion field (action triad, triggers, review cadence, AND the four sub-state verdicts) and emit a single bilingual "证据不足 / insufficient — refresh evidence" line, while keeping identity, gap-facts, the raw `产品驱动` numeric segment, and any partial evidence/appendix/footnotes. Sufficient rows are byte-identical to today's output. `.json` is unchanged.

**Architecture:** A single early branch inside `render_report_md`'s per-fund loop (`if r.position_risk_level == "insufficient":`). The disciplined insufficient block is a new pure helper `_insufficient_block(narrative, r)` in `report_appendix.py` (keeps `report.py` < 200 lines). The `产品驱动` raw-metrics segment is split onto its own line so it renders in BOTH branches (it currently rides the `子状态` line, which the insufficient branch suppresses). This mirrors the **H3 universal gapped-row invariant**'s conclusion-vs-fact split (`failure_renderer.py`) applied to a single-file surface as display discipline. `render_report_json` / `_report_dict` are untouched — `.json` stays the full source of truth (item 003 AC8).

**Tech Stack:** Python 3.12, frozen dataclasses, pure renderer functions, pytest, ruff. No new deps.

---

## Background — verified facts the engineer must not re-derive

- **Two ways an insufficient `NarrativeFundReport` is built** (`src/irc/narrative/analyze.py`):
  - `error_report` (line 31) — forces all four sub-states to `"evidence_insufficient"`, `opportunity_state="pause_wait"`, `dca_action="do_not_buy"`, `risk_action="review_required"`, `falsification_triggers=()`, `trim_triggers=()`, `review_cadence=""`, `evidence_gaps=(reason,)`.
  - `_report_from_card` (line 90) — calls `derive_position_risk_level` (`risk.py:60`: non-empty `evidence_gaps` ⇒ `"insufficient"`). The four sub-states come from the card via INDEPENDENT classifiers, so a row missing only ONE input (e.g. `missing_product_metadata`) can carry REAL verdicts like `valuation_state="expensive"`, `heat_state="overheated"`, `thesis_state="intact"` while still being `insufficient`. **This is why field-level suppression of the `子状态` line is required** — a renderer cannot statically tell a real `expensive` from `evidence_insufficient`, and value-conditional rendering is exactly what H3 rejects ("the renderer's signature is the enforcement mechanism"). See `004-spec.md` `## Resolved decisions` Q1.
- **H3 forbidden conclusion-field set** mirrored from `src/irc/opportunity/failure_renderer.py` (lines 6-9): `opportunity_state, dca, risk, note_cn, valuation_state, heat_state, thesis_state, product_quality_state, …`. The narrative SUPPRESS set is the action triad + triggers + cadence + the four sub-state verdicts. KEEP = `instrument_id, name_cn, position_risk_level, risk_rationale, risk_drivers, evidence_gaps`, the raw `product_metrics` (`产品驱动`) segment, and partial evidence/appendix/footnotes.
- **Renderer-only.** `risk.py`, `analyze.py`, the scorer, `classify_*`, `build_opportunity_row`, `_report_dict` / `render_report_json` are NON-GOALS. Do not touch them.
- **CONTEXT.md** already carries the authoritative glossary entry "Narrative `.md` insufficient-row display discipline (H3 analog)" (added by grill). No CONTEXT edit in this item.

### Current `render_report_md` per-fund block (`report.py:94-121`) — line inventory

```python
for r in reports:
    lines.append(f"## {r.instrument_id} {r.name_cn}")                                    # KEEP (identity, both branches)
    lines.append(f"- 仓位风险等级 / position_risk_level: **{r.position_risk_level}**")    # KEEP (gap-fact, both branches)
    lines.append(f"- 主因 / drivers: {', '.join(r.risk_drivers) or '—'}")                 # KEEP (gap-fact, both branches)
    lines.append(f"- 说明: {r.risk_rationale}")                                            # KEEP (gap-fact, both branches)
    lines.append(                                                                          # SUPPRESS on insufficient (action triad)
        f"- 机会 / dca / 风险: {r.opportunity_state} ｜ {r.dca_action} ｜ {r.risk_action}"
    )
    lines.append(                                                                          # 子状态 line: SUPPRESS on insufficient;
        f"- 子状态: 估值={r.valuation_state} 热度={r.heat_state} "                          #   the 产品驱动 segment currently RIDES this line —
        f"逻辑={r.thesis_state} 质量={r.product_quality_state} "                            #   it must be SPLIT to its own line (see Task 1)
        f"｜ 产品驱动: {_product_drivers_segment(r.product_metrics)}"
    )
    lines.append(f"- 复核节奏 / review_cadence: {r.review_cadence}")                       # SUPPRESS on insufficient (cadence)
    lines.append(f"- 证伪触发: {', '.join(r.falsification_triggers) or '—'}")             # SUPPRESS on insufficient (triggers)
    lines.append(f"- 减仓触发: {', '.join(r.trim_triggers) or '—'}")                      # SUPPRESS on insufficient (triggers)
    bullets = _evidence_bullets(r.thesis_evidence)                                         # KEEP (partial evidence, both branches)
    if bullets:
        lines.append("- 证据 / evidence:")
        lines.extend(bullets)
    appendix = _appendix_lines(r)                                                          # KEEP (持仓明细, both branches)
    lines.extend(appendix)
    footnotes = _footnote_lines(r)                                                         # KEEP (证据明细, both branches)
    if footnotes:
        lines.append("")
        lines.append("### 证据明细 / Evidence appendix")
        lines.extend(footnotes)
    lines.append("")
```

---

## File Structure

- **Modify** `src/irc/narrative/report.py`
  - Split the `产品驱动` segment off the `子状态` line into its own `- 产品驱动: …` line.
  - Add an early `if r.position_risk_level == "insufficient":` branch inside the per-fund loop. Insufficient ⇒ call the new helper for the verdict-bearing middle block; else ⇒ today's full middle block verbatim. Identity/gap-fact lines (above) and evidence/appendix/footnote lines (below) are shared by both branches.
- **Modify** `src/irc/narrative/report_appendix.py`
  - Add one pure helper `_insufficient_refresh_line(narrative: str, r: NarrativeFundReport) -> str` and one pure helper `_insufficient_middle(narrative: str, r: NarrativeFundReport) -> list[str]` (the verdict-suppressed middle: the standalone `产品驱动` line + the refresh line). Keeps `report.py` < 200 lines.
- **Modify** `tests/narrative/test_report.py`
  - Add insufficient-row tests (AC1-AC5, AC8, AC9), a golden sufficient-row byte-identity test (AC6), and the locked forbidden-token grep test (AC1/Q6). Existing sufficient-row tests stay green unchanged (AC6/AC10).

### Real signatures (quoted from the codebase, no placeholders)

```python
# report.py:89  (UNCHANGED signature)
def render_report_md(narrative: str, reports: tuple[NarrativeFundReport, ...]) -> str:

# report_appendix.py:71  (UNCHANGED — reused on both branches)
def _product_drivers_segment(pm) -> str:

# report_appendix.py NEW
def _insufficient_refresh_line(narrative: str, r: NarrativeFundReport) -> str:
def _insufficient_middle(narrative: str, r: NarrativeFundReport) -> list[str]:
```

### AC → test mapping (10 ACs)

| AC | Test(s) |
|---|---|
| AC1 — no triad **and no sub-state verdict line / token** (locked grep) | `test_insufficient_row_suppresses_triad_and_substates`, `test_insufficient_block_forbidden_tokens_locked` |
| AC2 — no triggers, no cadence | `test_insufficient_row_suppresses_triggers_and_cadence` |
| AC3 — renders the refresh-evidence line naming a gap + `--analyze` | `test_insufficient_row_renders_refresh_line` |
| AC4 — KEEPS gap-facts + standalone `产品驱动` line | `test_insufficient_row_keeps_gap_facts_and_product_drivers_line` |
| AC5 — KEEPS partial evidence / appendix / footnotes; refs resolve | `test_insufficient_row_keeps_partial_evidence_and_refs_resolve` |
| AC6 — sufficient row byte-identical to pre-004 (golden) | `test_sufficient_row_block_byte_identical_golden` + existing `test_report_md_renders_risk_and_action_fields` stays green |
| AC7 — `.json` unchanged | `test_insufficient_row_json_still_carries_conclusions` |
| AC8 — determinism | `test_insufficient_row_render_is_deterministic` |
| AC9 — mixed report branches per-row | `test_mixed_report_branches_per_row` |
| AC10 — tests + lint green; pre-existing insufficient-shape tests updated | final scope-run; **no existing test asserts triad/sub-states on an insufficient row** (`_report()` defaults to `level="elevated"`), so nothing to update — Task 5 documents the verification |

**Existing tests that need updating:** NONE. Verified: the only render test touching tokens is `test_report_md_renders_risk_and_action_fields` (line 99) which uses `level="elevated"` (a SUFFICIENT row) and stays green. All other render tests use `_report(...)` (default `elevated`) or assert only evidence/footnote/product-driver shapes that are KEPT on both branches. The `产品驱动` split (Task 1) changes WHERE the segment renders, not WHETHER — Task 1 confirms the existing `test_report_md_renders_product_drivers` / `test_report_md_none_metric_renders_em_dash` / `test_report_md_metadata_floored_weak_shows_all_em_dash` / `test_report_md_genuine_weak_shows_real_numbers` / `test_report_md_no_product_metrics_renders_em_dash_drivers` still pass because they assert substrings (`费率=…`, `质量=weak`) that survive on the (sufficient) row regardless of line layout. `test_report_md_genuine_weak_shows_real_numbers` splits on `"质量=weak"` then takes the rest of THAT line — it must stay green after the split; Task 1 Step 4 verifies it explicitly.

---

## Task 1: Split the `产品驱动` segment onto its own line (refactor, both branches)

Splitting first (before the branch) keeps the diff legible: the standalone `产品驱动` line is what survives suppression. This is a pure layout refactor for sufficient rows — substring assertions in existing product-driver tests still hold.

**Files:**
- Modify: `src/irc/narrative/report.py:102-106`
- Test: `tests/narrative/test_report.py`

- [ ] **Step 1: Write the failing test — 产品驱动 is on its own line**

Add to `tests/narrative/test_report.py` (after `test_report_md_renders_product_drivers`, ~line 269):

```python
def test_report_md_product_drivers_on_own_line() -> None:
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8,
                        manager_tenure_years=7.0, tracking_error=0.002)
    md = render_report_md("算力金属", (_report_pm("A", pm),))
    block = md.split("## A ")[1]
    # 产品驱动 must be a standalone bullet, NOT riding the 子状态 line.
    drivers_lines = [ln for ln in block.splitlines() if ln.startswith("- 产品驱动:")]
    assert len(drivers_lines) == 1
    assert "费率=0.005" in drivers_lines[0]
    substate_lines = [ln for ln in block.splitlines() if ln.startswith("- 子状态:")]
    assert len(substate_lines) == 1
    assert "产品驱动" not in substate_lines[0]  # decoupled (grill Q2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/narrative/test_report.py::test_report_md_product_drivers_on_own_line -v`
Expected: FAIL — `产品驱动` currently rides the `子状态` line (`assert "产品驱动" not in substate_lines[0]` fails).

- [ ] **Step 3: Implement — split the line**

In `src/irc/narrative/report.py`, replace the `子状态` block (lines 102-106):

```python
        lines.append(
            f"- 子状态: 估值={r.valuation_state} 热度={r.heat_state} "
            f"逻辑={r.thesis_state} 质量={r.product_quality_state} "
            f"｜ 产品驱动: {_product_drivers_segment(r.product_metrics)}"
        )
```

with:

```python
        lines.append(
            f"- 子状态: 估值={r.valuation_state} 热度={r.heat_state} "
            f"逻辑={r.thesis_state} 质量={r.product_quality_state}"
        )
        lines.append(f"- 产品驱动: {_product_drivers_segment(r.product_metrics)}")
```

- [ ] **Step 4: Run product-driver tests to verify all pass**

Run: `uv run pytest tests/narrative/test_report.py -k "product or drivers or metric or weak" -v`
Expected: PASS — `test_report_md_product_drivers_on_own_line` plus the five existing product-driver tests (`test_report_md_renders_product_drivers`, `test_report_md_none_metric_renders_em_dash`, `test_report_md_metadata_floored_weak_shows_all_em_dash`, `test_report_md_genuine_weak_shows_real_numbers`, `test_report_md_no_product_metrics_renders_em_dash_drivers`). `test_report_md_genuine_weak_shows_real_numbers` splits on `"质量=weak"` and reads the rest of that (now `子状态`-only) line — it must not contain `费率=—`; the line no longer contains `费率=` at all, so the negative assertions hold.

- [ ] **Step 5: Commit**

```bash
git add src/irc/narrative/report.py tests/narrative/test_report.py
git commit -m "refactor(004): split 产品驱动 onto its own line (survives 子状态 suppression)"
```

---

## Task 2: Add the insufficient-block helpers in `report_appendix.py` (refresh line + middle)

**Files:**
- Modify: `src/irc/narrative/report_appendix.py`
- Test: `tests/narrative/test_report.py`

- [ ] **Step 1: Write the failing test — the refresh line + the middle block**

Add to `tests/narrative/test_report.py` (after the product-driver tests). First add a helper and the unit tests for the new helpers:

```python
from irc.narrative.report_appendix import (
    _insufficient_middle,
    _insufficient_refresh_line,
)


def _report_insufficient(iid: str, *, gaps=("missing_product_metadata",),
                         evidence: tuple[ThesisEvidence, ...] = (),
                         pm: ProductMetrics | None = None) -> NarrativeFundReport:
    """An insufficient row that — like the _report_from_card path — carries REAL
    sub-state verdicts (not all evidence_insufficient), to prove field-level
    suppression (grill Q1)."""
    base = _report(iid, level="insufficient", evidence=evidence)
    return replace(
        base,
        risk_rationale="evidence_gaps present — risk cannot be assessed",
        risk_drivers=("evidence_gaps",),
        evidence_gaps=gaps,
        product_metrics=pm,
    )


def test_insufficient_refresh_line_names_gap_and_analyze() -> None:
    r = _report_insufficient("A", gaps=("missing_valuation_data", "missing_product_metadata"))
    line = _insufficient_refresh_line("算力金属", r)
    assert line.startswith("- ⚠️ 证据不足 / insufficient")
    assert "missing_valuation_data" in line
    assert "missing_product_metadata" in line
    assert "uv run irc narrative 算力金属 --analyze" in line


def test_insufficient_refresh_line_falls_back_to_rationale_then_literal() -> None:
    r_no_gaps = replace(_report_insufficient("A"), evidence_gaps=(),
                        risk_rationale="some why")
    assert "some why" in _insufficient_refresh_line("算力金属", r_no_gaps)
    r_empty = replace(_report_insufficient("A"), evidence_gaps=(), risk_rationale="")
    assert "evidence_insufficient" in _insufficient_refresh_line("算力金属", r_empty)


def test_insufficient_middle_has_product_drivers_and_refresh_no_substate() -> None:
    pm = ProductMetrics(expense_ratio=0.005)
    mid = _insufficient_middle("算力金属", _report_insufficient("A", pm=pm))
    text = "\n".join(mid)
    assert "- 产品驱动: " in text
    assert "费率=0.005" in text
    assert "⚠️ 证据不足 / insufficient" in text
    assert "子状态" not in text     # no sub-state line
    assert "机会 / dca / 风险" not in text  # no triad
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_report.py -k "insufficient_refresh or insufficient_middle" -v`
Expected: FAIL — `ImportError: cannot import name '_insufficient_middle'` / `_insufficient_refresh_line`.

- [ ] **Step 3: Implement the two helpers in `report_appendix.py`**

Append to `src/irc/narrative/report_appendix.py`:

```python
def _insufficient_refresh_line(narrative: str, r: NarrativeFundReport) -> str:
    """H3 analog: the single bilingual refresh line that REPLACES the suppressed
    triad/triggers/cadence on an insufficient row. Names evidence_gaps (mirrors
    failure_renderer.py's `原因: {gaps}`), points at the real refresh path
    (`--analyze`, NOT `fundamentals snapshot`). Deterministic — evidence_gaps is a
    stable tuple, risk_rationale a str, narrative an arg; no I/O.

    On both production insufficient paths evidence_gaps is non-empty (error_report
    sets `(reason,)`; _report_from_card reaches insufficient only via non-empty
    view.evidence_gaps), so the fallbacks are defensive-unreachable (grill Q3)."""
    gaps = ", ".join(r.evidence_gaps) or r.risk_rationale or "evidence_insufficient"
    return (
        f"- ⚠️ 证据不足 / insufficient — 行动建议已抑制 (未形成结论)；"
        f"缺口: {gaps}；刷新: `uv run irc narrative {narrative} --analyze`"
    )


def _insufficient_middle(narrative: str, r: NarrativeFundReport) -> list[str]:
    """The verdict-suppressed middle block for an insufficient row: the raw
    产品驱动 numeric segment (a gap-fact, KEEP — grill Q2) on its own line, then
    the refresh line. NO 子状态 line, NO 机会/dca/风险 triad, NO triggers, NO
    review_cadence (all H3-forbidden conclusions — grill Q1)."""
    return [
        f"- 产品驱动: {_product_drivers_segment(r.product_metrics)}",
        _insufficient_refresh_line(narrative, r),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_report.py -k "insufficient_refresh or insufficient_middle" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/narrative/report_appendix.py tests/narrative/test_report.py
git commit -m "feat(004): add insufficient-row refresh line + verdict-suppressed middle helpers"
```

---

## Task 3: Branch `render_report_md` per-fund on `insufficient` (wire the suppression)

**Files:**
- Modify: `src/irc/narrative/report.py` (per-fund loop) + its `report_appendix` import block (lines 6-11)
- Test: `tests/narrative/test_report.py`

- [ ] **Step 1: Write the failing tests — AC1, AC2, AC3, AC4, AC5, AC9**

Add to `tests/narrative/test_report.py`. (The `_report_insufficient` helper + the two helper-import lines from Task 2 are already present.)

```python
_FORBIDDEN_INSUFFICIENT_TOKENS = (
    # action triad
    "机会 / dca / 风险", "small_watch", "pause_wait", "slow_dca", "do_not_buy",
    "trim_review", "review_required",
    # triggers + cadence markers
    "证伪触发", "减仓触发", "复核节奏",
    # sub-state line marker + sub-state verdict tokens (grill Q1/Q6)
    "子状态",
    "expensive", "very_expensive", "overheated", "crowded", "under_pressure",
    "falsified", "weak", "poor", "intact", "cheap", "acceptable",
    "evidence_insufficient",
)


def test_insufficient_row_suppresses_triad_and_substates() -> None:
    r = _report_insufficient("A")  # carries real verdicts via _report (very_expensive/overheated/intact)
    md = render_report_md("算力金属", (r,))
    block = md.split("## A ")[1]
    assert "机会 / dca / 风险" not in block
    assert "子状态" not in block
    for tok in ("small_watch", "slow_dca", "trim_review",
                "very_expensive", "overheated", "intact", "acceptable"):
        assert tok not in block, f"forbidden verdict token leaked: {tok}"


def test_insufficient_block_forbidden_tokens_locked() -> None:
    """Locked grep — the enforcement mechanism (grill Q6, mirrors
    failure_renderer.py criterion 18). No triad/trigger/cadence/sub-state-verdict
    token survives on an insufficient block."""
    r = _report_insufficient("A")
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    for tok in _FORBIDDEN_INSUFFICIENT_TOKENS:
        assert tok not in block, f"forbidden token survived insufficient block: {tok}"


def test_insufficient_row_suppresses_triggers_and_cadence() -> None:
    block = render_report_md("算力金属", (_report_insufficient("A"),)).split("## A ")[1]
    assert "证伪触发" not in block
    assert "减仓触发" not in block
    assert "复核节奏" not in block


def test_insufficient_row_renders_refresh_line() -> None:
    r = _report_insufficient("A", gaps=("missing_product_metadata",))
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    assert "⚠️ 证据不足 / insufficient" in block
    assert "missing_product_metadata" in block
    assert "uv run irc narrative 算力金属 --analyze" in block


def test_insufficient_row_keeps_gap_facts_and_product_drivers_line() -> None:
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8)
    r = _report_insufficient("A", pm=pm)
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    assert "position_risk_level: **insufficient**" in block
    assert "主因 / drivers: evidence_gaps" in block
    assert "说明: evidence_gaps present — risk cannot be assessed" in block
    drivers_lines = [ln for ln in block.splitlines() if ln.startswith("- 产品驱动:")]
    assert len(drivers_lines) == 1
    assert "费率=0.005" in drivers_lines[0]


def test_insufficient_row_keeps_partial_evidence_and_refs_resolve() -> None:
    r = _report_insufficient("A", evidence=_multi("A"))
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    assert "证据明细" in block  # footnote table still renders
    inline_ids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", block))
    assert inline_ids, "partial evidence should still render inline refs"
    for cid in inline_ids:
        footnote = [ln for ln in block.splitlines() if ln.startswith(f"[ref:{cid}]")]
        assert len(footnote) == 1, f"{cid} resolved {len(footnote)} times"


def test_mixed_report_branches_per_row() -> None:
    suff = _report("S", evidence=(_evidence("S"),))            # elevated → full
    insf = _report_insufficient("I", gaps=("missing_product_metadata",))
    md = render_report_md("算力金属", (insf, suff))
    insf_block = md.split("## I ")[1].split("## S ")[0]
    suff_block = md.split("## S ")[1]
    # insufficient: suppressed
    assert "机会 / dca / 风险" not in insf_block
    assert "⚠️ 证据不足 / insufficient" in insf_block
    # sufficient: full triad + cadence + triggers
    assert "机会 / dca / 风险:" in suff_block
    assert "复核节奏" in suff_block
    assert "证伪触发" in suff_block
    assert "⚠️ 证据不足" not in suff_block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_report.py -k "insufficient_row or forbidden_tokens or mixed_report" -v`
Expected: FAIL — today the insufficient row still renders the triad / 子状态 / triggers / cadence (no branch yet).

- [ ] **Step 3: Implement the per-fund branch in `report.py`**

First extend the existing import block (`report.py:6-11`) to pull in `_insufficient_middle`:

```python
from irc.narrative.report_appendix import (
    _appendix_lines,
    _footnote_lines,
    _insufficient_middle,
    _product_drivers_segment,
    _safe_summary,
)
```

Then replace the middle of the per-fund loop. The current block (`report.py:99-109`):

```python
        lines.append(
            f"- 机会 / dca / 风险: {r.opportunity_state} ｜ {r.dca_action} ｜ {r.risk_action}"
        )
        lines.append(
            f"- 子状态: 估值={r.valuation_state} 热度={r.heat_state} "
            f"逻辑={r.thesis_state} 质量={r.product_quality_state}"
        )
        lines.append(f"- 产品驱动: {_product_drivers_segment(r.product_metrics)}")
        lines.append(f"- 复核节奏 / review_cadence: {r.review_cadence}")
        lines.append(f"- 证伪触发: {', '.join(r.falsification_triggers) or '—'}")
        lines.append(f"- 减仓触发: {', '.join(r.trim_triggers) or '—'}")
```

becomes:

```python
        if r.position_risk_level == "insufficient":
            lines.extend(_insufficient_middle(narrative, r))
        else:
            lines.append(
                f"- 机会 / dca / 风险: {r.opportunity_state} ｜ {r.dca_action} ｜ {r.risk_action}"
            )
            lines.append(
                f"- 子状态: 估值={r.valuation_state} 热度={r.heat_state} "
                f"逻辑={r.thesis_state} 质量={r.product_quality_state}"
            )
            lines.append(f"- 产品驱动: {_product_drivers_segment(r.product_metrics)}")
            lines.append(f"- 复核节奏 / review_cadence: {r.review_cadence}")
            lines.append(f"- 证伪触发: {', '.join(r.falsification_triggers) or '—'}")
            lines.append(f"- 减仓触发: {', '.join(r.trim_triggers) or '—'}")
```

Note: the identity/gap-fact lines (`##`, `仓位风险等级`, `主因`, `说明`) above this block and the evidence/appendix/footnote lines below it are SHARED by both branches and stay exactly as-is.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/narrative/test_report.py -k "insufficient_row or forbidden_tokens or mixed_report" -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Check `report.py` stays under the size budget**

Run: `wc -l src/irc/narrative/report.py`
Expected: < 200 lines (was 188; +6 net for the branch — confirm the helper extraction kept it under).

- [ ] **Step 6: Commit**

```bash
git add src/irc/narrative/report.py tests/narrative/test_report.py
git commit -m "feat(004): branch render_report_md to suppress conclusions on insufficient rows"
```

---

## Task 4: Lock determinism + sufficient-row golden + `.json` unchanged (AC6, AC7, AC8)

**Files:**
- Test: `tests/narrative/test_report.py`

- [ ] **Step 1: Write the failing tests — AC8 determinism, AC6 sufficient golden, AC7 .json**

```python
def test_insufficient_row_render_is_deterministic() -> None:
    r = _report_insufficient("A", evidence=_multi("A"),
                            pm=ProductMetrics(expense_ratio=0.005))
    reports = (r,)
    assert render_report_md("算力金属", reports) == render_report_md("算力金属", reports)


def test_sufficient_row_block_byte_identical_golden() -> None:
    """AC6: a sufficient (elevated) row's middle block is byte-identical to the
    pre-004 shape — full triad, 子状态, 产品驱动, cadence, both triggers."""
    pm = ProductMetrics(expense_ratio=0.005, aum_cny=5.0e8,
                        manager_tenure_years=7.0, tracking_error=0.002)
    r = replace(_report("A", level="elevated"), product_metrics=pm)
    block = render_report_md("算力金属", (r,)).split("## A ")[1]
    expected_middle = (
        "- 仓位风险等级 / position_risk_level: **elevated**\n"
        "- 主因 / drivers: valuation_state\n"
        "- 说明: elevated — very_expensive valuation\n"
        "- 机会 / dca / 风险: small_watch ｜ slow_dca ｜ trim_review\n"
        "- 子状态: 估值=very_expensive 热度=overheated 逻辑=intact 质量=acceptable\n"
        "- 产品驱动: 费率=0.005 规模=500000000.0 任职=7.0 跟踪误差=0.002\n"
        "- 复核节奏 / review_cadence: weekly_light_monthly_full\n"
        "- 证伪触发: theme thesis moves to falsified\n"
        "- 减仓触发: valuation_state in [expensive, very_expensive]\n"
    )
    assert expected_middle in block


def test_insufficient_row_json_still_carries_conclusions() -> None:
    """AC7: .md suppression is display-only; .json keeps the full real values."""
    r = _report_insufficient("A", gaps=("missing_product_metadata",))
    fund = json.loads(render_report_json("算力金属", (r,)))["funds"][0]
    assert fund["opportunity_state"] == "small_watch"
    assert fund["dca_action"] == "slow_dca"
    assert fund["risk_action"] == "trim_review"
    assert fund["valuation_state"] == "very_expensive"
    assert fund["thesis_state"] == "intact"
    assert fund["review_cadence"] == "weekly_light_monthly_full"
    assert fund["falsification_triggers"] == ["theme thesis moves to falsified"]
    assert fund["evidence_gaps"] == ["missing_product_metadata"]
```

> Note on the golden: the `规模=500000000.0` token reflects `_fmt_metric`'s plain `f"{v}"` rendering of `5.0e8` (verify by reading `report_appendix.py:66-68` — `_fmt_metric` returns `f"{v}"`). If the actual float repr differs, run the test once, copy the real `- 产品驱动:` line from the failure diff into `expected_middle`, and re-run. The point of the golden is byte-identity vs. the live renderer, not a hand-guessed float format.

- [ ] **Step 2: Run tests to verify they fail/pass appropriately**

Run: `uv run pytest tests/narrative/test_report.py -k "deterministic or byte_identical_golden or json_still_carries" -v`
Expected: `json_still_carries` and `deterministic` PASS immediately (no code change needed — `.json` untouched, branch is pure). `byte_identical_golden` PASS if the float repr matches; if it FAILS only on the `产品驱动` float format, fix `expected_middle` per the note and re-run (this is the golden-capture step, not an implementation gap).

- [ ] **Step 3: (only if golden float mismatch) capture the real product-drivers line and re-run**

Copy the actual `- 产品驱动: …` line from the pytest assertion diff into `expected_middle`.
Run: `uv run pytest tests/narrative/test_report.py::test_sufficient_row_block_byte_identical_golden -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/narrative/test_report.py
git commit -m "test(004): lock determinism, sufficient-row golden, and .json-unchanged invariants"
```

---

## Task 5: Verify existing tests + full scope-run + lint (AC10)

**Files:** none (verification only).

- [ ] **Step 1: Confirm no existing test asserted triad/sub-states on an insufficient row**

Run: `grep -n "insufficient" tests/narrative/test_report.py`
Expected: only the NEW `_report_insufficient` helper and the new insufficient tests appear; no pre-existing test constructs an insufficient row and asserts a triad/trigger/cadence/sub-state token. (Verified at plan time: `_report()` defaults to `level="elevated"`.) If any pre-existing test is found asserting the old insufficient shape, update it to the suppressed shape per AC1-AC4 — none is expected.

- [ ] **Step 2: Run the full narrative test scope**

Run: `uv run pytest tests/narrative -q`
Expected: PASS — all existing narrative tests plus the ~13 new item-004 tests green.

- [ ] **Step 3: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!` (line-length 100, py312). If the new helper or test lines exceed 100 cols, wrap them.

- [ ] **Step 4: Final commit (if Step 3 required any wrap fixes)**

```bash
git add src/irc/narrative tests/narrative/test_report.py
git commit -m "chore(004): lint fixes for narrative insufficient-row suppression"
```

---

## Verification points (run after each task, mandatory before claiming done)

- After Task 1: `uv run pytest tests/narrative/test_report.py -k "product or drivers or metric or weak" -v` → all green (layout split is transparent to substring assertions).
- After Task 2: `uv run pytest tests/narrative/test_report.py -k "insufficient_refresh or insufficient_middle" -v` → 3 green.
- After Task 3: `uv run pytest tests/narrative/test_report.py -k "insufficient_row or forbidden_tokens or mixed_report" -v` → 7 green; `wc -l src/irc/narrative/report.py` < 200.
- After Task 4: `uv run pytest tests/narrative/test_report.py -k "deterministic or byte_identical_golden or json_still_carries" -v` → 3 green.
- **Final scope-run (AC10):** `uv run pytest tests/narrative` AND `uv run ruff check src tests` → both green.

## Constraints recap (do not violate)

- **Renderer-only.** Do NOT edit `risk.py`, `analyze.py`, the scorer, `classify_*`, `build_opportunity_row`, `_report_dict`, or `render_report_json`.
- **H3 conclusion-vs-fact discipline.** SUPPRESS = triad + triggers + cadence + the four sub-state verdicts (field-level, NOT value-conditional). KEEP = identity + gap-facts + raw `产品驱动` + partial evidence.
- **`.json` is the full source of truth** (item 003 AC8) — `.md`-only suppression.
- **ADR 0004 determinism** — pure helpers, no I/O, no unsorted iteration; two calls byte-identical.
- **Frozen dataclasses, no mutation, no module state.** Files < 200 lines, functions < 20 lines.
