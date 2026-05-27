# Item 003 — QDII premium snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the memo-rendering loop on the existing `scoring.json::qdii_premium_pct` field — add a `溢价` column to the §5 picks-table (12 → 13 columns), replace the §6 "数据未采集" placeholder with a deterministic `IRC_QDII_PREMIUM_BEGIN/END` marker block listing per-row premium with threshold disclosure, prefix the §7 trigger lines for above-threshold QDII picks with `⛔ qdii_premium_too_high(...)｜`, and emit a top-level `outputs/<date>/qdii_premium.json` projection artefact.

**Architecture:** A new pure module `src/irc/memo/qdii_premium_lines.py` defines (a) `QDII_PREMIUM_THRESHOLD_PCT` re-export bound to `QDII_MAX_PREMIUM_DEFAULT`, (b) the `IRC_QDII_PREMIUM_BEGIN/END` marker constants, (c) the `_format_qdii_premium_cell(pick)` cell helper consumed by `picks_table.render_picks_table`, (d) `build_qdii_premium_projection(pick_rows, score_rows, *, evidence_cutoff, now_fn)` producing the sorted-by-iid `dict` that becomes both the §6 marker block input and the `qdii_premium.json` payload, (e) `render_qdii_premium_block(projection)` returning the marker-wrapped multi-line string, (f) `format_qdii_premium_prefix(row)` returning the §7 prefix string, and (g) `write_qdii_premium_snapshot(projection, *, out_dir)` (the I/O edge). `PickRow` gains one optional `qdii_premium_pct: float | None = None` field. `compose_fx_qdii_lines` in `diagnostics.py` gains optional kwargs `qdii_premium_rows` + `evidence_cutoff` and swaps element [1] of its 3-tuple from the legacy placeholder to the rendered marker block when supplied. `commands/memo_cmd.py` is the dependency-injection edge: builds the projection from in-scope `pick_rows + scoring` and threads it into `compose_fx_qdii_lines`, `_compose_execution_lines` (§7 prefix), and `write_qdii_premium_snapshot`. The synthesizer prompt gains a 7th verbatim-lock clause.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest, uv, `irc.io_utils.atomic_write_text`. Pure functions only; I/O stays at the CLI/edge.

**Project constraints (from CLAUDE.md + CONTEXT.md + 003-spec.md + ADR 0006):**
- **TDD mandatory**: red → green → refactor. Tests written **before** production code.
- **Functional / immutable**: tuples, `dataclass(frozen=True)`, no mutation of `PickRow`/`OpportunityRow`/scoring dicts.
- **Files < 200 lines; functions < 20 lines (ideal)**. `qdii_premium_lines.py` budget: < 200 lines. `picks_table.py` (253 lines, established) gains ≤ 20 lines. `commands/memo_cmd.py` (1073 lines, established violation per item 001 precedent) gains ~15 lines for the projection helper + threading.
- **Determinism / two-run byte equality (AC14)**: rows sorted by `instrument_id` ASC; `generated_at` from injected `now_fn`; `evidence_cutoff` from existing `extract_evidence_cutoff` (NOT a wall-clock read).
- **Module import contract** (per ADR 0006 + spec): `qdii_premium_lines.py` imports from `irc.schemas.discovery` (for `QDII_MAX_PREMIUM_DEFAULT`) and stdlib only. NO imports from `irc.opportunity.*`, `irc.scoring.*`, `irc.commands.*`. `picks_table.py` imports the cell helper; `diagnostics.py` imports the marker constants + block renderer; `commands/memo_cmd.py` is the only edge wiring them together.
- **TFM not a fetcher**: the existing `fetch_qdii_premium_pct` is NOT touched. This item reads `qdii_premium_pct` off `scoring.json` rows already in memory.
- **6 existing `IRC_*_BEGIN/END` marker pairs** (verified via grep + per item 002 plan): `IRC_PICKS_TABLE_*`, `IRC_EVIDENCE_GAP_*`, `IRC_EXECUTION_LINES_*`, `IRC_MACRO_LINES_*`, `IRC_GOLD_EVIDENCE_*`, `IRC_CONCENTRATION_*`. `IRC_QDII_PREMIUM_*` becomes the 7th. `memo/auditor.py` is an LLM content reviewer with no structural-marker awareness — do NOT touch it.
- **`QDII_PREMIUM_THRESHOLD_PCT` is RATIO units (0.05 = 5%)**, identical to `QDII_MAX_PREMIUM_DEFAULT`. Display uses `*100:.0f%`.
- **§7 prefix separator is `｜` (full-width U+FF5C)** to distinguish from the existing `|` (half-width) bullet separators.
- **Off-exchange cell format**: `0.00%（场外申赎）` literal (full-width parens). NOT `—`.
- **Citation ID format** `\[ref:[0-9a-f]{16}\]` unchanged; the new column + marker block emit no `[ref:...]` markers.
- **Do NOT introduce `qdii_premium_high`** — `qdii_premium_too_high` is canonical. Do NOT push.

---

## File Structure

**New files:**
- `src/irc/memo/qdii_premium_lines.py` — pure module: marker constants, threshold re-export, cell helper, projection builder, block renderer, §7 prefix helper, JSON writer (≤ 180 lines).
- `tests/memo/test_qdii_premium_lines.py` — pure-logic tests for everything in the new module + integration assertions.

**Modified files:**
- `src/irc/memo/picks_table.py` — extend `PickRow` with `qdii_premium_pct: float | None = None`; insert `溢价` column between `单次定投上限` and `触发状态` in `render_picks_table`; append the 溢价 explainer sentence to `_SCORING_FOOTNOTE`.
- `src/irc/memo/diagnostics.py` — extend `compose_fx_qdii_lines` signature with optional `qdii_premium_rows`/`evidence_cutoff` kwargs; replace element [1] of the returned tuple with the marker block when non-empty.
- `src/irc/memo/synthesizer.py` — append the 7th `if "<!-- IRC_QDII_PREMIUM_BEGIN -->" in skeleton:` clause to the locked-section instruction list.
- `src/irc/commands/memo_cmd.py` — populate `PickRow.qdii_premium_pct` in `_build_pick_rows`; build the projection once at the §6 + §7 dependency-injection edge; thread it into `compose_fx_qdii_lines` + `_compose_execution_lines` (§7 prefix); call `write_qdii_premium_snapshot` always (per AC G-Q5).
- `tests/memo/test_picks_table.py` — migrate `test_picks_table_header_contains_tranche_cap_and_trigger_status_columns` from 3-link to 4-link chain (`单次定投上限 → 溢价 → 触发状态 → 证据`); add AC1/AC2/AC3/AC4/AC12 tests.
- `tests/memo/test_diagnostics_fx_qdii.py` — add AC7/AC8 tests for the new kwargs and marker-block element [1].
- `tests/memo/test_template.py` — add AC10 test confirming `_render_execution_section` is feed-through (no premium awareness).
- `tests/commands/test_memo_cmd.py` — add AC9/AC13 integration tests (§7 prefix wired; no `qdii_premium_high` token leak).

**Not modified (cross-check):**
- `src/irc/scoring/qdii_premium.py` — routing helper untouched (provides `qdii_premium_pct` already).
- `src/irc/decision/gates.py` — `qdii_premium_too_high` reused verbatim.
- `src/irc/memo/template.py` — `_render_execution_section` stays a pure shape renderer per AC10.
- `src/irc/opportunity/types.py` — `OpportunityRow` shape unchanged (AC15).
- `src/irc/memo/auditor.py` — not a structural gate.
- `tests/integration/test_publishable_set_lockdown.py` — absorbs the column-add via two-run byte-equality automatically (per AC11 strikethrough + G-Q1).

---

## Task 1: Bootstrap `qdii_premium_lines.py` module — marker constants + threshold re-export

> **Amendment (2026-05-27 drift review — D1):** Tasks 1–7 were submitted as a single commit
> (`28eabba feat(003): bootstrap qdii_premium_lines`) and tasks 10–13 as a single commit
> (`23ba912 feat(003): wire qdii_premium_pct + projection + §7 prefix + artefact write`).
> Per-task commit granularity is scaffolding guidance only; AC coverage is fully preserved.
> Plan amended to note the consolidated delivery.

**Files:**
- Create: `src/irc/memo/qdii_premium_lines.py`
- Test: `tests/memo/test_qdii_premium_lines.py`

- [ ] **Step 1: Write the failing test for module-level constants (AC5).**

Create `tests/memo/test_qdii_premium_lines.py`:

```python
"""Pure-logic tests for src/irc/memo/qdii_premium_lines.py (item 003).

Covers AC1–AC18 of docs/2026-05-27-instrument-pickability/items/003-spec.md
and the four decisions locked in docs/adr/0006-qdii-premium-memo-surface.md.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT


def test_threshold_is_alias_of_decision_gate_default() -> None:
    """AC5: QDII_PREMIUM_THRESHOLD_PCT must be the SAME object/value as
    QDII_MAX_PREMIUM_DEFAULT so the memo display can never drift from
    the decision-gate value."""
    from irc.memo.qdii_premium_lines import QDII_PREMIUM_THRESHOLD_PCT

    assert QDII_PREMIUM_THRESHOLD_PCT == QDII_MAX_PREMIUM_DEFAULT
    assert QDII_PREMIUM_THRESHOLD_PCT == 0.05


def test_marker_constants_match_existing_convention() -> None:
    """Mirror IRC_CONCENTRATION_BEGIN/END and the rest of the
    `<!-- IRC_*_BEGIN -->` / `<!-- IRC_*_END -->` family."""
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_MARKER_BEGIN,
        QDII_PREMIUM_MARKER_END,
    )

    assert QDII_PREMIUM_MARKER_BEGIN == "<!-- IRC_QDII_PREMIUM_BEGIN -->"
    assert QDII_PREMIUM_MARKER_END == "<!-- IRC_QDII_PREMIUM_END -->"
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.memo.qdii_premium_lines'`.

