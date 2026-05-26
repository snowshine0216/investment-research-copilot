# Item 003 — Mirror Decision Sheet into memo §5 picks table

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface per-tranche sizing cap (`单次定投上限`) and compact trigger state (`触发状态`) as two new columns of the deterministic memo §5 picks table, so a reader of `memo.md` no longer needs to open `decision_report.md` to see *how much* / *when*.

**Architecture:** Pure renderer change in `src/irc/memo/picks_table.py` (two new `PickRow` fields + one new private compact-format helper + two header columns). Two mechanical relocations enable single-locus reuse: (1) `_MACRO_FIELD_TO_KEY` + `_resolve_trigger_current_value` move from `decision/report.py` to `decision/sizing.py` (drop `_` on the public surface) so memo can import them; (2) `_read_live_decision_inputs` moves from `commands/decision_cmd.py` to new `src/irc/decision/live_inputs.py` so both `decision_cmd.py` and `memo_cmd.py` feed the same `(macro_snapshot, weekly_return_by_id)` shape into their renderers. `decision_report.md` output is byte-identical post-refactor.

**Tech Stack:** Python 3.12, pytest, frozen dataclasses, DuckDB (read-only), Click CLI.

---

## File Structure

**Modify:**
- `src/irc/memo/picks_table.py` — add two `PickRow` fields, add `_format_trigger_status_compact` helper, extend header + row format, extend footnote.
- `src/irc/decision/sizing.py` — host the relocated `MACRO_FIELD_TO_KEY` constant and `resolve_trigger_current_value` pure function.
- `src/irc/decision/report.py` — replace inline `_MACRO_FIELD_TO_KEY` / `_resolve_trigger_current_value` with imports from `decision.sizing`. Zero behaviour change.
- `src/irc/commands/decision_cmd.py` — replace inline `_read_live_decision_inputs` with import from `decision.live_inputs`. Zero behaviour change.
- `src/irc/commands/memo_cmd.py` — thread `build_mode` + `macro_snapshot` + `weekly_return_by_id` through `_build_pick_rows`; `run_memo` calls `read_live_decision_inputs` and passes the snapshot through.

**Create:**
- `src/irc/decision/live_inputs.py` — pure I/O wrapper exposing `read_live_decision_inputs(repo_root, instrument_ids)`. Verbatim relocation of the function body from `decision_cmd.py`.
- `tests/memo/test_trigger_status_compact.py` — covers `_format_trigger_status_compact` (single-trigger met/not_met/missing, multi-trigger ordering, empty tuple, unknown comparator).
- `tests/decision/test_trigger_resolution.py` — covers `resolve_trigger_current_value` after relocation.
- `tests/decision/test_live_inputs.py` — covers `read_live_decision_inputs` after extraction (DB-missing graceful degrade + DB-present read path).

**Extend:**
- `tests/memo/test_picks_table.py` — header column order, `≤ X.XX%` format, `—` fallback, multi-trigger `<br>` join, footnote.
- `tests/memo/test_pick_rows.py` — `_build_pick_rows` populates both new fields when live inputs are passed; defaults safely when omitted.

**Verify regression (no edits):**
- `tests/decision/test_three_section_markdown.py` — confirms `_decision_sheet_section` still renders byte-identical output after the relocations.
- `tests/decision/test_sizing.py` — confirms `suggest_tranche_pct` / `evaluate_trigger` / `format_why_when_line` unchanged.

---

## Task 1: Extract `MACRO_FIELD_TO_KEY` + `resolve_trigger_current_value` into `decision/sizing.py`

**Files:**
- Modify: `src/irc/decision/sizing.py` (append new public symbols)
- Modify: `src/irc/decision/report.py` (replace local defs with import)
- Create: `tests/decision/test_trigger_resolution.py`

- [ ] **Step 1: Write the failing test**

Create `tests/decision/test_trigger_resolution.py`:

```python
"""Tests for `resolve_trigger_current_value` after relocation to sizing.py.

Pure function: maps a trade_plan trigger dict + live snapshots to a
(value, unit_hint) pair consumed by `format_why_when_line` and
`_format_trigger_status_compact`. No I/O, no caching.
"""
from __future__ import annotations

from irc.decision.sizing import MACRO_FIELD_TO_KEY, resolve_trigger_current_value


def test_macro_field_to_key_maps_known_macro_fields() -> None:
    """The mapping covers the three macro series the trade plan can name."""
    assert MACRO_FIELD_TO_KEY["macro.vix"] == "vix"
    assert MACRO_FIELD_TO_KEY["macro.real_yield_10y_tips"] == "real_yield_10y_tips"
    assert MACRO_FIELD_TO_KEY["macro.dxy"] == "DXY"


def test_resolve_trigger_instrument_weekly_return_returns_pct_unit() -> None:
    """`instrument.weekly_return` short-circuits to weekly_return_by_id[iid]
    with unit 'pct' (caller formats as XX.XX%)."""
    trig = {"data_field": "instrument.weekly_return"}
    value, unit = resolve_trigger_current_value(
        trig,
        instrument_id="510300",
        macro_snapshot={"vix": 16.76},
        weekly_return_by_id={"510300": -0.0077},
    )
    assert value == -0.0077
    assert unit == "pct"


def test_resolve_trigger_macro_field_returns_raw_unit() -> None:
    """`macro.*` fields map via MACRO_FIELD_TO_KEY to macro_snapshot keys
    with unit 'raw' (caller formats as plain scalar)."""
    trig = {"data_field": "macro.real_yield_10y_tips"}
    value, unit = resolve_trigger_current_value(
        trig,
        instrument_id="510300",
        macro_snapshot={"real_yield_10y_tips": 2.18},
        weekly_return_by_id={},
    )
    assert value == 2.18
    assert unit == "raw"


def test_resolve_trigger_unknown_field_returns_none_raw() -> None:
    """Unknown data_field → (None, 'raw'). Renderer then falls back to
    a 'missing' marker."""
    trig = {"data_field": "macro.unknown_series"}
    value, unit = resolve_trigger_current_value(
        trig,
        instrument_id="510300",
        macro_snapshot={},
        weekly_return_by_id={},
    )
    assert value is None
    assert unit == "raw"


def test_resolve_trigger_missing_macro_key_returns_none_raw() -> None:
    """A known field whose key is absent from macro_snapshot → (None, 'raw')."""
    trig = {"data_field": "macro.vix"}
    value, unit = resolve_trigger_current_value(
        trig,
        instrument_id="510300",
        macro_snapshot={},  # vix missing
        weekly_return_by_id={},
    )
    assert value is None
    assert unit == "raw"


def test_resolve_trigger_empty_data_field_returns_none_raw() -> None:
    """Defensive: missing data_field key in the trigger dict → (None, 'raw')."""
    value, unit = resolve_trigger_current_value(
        {},
        instrument_id="510300",
        macro_snapshot={},
        weekly_return_by_id={},
    )
    assert value is None
    assert unit == "raw"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/decision/test_trigger_resolution.py -v`
