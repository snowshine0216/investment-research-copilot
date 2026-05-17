# Item 010 — Implementation Plan

> Reference: `docs/AUTODEV-LOOP/items/010-spec.md`. Base branch: `feat/evidence-wiring-and-memo-enrichment`. Sub-branch: `claude/p1p2-010-geopolitical-stress-wired`.

**Goal:** Replace the hardcoded `geopolitical_stress_0to1=0.4` at `src/irc/commands/gold_cmd.py:74` with a value derived from the persisted `geopolitics` theme report. Default to 0.4 when no usable report exists, so behavior is unchanged in degraded/unwired scenarios.

**Architecture:** A new pure-function helper `geopolitical_stress_from_theme_report` lives in `src/irc/research/geopolitical_stress.py`. `gold_cmd.py` loads the existing `ThemeReport` cache via `load_theme_reports()` (already in `research/persistence.py`) and passes the `geopolitics` entry to the helper.

---

## Task 1: Create the helper

**Files:** `src/irc/research/geopolitical_stress.py` (new), `tests/research/test_geopolitical_stress.py` (new)

### Step 1.1: Write the failing test
- [ ] Create `tests/research/test_geopolitical_stress.py`:

```python
from __future__ import annotations
from irc.research.theme_research import ThemeReport
from irc.research.geopolitical_stress import (
    geopolitical_stress_from_theme_report,
    GEOPOLITICAL_STRESS_DEFAULT,
)


def _report(report_md: str = "", failure_reason: str = "") -> ThemeReport:
    return ThemeReport(
        theme="geopolitics", query="q", locale="en",
        report_md=report_md, citations=[], failure_reason=failure_reason,
    )


def test_none_returns_default():
    assert geopolitical_stress_from_theme_report(None) == GEOPOLITICAL_STRESS_DEFAULT


def test_failed_report_returns_default():
    r = _report(failure_reason="no_results")
    assert geopolitical_stress_from_theme_report(r) == GEOPOLITICAL_STRESS_DEFAULT


def test_empty_report_returns_default():
    r = _report(report_md="   ")
    assert geopolitical_stress_from_theme_report(r) == GEOPOLITICAL_STRESS_DEFAULT


def test_stress_keywords_push_score_above_default():
    r = _report(report_md=(
        "Russia escalated the war this week. New sanctions on China. "
        "Tariff hike announced. Strike in the Red Sea. "
        "Conflict 冲突 制裁 升级."
    ))
    assert geopolitical_stress_from_theme_report(r) > GEOPOLITICAL_STRESS_DEFAULT


def test_calm_keywords_pull_score_below_default():
    r = _report(report_md=(
        "Peace talks resumed. Ceasefire holding. Agreement signed. "
        "缓和 协议 停火."
    ))
    assert geopolitical_stress_from_theme_report(r) < GEOPOLITICAL_STRESS_DEFAULT


def test_score_clipped_to_unit_interval():
    r = _report(report_md=("war sanction tariff strike conflict " * 50))
    assert 0.0 <= geopolitical_stress_from_theme_report(r) <= 1.0


def test_neutral_report_returns_default():
    r = _report(report_md="Markets closed flat on quiet trading.")
    assert geopolitical_stress_from_theme_report(r) == GEOPOLITICAL_STRESS_DEFAULT
```

### Step 1.2: Run tests
- [ ] Run: `uv run pytest tests/research/test_geopolitical_stress.py -v`
- [ ] Expected: ImportError — module doesn't exist yet.

### Step 1.3: Implement the helper
- [ ] Create `src/irc/research/geopolitical_stress.py`:

```python
from __future__ import annotations

from irc.research.theme_research import ThemeReport

GEOPOLITICAL_STRESS_DEFAULT: float = 0.4
"""Default returned when no usable theme report is available. Matches the
prior hardcoded value at gold_cmd.py:74 so behavior is unchanged on the
degraded path."""

_STRESS_TOKENS: tuple[str, ...] = (
    # English
    "war", "sanction", "tariff", "strike", "conflict", "escalat",
    "invasion", "missile", "attack", "embargo",
    # Chinese
    "战争", "制裁", "关税", "冲突", "升级", "袭击", "导弹", "封锁",
)

_CALM_TOKENS: tuple[str, ...] = (
    # English
    "peace", "ceasefire", "agreement", "truce", "deescalat", "diplomacy",
    # Chinese
    "缓和", "协议", "停火", "和谈", "和平",
)

# Each net stress-vs-calm hit moves the score by this much; chosen so a
# handful of clear hits is enough to deviate meaningfully from the default
# without saturating on a single mention.
_PER_HIT_DELTA: float = 0.05


def _count_hits(text: str, tokens: tuple[str, ...]) -> int:
    lower = text.lower()
    return sum(lower.count(token) for token in tokens)


def _has_usable_report(report: ThemeReport | None) -> bool:
    if report is None:
        return False
    if report.failure_reason:
        return False
    return bool(report.report_md and report.report_md.strip())


def geopolitical_stress_from_theme_report(
    report: ThemeReport | None,
    *,
    default: float = GEOPOLITICAL_STRESS_DEFAULT,
) -> float:
    """Derive a 0..1 geopolitical-stress score from a theme report.

    Returns `default` when the report is missing, failed, or empty. Otherwise
    counts stress vs calm keyword hits in the report body, applies a small
    per-hit delta to the default, and clips to [0, 1].

    Intentionally simple — the goal is to remove the hardcoded constant,
    not to build a sentiment model. Replace with something stronger when
    we have one.
    """
    if not _has_usable_report(report):
        return default
    assert report is not None  # for type checker
    stress = _count_hits(report.report_md, _STRESS_TOKENS)
    calm = _count_hits(report.report_md, _CALM_TOKENS)
    net = stress - calm
    if net == 0:
        return default
    score = default + (net * _PER_HIT_DELTA)
    return max(0.0, min(1.0, score))
```