- [ ] **Step 3: Create the module with constants only.**

Create `src/irc/memo/qdii_premium_lines.py`:

```python
"""QDII premium-to-NAV memo-surface module (item 003).

Pure module. Tier-1 import contract: imports from `irc.schemas.discovery`
(for `QDII_MAX_PREMIUM_DEFAULT`) and stdlib only — NO imports from
`irc.opportunity.*`, `irc.scoring.*`, or `irc.commands.*`. Mirrors
`aliases.py` / `concentration.py` per the renderer tier-1 import contract.

Surfaces four things consumed by the memo edge:
  1. `QDII_PREMIUM_THRESHOLD_PCT` — alias of `QDII_MAX_PREMIUM_DEFAULT` so
     the memo display value can never drift from the decision-gate value.
  2. `QDII_PREMIUM_MARKER_BEGIN/END` — deterministic §6 marker pair.
  3. Pure render helpers: `_format_qdii_premium_cell`,
     `build_qdii_premium_projection`, `render_qdii_premium_block`,
     `format_qdii_premium_prefix`.
  4. `write_qdii_premium_snapshot` — the only I/O edge, writes the
     top-level `outputs/<date>/qdii_premium.json` projection artefact
     via `irc.io_utils.atomic_write_text`.

See docs/adr/0006-qdii-premium-memo-surface.md and
docs/2026-05-27-instrument-pickability/items/003-spec.md.
"""
from __future__ import annotations

from typing import Final

from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT


# AC5: re-export alias (NOT a redefinition) so the memo display value
# tracks the decision-gate value forever.
QDII_PREMIUM_THRESHOLD_PCT: Final[float] = QDII_MAX_PREMIUM_DEFAULT

# AC7 / G-Q2: marker constants live in the producing module
# (concentration.py / macro_pillar.py precedent).
QDII_PREMIUM_MARKER_BEGIN: Final[str] = "<!-- IRC_QDII_PREMIUM_BEGIN -->"
QDII_PREMIUM_MARKER_END: Final[str] = "<!-- IRC_QDII_PREMIUM_END -->"
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/qdii_premium_lines.py tests/memo/test_qdii_premium_lines.py
git commit -m "feat(memo): bootstrap qdii_premium_lines module + threshold/marker constants (item 003 AC5)"
```

---

## Task 2: `_format_qdii_premium_cell` — picks-table cell renderer (AC2 / AC3)

**Files:**
- Modify: `src/irc/memo/qdii_premium_lines.py`
- Test: `tests/memo/test_qdii_premium_lines.py`

- [ ] **Step 1: Write the failing tests for AC2 + AC3.**

Append to `tests/memo/test_qdii_premium_lines.py`:

```python
def test_format_cell_none_returns_em_dash() -> None:
    """AC2 branch 1: non-QDII rows (premium is None) render `—`."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    assert _format_qdii_premium_cell(qdii_premium_pct=None,
                                     asset_class="cn_etf") == "—"


def test_format_cell_off_exchange_zero_renders_with_suffix() -> None:
    """AC2 branch 2 (G-Q4): synthetic-zero from off-exchange feeders
    renders `0.00%（场外申赎）` so it's not confused with a same-day
    on-exchange NAV coincidence."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    for asset_class in ("us_etf", "hk_etf", "qdii_global"):
        cell = _format_qdii_premium_cell(qdii_premium_pct=0.0,
                                         asset_class=asset_class)
        assert cell == "0.00%（场外申赎）"


def test_format_cell_positive_premium_renders_signed_two_decimals() -> None:
    """AC2 branch 3: on-exchange premium — always-signed, 2 decimals."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    cell = _format_qdii_premium_cell(qdii_premium_pct=0.0648,
                                     asset_class="us_etf")
    assert cell == "+6.48%"


def test_format_cell_negative_discount_renders_signed_two_decimals() -> None:
    """AC2 branch 3 (discount path): -0.34% on 513690."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    cell = _format_qdii_premium_cell(qdii_premium_pct=-0.0034,
                                     asset_class="hk_etf")
    assert cell == "-0.34%"


def test_format_cell_defensive_non_qdii_zero_returns_em_dash() -> None:
    """AC2 branch 4 (defensive): structurally impossible per
    qdii_premium_for_row routing, but rendered as `—` if it ever occurs."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    assert _format_qdii_premium_cell(qdii_premium_pct=0.0,
                                     asset_class="cn_etf") == "—"


def test_format_cell_never_contains_pipe_or_br() -> None:
    """AC3: every render path must keep the markdown row single-line."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    samples = (
        _format_qdii_premium_cell(None, "cn_etf"),
        _format_qdii_premium_cell(0.0, "us_etf"),
        _format_qdii_premium_cell(0.0648, "us_etf"),
        _format_qdii_premium_cell(-0.0034, "hk_etf"),
    )
    for s in samples:
        assert "|" not in s
        assert "<br>" not in s
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v`
Expected: 6 new tests FAIL with `ImportError: cannot import name '_format_qdii_premium_cell'`.

- [ ] **Step 3: Implement `_format_qdii_premium_cell`.**

Append to `src/irc/memo/qdii_premium_lines.py`:

```python
# AC2 spec: QDII asset-class set comes from scoring.qdii_premium per the
# canonical home declaration there. We re-list as a module-local tuple to
# keep the tier-1 import contract (no imports from irc.scoring.*).
_QDII_ASSET_CLASSES_LOCAL: Final[frozenset[str]] = frozenset(
    {"us_etf", "hk_etf", "qdii_global"}
)


def _format_qdii_premium_cell(
    qdii_premium_pct: float | None,
    asset_class: str,
) -> str:
    """Render the 溢价 picks-table cell (AC2).

    Branches:
      - None              → `—` (non-QDII rows; matches empty-citations).
      - 0.0 + QDII class  → `0.00%（场外申赎）` (synthetic-zero off-exchange).
      - non-zero          → `+{pct:.2f}%` / `-{pct:.2f}%` (signed, 2 decimals).
      - 0.0 + non-QDII    → `—` (defensive; structurally impossible).
    """
    if qdii_premium_pct is None:
        return "—"
    if qdii_premium_pct == 0.0:
        if asset_class in _QDII_ASSET_CLASSES_LOCAL:
            return "0.00%（场外申赎）"
        return "—"
    pct = qdii_premium_pct * 100
    sign = "+" if pct > 0 else "-"
    return f"{sign}{abs(pct):.2f}%"
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/qdii_premium_lines.py tests/memo/test_qdii_premium_lines.py
git commit -m "feat(memo): _format_qdii_premium_cell — signed/off-exchange/none branches (item 003 AC2-AC3)"
```

---

## Task 3: Extend `PickRow` with `qdii_premium_pct` field (AC1 / AC12)

**Files:**
- Modify: `src/irc/memo/picks_table.py`
- Test: `tests/memo/test_picks_table.py`

- [ ] **Step 1: Write the failing tests for AC1 + AC12.**

Append to `tests/memo/test_picks_table.py` (near the existing tranche_cap tests around line 250):

```python
def test_pick_row_qdii_premium_pct_defaults_to_none():
    """AC12: existing 32 test call sites stay green — new field optional."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="cn_etf", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
    )
    assert row.qdii_premium_pct is None


def test_pick_row_qdii_premium_pct_accepts_negative_float():
    """AC1: -0.34% premium (513690 discount) survives the frozen dataclass."""
    row = PickRow(
        instrument_id="513690", name_cn="港股红利ETF博时",
        asset_class="hk_etf", role="satellite_hk_equity",
        target_weight=0.05, composite_score=55.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        qdii_premium_pct=-0.0034,
    )
    assert row.qdii_premium_pct == -0.0034


def test_pick_row_qdii_premium_pct_accepts_positive_float():
    """AC1: 6.48% premium (above threshold) survives."""
    row = PickRow(
        instrument_id="159501", name_cn="标普消费ETF",
        asset_class="us_etf", role="satellite_us_consumer",
        target_weight=0.05, composite_score=52.6,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        qdii_premium_pct=0.0648,
    )
    assert row.qdii_premium_pct == 0.0648
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/memo/test_picks_table.py::test_pick_row_qdii_premium_pct_defaults_to_none tests/memo/test_picks_table.py::test_pick_row_qdii_premium_pct_accepts_negative_float tests/memo/test_picks_table.py::test_pick_row_qdii_premium_pct_accepts_positive_float -v`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'qdii_premium_pct'` (last two) and `AttributeError` (first).

- [ ] **Step 3: Add the field to `PickRow`.**

Edit `src/irc/memo/picks_table.py`. After the `advisory_gaps` field declaration (around line 76), append inside the `PickRow` dataclass:

```python
    # Item 003: QDII premium-to-NAV from scoring.json. None for non-QDII
    # rows (qdii_premium_for_row routing); 0.0 + QDII asset_class for
    # off-exchange synthetic-zero. Spec AC1 / AC12 (default keeps the 34
    # call sites — 2 production + 32 test — green).
    qdii_premium_pct: float | None = None
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/memo/test_picks_table.py -v`
Expected: all picks-table tests pass (existing 30+ stay green via `None` default).

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/picks_table.py tests/memo/test_picks_table.py
git commit -m "feat(memo): extend PickRow with optional qdii_premium_pct (item 003 AC1 AC12)"
```

---

## Task 4: Migrate 13-column lock + render `溢价` column (AC2 / AC11 / AC4)

**Files:**
- Modify: `src/irc/memo/picks_table.py`
- Test: `tests/memo/test_picks_table.py`

- [ ] **Step 1: Migrate the column-order lock test (AC11) — write it failing for the new order.**