Expected: FAIL with `ImportError: cannot import name 'MACRO_FIELD_TO_KEY' from 'irc.decision.sizing'`.

- [ ] **Step 3: Add the public symbols to `decision/sizing.py`**

Append to `src/irc/decision/sizing.py` (after `format_why_when_line`):

```python
# ── Trigger field resolution ──────────────────────────────────────────────────
#
# Maps the trade_plan trigger schema's `data_field` strings to macro_snapshot
# keys. Imported by both `decision/report.py::_decision_sheet_section` and
# `memo/picks_table.py::_format_trigger_status_compact` so memo + decision
# never drift on what a trigger's "current value" means. See CONTEXT.md
# "Renderers + alias-builder" → MACRO_FIELD_TO_KEY entry.
MACRO_FIELD_TO_KEY: dict[str, str] = {
    "macro.vix": "vix",
    "macro.real_yield_10y_tips": "real_yield_10y_tips",
    "macro.dxy": "DXY",
}


def resolve_trigger_current_value(
    trig: dict,
    instrument_id: str,
    macro_snapshot: dict[str, float],
    weekly_return_by_id: dict[str, float],
) -> tuple[float | None, str]:
    """Resolve a trigger's current value + unit hint from the live snapshots.

    `instrument.weekly_return` lookups go to weekly_return_by_id; macro
    triggers map via MACRO_FIELD_TO_KEY. Returns (value, unit_hint) where
    unit_hint is "pct" for return-like fractions (display as XX.XX%) and
    "raw" for raw scalars. Returns (None, "raw") for unknown fields so the
    renderer falls back to a 'missing' marker.
    """
    field = str(trig.get("data_field") or "")
    if field == "instrument.weekly_return":
        return weekly_return_by_id.get(instrument_id), "pct"
    if field.startswith("macro."):
        key = MACRO_FIELD_TO_KEY.get(field.lower())
        if key is None:
            return None, "raw"
        return macro_snapshot.get(key), "raw"
    return None, "raw"
```

- [ ] **Step 4: Run trigger-resolution test to verify it passes**

Run: `uv run pytest tests/decision/test_trigger_resolution.py -v`
Expected: 6 passed.

- [ ] **Step 5: Replace local defs in `decision/report.py` with imports**

In `src/irc/decision/report.py`:

Edit the existing import block (lines 6-10) to add the two new symbols:

```python
from irc.decision.sizing import (
    MACRO_FIELD_TO_KEY,
    TriggerSpec,
    format_why_when_line,
    resolve_trigger_current_value,
    suggest_tranche_pct,
)
```

Delete the now-duplicate definitions (lines 461-493: `_MACRO_FIELD_TO_KEY` and `_resolve_trigger_current_value` and their docstring/blank lines). The two-line block becomes empty.

Update the one call site at line ~555 inside `_decision_sheet_section`:

```python
                current, unit = resolve_trigger_current_value(
                    trig, iid, macro_snapshot, weekly_return_by_id,
                )
```

(drop the leading `_`).

- [ ] **Step 6: Verify the decision report regression suite still passes byte-for-byte**

Run: `uv run pytest tests/decision/ -v`
Expected: all tests in `tests/decision/` pass — including `test_three_section_markdown.py`, `test_report.py`, `test_sizing.py`. Zero changes to `decision_report.md` output (the relocation is mechanical).

- [ ] **Step 7: Commit**

```bash
git add src/irc/decision/sizing.py src/irc/decision/report.py tests/decision/test_trigger_resolution.py
git commit -m "$(cat <<'EOF'
refactor(decision): relocate MACRO_FIELD_TO_KEY + resolve_trigger_current_value to sizing.py

Promotes the two helpers from decision/report.py-private to decision/sizing.py-public
so memo §5 picks-table (item 003) can import the same trigger-resolution logic the
Decision Sheet uses. Drops the `_` prefix on cross-module export per project naming
convention. decision_report.md output is byte-identical.
EOF
)"
```

---

## Task 2: Extract `_read_live_decision_inputs` into `decision/live_inputs.py`

**Files:**
- Create: `src/irc/decision/live_inputs.py`
- Modify: `src/irc/commands/decision_cmd.py:1-12,85-150,228`
- Create: `tests/decision/test_live_inputs.py`

- [ ] **Step 1: Write the failing test**

Create `tests/decision/test_live_inputs.py`:

```python
"""Tests for `read_live_decision_inputs` after extraction from decision_cmd.

I/O wrapper: pure read over `data/local.duckdb`. Graceful degrade on
DB-missing / connect-fail / query-fail returns ({}, {}).
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from irc.decision.live_inputs import read_live_decision_inputs


def test_read_live_decision_inputs_returns_empty_when_db_missing(
    tmp_path: Path,
) -> None:
    """When `data/local.duckdb` does not exist the helper returns ({}, {})
    so the renderer can gracefully show 'unknown' rather than crashing."""
    # tmp_path/data/local.duckdb intentionally not created.
    macro, returns = read_live_decision_inputs(tmp_path, {"510300"})
    assert macro == {}
    assert returns == {}


def test_read_live_decision_inputs_reads_macro_and_returns(tmp_path: Path) -> None:
    """Happy path: macro_series row + 8 nav_history rows → populated dicts."""
    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_path = db_dir / "local.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE macro_series ("
        "  series_id VARCHAR, date DATE, value DOUBLE"
        ")"
    )
    con.execute(
        "INSERT INTO macro_series VALUES "
        "('vix', '2026-05-25', 16.76), "
        "('vix', '2026-05-20', 17.50)"  # older row should be filtered out
    )
    con.execute(
        "CREATE TABLE nav_history ("
        "  instrument_id VARCHAR, date DATE, nav DOUBLE"
        ")"
    )
    # 8 NAV points → weekly return computable.
    for i, nav in enumerate([1.10, 1.09, 1.08, 1.07, 1.06, 1.05, 1.04, 1.00]):
        con.execute(
            "INSERT INTO nav_history VALUES (?, ?, ?)",
            ["510300", f"2026-05-{18 + i:02d}", nav],
        )
    con.close()

    macro, returns = read_live_decision_inputs(tmp_path, {"510300"})

    assert macro == {"vix": 16.76}
    # latest (1.10) / oldest (1.00) - 1 = 0.10
    assert returns["510300"] == pytest.approx(0.10)


def test_read_live_decision_inputs_skips_instruments_with_too_few_navs(
    tmp_path: Path,
) -> None:
    """Fewer than 5 NAV rows → instrument absent from returns dict.
    Renderer shows 'missing' rather than a spurious value."""
    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_path = db_dir / "local.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE macro_series (series_id VARCHAR, date DATE, value DOUBLE)"
    )
    con.execute(
        "CREATE TABLE nav_history (instrument_id VARCHAR, date DATE, nav DOUBLE)"
    )
    # Only 4 NAV rows — below the 5-row threshold.
    for i, nav in enumerate([1.10, 1.09, 1.08, 1.07]):
        con.execute(
            "INSERT INTO nav_history VALUES (?, ?, ?)",
            ["510300", f"2026-05-{18 + i:02d}", nav],
        )
    con.close()

    macro, returns = read_live_decision_inputs(tmp_path, {"510300"})
    assert macro == {}
    assert returns == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/decision/test_live_inputs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.decision.live_inputs'`.

- [ ] **Step 3: Create the new module**

Create `src/irc/decision/live_inputs.py`:

```python
"""Read-only I/O wrapper around `data/local.duckdb` for the decision +
memo renderers.

Exposes a single public function, `read_live_decision_inputs`, that returns
the latest macro snapshot + per-instrument weekly returns. Graceful degrade
(`({}, {})` on any failure) is preserved so callers can render placeholder
text rather than crash. Imported by both `commands/decision_cmd.py` and
`commands/memo_cmd.py` — single locus, no two-place drift.
"""
from __future__ import annotations

from pathlib import Path


def read_live_decision_inputs(
    repo_root: Path,
    instrument_ids: set[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Read latest macro snapshot + per-instrument weekly returns from the
    local DuckDB. Returns ``(macro_snapshot, weekly_return_by_id)``.

    Empty dicts on any failure — the renderer gracefully shows "未知" when
    a value is missing. Pure read; no caching, no mutation.
    """
    db_path = repo_root / "data" / "local.duckdb"
    if not db_path.exists():
        return {}, {}
    try:
        import duckdb  # local import — keep callers fast when db is absent
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        # Locked DBs (concurrent `irc run --only ingest`) and other I/O
        # failures should not block the decision report; render with
        # placeholders instead.
        print(
            f"WARNING: decision report could not read live macro/returns "
            f"({exc.__class__.__name__}); per-pick triggers will show "
            f"'未知 / unknown'."
        )
        return {}, {}
    macro: dict[str, float] = {}
    returns: dict[str, float] = {}
    try:
        macro_df = con.execute(
            "SELECT series_id, value FROM ("
            "  SELECT series_id, value, "
            "         ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) AS rn"
            "  FROM macro_series"
            ") WHERE rn = 1"
        ).fetchdf()
        for _, r in macro_df.iterrows():
            try:
                macro[str(r["series_id"])] = float(r["value"])
            except (TypeError, ValueError):
                continue
        for iid in instrument_ids:
            navs = con.execute(
                "SELECT nav FROM nav_history WHERE instrument_id = ? "
                "ORDER BY date DESC LIMIT 8",
                [iid],
            ).fetchdf()
            if len(navs) < 5:
                continue
            latest = float(navs.iloc[0]["nav"])
            prior = float(navs.iloc[-1]["nav"])
            if prior > 0:
                returns[iid] = latest / prior - 1.0
    except Exception:
        pass
    finally:
        con.close()
    return macro, returns
```

- [ ] **Step 4: Run live-inputs tests**

Run: `uv run pytest tests/decision/test_live_inputs.py -v`
Expected: 3 passed.

- [ ] **Step 5: Replace local def in `decision_cmd.py` with import**

In `src/irc/commands/decision_cmd.py`:

Add to the import block at the top of the file (after the existing `from irc.decision.report import ...` line, line 11):

```python
from irc.decision.live_inputs import read_live_decision_inputs
```

Delete the now-duplicate definition (lines 93-150: `def _read_live_decision_inputs(...)` and its body).

Update the call site at line ~228:

```python
    macro_snapshot, weekly_returns = read_live_decision_inputs(root, trade_ids)
```

(drop the leading `_`).

- [ ] **Step 6: Verify the decision_cmd regression suite still passes**

Run: `uv run pytest tests/decision/ tests/commands/ -v -k "decision"`
Expected: every test continues to pass — extraction is mechanical.

- [ ] **Step 7: Commit**

```bash
git add src/irc/decision/live_inputs.py src/irc/commands/decision_cmd.py tests/decision/test_live_inputs.py
git commit -m "$(cat <<'EOF'
refactor(decision): extract read_live_decision_inputs into decision/live_inputs.py

Promotes the DuckDB read helper from decision_cmd.py-private to a shared
location so memo_cmd.py::run_memo (item 003) can feed the same
(macro_snapshot, weekly_return_by_id) shape into the picks-table renderer.
Graceful degrade (returns ({}, {}) on DB-missing / connect-fail) preserved.
EOF
)"
```

---