### Step 1.4: Run tests, verify pass
- [ ] Run: `uv run pytest tests/research/test_geopolitical_stress.py -v`
- [ ] Expected: 7 PASS.

### Step 1.5: Commit
- [ ] Run:

```bash
git add src/irc/research/geopolitical_stress.py tests/research/test_geopolitical_stress.py
git commit -m "feat(research): geopolitical_stress_from_theme_report helper (keyword tally)"
```

---

## Task 2: Wire the helper into `gold_cmd.py`

**Files:** `src/irc/commands/gold_cmd.py:74` (and imports at top)

### Step 2.1: Write the failing test
- [ ] Add to `tests/commands/test_gold_cmd.py` (read the file first to find the existing test pattern; pick a fixture-driven approach already in use):

```python
def test_gold_uses_geopolitical_stress_from_theme_report(monkeypatch, tmp_path):
    """When a stressful geopolitics theme report exists in data/research/,
    gold_cmd uses a stress score above the hardcoded 0.4 default."""
    from irc.research.theme_research import ThemeReport

    captured: dict[str, float] = {}
    stress_report = ThemeReport(
        theme="geopolitics", query="q", locale="en",
        report_md="war war sanction tariff strike conflict",
        citations=[], failure_reason="",
    )

    monkeypatch.setattr(
        "irc.commands.gold_cmd.load_theme_reports",
        lambda root: {"geopolitics": stress_report},
    )

    def capture_score(inputs, cfg):
        captured["stress"] = inputs.geopolitical_stress_0to1
        from irc.scoring.gold_score import compute_gold_score as real_fn
        return real_fn(inputs, cfg)

    monkeypatch.setattr("irc.commands.gold_cmd.compute_gold_score", capture_score)

    # ... call run_gold with a minimal fixture (use the existing test_gold_cmd helpers)
    # Then assert captured["stress"] > 0.4
```

> The exact call site / fixture for `run_gold` lives in `tests/commands/test_gold_cmd.py`. Read the existing tests to see how they invoke `run_gold` (`repo: Path` fixture is the pattern, see `test_ingest_cmd.py`). The assertion is the important part: `captured["stress"] > 0.4`.

### Step 2.2: Run the test, verify it fails
- [ ] Run: `uv run pytest tests/commands/test_gold_cmd.py::test_gold_uses_geopolitical_stress_from_theme_report -v`
- [ ] Expected: FAIL — the call to `load_theme_reports` doesn't happen yet, so the monkeypatch is unreachable.

### Step 2.3: Wire the helper
- [ ] In `src/irc/commands/gold_cmd.py`, add to imports near the top:

```python
from irc.research.persistence import load_theme_reports
from irc.research.geopolitical_stress import geopolitical_stress_from_theme_report
```

- [ ] Replace the body around line 68-74 (the `GoldDriverInputs(...)` construction):

```python
        reports = load_theme_reports(root)
        geo_stress = geopolitical_stress_from_theme_report(
            reports.get("geopolitics"),
        )
        inputs = GoldDriverInputs(
            real_yield_10y_tips=_macro_value(con, "DGS10", 1.65) - 2.30,
            dxy=_macro_value(con, "DXY", 104.0),
            inflation_5y5y=_macro_value(con, "T5YIFR", 2.30),
            cb_purchases_yearly_tons=cb_tons,
            etf_holdings_30d_change_tons=etf_change,
            geopolitical_stress_0to1=geo_stress,
        )
```

- [ ] Update the WARN line just below (the existing check looks for stub geo_stress):

```python
        if cb_tons == 0.0 or etf_change == 0.0:
            print("WARN: gold driver(s) using stub value; "
                  "WGC CSV absent for cb_purchases/etf_holdings → 0.0 fallback")
```

(Drop the `(geo_stress)` hint since it's no longer stub-by-default.)

### Step 2.4: Run the new test, verify pass
- [ ] Run: `uv run pytest tests/commands/test_gold_cmd.py::test_gold_uses_geopolitical_stress_from_theme_report -v`
- [ ] Expected: PASS.

### Step 2.5: Run the full gold test suite
- [ ] Run: `uv run pytest tests/commands/test_gold_cmd.py tests/commands/test_gold_cmd_real_drivers.py -v`
- [ ] Expected: all PASS.

### Step 2.6: Commit
- [ ] Run:

```bash
git add src/irc/commands/gold_cmd.py tests/commands/test_gold_cmd.py
git commit -m "feat(gold): wire geopolitical_stress from persisted geopolitics theme report"
```

---

## Task 3: Full-suite verification

### Step 3.1: Run all tests
- [ ] Run: `uv run pytest -q -x`
- [ ] Expected: all PASS.

### Step 3.2: Ruff
- [ ] Run: `uv run ruff check src/irc/research/geopolitical_stress.py src/irc/commands/gold_cmd.py tests/research/test_geopolitical_stress.py`
- [ ] Expected: no new findings.