Edit `tests/memo/test_picks_table.py` lines 285–301 (`test_picks_table_header_contains_tranche_cap_and_trigger_status_columns`). Replace the 3-link chain with the 4-link chain:

```python
def test_picks_table_header_contains_tranche_cap_and_trigger_status_columns():
    """Header order locked: ... | 主要理由 | 单次定投上限 | 溢价 | 触发状态 | 证据 |.
    Item 003 (instrument-pickability) extended the 12-column lock to 13 by
    inserting 溢价 between 单次定投上限 and 触发状态."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
    )
    md = render_picks_table([row])
    header_line = next(line for line in md.split("\n") if line.startswith("| 代码"))
    cols = [c.strip() for c in header_line.strip("|").split("|")]
    assert "单次定投上限" in cols
    assert "溢价" in cols
    assert "触发状态" in cols
    # Order: 主要理由 → 单次定投上限 → 溢价 → 触发状态 → 证据
    assert cols.index("单次定投上限") == cols.index("主要理由") + 1
    assert cols.index("溢价") == cols.index("单次定投上限") + 1
    assert cols.index("触发状态") == cols.index("溢价") + 1
    assert cols.index("证据") == cols.index("触发状态") + 1
```

Also append two cell-level tests (AC2 end-to-end via `render_picks_table`):

```python
def test_picks_table_renders_signed_premium_cell_for_qdii_pick():
    """AC2 end-to-end: 6.48% premium QDII row produces a `+6.48%` cell
    in the rendered markdown table."""
    row = PickRow(
        instrument_id="159501", name_cn="标普消费ETF",
        asset_class="us_etf", role="satellite_us_consumer",
        target_weight=0.05, composite_score=52.6,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        qdii_premium_pct=0.0648,
    )
    md = render_picks_table([row])
    assert "+6.48%" in md


def test_picks_table_renders_off_exchange_suffix_for_synthetic_zero_qdii():
    """AC2 + G-Q4: off-exchange feeder shows `0.00%（场外申赎）` not bare zero."""
    row = PickRow(
        instrument_id="017641", name_cn="国泰纳指联接",
        asset_class="us_etf", role="core_us_equity",
        target_weight=0.05, composite_score=60.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        qdii_premium_pct=0.0,
    )
    md = render_picks_table([row])
    assert "0.00%（场外申赎）" in md


def test_picks_table_renders_em_dash_for_non_qdii_row():
    """AC2 branch 1: cn_etf has no premium signal → cell is `—`."""
    row = PickRow(
        instrument_id="510300", name_cn="沪深300ETF",
        asset_class="cn_etf", role="core_a_share",
        target_weight=0.1, composite_score=55.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        qdii_premium_pct=None,
    )
    md = render_picks_table([row])
    # 溢价 column cell renders em-dash. Trigger-status cell ALSO renders
    # em-dash for empty trigger_status — count "—" in the data row only.
    data_line = next(line for line in md.split("\n") if line.startswith("| 510300"))
    cells = [c.strip() for c in data_line.strip("|").split("|")]
    # 13 cells total; index 10 is 溢价 (after the 10 leading cells:
    # 代码 名称 角色 权重上限 综合分* 决策 机会状态 本期行动 主要理由 单次定投上限).
    assert cells[10] == "—"
```

Append the AC4 footnote test:

```python
def test_scoring_footnote_includes_premium_explainer_sentence():
    """AC4: footnote gains the 溢价反映 sentence; existing 触发状态
    sentence stays byte-unchanged."""
    from irc.memo.picks_table import _SCORING_FOOTNOTE

    assert "溢价反映" in _SCORING_FOOTNOTE
    assert "fund_etf_spot_em" in _SCORING_FOOTNOTE
    assert "场外申赎" in _SCORING_FOOTNOTE
    # Existing sentence preserved verbatim (regression lock).
    assert "触发状态反映第7节触发条件相对当前宏观/净值快照的评估结果。" in _SCORING_FOOTNOTE
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/memo/test_picks_table.py -v -k "header_contains or renders_signed_premium or off_exchange_suffix or em_dash_for_non_qdii or footnote_includes_premium"`
Expected: 5 FAILs — `溢价` not in header; `+6.48%`/`0.00%（场外申赎）` not in md; footnote missing the sentence.

- [ ] **Step 3: Migrate `render_picks_table` to 13 columns and append the footnote sentence.**

Edit `src/irc/memo/picks_table.py`:

(a) Append to `_SCORING_FOOTNOTE` (around lines 42–50). Replace the final closing `"详见评分体系说明文档。"` line with:

```python
    "溢价反映该 QDII 在二级市场相对单位净值的偏离（正值=溢价/折价为负），"
    "数据来源 AkShare fund_etf_spot_em 收盘快照，场外申赎类显示 0.00%（场外申赎）。"
    "详见评分体系说明文档。"
```

(b) Add the cell-helper import near the top of `picks_table.py` (after the existing `from irc.opportunity.types import ThesisEvidence`):

```python
from irc.memo.qdii_premium_lines import _format_qdii_premium_cell
```

(c) Replace the `header` block + the per-row `lines.append(...)` (lines ~184–202) with:

```python
    header = (
        "| 代码 | 名称 | 角色 | 权重上限 | 综合分* | 决策 | 机会状态 | 本期行动 | "
        "主要理由 | 单次定投上限 | 溢价 | 触发状态 | 证据 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [header]
    for r in unique:
        weight_str = f"{r.target_weight * 100:.1f}%"
        score_str = _format_score(r)
        citations_cell = _format_citations_cell(r.citations)
        decision_cell = _DECISION_CN.get(r.decision_status, r.decision_status)
        tranche_cell = _format_tranche_cap_cell(r.tranche_cap_pct)
        premium_cell = _format_qdii_premium_cell(r.qdii_premium_pct, r.asset_class)
        trigger_cell = _format_trigger_status_cell(r.trigger_status)
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {r.role} | "
            f"{weight_str} | {score_str} | {decision_cell} | {r.opportunity_state} | "
            f"{_action_cn(r)} | {r.one_line_reason} | "
            f"{tranche_cell} | {premium_cell} | {trigger_cell} | {citations_cell} |"
        )
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/memo/test_picks_table.py -v`
Expected: all picks-table tests pass.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/picks_table.py tests/memo/test_picks_table.py
git commit -m "feat(memo): picks-table 13-column lock + 溢价 column + footnote sentence (item 003 AC2 AC4 AC11)"
```

---

## Task 5: `build_qdii_premium_projection` — pure projection builder (AC6 / AC14)

**Files:**
- Modify: `src/irc/memo/qdii_premium_lines.py`
- Test: `tests/memo/test_qdii_premium_lines.py`

- [ ] **Step 1: Write the failing tests for AC6 + AC14 (sorted, blocking flag, threshold, evidence_cutoff, deterministic ordering).**

Append to `tests/memo/test_qdii_premium_lines.py`:

```python
def _fixed_clock() -> datetime:
    return datetime(2026, 5, 27, 15, 30, 0, tzinfo=timezone(timedelta(hours=8)))


def test_build_projection_sorts_rows_by_instrument_id() -> None:
    """AC6 + AC14(a): rows sorted by instrument_id ASC for two-run byte
    equality."""
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
        {"instrument_id": "017641", "name_cn": "国泰纳指联接",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0},
    ]
    proj = build_qdii_premium_projection(
        score_rows,
        evidence_cutoff="2026-05-26",
        now_fn=_fixed_clock,
    )
    iids = [r["instrument_id"] for r in proj["rows"]]
    assert iids == ["017641", "159501", "513690"]


def test_build_projection_blocking_flag_marks_above_threshold() -> None:
    """AC6: blocking = (pct is not None) AND (pct > threshold_pct)."""
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    by_iid = {r["instrument_id"]: r for r in proj["rows"]}
    assert by_iid["159501"]["blocking"] is True
    assert by_iid["513690"]["blocking"] is False


def test_build_projection_renders_cell_per_row() -> None:
    """AC6: each row carries `render_cell` (the picks-table cell value)
    so downstream consumers can echo the memo text verbatim."""
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    assert proj["rows"][0]["render_cell"] == "-0.34%"


def test_build_projection_threshold_and_metadata() -> None:
    """AC6: top-level fields generated_at, threshold_pct, evidence_cutoff."""
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_THRESHOLD_PCT,
        build_qdii_premium_projection,
    )

    proj = build_qdii_premium_projection(
        score_rows=[], evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    assert proj["threshold_pct"] == QDII_PREMIUM_THRESHOLD_PCT
    assert proj["evidence_cutoff"] == "2026-05-26"
    assert proj["generated_at"] == "2026-05-27T15:30:00+08:00"
    assert proj["rows"] == []


def test_build_projection_skips_rows_without_premium() -> None:
    """AC6: only rows whose qdii_premium_pct is not None are included.
    NG10 + G-Q11: a None value means data is unknown — excluded from §6
    and the artefact."""
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "513690", "name_cn": "港股红利",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
        {"instrument_id": "159949", "name_cn": "未知溢价",
         "asset_class": "us_etf", "qdii_premium_pct": None},
        {"instrument_id": "510300", "name_cn": "沪深300",
         "asset_class": "cn_etf", "qdii_premium_pct": None},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    iids = [r["instrument_id"] for r in proj["rows"]]
    assert iids == ["513690"]


def test_build_projection_is_deterministic_across_two_calls() -> None:
    """AC14: same inputs → byte-identical outputs."""
    import json
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "159501", "name_cn": "X", "asset_class": "us_etf",
         "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "Y", "asset_class": "hk_etf",
         "qdii_premium_pct": -0.0034},
    ]
    a = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock)
    b = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock)
    assert json.dumps(a, ensure_ascii=False, sort_keys=True) == \
        json.dumps(b, ensure_ascii=False, sort_keys=True)
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v -k "build_projection"`
Expected: 6 FAILs with `ImportError: cannot import name 'build_qdii_premium_projection'`.

- [ ] **Step 3: Implement `build_qdii_premium_projection`.**

Append to `src/irc/memo/qdii_premium_lines.py`:

```python
from collections.abc import Callable, Sequence
from datetime import datetime