## Task 3: Add `_format_trigger_status_compact` helper to `picks_table.py`

**Files:**
- Modify: `src/irc/memo/picks_table.py` (add helper)
- Create: `tests/memo/test_trigger_status_compact.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memo/test_trigger_status_compact.py`:

```python
"""Tests for `_format_trigger_status_compact` — the picks-table-cell
compact form of the decision-report's `format_why_when_line`.

Per trigger: `{trigger.name} {marker}` where marker is one of ✓ / ✗ / ⚠.
Multi-trigger: `<br>` joined, YAML insertion order preserved (no sort).
Empty triggers tuple → "" (renderer then emits "—" for the cell).
"""
from __future__ import annotations

from irc.memo.picks_table import _format_trigger_status_compact


def test_format_empty_triggers_returns_empty_string() -> None:
    """No triggers → empty string. Renderer converts "" to em-dash."""
    assert _format_trigger_status_compact(
        triggers=(),
        macro_snapshot={},
        weekly_return_by_id={},
        instrument_id="510300",
    ) == ""


def test_format_single_met_trigger_uses_checkmark() -> None:
    """Drawdown -5% under -4% threshold → met → ✓."""
    triggers = (
        {
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.05},
        instrument_id="510300",
    )
    assert out == "weekly_drawdown_4pct ✓"


def test_format_single_not_met_trigger_uses_cross() -> None:
    """Drawdown -1% above -4% threshold → not_met → ✗."""
    triggers = (
        {
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.01},
        instrument_id="510300",
    )
    assert out == "weekly_drawdown_4pct ✗"


def test_format_single_missing_trigger_uses_warning() -> None:
    """No weekly_return for the instrument → missing → ⚠."""
    triggers = (
        {
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={},  # 510300 absent
        instrument_id="510300",
    )
    assert out == "weekly_drawdown_4pct ⚠"


def test_format_multi_trigger_joined_with_br_preserves_yaml_order() -> None:
    """Two triggers → one row, joined by <br>. YAML order from the input
    tuple is preserved (no sort, no shuffle)."""
    triggers = (
        {
            "name": "vix_above_25",
            "comparator": ">",
            "threshold": 25.0,
            "data_field": "macro.vix",
        },
        {
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={"vix": 27.0},  # met
        weekly_return_by_id={"510300": -0.01},  # not_met
        instrument_id="510300",
    )
    assert out == "vix_above_25 ✓<br>weekly_drawdown_4pct ✗"


def test_format_unknown_comparator_falls_back_to_missing() -> None:
    """Comparator that evaluate_trigger doesn't recognise → missing → ⚠."""
    triggers = (
        {
            "name": "weird_trigger",
            "comparator": "~~",
            "threshold": 0.0,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.05},
        instrument_id="510300",
    )
    assert out == "weird_trigger ⚠"


def test_format_trigger_with_missing_name_uses_default_label() -> None:
    """Defensive: trigger dict without a `name` key → label 'trigger'."""
    triggers = (
        {
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        },
    )
    out = _format_trigger_status_compact(
        triggers=triggers,
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.05},
        instrument_id="510300",
    )
    assert out == "trigger ✓"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/memo/test_trigger_status_compact.py -v`
Expected: FAIL with `ImportError: cannot import name '_format_trigger_status_compact'`.

- [ ] **Step 3: Implement the helper in `picks_table.py`**

In `src/irc/memo/picks_table.py`:

Add to the imports near the top (after the `from irc.opportunity.types import ThesisEvidence` line):

```python
from irc.decision.sizing import (
    TriggerSpec,
    evaluate_trigger,
    resolve_trigger_current_value,
)
```

Add the helper above `_format_score` (after `_format_citations_cell`):

```python
_TRIGGER_STATE_GLYPH: dict[str, str] = {
    "met": "✓",
    "not_met": "✗",
    "missing": "⚠",
}


def _format_trigger_status_compact(
    triggers: tuple[dict, ...] | list[dict],
    macro_snapshot: dict[str, float],
    weekly_return_by_id: dict[str, float],
    instrument_id: str,
) -> str:
    """Render the 触发状态 column cell. One line per trigger
    (`{name} {✓|✗|⚠}`), multi-trigger joined by ``<br>`` to keep the
    markdown row single-line (mirrors `_format_citations_cell`).

    YAML insertion order from `trade_plan.yaml::trades[*].triggers` is
    preserved (no re-sort). Empty tuple → "" (renderer emits em-dash).
    Trigger state is computed by `evaluate_trigger`; current value is
    resolved via `resolve_trigger_current_value`.
    """
    if not triggers:
        return ""
    parts: list[str] = []
    for trig in triggers:
        name = str(trig.get("name") or "trigger")
        spec = TriggerSpec(
            name=name,
            comparator=str(trig.get("comparator") or "<="),
            threshold=float(trig.get("threshold") or 0.0),
        )
        current, _unit = resolve_trigger_current_value(
            trig, instrument_id, macro_snapshot, weekly_return_by_id,
        )
        state = evaluate_trigger(spec, current)
        glyph = _TRIGGER_STATE_GLYPH.get(state, "⚠")
        parts.append(f"{name} {glyph}")
    return "<br>".join(parts)
```

- [ ] **Step 4: Run trigger-status-compact tests**

Run: `uv run pytest tests/memo/test_trigger_status_compact.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/picks_table.py tests/memo/test_trigger_status_compact.py
git commit -m "$(cat <<'EOF'
feat(memo): add _format_trigger_status_compact helper for §5 picks table

Pure renderer helper that formats trade_plan triggers as compact, table-cell
ready strings ({name} ✓/✗/⚠), <br>-joined across multiple triggers. Reuses
evaluate_trigger + resolve_trigger_current_value from decision/sizing.py so
memo and decision_report never drift on what a trigger's state means.
Empty input → empty string; renderer emits em-dash.
EOF
)"
```

---

## Task 4: Add two new fields to `PickRow` (defaults; no render changes yet)

**Files:**
- Modify: `src/irc/memo/picks_table.py` (extend dataclass only)
- Test: existing `tests/memo/test_picks_table.py` and `tests/memo/test_pick_rows.py` must stay green