def _coerce_premium(value: object) -> float | None:
    """Best-effort float coercion. Returns None when value is None or
    can't be parsed — same pattern as `_decision_status_for_pick`."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _project_row(score_row: dict) -> dict | None:
    """One projection row from one scoring row. Returns None when the
    row has no premium signal (filters out non-QDII + unknown-premium
    rows in one pass)."""
    pct = _coerce_premium(score_row.get("qdii_premium_pct"))
    if pct is None:
        return None
    asset_class = str(score_row.get("asset_class") or "")
    return {
        "instrument_id": str(score_row.get("instrument_id") or ""),
        "name_cn": str(score_row.get("name_cn") or ""),
        "asset_class": asset_class,
        "market": str(score_row.get("market") or ""),
        "qdii_premium_pct": pct,
        "blocking": pct > QDII_PREMIUM_THRESHOLD_PCT,
        "render_cell": _format_qdii_premium_cell(pct, asset_class),
    }


def build_qdii_premium_projection(
    score_rows: Sequence[dict],
    *,
    evidence_cutoff: str | None,
    now_fn: Callable[[], datetime],
) -> dict:
    """Build the deterministic projection dict consumed by both the §6
    marker block and the qdii_premium.json artefact (AC6 / AC14).

    Pure. `now_fn` is the clock-injection edge so two-run byte equality
    holds under test stubs and the production caller passes
    `lambda: datetime.now(timezone(timedelta(hours=8)))`.
    """
    rows = [r for r in (_project_row(s) for s in score_rows) if r is not None]
    rows.sort(key=lambda r: r["instrument_id"])
    return {
        "generated_at": now_fn().isoformat(),
        "threshold_pct": QDII_PREMIUM_THRESHOLD_PCT,
        "evidence_cutoff": evidence_cutoff,
        "rows": rows,
    }
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/qdii_premium_lines.py tests/memo/test_qdii_premium_lines.py
git commit -m "feat(memo): build_qdii_premium_projection — sorted, deterministic, clock-injected (item 003 AC6 AC14)"
```

---

## Task 6: `render_qdii_premium_block` + `format_qdii_premium_prefix` (AC7 / AC9)

**Files:**
- Modify: `src/irc/memo/qdii_premium_lines.py`
- Test: `tests/memo/test_qdii_premium_lines.py`

- [ ] **Step 1: Write the failing tests for the marker block + the §7 prefix.**

Append to `tests/memo/test_qdii_premium_lines.py`:

```python
def test_render_block_wraps_in_markers_and_lists_rows() -> None:
    """AC7: full block — marker BEGIN + header + per-row bullets +
    marker END. Above-threshold rows get （超阈值，已暂缓执行）."""
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_MARKER_BEGIN,
        QDII_PREMIUM_MARKER_END,
        build_qdii_premium_projection,
        render_qdii_premium_block,
    )

    score_rows = [
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    block = render_qdii_premium_block(proj)
    lines = block.splitlines()
    assert lines[0] == QDII_PREMIUM_MARKER_BEGIN
    assert lines[-1] == QDII_PREMIUM_MARKER_END
    assert "数据截止 2026-05-26" in lines[1]
    assert "阈值 5%" in lines[1]
    # Sorted by iid → 159501 before 513690.
    assert "159501 标普消费ETF：+6.92%（超阈值，已暂缓执行）" in block
    assert "513690 港股红利ETF博时：-0.34%" in block
    # The discount row is NOT marked as blocking.
    discount_line = next(
        l for l in lines if "513690" in l
    )
    assert "超阈值" not in discount_line


def test_render_block_empty_projection_returns_empty_string() -> None:
    """AC7: empty projection → empty string (caller falls back to legacy
    placeholder)."""
    from irc.memo.qdii_premium_lines import (
        build_qdii_premium_projection,
        render_qdii_premium_block,
    )

    proj = build_qdii_premium_projection(
        score_rows=[], evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    assert render_qdii_premium_block(proj) == ""


def test_format_prefix_for_blocking_row() -> None:
    """AC9 / G-Q3: ⛔ qdii_premium_too_high（{cell} > 5%，已暂缓）｜ — note
    the full-width ｜ (U+FF5C) separator."""
    from irc.memo.qdii_premium_lines import format_qdii_premium_prefix

    row = {
        "instrument_id": "159501", "blocking": True,
        "render_cell": "+6.92%",
    }
    prefix = format_qdii_premium_prefix(row)
    assert prefix == "⛔ qdii_premium_too_high（+6.92% > 5%，已暂缓）｜"
    # Separator is full-width (U+FF5C), distinct from half-width `|`.
    assert "｜" in prefix
    assert "|" not in prefix


def test_format_prefix_for_non_blocking_row_returns_empty_string() -> None:
    """AC9: rows whose `blocking` is False receive no prefix."""
    from irc.memo.qdii_premium_lines import format_qdii_premium_prefix

    row = {
        "instrument_id": "513690", "blocking": False,
        "render_cell": "-0.34%",
    }
    assert format_qdii_premium_prefix(row) == ""
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v -k "render_block or format_prefix"`
Expected: 4 FAILs with `ImportError`.

- [ ] **Step 3: Implement both renderers.**

Append to `src/irc/memo/qdii_premium_lines.py`:

```python
def _format_row_bullet(row: dict) -> str:
    """One " - {iid} {name}：{cell}{（超阈值，已暂缓执行） if blocking}" line."""
    base = f" - {row['instrument_id']} {row['name_cn']}：{row['render_cell']}"
    if row.get("blocking"):
        return base + "（超阈值，已暂缓执行）"
    return base


def render_qdii_premium_block(projection: dict) -> str:
    """Render the §6 marker block (AC7 / G-Q2).

    Empty projection → empty string (caller emits the legacy placeholder).
    Otherwise: MARKER_BEGIN + header + per-row bullets + MARKER_END,
    joined by newlines. Header carries `evidence_cutoff` + threshold.
    """
    rows = projection.get("rows") or []
    if not rows:
        return ""
    threshold_pct = float(projection.get("threshold_pct") or 0.0)
    cutoff = projection.get("evidence_cutoff") or "(未知)"
    header = (
        f"溢价/折价：QDII 候选标的二级市场偏离快照"
        f"（数据截止 {cutoff}，阈值 {threshold_pct * 100:.0f}%）："
    )
    body = [_format_row_bullet(r) for r in rows]
    return "\n".join([QDII_PREMIUM_MARKER_BEGIN, header, *body, QDII_PREMIUM_MARKER_END])


def format_qdii_premium_prefix(row: dict) -> str:
    """§7 hard-block prefix (AC9 / G-Q3).

    Empty string for non-blocking rows; the canonical
    `⛔ qdii_premium_too_high（{cell} > {threshold_pct*100:.0f}%，已暂缓）｜`
    string for blocking rows. Separator is full-width U+FF5C `｜` to
    distinguish from the existing half-width `|` bullet separators.
    """
    if not row.get("blocking"):
        return ""
    threshold_display = f"{QDII_PREMIUM_THRESHOLD_PCT * 100:.0f}%"
    return (
        f"⛔ qdii_premium_too_high（{row['render_cell']} > "
        f"{threshold_display}，已暂缓）｜"
    )
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/qdii_premium_lines.py tests/memo/test_qdii_premium_lines.py
git commit -m "feat(memo): render_qdii_premium_block + §7 prefix helper (item 003 AC7 AC9)"
```

---

## Task 7: `write_qdii_premium_snapshot` — atomic JSON writer (AC6 / G-Q5)

**Files:**
- Modify: `src/irc/memo/qdii_premium_lines.py`
- Test: `tests/memo/test_qdii_premium_lines.py`

- [ ] **Step 1: Write the failing test for the writer (always-written invariant + atomic + byte-identical across two runs).**

Append to `tests/memo/test_qdii_premium_lines.py`:

```python
def test_write_snapshot_always_writes_even_when_rows_empty(tmp_path: Path) -> None:
    """G-Q5: always-written invariant — empty rows list still produces
    a file with the four schema fields populated."""
    import json
    from irc.memo.qdii_premium_lines import (
        build_qdii_premium_projection,
        write_qdii_premium_snapshot,
    )

    proj = build_qdii_premium_projection(
        score_rows=[], evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    write_qdii_premium_snapshot(proj, out_dir=tmp_path)
    artefact = tmp_path / "qdii_premium.json"
    assert artefact.exists()
    payload = json.loads(artefact.read_text(encoding="utf-8"))
    assert payload["rows"] == []
    assert payload["threshold_pct"] == 0.05
    assert payload["evidence_cutoff"] == "2026-05-26"
    assert payload["generated_at"] == "2026-05-27T15:30:00+08:00"


def test_write_snapshot_two_runs_produce_byte_identical_file(tmp_path: Path) -> None:
    """AC14: stub clock + identical scoring → byte-identical files."""
    from irc.memo.qdii_premium_lines import (
        build_qdii_premium_projection,
        write_qdii_premium_snapshot,
    )

    score_rows = [
        {"instrument_id": "159501", "name_cn": "X", "asset_class": "us_etf",
         "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "Y", "asset_class": "hk_etf",
         "qdii_premium_pct": -0.0034},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock)

    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    write_qdii_premium_snapshot(proj, out_dir=a_dir)
    write_qdii_premium_snapshot(proj, out_dir=b_dir)
    a_bytes = (a_dir / "qdii_premium.json").read_bytes()
    b_bytes = (b_dir / "qdii_premium.json").read_bytes()
    assert a_bytes == b_bytes


def test_write_snapshot_emits_above_threshold_row_with_blocking_flag(
    tmp_path: Path,
) -> None:
    """AC6: 159501 at 6.92% renders blocking=True; 513690 at -0.34%
    renders blocking=False."""
    import json
    from irc.memo.qdii_premium_lines import (
        build_qdii_premium_projection,
        write_qdii_premium_snapshot,
    )

    score_rows = [
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    write_qdii_premium_snapshot(proj, out_dir=tmp_path)
    payload = json.loads(
        (tmp_path / "qdii_premium.json").read_text(encoding="utf-8")
    )
    by_iid = {r["instrument_id"]: r for r in payload["rows"]}
    assert by_iid["159501"]["blocking"] is True
    assert by_iid["159501"]["render_cell"] == "+6.92%"
    assert by_iid["513690"]["blocking"] is False
    assert by_iid["513690"]["render_cell"] == "-0.34%"
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v -k "write_snapshot"`
Expected: 3 FAILs with `ImportError: cannot import name 'write_qdii_premium_snapshot'`.

- [ ] **Step 3: Implement `write_qdii_premium_snapshot`.**

Append to `src/irc/memo/qdii_premium_lines.py`:

```python
import json
from pathlib import Path

from irc.io_utils import atomic_write_text


def write_qdii_premium_snapshot(projection: dict, *, out_dir: Path) -> None:
    """Write the top-level `qdii_premium.json` artefact (AC6 / G-Q5).

    Always-written invariant: even with empty `rows`, the file is written
    so a missing file becomes a build error rather than ambiguous "no
    QDII this week." Atomic via `atomic_write_text` (`.tmp.{pid} → os.replace`).

    Serialisation uses `sort_keys=True` and `ensure_ascii=False` for
    byte-stable Chinese names.
    """
    payload = json.dumps(
        projection, ensure_ascii=False, sort_keys=True, indent=2,
    )
    atomic_write_text(Path(out_dir) / "qdii_premium.json", payload + "\n")
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/memo/test_qdii_premium_lines.py -v`
Expected: all pass.

- [ ] **Step 5: Verify the module is under the 200-line budget.**

Run: `wc -l src/irc/memo/qdii_premium_lines.py`
Expected: ≤ 180 lines (spec AC18).

> **Amendment (2026-05-27 drift review — D3):** Actual delivered count is 186 lines — 6 lines over
> the 180 soft target but under the 200 hard limit. The overage comes from moving all stdlib
> imports (`json`, `Callable`, `Sequence`, `Path`) to the module top (consolidated from Tasks 1–7)
> rather than appending them across task steps. AC18 hard limit satisfied; 180 wc target is a
> planning estimate only.

- [ ] **Step 6: Commit.**

```bash
git add src/irc/memo/qdii_premium_lines.py tests/memo/test_qdii_premium_lines.py
git commit -m "feat(memo): write_qdii_premium_snapshot — atomic top-level projection artefact (item 003 AC6 G-Q5)"
```

---

## Task 8: Extend `compose_fx_qdii_lines` with marker-block injection (AC7 / AC8)

**Files:**
- Modify: `src/irc/memo/diagnostics.py`
- Test: `tests/memo/test_diagnostics_fx_qdii.py`

- [ ] **Step 1: Write the failing tests for AC7 + AC8 (marker block replaces placeholder; 3-tuple shape preserved).**

Append to `tests/memo/test_diagnostics_fx_qdii.py`:

```python
def test_fx_qdii_lines_keeps_3_tuple_with_empty_projection() -> None:
    """AC8: empty projection → element [1] is the legacy placeholder;
    3-tuple shape preserved (back-compat for the existing call site)."""
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.30},
    ])
    lines = compose_fx_qdii_lines(
        alloc, usd_tolerance=(0.25, 0.45),
        qdii_premium_rows=None,
        evidence_cutoff="2026-05-26",
    )
    assert len(lines) == 3
    assert lines[1] == "溢价/折价：数据未采集——请在交易前查阅各 QDII 二级市场溢价。"


def test_fx_qdii_lines_swaps_placeholder_for_marker_block() -> None:
    """AC7: non-empty projection → element [1] is the IRC_QDII_PREMIUM_BEGIN/END
    wrapped marker block (a single string, newline-separated)."""
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_MARKER_BEGIN,
        QDII_PREMIUM_MARKER_END,
    )

    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.30},
    ])
    projection_rows = [
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "market": "cn_on_exchange",
         "qdii_premium_pct": -0.0034, "blocking": False,
         "render_cell": "-0.34%"},
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "market": "cn_on_exchange",
         "qdii_premium_pct": 0.0692, "blocking": True,
         "render_cell": "+6.92%"},
    ]
    lines = compose_fx_qdii_lines(
        alloc, usd_tolerance=(0.25, 0.45),
        qdii_premium_rows=projection_rows,
        evidence_cutoff="2026-05-26",
    )
    assert len(lines) == 3
    block = lines[1]
    assert QDII_PREMIUM_MARKER_BEGIN in block
    assert QDII_PREMIUM_MARKER_END in block
    assert "数据截止 2026-05-26" in block
    assert "159501 标普消费ETF：+6.92%（超阈值，已暂缓执行）" in block
    assert "513690 港股红利ETF博时：-0.34%" in block
    # Element [0] (header) and [2] (hedge) unchanged shape.
    assert "外汇与QDII敞口提醒" in lines[0]
    assert "对冲成本" in lines[2]


def test_fx_qdii_lines_below_floor_still_returns_empty() -> None:
    """AC8 + back-compat: when QDII weight is below the floor the function
    still returns () regardless of qdii_premium_rows kwarg."""
    alloc = _alloc([
        {"instrument_id": "X", "asset_class": "us_etf", "target_weight": 0.05},
    ])
    lines = compose_fx_qdii_lines(
        alloc, usd_tolerance=(0.25, 0.45),
        qdii_premium_rows=[{"instrument_id": "X", "blocking": False}],
        evidence_cutoff="2026-05-26",
    )
    assert lines == ()
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/memo/test_diagnostics_fx_qdii.py -v -k "keeps_3_tuple or swaps_placeholder or below_floor_still"`
Expected: 3 FAILs with `TypeError: compose_fx_qdii_lines() got an unexpected keyword argument 'qdii_premium_rows'`.

- [ ] **Step 3: Add kwargs and marker-block swap to `compose_fx_qdii_lines`.**

Edit `src/irc/memo/diagnostics.py`. Replace the `compose_fx_qdii_lines` signature + body's `premium = ...` line (around line 136):

Change the signature from:
```python
def compose_fx_qdii_lines(
    allocation: dict[str, Any] | None,
    usd_tolerance: tuple[float, float] | None,
    fx_hedge_policy: str | None = None,
) -> tuple[str, ...]:
```

To:
```python
def compose_fx_qdii_lines(
    allocation: dict[str, Any] | None,
    usd_tolerance: tuple[float, float] | None,
    fx_hedge_policy: str | None = None,
    *,
    qdii_premium_rows: Sequence[dict] | None = None,
    evidence_cutoff: str | None = None,
) -> tuple[str, ...]:
```

Add the import at the top of `diagnostics.py` (after the existing `from typing import Any`):

```python
from collections.abc import Sequence
```

Replace the `premium = "溢价/折价：数据未采集——请在交易前查阅各 QDII 二级市场溢价。"` line with:

```python
    premium = _compose_premium_element(qdii_premium_rows, evidence_cutoff)
```

Add the helper above `compose_fx_qdii_lines` (after `_compose_hedge_line` or before `compose_fx_qdii_lines`):

```python
_LEGACY_PREMIUM_PLACEHOLDER = (
    "溢价/折价：数据未采集——请在交易前查阅各 QDII 二级市场溢价。"
)


def _compose_premium_element(
    qdii_premium_rows: Sequence[dict] | None,
    evidence_cutoff: str | None,
) -> str:
    """§6 premium element (AC7 / AC8). Empty/None projection → legacy
    placeholder; non-empty → marker-wrapped block."""
    if not qdii_premium_rows:
        return _LEGACY_PREMIUM_PLACEHOLDER
    from irc.memo.qdii_premium_lines import render_qdii_premium_block

    projection = {
        "rows": list(qdii_premium_rows),
        "threshold_pct": _QDII_PREMIUM_DISPLAY_THRESHOLD,
        "evidence_cutoff": evidence_cutoff,
    }
    rendered = render_qdii_premium_block(projection)
    return rendered or _LEGACY_PREMIUM_PLACEHOLDER
```

Add the threshold constant at the top of `diagnostics.py` (near `_QDII_WEIGHT_FLOOR_FOR_DIAGNOSTIC`):

```python
# Re-imported from qdii_premium_lines via a lazy local import inside
# _compose_premium_element to keep the existing tier-1 import contract
# (diagnostics.py is consumed by commands/memo_cmd.py; qdii_premium_lines
# is consumed too — neither imports the other at module scope).
from irc.memo.qdii_premium_lines import QDII_PREMIUM_THRESHOLD_PCT \
    as _QDII_PREMIUM_DISPLAY_THRESHOLD
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/memo/test_diagnostics_fx_qdii.py -v`
Expected: all pass (including the existing 4 tests via back-compat).

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/diagnostics.py tests/memo/test_diagnostics_fx_qdii.py
git commit -m "feat(memo): compose_fx_qdii_lines optional qdii_premium_rows + evidence_cutoff kwargs (item 003 AC7 AC8)"
```

---

## Task 9: Synthesizer 7th verbatim-lock clause for `IRC_QDII_PREMIUM_*` (constraint per CONTEXT.md)

**Files:**
- Modify: `src/irc/memo/synthesizer.py`
- Test: `tests/memo/test_synthesizer_glossary.py` (or `test_markers.py` if that's where the existing marker clauses are tested — check both)

- [ ] **Step 1: Find the existing test that locks the synthesizer's marker clauses, then add a failing test for the new clause.**

Run: `grep -rn "IRC_CONCENTRATION_BEGIN" tests/memo/ | head -5`

Append to whichever test file already covers `IRC_CONCENTRATION_BEGIN` (most likely `tests/memo/test_synthesizer_glossary.py` or `tests/memo/test_markers.py`):

```python
def test_synthesizer_prompt_locks_qdii_premium_marker_block():
    """Item 003 constraint: when the skeleton contains
    IRC_QDII_PREMIUM_BEGIN, the synthesizer must be instructed to preserve
    the block verbatim."""
    from irc.memo.synthesizer import _build_user_message  # or whatever
    # the helper name is — adapt to existing test pattern.

    skeleton = (
        "## 6. 风险提示\n"
        "<!-- IRC_QDII_PREMIUM_BEGIN -->\n"
        "溢价/折价：QDII 候选标的二级市场偏离快照（数据截止 2026-05-26，阈值 5%）：\n"
        " - 159501 标普消费ETF：+6.92%（超阈值，已暂缓执行）\n"
        "<!-- IRC_QDII_PREMIUM_END -->\n"
    )
    user_msg = _build_user_message(skeleton=skeleton, refs_block="")
    assert "IRC_QDII_PREMIUM_BEGIN/END" in user_msg
    assert "原样保留" in user_msg
```

If `_build_user_message` does not exist as a separate function, fall back to the integration approach used by item 002's plan: assert the substring appears in the constructed `user_msg` inside `synthesize_memo` via a stub `call_chat` (look up the precedent in `tests/memo/test_synthesizer_glossary.py`).

- [ ] **Step 2: Run the test to verify it fails.**

Run: `uv run pytest tests/memo/ -v -k "qdii_premium_marker_block"`
Expected: FAIL — substring `IRC_QDII_PREMIUM_BEGIN/END` not in the constructed user message.

- [ ] **Step 3: Append the 7th clause to `synthesizer.py`.**

Edit `src/irc/memo/synthesizer.py`. After the existing `if "<!-- IRC_CONCENTRATION_BEGIN -->" in skeleton:` block (around lines 142–147), append:

```python
    # Item 003 (instrument-pickability) lock for the §6 QDII premium block.
    if "<!-- IRC_QDII_PREMIUM_BEGIN -->" in skeleton:
        locked_section_lines.append(
            "第6节『风险提示』在 IRC_QDII_PREMIUM_BEGIN/END 标记之间的 bullet 必须**原样保留**："
            "该 bullet 由系统根据 scoring.json 中的 QDII 溢价/折价快照自动生成，"
            "禁止改写、合并、新增或删除其中的任何条目，"
            "亦禁止改写其中的标的代码、名称、溢价百分比或阈值警示文案。"
        )
```

- [ ] **Step 4: Run the test to verify it passes.**

Run: `uv run pytest tests/memo/ -v -k "qdii_premium_marker_block"`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/memo/synthesizer.py tests/memo/test_synthesizer_glossary.py
git commit -m "feat(memo): synthesizer 7th verbatim-lock clause for IRC_QDII_PREMIUM_*" 
```

(Use `tests/memo/test_markers.py` instead of `test_synthesizer_glossary.py` in the `git add` line if that's where the test landed.)

---

## Task 10: Wire `qdii_premium_pct` into `PickRow` construction (AC1 via memo_cmd)

> **Amendment (2026-05-27 drift review — D2):** Fixture fields `evidence_gaps`, `thesis_evidence`,
> and `advisory_gaps` use `[]` (list) not `()` (tuple) because `_parse_advisory_gaps` (item 001)
> enforces list-type at the parse boundary, making tuples incorrect here. Plan fixtures corrected
> in-place above.

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Test: `tests/commands/test_memo_cmd.py`

- [ ] **Step 1: Write the failing integration test for AC1 (premium stamped on PickRow).**

Append to `tests/commands/test_memo_cmd.py`:

```python
def test_build_pick_rows_stamps_qdii_premium_pct_from_scoring():
    """AC1 integration: a hand-rolled scoring row with qdii_premium_pct=0.0648
    produces a PickRow whose qdii_premium_pct == 0.0648."""
    from irc.commands.memo_cmd import _build_pick_rows

    trades = [{
        "target": "159501", "role": "satellite_us_consumer",
        "target_weight": 0.05, "asset_class": "us_etf",
        "triggers": (), "buy_method": "limit", "granularity": "weekly",
        "venue_note": "ok",
    }]
    opportunity = {"rows": [{
        "instrument_id": "159501", "name_cn": "标普消费ETF",
        "asset_class": "us_etf",
        "evidence_gaps": [],
        "thesis_evidence": [],
        "valuation_state": "fair",
        "opportunity_state": "small_watch",
        "opportunity_reason": "—",
        "advisory_gaps": [],
    }]}
    scoring = {"scores": [{
        "instrument_id": "159501",
        "composite_score": 52.6,
        "action": "watch",
        "asset_class": "us_etf",
        "qdii_premium_pct": 0.0648,
        "data_completeness": 0.8,
    }]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, scoring)
    assert len(pick_rows) == 1
    assert pick_rows[0].qdii_premium_pct == 0.0648


def test_build_pick_rows_non_qdii_leaves_premium_none():
    """AC1: cn_etf rows (no qdii_premium_pct in scoring) keep the field None."""
    from irc.commands.memo_cmd import _build_pick_rows

    trades = [{
        "target": "510300", "role": "core_a_share",
        "target_weight": 0.10, "asset_class": "cn_etf",
        "triggers": (), "buy_method": "limit", "granularity": "weekly",
        "venue_note": "ok",
    }]
    opportunity = {"rows": [{
        "instrument_id": "510300", "name_cn": "沪深300ETF",
        "asset_class": "cn_etf",
        "evidence_gaps": [],
        "thesis_evidence": [],
        "valuation_state": "fair",
        "opportunity_state": "core_dca",
        "opportunity_reason": "—",
        "advisory_gaps": [],
    }]}
    scoring = {"scores": [{
        "instrument_id": "510300",
        "composite_score": 55.0,
        "action": "watch",
        "asset_class": "cn_etf",
        "data_completeness": 0.8,
    }]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, scoring)
    assert len(pick_rows) == 1
    assert pick_rows[0].qdii_premium_pct is None
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/commands/test_memo_cmd.py -v -k "stamps_qdii_premium_pct or leaves_premium_none"`
Expected: 2 FAILs — `qdii_premium_pct` is `None` on the 159501 row (not yet wired).

- [ ] **Step 3: Wire `qdii_premium_pct` into `_build_pick_rows`.**

Edit `src/irc/commands/memo_cmd.py`. In the `_build_pick_rows` function, locate the `PickRow(...)` construction (around line 708). After the `tranche_cap_pct=tranche_cap_pct,` line (line 723), and after `trigger_status=trigger_status,` (line 724), and after `advisory_gaps=...` (lines 725–727), add the new field assignment. Just before the closing `))` of the `PickRow(...)`, append:

```python
            qdii_premium_pct=(
                float(sc["qdii_premium_pct"])
                if sc.get("qdii_premium_pct") is not None
                else None
            ),
```

(Coercion uses the same try-pattern shape as `_decision_status_for_pick` line 567; the dict-lookup form here is the parsimonious version since the field is already a float in `scoring.json`. Wrap in a `try/except (TypeError, ValueError)` block locally if a defensive coercion is preferred — but the existing test uses a plain float so this is sufficient.)

For robustness against malformed scoring data, prefer the helper form. Add at the top of `_build_pick_rows` (just before the loop) or inline using the existing pattern. The simpler/correct form:

```python
            qdii_premium_pct=_coerce_optional_float(sc.get("qdii_premium_pct")),
```

And add the helper near the other `_format_*` helpers in `memo_cmd.py`:

```python
def _coerce_optional_float(value: object) -> float | None:
    """Best-effort optional float; None or unparseable → None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/commands/test_memo_cmd.py -v -k "stamps_qdii_premium_pct or leaves_premium_none"`
Expected: 2 passed.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/commands/memo_cmd.py tests/commands/test_memo_cmd.py
git commit -m "feat(memo): wire qdii_premium_pct from scoring.json onto PickRow (item 003 AC1)"
```

---

## Task 11: Wire projection + §6 marker block at the memo_cmd edge (AC7)

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`

- [ ] **Step 1: Write the failing integration test asserting the §6 marker block reaches the final memo input.**

Append to `tests/commands/test_memo_cmd.py`:

```python
def test_memo_cmd_emits_qdii_premium_marker_block_in_risk_notes(tmp_path):
    """AC7 integration: when scoring carries qdii_premium_pct AND QDII
    weight crosses the floor, risk_notes includes the marker block."""
    # This is a focused unit test against the helper composition; the
    # full pipeline integration is verified by the final post-run check.
    from irc.commands.memo_cmd import _compose_qdii_premium_projection
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_MARKER_BEGIN,
        QDII_PREMIUM_MARKER_END,
    )

    scoring = {"scores": [
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
    ]}
    proj = _compose_qdii_premium_projection(
        scoring, evidence_cutoff="2026-05-26",
    )
    assert proj["evidence_cutoff"] == "2026-05-26"
    iids = [r["instrument_id"] for r in proj["rows"]]
    assert iids == ["159501", "513690"]
    # blocking flag correct
    by_iid = {r["instrument_id"]: r for r in proj["rows"]}
    assert by_iid["159501"]["blocking"] is True
    assert by_iid["513690"]["blocking"] is False
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `uv run pytest tests/commands/test_memo_cmd.py -v -k "qdii_premium_marker_block_in_risk_notes"`
Expected: FAIL — `_compose_qdii_premium_projection` not defined.