- [ ] **Step 1: Write the failing default-value test**

Append to `tests/memo/test_picks_table.py`:

```python
def test_pick_row_tranche_cap_pct_defaults_to_none():
    """Backward compatibility: existing callers/tests omit the new field;
    default keeps the legacy construction site call sites compiling unchanged."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
    )
    assert row.tranche_cap_pct is None


def test_pick_row_trigger_status_defaults_to_empty_string():
    """Backward compatibility: omitted field defaults to '' so the renderer
    emits em-dash, matching the empty-citations convention."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
    )
    assert row.trigger_status == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/memo/test_picks_table.py::test_pick_row_tranche_cap_pct_defaults_to_none tests/memo/test_picks_table.py::test_pick_row_trigger_status_defaults_to_empty_string -v`
Expected: FAIL with `AttributeError: 'PickRow' object has no attribute 'tranche_cap_pct'` (and similar for `trigger_status`).

- [ ] **Step 3: Add the two fields to `PickRow`**

In `src/irc/memo/picks_table.py`, edit the `PickRow` dataclass to append the two fields after `decision_status`:

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
    valuation_state: str = ""
    venue_note: str = ""
    citations: tuple[ThesisEvidence, ...] = field(default_factory=tuple)
    # Gates verdict (actionable_buy / blocked / watch_only / avoid). Defaults
    # to watch_only so callers/tests that omit it stay backwards-compatible.
    decision_status: str = "watch_only"
    # Item 003: Decision Sheet mirror columns. Both default to safe sentinels
    # so legacy callers/tests (21 PickRow(...) call sites — all kwargs) stay
    # green; the renderer emits em-dash for missing values.
    tranche_cap_pct: float | None = None
    trigger_status: str = ""
```

- [ ] **Step 4: Run the two new tests + all existing picks-table / pick-rows tests**

Run: `uv run pytest tests/memo/test_picks_table.py tests/memo/test_pick_rows.py -v`
Expected: every test passes — defaults preserve backward compatibility for all 21 existing `PickRow(...)` call sites.

- [ ] **Step 5: Commit**

```bash
git add src/irc/memo/picks_table.py tests/memo/test_picks_table.py
git commit -m "$(cat <<'EOF'
feat(memo): add tranche_cap_pct + trigger_status fields to PickRow

Frozen dataclass appended with two default-valued fields:
- tranche_cap_pct: float | None = None  (per-tranche sizing cap, fraction of NAV)
- trigger_status:  str = ""              (pre-formatted compact trigger marker)
All 21 existing PickRow(...) call sites use kwargs and keep compiling untouched.
Renderer hookup follows in the next task.
EOF
)"
```

---

## Task 5: Extend `render_picks_table` header + row format + footnote

**Files:**
- Modify: `src/irc/memo/picks_table.py` (header, body line, footnote)
- Test: `tests/memo/test_picks_table.py` (add column-render + footnote tests)

- [ ] **Step 1: Write failing tests for header order, cell formats, and footnote**

Append to `tests/memo/test_picks_table.py`:

```python
def test_picks_table_header_contains_tranche_cap_and_trigger_status_columns():
    """Header order locked: ... | 主要理由 | 单次定投上限 | 触发状态 | 证据 |."""
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
    assert "触发状态" in cols
    # Order: 主要理由 → 单次定投上限 → 触发状态 → 证据
    assert cols.index("单次定投上限") == cols.index("主要理由") + 1
    assert cols.index("触发状态") == cols.index("单次定投上限") + 1
    assert cols.index("证据") == cols.index("触发状态") + 1


def test_picks_table_tranche_cap_renders_with_two_decimals_and_le_prefix():
    """`tranche_cap_pct=0.05` → cell shows `≤ 5.00%` (two decimals, locked)."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.2, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        tranche_cap_pct=0.05,
    )
    md = render_picks_table([row])
    assert "≤ 5.00%" in md


def test_picks_table_tranche_cap_none_renders_em_dash():
    """`tranche_cap_pct=None` → cell shows `—` (matches empty-citations convention)."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.0, composite_score=50.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        tranche_cap_pct=None,
    )
    md = render_picks_table([row])
    # Find the data row and confirm an em-dash appears
    data_lines = [line for line in md.split("\n")
                  if line.startswith("| A ")]
    assert data_lines, "no data row found for A"
    assert "| — |" in data_lines[0]


def test_picks_table_tranche_cap_zero_renders_em_dash():
    """`tranche_cap_pct=0.0` (observation-only pick) → cell shows `—`,
    not `≤ 0.00%` which would be visually misleading."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.0, composite_score=50.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        tranche_cap_pct=0.0,
    )
    md = render_picks_table([row])
    data_lines = [line for line in md.split("\n")
                  if line.startswith("| A ")]
    assert "≤ 0.00%" not in data_lines[0]
    assert "| — |" in data_lines[0]


def test_picks_table_trigger_status_renders_verbatim_when_non_empty():
    """Pre-formatted string is rendered as-is — renderer does not re-evaluate."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        trigger_status="vix_above_25 ✓<br>weekly_drawdown_4pct ✗",
    )
    md = render_picks_table([row])
    assert "vix_above_25 ✓<br>weekly_drawdown_4pct ✗" in md


def test_picks_table_trigger_status_empty_renders_em_dash():
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        trigger_status="",
    )
    md = render_picks_table([row])
    data_lines = [line for line in md.split("\n")
                  if line.startswith("| A ")]
    assert "| — |" in data_lines[0]


def test_picks_table_footnote_explains_tranche_cap_and_trigger_status():
    """Footnote text gains a short clause about both new columns. Existing
    audit P5 disclaimer (不构成投资建议) must remain the closing token."""
    md = render_picks_table([])
    assert "单次定投上限" in md
    assert "触发状态" in md
    assert "build" in md or "目标权重" in md
    # P5 lock: 不构成投资建议 stays present
    assert "不构成投资建议" in md


def test_picks_table_new_columns_carry_no_citation_markers():
    """SAME-3 invariant guard: 单次定投上限 + 触发状态 cells must not emit
    any [ref:...] markers. All citations live in the 证据 column."""
    import re
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.2, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        tranche_cap_pct=0.05,
        trigger_status="vix_above_25 ✓<br>weekly_drawdown_4pct ✗",
    )
    md = render_picks_table([row])
    data_lines = [line for line in md.split("\n")
                  if line.startswith("| A ")]
    assert data_lines
    cells = [c.strip() for c in data_lines[0].strip("|").split("|")]
    # The two new cells are at positions [-3] and [-2] (证据 is last)
    tranche_cell = cells[-3]
    trigger_cell = cells[-2]
    assert not re.search(r"\[ref:[0-9a-f]{16}\]", tranche_cell)
    assert not re.search(r"\[ref:[0-9a-f]{16}\]", trigger_cell)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/memo/test_picks_table.py -v`
Expected: 8 new tests FAIL (header missing new columns; data row format unchanged; footnote missing new sentence). All other tests continue to pass.

- [ ] **Step 3: Add cell-format helper for tranche cap**

In `src/irc/memo/picks_table.py`, add a small helper near `_format_citations_cell`:

```python
def _format_tranche_cap_cell(tranche_cap_pct: float | None) -> str:
    """Render the 单次定投上限 cell. None or ≤ 0 → em-dash (matches the
    empty-citations convention; spec AC3)."""
    if tranche_cap_pct is None or tranche_cap_pct <= 0.0:
        return "—"
    return f"≤ {tranche_cap_pct * 100:.2f}%"


def _format_trigger_status_cell(trigger_status: str) -> str:
    """Render the 触发状态 cell. Empty string → em-dash; otherwise verbatim
    (helper precomputed the `{name} ✓/✗/⚠<br>...` form upstream)."""
    if not trigger_status:
        return "—"
    return trigger_status
```

- [ ] **Step 4: Update `render_picks_table` to include the new columns**

Replace the `header` and the per-row `lines.append(...)` block inside `render_picks_table`:

```python
    header = (
        "| 代码 | 名称 | 角色 | 权重上限 | 综合分* | 决策 | 机会状态 | 本期行动 | "
        "主要理由 | 单次定投上限 | 触发状态 | 证据 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [header]
    for r in unique:
        weight_str = f"{r.target_weight * 100:.1f}%"
        score_str = _format_score(r)
        citations_cell = _format_citations_cell(r.citations)
        decision_cell = _DECISION_CN.get(r.decision_status, r.decision_status)
        tranche_cell = _format_tranche_cap_cell(r.tranche_cap_pct)
        trigger_cell = _format_trigger_status_cell(r.trigger_status)
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {r.role} | "
            f"{weight_str} | {score_str} | {decision_cell} | {r.opportunity_state} | "
            f"{_action_cn(r)} | {r.one_line_reason} | "
            f"{tranche_cell} | {trigger_cell} | {citations_cell} |"
        )
```

- [ ] **Step 5: Update `_SCORING_FOOTNOTE` to document the new columns**

Replace `_SCORING_FOOTNOTE` in `src/irc/memo/picks_table.py`:

```python
# Audit P5 (2026-05-20) required composite_score methodology disclosure.
# Single-line footnote keeps the table compact while satisfying the
# transparency requirement and carrying the load-bearing disclaimer.
# Item 003 (2026-05-26) added the 单次定投上限 + 触发状态 explainer
# sentence between the existing weight/score caveat and the closing 不构成
# 投资建议 disclaimer (P5 lock: disclaimer stays at the end).
_SCORING_FOOTNOTE = (
    "> *综合分由内部多因子模型生成（估值百分位 / 热度 / 长期逻辑 / 产品质量 / 宏观契合度 /"
    " 持有成本），仅作为辅助参考，不构成投资建议。表中权重均为上限约束（≤），"
    "非强制建仓目标；条件性减速定投在第7节触发条件未满足时实际执行量为零。"
    "估值维度缺失的综合分不得单独依据分值高低作为配置优先级依据。"
    "单次定投上限 = 目标权重 ÷ 4（build 模式），表示一次建仓的最大占总资产比例；"
    "触发状态反映第7节触发条件相对当前宏观/净值快照的评估结果。"
    "详见评分体系说明文档。"
)
```

- [ ] **Step 6: Run all picks_table tests + the existing regression suites**

Run: `uv run pytest tests/memo/test_picks_table.py tests/memo/test_pick_rows.py tests/memo/test_same_3_invariant.py -v`
Expected: all tests pass — new column tests green; legacy tests untouched (they don't check the column count); SAME-3 invariant intact (new cells emit no `[ref:...]` markers).

- [ ] **Step 7: Commit**

```bash
git add src/irc/memo/picks_table.py tests/memo/test_picks_table.py
git commit -m "$(cat <<'EOF'
feat(memo): render 单次定投上限 + 触发状态 columns in §5 picks table