- [ ] **Step 3: Add the projection helper + thread it into `compose_fx_qdii_lines`.**

Edit `src/irc/commands/memo_cmd.py`:

(a) Add the imports near the top with the other `irc.memo.*` imports:

```python
from irc.memo.qdii_premium_lines import (
    build_qdii_premium_projection,
    write_qdii_premium_snapshot,
)
```

(b) Add the helper near `_compose_concentration_lines` (around line 287):

```python
def _compose_qdii_premium_projection(
    scoring: dict,
    *,
    evidence_cutoff: str | None,
) -> dict:
    """Build the projection consumed by §6 marker block, §7 prefix, and
    the `qdii_premium.json` artefact (AC6 / AC14). Pure — clock injected
    via the local _utc8_now closure for two-run byte equality."""
    score_rows = list(scoring.get("scores") or [])
    return build_qdii_premium_projection(
        score_rows,
        evidence_cutoff=evidence_cutoff,
        now_fn=_utc8_now,
    )


def _utc8_now() -> datetime:
    """UTC+8 clock; centralised so the writer is testable via stubs."""
    return datetime.now(timezone(timedelta(hours=8)))
```

(c) In `run_memo`, locate the existing `fx_lines = compose_fx_qdii_lines(...)` call (around line 874). Build the projection just before, and thread the kwargs in:

```python
    qdii_projection = _compose_qdii_premium_projection(
        scoring, evidence_cutoff=cutoff,
    )
    fx_lines = compose_fx_qdii_lines(
        alloc, usd_tol_pair,
        fx_hedge_policy=fx_policy,
        qdii_premium_rows=qdii_projection["rows"],
        evidence_cutoff=cutoff,
    )
```

- [ ] **Step 4: Run the test to verify it passes.**

Run: `uv run pytest tests/commands/test_memo_cmd.py -v -k "qdii_premium_marker_block_in_risk_notes"`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/commands/memo_cmd.py tests/commands/test_memo_cmd.py
git commit -m "feat(memo): wire §6 QDII premium marker block at memo_cmd edge (item 003 AC7 AC14)"
```

---

## Task 12: §7 hard-block prefix for above-threshold QDII picks (AC9 / AC10 / AC13)

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Modify: `src/irc/memo/template.py` (NO change — AC10 lock; assertion-only test below)
- Test: `tests/commands/test_memo_cmd.py`
- Test: `tests/memo/test_template.py`

- [ ] **Step 1: Write the failing AC9/AC10/AC13 tests.**

Append to `tests/commands/test_memo_cmd.py`:

```python
def test_compose_execution_lines_prefixes_above_threshold_qdii():
    """AC9 / G-Q3: a pick with blocking=True receives the
    `⛔ qdii_premium_too_high（{cell} > 5%，已暂缓）｜` prefix."""
    from irc.commands.memo_cmd import _compose_execution_lines

    trades = [
        {"target": "159501", "target_weight": 0.05,
         "buy_method": "limit", "granularity": "weekly",
         "triggers": [], "venue_note": "ok"},
        {"target": "513690", "target_weight": 0.05,
         "buy_method": "limit", "granularity": "weekly",
         "triggers": [], "venue_note": "ok"},
    ]
    opportunity_rows = [
        {"instrument_id": "159501", "name_cn": "标普消费ETF"},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时"},
    ]
    qdii_premium_rows = [
        {"instrument_id": "159501", "blocking": True, "render_cell": "+6.92%"},
        {"instrument_id": "513690", "blocking": False, "render_cell": "-0.34%"},
    ]
    lines = _compose_execution_lines(
        trades, opportunity_rows,
        qdii_premium_rows=qdii_premium_rows,
    )
    assert any(l.startswith("⛔ qdii_premium_too_high（+6.92% > 5%，已暂缓）｜")
               for l in lines)
    # 513690 (non-blocking) line gets no prefix.
    line_513690 = next(l for l in lines if "513690" in l)
    assert not line_513690.startswith("⛔")


def test_no_qdii_premium_high_synonym_in_src():
    """AC13: codename unification — `qdii_premium_high` must NOT appear
    anywhere in src/irc/. The canonical name is `qdii_premium_too_high`."""
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "qdii_premium_high", "src/irc/"],
        capture_output=True, text=True,
    )
    # grep returns 1 when no matches — that's the success path.
    assert result.returncode == 1, (
        f"Unexpected `qdii_premium_high` token in src/:\n{result.stdout}"
    )
```

Append to `tests/memo/test_template.py`:

```python
def test_render_execution_section_is_premium_unaware():
    """AC10: _render_execution_section takes pre-prefixed strings verbatim
    and emits them. No premium-awareness inside template.py — FP 'effects
    at edges'."""
    from irc.memo.template import _render_execution_section

    lines = (
        "⛔ qdii_premium_too_high（+6.92% > 5%，已暂缓）｜**159501 X** | ...",
        "**513690 Y** | ...",
    )
    rendered = _render_execution_section(lines)
    # Both lines emit as-is, each wrapped with `- ` bullet prefix.
    assert "- ⛔ qdii_premium_too_high（+6.92% > 5%，已暂缓）｜**159501 X**" in rendered
    assert "- **513690 Y**" in rendered
    # template.py never reads premium/blocking — it can't have changed.
    assert "qdii_premium_pct" not in rendered
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `uv run pytest tests/commands/test_memo_cmd.py tests/memo/test_template.py -v -k "prefixes_above_threshold_qdii or no_qdii_premium_high_synonym or premium_unaware"`
Expected: 2–3 FAILs (the template test should PASS already since template.py is unchanged; the memo_cmd tests fail).

- [ ] **Step 3: Extend `_compose_execution_lines` with optional `qdii_premium_rows` kwarg.**

Edit `src/irc/commands/memo_cmd.py`. Change the `_compose_execution_lines` signature (around line 155):

From:
```python
def _compose_execution_lines(
    trades: list[dict],
    opportunity_rows: list[dict],
    extra_names: dict[str, str] | None = None,
    require_opportunity_row: bool = False,
) -> tuple[str, ...]:
```

To:
```python
def _compose_execution_lines(
    trades: list[dict],
    opportunity_rows: list[dict],
    extra_names: dict[str, str] | None = None,
    require_opportunity_row: bool = False,
    *,
    qdii_premium_rows: Sequence[dict] | None = None,
) -> tuple[str, ...]:
```

Add the `Sequence` import near the existing typing imports at the top of `memo_cmd.py`:

```python
from collections.abc import Sequence
```

Add the prefix-lookup setup near the start of `_compose_execution_lines` (after `extra_names = extra_names or {}` line ~176):

```python
    from irc.memo.qdii_premium_lines import format_qdii_premium_prefix
    prefix_by_iid: dict[str, str] = {}
    for r in (qdii_premium_rows or ()):
        iid = str(r.get("instrument_id") or "")
        prefix = format_qdii_premium_prefix(r)
        if iid and prefix:
            prefix_by_iid[iid] = prefix
```

Modify the `bullet = ...` assembly (around line 203). Replace:

```python
        bullet = (
            f"**{label}** | 目标权重 ≤ {weight*100:.1f}% | "
            f"建仓方式 {t.get('buy_method', 'unknown')} ({t.get('granularity', 'default')}) | "
            f"触发 {triggers} | 渠道 {venue_note}"
        )
        lines.append(bullet)
```

With:
```python
        bullet_body = (
            f"**{label}** | 目标权重 ≤ {weight*100:.1f}% | "
            f"建仓方式 {t.get('buy_method', 'unknown')} ({t.get('granularity', 'default')}) | "
            f"触发 {triggers} | 渠道 {venue_note}"
        )
        prefix = prefix_by_iid.get(iid, "")
        lines.append(prefix + bullet_body)
```

And update the `run_memo` call site (around line 896) to pass the projection:

```python
    execution_lines = _compose_execution_lines(
        trades, opportunity.get("rows") or [],
        extra_names=fallback_names,
        require_opportunity_row=True,
        qdii_premium_rows=qdii_projection["rows"],
    )
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `uv run pytest tests/commands/test_memo_cmd.py tests/memo/test_template.py -v -k "prefixes_above_threshold_qdii or no_qdii_premium_high_synonym or premium_unaware"`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/commands/memo_cmd.py tests/commands/test_memo_cmd.py tests/memo/test_template.py
git commit -m "feat(memo): §7 hard-block prefix for above-threshold QDII picks at memo_cmd edge (item 003 AC9 AC10 AC13)"
```

---

## Task 13: Always-write `qdii_premium.json` artefact at memo stage (AC6 / G-Q5)

**Files:**
- Modify: `src/irc/commands/memo_cmd.py`
- Test: `tests/commands/test_memo_cmd.py`

- [ ] **Step 1: Write the failing test asserting the artefact is always written.**

Append to `tests/commands/test_memo_cmd.py`:

```python
def test_run_memo_writes_qdii_premium_json_always(monkeypatch, tmp_path):
    """AC6 / G-Q5: qdii_premium.json is written on every memo run, even
    when zero QDII rows exist. Smoke test scoped to the artefact write —
    the full pipeline is exercised by the post-run check at the end of
    this plan."""
    # Minimal scoring with zero QDII rows.
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_THRESHOLD_PCT,
        build_qdii_premium_projection,
        write_qdii_premium_snapshot,
    )

    proj = build_qdii_premium_projection(
        score_rows=[],
        evidence_cutoff="2026-05-26",
        now_fn=lambda: __import__("datetime").datetime(2026, 5, 27),
    )
    write_qdii_premium_snapshot(proj, out_dir=tmp_path)
    assert (tmp_path / "qdii_premium.json").exists()
    import json
    payload = json.loads(
        (tmp_path / "qdii_premium.json").read_text(encoding="utf-8")
    )
    assert payload["threshold_pct"] == QDII_PREMIUM_THRESHOLD_PCT
    assert payload["rows"] == []
```