Two new columns sit between 主要理由 and 证据:
- 单次定投上限: ≤ X.XX% (or — when None / 0)
- 触发状态:   {name} ✓/✗/⚠ joined by <br> (or — when empty)
Footnote gains a short explainer; P5 disclaimer remains the closing token.
New cells carry zero [ref:...] markers — SAME-3 invariant preserved.
EOF
)"
```

---

## Task 6: Thread live inputs through `_build_pick_rows`

**Files:**
- Modify: `src/irc/commands/memo_cmd.py:494-574` (extend `_build_pick_rows` signature + body)
- Test: `tests/memo/test_pick_rows.py` (extend)

- [ ] **Step 1: Write failing tests for `_build_pick_rows` populating the two new fields**

Append to `tests/memo/test_pick_rows.py`:

```python
def test_build_pick_rows_populates_tranche_cap_pct_in_build_mode():
    """`target_weight=0.20` + `build_mode='build'` → `tranche_cap_pct=0.05`
    (target ÷ 4 tranches). Reuses suggest_tranche_pct verbatim."""
    trades = [{"target": "510300", "target_weight": 0.20}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, _, _ = _build_pick_rows(
        trades, opportunity, {"scores": []},
        build_mode="build",
    )
    assert pick_rows[0].tranche_cap_pct == 0.05


def test_build_pick_rows_populates_trigger_status_from_trade_triggers():
    """Triggers on the trade row → compact-format string on the PickRow."""
    trades = [{
        "target": "510300",
        "target_weight": 0.20,
        "triggers": [{
            "name": "weekly_drawdown_4pct",
            "comparator": "<=",
            "threshold": -0.04,
            "data_field": "instrument.weekly_return",
        }],
    }]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, _, _ = _build_pick_rows(
        trades, opportunity, {"scores": []},
        build_mode="build",
        macro_snapshot={},
        weekly_return_by_id={"510300": -0.05},
    )
    assert pick_rows[0].trigger_status == "weekly_drawdown_4pct ✓"


def test_build_pick_rows_defaults_when_live_inputs_omitted():
    """Legacy callers (e.g. older tests) omit the new kwargs; fields fall
    back to safe sentinels — None for cap (when build_mode default = 'build'
    still yields target/4) and "" for triggers (no live data to evaluate)."""
    trades = [{"target": "510300", "target_weight": 0.20}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, {"scores": []})
    # build_mode defaults to 'build', so cap is computed.
    assert pick_rows[0].tranche_cap_pct == 0.05
    # No triggers on the trade → empty string.
    assert pick_rows[0].trigger_status == ""


def test_build_pick_rows_missing_triggers_yields_empty_trigger_status():
    """Trade without `triggers` key → trigger_status = "" (renderer → —)."""
    trades = [{"target": "510300", "target_weight": 0.20}]
    opportunity = {"rows": [_op_row(iid="510300")]}
    pick_rows, _, _ = _build_pick_rows(
        trades, opportunity, {"scores": []},
        build_mode="build",
        macro_snapshot={"vix": 16.76},
        weekly_return_by_id={"510300": -0.01},
    )
    assert pick_rows[0].trigger_status == ""


def test_build_pick_rows_zero_weight_yields_zero_cap():
    """target_weight=0 (observation-only) → tranche_cap_pct=0.0; renderer
    will emit em-dash (per spec AC11)."""
    trades = [{"target": "510300", "target_weight": 0.0}]
    opportunity = {"rows": [_op_row(iid="510300", opportunity_state="small_watch")]}
    pick_rows, _, _ = _build_pick_rows(
        trades, opportunity, {"scores": []},
        build_mode="build",
    )
    assert pick_rows[0].tranche_cap_pct == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/memo/test_pick_rows.py -v -k "tranche_cap_pct or trigger_status or zero_weight"`
Expected: 5 FAIL — `_build_pick_rows` doesn't accept the new kwargs yet, and the constructed `PickRow` has default-`None` / default-`""` for the new fields.

- [ ] **Step 3: Extend `_build_pick_rows` signature + body**

In `src/irc/commands/memo_cmd.py`:

Find the existing import for picks-table helpers (the line near top with `from irc.memo.picks_table import ...`). It currently imports `PickRow, render_picks_table, render_failure_sections`. Extend it to add the compact helper:

```python
from irc.memo.picks_table import (
    PickRow,
    _format_trigger_status_compact,
    render_failure_sections,
    render_picks_table,
)
```

Add an import for `suggest_tranche_pct`:

```python
from irc.decision.sizing import suggest_tranche_pct
```

(if not already present — check existing imports first).

Replace the `_build_pick_rows` signature at line 494:

```python
def _build_pick_rows(
    trades: list[dict],
    opportunity: dict,
    scoring: dict,
    extra_names: dict[str, str] | None = None,
    *,
    qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT,
    build_mode: str = "build",
    macro_snapshot: dict[str, float] | None = None,
    weekly_return_by_id: dict[str, float] | None = None,
) -> tuple[list[PickRow], list[dict], list[dict]]:
```

Add at the top of the function body (after the `extra_names = extra_names or {}` line ~516) two more nil-safe coalesces:

```python
    macro_snapshot = macro_snapshot or {}
    weekly_return_by_id = weekly_return_by_id or {}
```

Inside the `for t in trades:` loop, just before the `pick_rows.append(PickRow(...))` block (~line 557), compute the two new field values:

```python
        target_weight = float(t.get("target_weight") or 0.0)
        tranche_cap_pct = suggest_tranche_pct(target_weight, build_mode)
        trigger_status = _format_trigger_status_compact(
            tuple(t.get("triggers") or ()),
            macro_snapshot,
            weekly_return_by_id,
            str(iid_raw),
        )
```

Pass them into the `PickRow(...)` constructor by appending two kwargs at the end of the existing call (preserving the existing field order). Also reuse the local `target_weight` for the existing `target_weight=...` line (avoid double evaluation):

```python
        pick_rows.append(PickRow(
            instrument_id=iid_raw,
            name_cn=name,
            asset_class=op.get("asset_class") or t.get("asset_class", ""),
            role=t.get("role") or "",
            target_weight=target_weight,
            composite_score=float(score),
            opportunity_state=opp_state,
            dca_action=dca,
            risk_action="none",
            one_line_reason=reason,
            valuation_state=op.get("valuation_state", ""),
            venue_note=str(t.get("venue_note", "")),
            citations=citations,
            decision_status=decision_status,
            tranche_cap_pct=tranche_cap_pct,
            trigger_status=trigger_status,
        ))
```

- [ ] **Step 4: Run the new + existing pick-rows tests**

Run: `uv run pytest tests/memo/test_pick_rows.py -v`
Expected: all tests pass — the 5 new tests are green, every existing test stays green (defaults preserve legacy behavior).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/memo_cmd.py tests/memo/test_pick_rows.py
git commit -m "$(cat <<'EOF'
feat(memo): wire tranche_cap_pct + trigger_status into _build_pick_rows

_build_pick_rows gains three optional kwargs (build_mode, macro_snapshot,
weekly_return_by_id) and populates PickRow's two new fields per trade:
- tranche_cap_pct = suggest_tranche_pct(target_weight, build_mode)
- trigger_status  = _format_trigger_status_compact(trade.triggers, ...)
All legacy call sites work unchanged (defaults nil-safe).
EOF
)"
```

---

## Task 7: Wire `run_memo` to read live inputs and feed `_build_pick_rows`

**Files:**
- Modify: `src/irc/commands/memo_cmd.py` (imports + `run_memo` body)

- [ ] **Step 1: Verify the integration smoke path — search for existing `run_memo` tests**

Run: `grep -rn "run_memo" tests/memo/ tests/commands/ 2>/dev/null || true`
Expected: locate any existing integration test. If none touches the picks-table path, the lockdown integration suite (`tests/integration/test_publishable_set_lockdown.py`) covers the byte-equality contract on the full pipeline.

- [ ] **Step 2: Add the import to `memo_cmd.py`**

In `src/irc/commands/memo_cmd.py`, add at the top with the other `irc.decision.*` imports:

```python
from irc.decision.live_inputs import read_live_decision_inputs
```

- [ ] **Step 3: Resolve macro + weekly returns in `run_memo` and thread them through**

In `run_memo`, locate the `_build_pick_rows(...)` call site (~line 616). Just BEFORE that call (after `trades = list(plan.get("trades") or [])` and the `fallback_names` / `_qdii_max` blocks), insert:

```python
    # Item 003: feed the same (macro_snapshot, weekly_return_by_id) into the
    # picks-table renderer that the Decision Sheet uses, so 单次定投上限 +
    # 触发状态 columns can compute live trigger states. Graceful degrade:
    # read_live_decision_inputs returns ({}, {}) when data/local.duckdb is
    # absent — renderer then shows em-dash.
    trade_ids = {str(t.get("target")) for t in trades if t.get("target")}
    macro_snapshot, weekly_return_by_id = read_live_decision_inputs(root, trade_ids)
    build_mode = str(plan.get("mode") or "build")
```

Then update the `_build_pick_rows(...)` call to thread the three new kwargs:

```python
    pick_rows, absent_targets, gapped_targets = _build_pick_rows(
        trades, opportunity, scoring, fallback_names,
        qdii_max_premium_pct=_qdii_max,
        build_mode=build_mode,
        macro_snapshot=macro_snapshot,
        weekly_return_by_id=weekly_return_by_id,
    )
```

- [ ] **Step 4: Run the full memo + decision unit suites**

Run: `uv run pytest tests/memo/ tests/decision/ -v`
Expected: every test passes — extraction + wiring are non-breaking.

- [ ] **Step 5: Run the SAME-3 invariant + auditor + numeric audit guards**

Run: `uv run pytest tests/memo/test_same_3_invariant.py tests/memo/test_numeric_audit.py tests/memo/test_audit_blocking.py -v`
Expected: all pass — new cells carry no citation markers; numeric audit unaffected.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/memo_cmd.py
git commit -m "$(cat <<'EOF'
feat(memo): run_memo reads live macro+returns and feeds picks-table renderer

run_memo now calls read_live_decision_inputs and threads
(build_mode, macro_snapshot, weekly_return_by_id) into _build_pick_rows so
the §5 picks table's 单次定投上限 + 触发状态 columns reflect today's
DuckDB snapshot. DB-missing → graceful degrade (renderer emits —).
Closes item 003 wiring; decision_report.md output unchanged.
EOF
)"
```

---

## Task 8: Final regression sweep + lint

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full unit + integration suites**

Run: `uv run pytest`
Expected: every test passes. Live tests (gated by `IRC_*=1`) remain skipped.

- [ ] **Step 2: Run the two-run lockdown determinism test if available locally**

Run: `uv run pytest tests/integration/test_publishable_set_lockdown.py -v`
Expected: passes (or is skipped on missing live data). Memo §5 picks-table determinism: two runs over identical inputs produce byte-identical output.

- [ ] **Step 3: Lint**

Run: `uv run ruff check src tests`
Expected: zero errors.

- [ ] **Step 4: Final commit if any lint touch-ups required**

If lint produced fixes, commit:

```bash
git add -u
git commit -m "chore(memo): ruff fixups for item 003"
```

Otherwise skip.

---

## Self-Review (run before handoff)

**Spec coverage matrix:**

| Spec AC | Plan Task |
|---|---|
| AC1 — `PickRow` two new fields with defaults | Task 4 |
| AC2 — header order `… 主要理由 \| 单次定投上限 \| 触发状态 \| 证据 \|` | Task 5 |
| AC3 — `≤ X.XX%` / `—` cap cell | Task 5 |
| AC4 — `trigger_status` verbatim or `—` | Task 5 |
| AC5 — `_format_trigger_status_compact` helper | Task 3 |
| AC6 — `_build_pick_rows` populates both fields | Task 6 |
| AC7 — `read_live_decision_inputs` extraction | Task 2 + Task 7 |
| AC8 — `MACRO_FIELD_TO_KEY` + `resolve_trigger_current_value` extraction | Task 1 |
| AC9 — footnote update | Task 5 |
| AC10 — determinism | Task 8 (lockdown test) |
| AC11 — empty / zero-weight / DB-missing edge cases | Task 5 + Task 6 |
| AC12 — test coverage (3 new test files + 2 extended) | Tasks 1, 2, 3, 4, 5, 6 |
| AC13 — `decision_report.md` byte-identical | Task 1 step 6 (regression) |
| AC14 — SAME-3 not broken | Task 5 step 6 + step 7 (new test guard) |

**Placeholder scan:** no `TBD` / `TODO` / "implement later". Every step has concrete code or shell.

**Type consistency:**
- `resolve_trigger_current_value(trig, instrument_id, macro_snapshot, weekly_return_by_id) -> tuple[float | None, str]` — same signature in Task 1 and Task 3 (consumer).
- `read_live_decision_inputs(repo_root, instrument_ids) -> tuple[dict[str, float], dict[str, float]]` — same signature in Task 2 and Task 7 (consumer).
- `_format_trigger_status_compact(triggers, macro_snapshot, weekly_return_by_id, instrument_id) -> str` — same signature in Task 3 and Task 6 (consumer).
- `PickRow.tranche_cap_pct: float | None`, `PickRow.trigger_status: str` — consistent across Tasks 4, 5, 6.
- Footnote sentence in Task 5 references `单次定投上限`, `触发状态`, `build` — same vocabulary used in spec AC9, AC2.