- [ ] **Step 2: Run the test to verify it passes immediately (smoke test against the writer alone).**

Run: `uv run pytest tests/commands/test_memo_cmd.py -v -k "writes_qdii_premium_json_always"`
Expected: PASS (writer was tested in Task 7; this is a confirmation of the contract a level up).

- [ ] **Step 3: Add the artefact-write call inside `run_memo`.**

Edit `src/irc/commands/memo_cmd.py`. In `run_memo`, after the existing `out_dir.mkdir(parents=True, exist_ok=True)` line (around line 927), and before the `audit_blocks_publish` call, add:

```python
    # Item 003 (instrument-pickability): always-written QDII premium
    # projection artefact (AC6 / G-Q5). Missing file = build error.
    write_qdii_premium_snapshot(qdii_projection, out_dir=out_dir)
```

- [ ] **Step 4: Run the test to verify it stays passing.**

Run: `uv run pytest tests/commands/test_memo_cmd.py -v -k "writes_qdii_premium_json_always"`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/irc/commands/memo_cmd.py tests/commands/test_memo_cmd.py
git commit -m "feat(memo): always-write qdii_premium.json artefact (item 003 AC6 G-Q5)"
```

---

## Task 14: Full regression sweep + end-to-end verification on cached evidence

**Files:**
- None modified — verification only.

- [ ] **Step 1: Run the full unit + integration suite.**

Run: `uv run pytest -x`
Expected: all tests pass. If any test breaks, investigate the regression before continuing — most likely candidate is `tests/integration/test_publishable_set_lockdown.py::test_two_run_byte_equality_memo_after_run_memo` if the determinism guarantees weren't met (per AC14 / G-Q1).

- [ ] **Step 2: Run lint.**

Run: `uv run ruff check src tests`
Expected: clean.

- [ ] **Step 3: Re-run the memo stage on today's cached evidence and inspect the four deliverables.**

Run: `uv run irc run --only memo`
Expected: `memo OK: ...` log line (no halt).

- [ ] **Step 4: Verify (a) — the 溢价 column is populated for QDII rows in `outputs/2026-05-27/memo.md`.**

Run: `grep -E "^\| [0-9]" outputs/2026-05-27/memo.md | grep -E "us_etf|hk_etf|qdii"` (or simpler: visually inspect the picks table).

Better, deterministic check:

```bash
grep -E "(\+|\-)[0-9]+\.[0-9]{2}%|0\.00%（场外申赎）" outputs/2026-05-27/memo.md | head -10
```

Expected: at least one match showing `-0.34%` (513690), `0.00%（场外申赎）` (017641 / 019441), or `+X.XX%` (any on-exchange QDII pick).

- [ ] **Step 5: Verify (b) — §6 marker block emits real premium data, not the legacy placeholder.**

Run:
```bash
grep -A 20 "IRC_QDII_PREMIUM_BEGIN" outputs/2026-05-27/memo.md
```

Expected:
```
<!-- IRC_QDII_PREMIUM_BEGIN -->
溢价/折价：QDII 候选标的二级市场偏离快照（数据截止 2026-05-26，阈值 5%）：
 - 513690 港股红利ETF博时：-0.34%
 ...
<!-- IRC_QDII_PREMIUM_END -->
```

(Confirms the legacy `数据未采集——请在交易前查阅各 QDII 二级市场溢价。` placeholder is gone.)

Run:
```bash
grep "数据未采集" outputs/2026-05-27/memo.md
```

Expected: no match (placeholder replaced).

- [ ] **Step 6: Verify (c) — §7 trigger lines for above-threshold QDII picks carry the prefix.**

Today's scoring has 159941 / 513300 / 159501 above 5% — but they are watched-not-picked (NG2), so they do NOT appear in §7. If today's pick set has zero above-threshold QDII, the §7 prefix verification path is "empty above-threshold set → no prefixes anywhere" (per AC9 invariant).

Run:
```bash
grep -E "^- ⛔ qdii_premium_too_high" outputs/2026-05-27/memo.md
```

Expected: zero matches today (no above-threshold QDII in pick set per current trade plan), AND zero `⛔` glyphs ever appear in the file. To exercise the prefix path under test, the unit test in Task 12 covers it deterministically.

Belt-and-suspenders: confirm the §7 prefix path is wired even if today doesn't trigger it:
```bash
grep -A 5 "QDII标的执行前须查阅二级市场溢价" outputs/2026-05-27/memo.md
```

Expected: the legacy preamble is still in place; the bullets follow it as before.

- [ ] **Step 7: Verify (d) — `outputs/2026-05-27/qdii_premium.json` artefact is written.**

Run:
```bash
ls -la outputs/2026-05-27/qdii_premium.json
cat outputs/2026-05-27/qdii_premium.json | python -m json.tool | head -30
```

Expected: file exists; payload has `generated_at`, `threshold_pct: 0.05`, `evidence_cutoff: "2026-05-26"`, `rows: [...]` with sorted-by-iid entries including 513690 (blocking: false) and the above-threshold watch symbols (blocking: true).

- [ ] **Step 8: Verify two-run byte equality of the artefact.**

Run:
```bash
cp outputs/2026-05-27/qdii_premium.json /tmp/qdii_a.json
uv run irc run --only memo
diff /tmp/qdii_a.json outputs/2026-05-27/qdii_premium.json
```

Expected: empty diff (AC14 invariant).

(Note: `generated_at` will differ between runs because `_utc8_now` uses the wall clock. If the diff is non-empty solely due to `generated_at`, that's the wall-clock-difference path; the unit-test in Task 5 covers the stubbed-clock determinism contract. If a stricter two-run byte equality at the artefact level is required across `irc run --only memo` invocations, treat that as a follow-up — the unit-test coverage with `now_fn` stub is the canonical AC14 lock per spec.)

- [ ] **Step 9: Confirm the integration lockdown two-run byte-equality of `memo.md` still holds.**

Run:
```bash
uv run pytest tests/integration/test_publishable_set_lockdown.py -v -k "two_run_byte_equality_memo"
```

Expected: PASS — the integration test re-renders `memo.md` twice in the same run and asserts byte equality. Item 003's column-add lives inside that re-render path; if the test passes, the picks-table 13-column lock holds across two consecutive in-test renders.

- [ ] **Step 10: Final commit (if any cleanup needed) + tag the plan as complete.**

Most likely no additional changes are needed. If the regression sweep surfaced anything (e.g. a test that needed to be updated for the new column count beyond `tests/memo/test_picks_table.py`), fix it now with a focused commit:

```bash
git add <files>
git commit -m "fix(memo): regression cleanup after item 003 13-column lock"
```

---

## Self-Review Checklist (run before handing off)

- [ ] **AC1**: PickRow has `qdii_premium_pct: float | None = None`; `_build_pick_rows` stamps it (Tasks 3 + 10).
- [ ] **AC2**: 13-column picks table with 溢价 between 单次定投上限 and 触发状态; 4 render branches (Task 4).
- [ ] **AC3**: cell never contains `|` or `<br>` (Task 2 test).
- [ ] **AC4**: `_SCORING_FOOTNOTE` gains the 溢价反映 sentence (Task 4).
- [ ] **AC5**: `QDII_PREMIUM_THRESHOLD_PCT = QDII_MAX_PREMIUM_DEFAULT` (Task 1).
- [ ] **AC6**: `qdii_premium.json` projection artefact written via atomic helper, sorted by iid, blocking flag (Tasks 5 + 7 + 13).
- [ ] **AC7**: §6 marker block with header + per-row bullets + super-阈值 suffix (Tasks 6 + 8 + 11).
- [ ] **AC8**: `compose_fx_qdii_lines` returns 3-tuple; empty projection → legacy placeholder (Task 8).
- [ ] **AC9**: §7 prefix `⛔ qdii_premium_too_high（{cell} > 5%，已暂缓）｜` (Tasks 6 + 12).
- [ ] **AC10**: prefix composed at memo_cmd edge; template.py unchanged (Task 12).
- [ ] **AC11**: 4-link column-order chain in the lockdown test (Task 4).
- [ ] **AC12**: existing 34 PickRow call sites stay green via `None` default (Task 3 + final regression sweep).
- [ ] **AC13**: no `qdii_premium_high` token in `src/irc/` (Task 12 grep test).
- [ ] **AC14**: determinism via injected clock + sorted rows + identical two-run output (Tasks 5 + 7).
- [ ] **AC15**: no row-level state change — `OpportunityRow` untouched, `thesis_state` untouched (cross-check).
- [ ] **AC16**: SAME-3 / citation gate invariants — new column emits zero `[ref:...]` (cross-check via regression sweep).
- [ ] **AC17**: every AC1–AC16 has at least one test, written before production code (TDD discipline maintained throughout).
- [ ] **AC18**: `qdii_premium_lines.py` ≤ 180 lines; new helpers ≤ 20 lines (Task 7 Step 5 verification).
- [ ] **NG1–NG10**: cross-checked against spec — no new fetcher, no discipline integration, no `qdii_premium_high`, no allocation change, no §5 触发状态 column overload, no historical back-fill, no provider switch, no item 001/002 coupling, no `qdii_premium_unknown` semantic change.
- [ ] **Constraints**: TDD ✓; functional/immutable ✓; new module < 200 lines ✓; tier-1 import contract ✓; deterministic markers follow synthesizer lockdown pattern ✓; atomic write pattern ✓.

---

## Execution Handoff

Plan complete and saved to `docs/2026-05-27-instrument-pickability/items/003-plan.md`.
