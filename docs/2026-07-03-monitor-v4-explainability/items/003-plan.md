# Item 003 — Divergence Caveat Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixed divergence caveat strings on fund-card risk blocks with parametrized detail that names the disagreeing factors and their signed values, keeping the static map as fallback.

**Architecture:** One new pure function `divergence_caveat_detail(code, contributions)` in `src/irc/monitor/render_factors.py` renders the P6-locked formats (three pairwise conflict lines, a sign-grouped `low_factor_agreement` form, a dispersion-σ form) and delegates every degraded case to the existing `divergence_caveat(code)`. The σ threshold literal `0.5` in `signal._divergence` is promoted to `_LOW_AGREEMENT_STDEV` and imported by the renderer so display can never drift from the gate. The single production call site (`render_cards.risk_block_html`) swaps to the new function.

**Tech Stack:** Python 3.12, stdlib only (`statistics.pstdev`, `html.escape`), pytest via `uv run pytest`, ruff (line-length 100).

**Spec:** `docs/2026-07-03-monitor-v4-explainability/items/003-spec.md` (honor Resolved decisions G1–G12).

## Global Constraints

- Branch `claude/monitor-v4-explainability-003` already exists (cut from `autodev/monitor-v4-explainability-feature`). Work on it. Commit per task; do NOT push (orchestrator pushes).
- NO `schema_version` change, NO `_ENGINE_VERSION` change (grill-locked). NO edits under `src/irc/monitor/eval/`.
- Diff scope: only `src/irc/monitor/render_factors.py`, `src/irc/monitor/render_cards.py`, `src/irc/monitor/signal.py`, `tests/monitor/test_render_factors.py`, `tests/monitor/test_render_cards.py`, `tests/monitor/test_signal.py`.
- Pure functions, no mutation, no I/O in the new code; gloss/display tables are module-level constants.
- Source files stay < 200 lines; functions < 20 lines.
- Number format is ASCII `{:+.2f}` (never the typographic `−` U+2212). σ displayed `{:.2f}`; threshold displayed `{:g}` (renders `0.5`, never `0.50`). Comparison uses the RAW recomputed pstdev, before any rounding (G2).
- Negative-zero normalization: format `value + 0.0` so `-0.0` renders `+0.00` (G8).
- All fallback paths delegate to `divergence_caveat(code)` — never read `_DIVERGENCE_CAVEATS` directly from the detail function (G5).
- `divergence_caveat`, `factor_table_html`, `returns_table_html`, `CANONICAL_FACTOR_ORDER`, and all `render_cards` exports keep their signatures. The existing exact-string tests at `tests/monitor/test_render_factors.py:13-26` must pass UNMODIFIED.
- NEVER run `uv run pytest tests/commands/` as a whole directory — it hangs on suite ordering. Per-file only.
- Lint gate: `uv run ruff check src tests` must be clean after every task.

---

### Task 1: Promote the σ threshold to `_LOW_AGREEMENT_STDEV` in signal.py

**Files:**
- Modify: `src/irc/monitor/signal.py` (line 12 area + line 59)
- Test: `tests/monitor/test_signal.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `signal._LOW_AGREEMENT_STDEV: float = 0.5` — imported by Task 3 (`from irc.monitor.signal import _LOW_AGREEMENT_STDEV`). Pure rename of an existing inline literal; `_divergence` behavior is byte-identical.

- [ ] **Step 1: Confirm branch and baseline green**

Run:
```bash
git branch --show-current
uv run pytest tests/monitor/test_signal.py tests/monitor/test_render_factors.py tests/monitor/test_render_cards.py -q
```
Expected: branch prints `claude/monitor-v4-explainability-003`; all tests pass (exit 0). If the branch name differs, STOP and report — do not create branches.

- [ ] **Step 2: Write the failing test**

Append to the END of `tests/monitor/test_signal.py`:

```python
def test_low_agreement_stdev_constant_is_named_and_locked():
    # G1: the σ gate for low_factor_agreement is a named constant beside _DIVERGE,
    # imported by render_factors so the rendered "≥ 0.5" can never drift from the gate.
    from irc.monitor import signal
    assert signal._LOW_AGREEMENT_STDEV == 0.5
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_signal.py::test_low_agreement_stdev_constant_is_named_and_locked -v`
Expected: FAIL with `AttributeError: module 'irc.monitor.signal' has no attribute '_LOW_AGREEMENT_STDEV'`

- [ ] **Step 4: Implement the constant promotion**

In `src/irc/monitor/signal.py`, replace line 12:

```python
_DIVERGE = 0.3
```

with:

```python
_DIVERGE = 0.3
_LOW_AGREEMENT_STDEV = 0.5  # σ gate for low_factor_agreement; rendered in the caveat detail
```

Then in `_divergence`, replace line 59:

```python
    if len(vals) >= 2 and (statistics.pstdev(vals) >= 0.5 or (
```

with:

```python
    if len(vals) >= 2 and (statistics.pstdev(vals) >= _LOW_AGREEMENT_STDEV or (
```

No other change to `signal.py`.

- [ ] **Step 5: Run the full mirror test file to verify no behavior change**

Run: `uv run pytest tests/monitor/test_signal.py -v`
Expected: PASS — every pre-existing test green unchanged, plus the new constant test (spec AC-4: promotion changes no behavior).

- [ ] **Step 6: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/monitor/signal.py tests/monitor/test_signal.py
git commit -m "refactor(monitor): promote low-agreement sigma threshold to _LOW_AGREEMENT_STDEV"
```

---

### Task 2: `divergence_caveat_detail` — pairwise conflict lines + fallback routing

**Files:**
- Modify: `src/irc/monitor/render_factors.py` (constants after `_DIVERGENCE_CAVEATS`, functions after `divergence_caveat`)
- Test: `tests/monitor/test_render_factors.py`

**Interfaces:**
- Consumes: `FactorContribution` (already imported in both files), `divergence_caveat` (existing, unchanged).
- Produces: `divergence_caveat_detail(code: str, contributions: tuple[FactorContribution, ...]) -> str` — public, additive; Task 4 imports it into `render_cards.py`. In this task it handles the three pairwise codes and routes everything else (including `low_factor_agreement`, extended in Task 3) to `divergence_caveat(code)`.

- [ ] **Step 1: Write the failing tests**

In `tests/monitor/test_render_factors.py`, replace the import block (lines 2–4):

```python
from irc.monitor.render_factors import (
    CANONICAL_FACTOR_ORDER, divergence_caveat, factor_table_html, returns_table_html,
)
```

with:

```python
from irc.monitor.render_factors import (
    CANONICAL_FACTOR_ORDER, divergence_caveat, divergence_caveat_detail,
    factor_table_html, returns_table_html,
)
```

Then insert the following AFTER `test_unknown_divergence_code_is_escaped_passthrough` (currently ends line 26) and BEFORE the `_rec` helper:

```python
def _fc(name, value):
    return FactorContribution(name, 0.5, value, 0.5 * value, 1.0, True, "")


def test_trend_macro_conflict_detail_is_exact():
    contribs = (_fc("trend", -0.75), _fc("macro_tilt", 0.62))
    assert divergence_caveat_detail("trend_macro_conflict", contribs) == (
        "趋势与宏观背离：趋势 -0.75（价格动能向下） vs 宏观 +0.62（新闻/宏观偏多）"
    )


def test_trend_valuation_conflict_detail_is_exact():
    contribs = (_fc("trend", 0.45), _fc("valuation", -0.80))
    assert divergence_caveat_detail("trend_valuation_conflict", contribs) == (
        "趋势与估值背离：趋势 +0.45（价格动能向上） vs 估值 -0.80（估值偏贵）"
    )


def test_valuation_flow_conflict_detail_is_exact():
    contribs = (_fc("valuation", 0.80), _fc("flow", -0.45))
    assert divergence_caveat_detail("valuation_flow_conflict", contribs) == (
        "估值与资金流背离：估值 +0.80（估值偏便宜） vs 资金流 -0.45（资金净流出）"
    )


def test_pairwise_detail_missing_factor_falls_back_to_static_string():
    contribs = (_fc("trend", -0.75),)  # macro_tilt absent → AC-5 fallback
    assert divergence_caveat_detail("trend_macro_conflict", contribs) == (
        "趋势与宏观背离：价格动能与宏观信号方向相反"
    )


def test_detail_unknown_code_is_escaped_passthrough():
    assert divergence_caveat_detail("<x>", ()) == "&lt;x&gt;"
```

(Exact strings: full-width `：` and `（）`, ASCII `-`/`+` signs, single ASCII spaces around `vs`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: collection ERROR for the whole file — `ImportError: cannot import name 'divergence_caveat_detail' from 'irc.monitor.render_factors'`

- [ ] **Step 3: Implement pairwise detail**

In `src/irc/monitor/render_factors.py`, insert AFTER the `_DIVERGENCE_CAVEATS = { ... }` dict (after current line 13) and BEFORE `def divergence_caveat`:

```python
_PAIRWISE = {  # code → (title, factor_a, factor_b); factor order follows the code name
    "trend_valuation_conflict": ("趋势与估值背离", "trend", "valuation"),
    "trend_macro_conflict": ("趋势与宏观背离", "trend", "macro_tilt"),
    "valuation_flow_conflict": ("估值与资金流背离", "valuation", "flow"),
}
_DISPLAY_NAME = {"trend": "趋势", "macro_tilt": "宏观", "valuation": "估值", "flow": "资金流"}
_SIGN_GLOSS = {  # factor → (gloss when value >= 0, gloss when value < 0)
    "trend": ("价格动能向上", "价格动能向下"),
    "macro_tilt": ("新闻/宏观偏多", "新闻/宏观偏空"),
    "valuation": ("估值偏便宜", "估值偏贵"),
    "flow": ("资金净流入", "资金净流出"),
}
```

Then insert AFTER the existing `divergence_caveat` function (after current line 18) and BEFORE `def _num`:

```python
def _signed(v: float) -> str:
    return f"{v + 0.0:+.2f}"  # +0.0 normalizes -0.0 so it renders +0.00, never -0.00 (G8)


def _factor_phrase(name: str, value: float) -> str:
    pos_gloss, neg_gloss = _SIGN_GLOSS[name]
    gloss = neg_gloss if value < 0 else pos_gloss
    return f"{_DISPLAY_NAME[name]} {_signed(value)}（{gloss}）"


def _pairwise_detail(code: str, contributions: tuple[FactorContribution, ...]) -> str:
    title, a, b = _PAIRWISE[code]
    by = {c.name: c.value for c in contributions}
    if a not in by or b not in by:
        return divergence_caveat(code)  # AC-5: required factor absent → static fallback
    return f"{title}：{_factor_phrase(a, by[a])} vs {_factor_phrase(b, by[b])}"


def divergence_caveat_detail(code: str, contributions: tuple[FactorContribution, ...]) -> str:
    """PURE: divergence code + present contributions → parametrized caveat naming the
    disagreeing factors with signed values; every degraded case delegates to
    divergence_caveat(code) (static map / escaped-passthrough fallback, G5)."""
    if code in _PAIRWISE:
        return _pairwise_detail(code, contributions)
    return divergence_caveat(code)
```

Do NOT touch `divergence_caveat`, `_DIVERGENCE_CAVEATS`, or anything below `_num`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: PASS — all pre-existing tests (the exact-string tests at lines 13–26 unmodified) plus the 5 new ones.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/render_factors.py tests/monitor/test_render_factors.py
git commit -m "feat(monitor): pairwise divergence caveat detail with signed factor values"
```

---

### Task 3: `low_factor_agreement` detail — sign groups, 中性 tail, dispersion σ form

**Files:**
- Modify: `src/irc/monitor/render_factors.py`
- Test: `tests/monitor/test_render_factors.py`

**Interfaces:**
- Consumes: `signal._LOW_AGREEMENT_STDEV` (Task 1), `statistics.pstdev` (stdlib), `_signed` / `divergence_caveat` (Task 2), `CANONICAL_FACTOR_ORDER` (existing).
- Produces: the `low_factor_agreement` branch of `divergence_caveat_detail`. Branch order (AC-3/AC-4/Q4): fewer than 2 values → fallback; mixed signs → grouped form (even if σ ≥ 0.5); else raw σ ≥ threshold → σ sentence; else → fallback (Q9 honesty).

- [ ] **Step 1: Write the failing tests**

Append to the END of `tests/monitor/test_render_factors.py`:

```python
def test_low_agreement_mixed_sign_grouped_canonical_order():
    contribs = (_fc("heat", 0.30), _fc("macro_tilt", 0.62), _fc("trend", -0.75))
    assert divergence_caveat_detail("low_factor_agreement", contribs) == (
        "因子分歧较大：偏多 heat +0.30、macro_tilt +0.62 ↔ 偏空 trend -0.75"
    )


def test_low_agreement_zero_factor_appends_neutral_group():
    contribs = (
        _fc("heat", 0.30), _fc("macro_tilt", 0.62), _fc("trend", -0.75),
        _fc("constituent", 0.0),
    )
    assert divergence_caveat_detail("low_factor_agreement", contribs) == (
        "因子分歧较大：偏多 heat +0.30、macro_tilt +0.62 ↔ 偏空 trend -0.75、中性 constituent +0.00"
    )


def test_low_agreement_negative_zero_renders_plus_zero():
    contribs = (_fc("trend", 0.75), _fc("heat", -0.60), _fc("constituent", -0.0))
    out = divergence_caveat_detail("low_factor_agreement", contribs)
    assert "中性 constituent +0.00" in out  # G8: -0.0 lands in 中性, formatted +0.00
    assert "-0.00" not in out


def test_low_agreement_dispersion_only_sigma_sentence():
    # same-sign values; pstdev([0.10, 1.22]) = 0.56 — reproduces the locked example σ
    contribs = (_fc("trend", 0.10), _fc("macro_tilt", 1.22))
    assert divergence_caveat_detail("low_factor_agreement", contribs) == (
        "因子分歧较大：强度离散 σ=0.56 ≥ 0.5"
    )


def test_low_agreement_fewer_than_two_values_falls_back():
    assert divergence_caveat_detail("low_factor_agreement", (_fc("trend", 0.9),)) == (
        "因子分歧较大：各因子方向/强度不一致"
    )
    assert divergence_caveat_detail("low_factor_agreement", ()) == (
        "因子分歧较大：各因子方向/强度不一致"
    )


def test_low_agreement_sigma_below_threshold_falls_back():
    # same sign, pstdev([0.10, 0.30]) = 0.10 < 0.5 → never render a false σ claim (Q9)
    contribs = (_fc("trend", 0.10), _fc("macro_tilt", 0.30))
    assert divergence_caveat_detail("low_factor_agreement", contribs) == (
        "因子分歧较大：各因子方向/强度不一致"
    )


def test_grouped_hostile_factor_name_is_html_escaped():
    contribs = (_fc("<b>", 0.30), _fc("trend", -0.75))
    out = divergence_caveat_detail("low_factor_agreement", contribs)
    assert "<b>" not in out       # AC-8: lands inside <li> unescaped by the caller
    assert "&lt;b&gt;" in out


def test_grouped_unknown_factor_name_sorts_after_canonical():
    contribs = (_fc("zz_future", 0.20), _fc("heat", 0.30), _fc("trend", -0.75))
    out = divergence_caveat_detail("low_factor_agreement", contribs)
    assert "偏多 heat +0.30、zz_future +0.20" in out  # Q8: unknowns append in input order
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: 6 of the 8 new tests FAIL — `divergence_caveat_detail` currently routes `low_factor_agreement` to the static fallback `因子分歧较大：各因子方向/强度不一致`, so `test_low_agreement_mixed_sign_grouped_canonical_order`, `test_low_agreement_zero_factor_appends_neutral_group`, `test_low_agreement_negative_zero_renders_plus_zero`, `test_low_agreement_dispersion_only_sigma_sentence`, `test_grouped_hostile_factor_name_is_html_escaped`, `test_grouped_unknown_factor_name_sorts_after_canonical` all FAIL on their assertions. `test_low_agreement_fewer_than_two_values_falls_back` and `test_low_agreement_sigma_below_threshold_falls_back` already PASS (fallback IS the current behavior — they pin the AC-5 contract). All pre-existing tests PASS.

- [ ] **Step 3: Implement the low_factor_agreement branch**

In `src/irc/monitor/render_factors.py`:

3a. Replace the import block at the top of the file (currently lines 1–4):

```python
from __future__ import annotations
from html import escape
from irc.monitor.types import FactorContribution, FactorScore, SignalRecord
from irc.monitor.annotate import factor_annotation, composite_annotation
```

with:

```python
from __future__ import annotations
import statistics
from html import escape
from irc.monitor.types import FactorContribution, FactorScore, SignalRecord
from irc.monitor.annotate import factor_annotation, composite_annotation
from irc.monitor.signal import _LOW_AGREEMENT_STDEV
```

(Underscore cross-module import follows the existing `annotate.py` ← `signal._FAMILY_OF` precedent, G1. No import cycle: `signal.py` imports only from `types`.)

3b. Insert AFTER `_pairwise_detail` and BEFORE `divergence_caveat_detail`:

```python
def _canonical_order(cs: tuple[FactorContribution, ...]) -> tuple[FactorContribution, ...]:
    rank = {n: i for i, n in enumerate(CANONICAL_FACTOR_ORDER)}
    return tuple(sorted(cs, key=lambda c: rank.get(c.name, len(CANONICAL_FACTOR_ORDER))))


def _group(ordered: tuple[FactorContribution, ...], keep) -> str:
    return "、".join(f"{escape(c.name)} {_signed(c.value)}" for c in ordered if keep(c.value))


def _grouped_by_sign(contributions: tuple[FactorContribution, ...]) -> str:
    ordered = _canonical_order(contributions)
    pos = _group(ordered, lambda v: v > 0)
    neg = _group(ordered, lambda v: v < 0)
    zero = _group(ordered, lambda v: v == 0)
    tail = f"、中性 {zero}" if zero else ""  # Q5: exact-zero factors trail as 中性
    return f"因子分歧较大：偏多 {pos} ↔ 偏空 {neg}{tail}"


def _low_agreement_detail(contributions: tuple[FactorContribution, ...]) -> str:
    vals = [c.value for c in contributions]
    if len(vals) < 2:
        return divergence_caveat("low_factor_agreement")  # AC-5 fallback
    if any(v > 0 for v in vals) and any(v < 0 for v in vals):
        return _grouped_by_sign(contributions)  # Q4: grouped wins when signs conflict
    sigma = statistics.pstdev(vals)  # RAW value gates (G2); rounding is display-only
    if sigma < _LOW_AGREEMENT_STDEV:
        return divergence_caveat("low_factor_agreement")  # Q9: never a false σ claim
    return f"因子分歧较大：强度离散 σ={sigma:.2f} ≥ {_LOW_AGREEMENT_STDEV:g}"
```

3c. Replace the whole `divergence_caveat_detail` function (added in Task 2):

```python
def divergence_caveat_detail(code: str, contributions: tuple[FactorContribution, ...]) -> str:
    """PURE: divergence code + present contributions → parametrized caveat naming the
    disagreeing factors with signed values; every degraded case delegates to
    divergence_caveat(code) (static map / escaped-passthrough fallback, G5)."""
    if code in _PAIRWISE:
        return _pairwise_detail(code, contributions)
    if code == "low_factor_agreement":
        return _low_agreement_detail(contributions)
    return divergence_caveat(code)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: PASS — all tests, old and new.

- [ ] **Step 5: Verify no behavior change leaked into signal + line budget**

Run:
```bash
uv run pytest tests/monitor/test_signal.py -q
wc -l src/irc/monitor/render_factors.py
```
Expected: test_signal.py all PASS; render_factors.py < 200 lines (estimate ~145).

- [ ] **Step 6: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/monitor/render_factors.py tests/monitor/test_render_factors.py
git commit -m "feat(monitor): low_factor_agreement detail - sign groups, neutral tail, dispersion sigma form"
```

---

### Task 4: Call-site swap in `render_cards.risk_block_html`

**Files:**
- Modify: `src/irc/monitor/render_cards.py` (import line 5, comprehension line 102 — re-verify line numbers before editing; item 001 lands after 003 so drift is unlikely but possible)
- Test: `tests/monitor/test_render_cards.py`

**Interfaces:**
- Consumes: `divergence_caveat_detail` (Tasks 2–3), `SignalRecord.contributions` (existing field, sits next to the call site).
- Produces: `risk_block_html` renders parametrized caveats. Signature unchanged — `render_html.py:324` (the only other consumer) needs no edit.

- [ ] **Step 1: Write the failing test**

In `tests/monitor/test_render_cards.py`:

1a. Replace line 1:

```python
from irc.monitor.types import SignalRecord, NarrativeDoc, Claim
```

with:

```python
from irc.monitor.types import SignalRecord, NarrativeDoc, Claim, FactorContribution
```

1b. Replace the `_rec` helper (currently lines 11–16) — G6: extend with a `contribs=()` keyword so every existing call site is preserved byte-for-byte:

```python
def _rec(status="ok", bias="ADD_BIAS", c=0.5563, conf=0.9, fams=("price-momentum", "news"),
         aw=0.8, div=(), contribs=()):
    return SignalRecord(
        fund_id="x", status=status, bias=bias, composite=c, signal_confidence=conf,
        available_weight=aw, present_families=fams, contributions=contribs,
        divergence_codes=div,
    )
```

1c. Insert AFTER `test_risk_block_empty_renders_muted_placeholder` (currently ends line 84):

```python
def test_risk_block_divergence_detail_names_factors_not_static_string():
    # AC-7: with codes AND the required contributions, the risk block names the
    # disagreeing factors with signed values and drops the bare static string.
    contribs = (
        FactorContribution("trend", 0.5, -0.75, -0.375, 1.0, True, ""),
        FactorContribution("macro_tilt", 0.5, 0.62, 0.31, 1.0, True, ""),
    )
    html = risk_block_html(
        _rec(div=("trend_macro_conflict", "low_factor_agreement"), contribs=contribs),
        _narr(), _EMPTY_IDX)
    assert "趋势 -0.75" in html and "宏观 +0.62" in html   # pairwise detail
    assert "偏多 macro_tilt +0.62" in html                  # grouped low-agreement detail
    assert "各因子方向/强度不一致" not in html               # bare static string gone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_cards.py::test_risk_block_divergence_detail_names_factors_not_static_string -v`
Expected: FAIL — `assert '趋势 -0.75' in html` fails (call site still renders the static `divergence_caveat` strings).

- [ ] **Step 3: Swap the call site**

In `src/irc/monitor/render_cards.py`:

3a. Replace line 5 (G4 — REPLACE, do not extend; the old name would be an unused import):

```python
from irc.monitor.render_factors import divergence_caveat
```

with:

```python
from irc.monitor.render_factors import divergence_caveat_detail
```

3b. In `risk_block_html`, replace line 102:

```python
    caveats = [f"<li>{divergence_caveat(code)}</li>" for code in rec.divergence_codes]
```

with (wrapped — the one-line form exceeds ruff's 100-char limit):

```python
    caveats = [
        f"<li>{divergence_caveat_detail(code, rec.contributions)}</li>"
        for code in rec.divergence_codes
    ]
```

No other edits to `render_cards.py`.

- [ ] **Step 4: Run the full mirror test files to verify green**

Run: `uv run pytest tests/monitor/test_render_cards.py tests/monitor/test_render_factors.py -v`
Expected: PASS — all tests. Note `test_risk_block_maps_divergence_codes_to_caveats` (existing, contributions=()) stays green through the AC-5 fallback: `divergence_caveat_detail("trend_valuation_conflict", ())` → static `趋势与估值背离：…`.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/render_cards.py tests/monitor/test_render_cards.py
git commit -m "feat(monitor): risk block renders divergence detail from contributions"
```

---

### Task 5: Final verification (AC-9, AC-10) — no code changes expected

**Files:** none (verification only; fix-and-recommit only if a check fails).

- [ ] **Step 1: Full monitor suite**

Run: `uv run pytest tests/monitor/ -q`
Expected: all tests pass, 0 failures.

- [ ] **Step 2: Lint + size budget**

Run:
```bash
uv run ruff check src tests
wc -l src/irc/monitor/render_factors.py src/irc/monitor/render_cards.py src/irc/monitor/signal.py
```
Expected: `All checks passed!`; every file < 200 lines (render_factors ~145, render_cards ~138, signal ~95).

- [ ] **Step 3: Diff-scope check (AC-9)**

Run:
```bash
git diff --name-only autodev/monitor-v4-explainability-feature...HEAD
git diff autodev/monitor-v4-explainability-feature...HEAD | grep -E "schema_version|_ENGINE_VERSION"
```
Expected: first command lists EXACTLY these 6 files —
`src/irc/monitor/render_cards.py`, `src/irc/monitor/render_factors.py`, `src/irc/monitor/signal.py`, `tests/monitor/test_render_cards.py`, `tests/monitor/test_render_factors.py`, `tests/monitor/test_signal.py`
(plus this plan file if it was committed on this branch rather than the feature branch — that is acceptable; nothing under `src/irc/monitor/eval/`).
Second command: NO output (grep exit code 1 IS the pass condition).

- [ ] **Step 4: Commands-layer safety net (per-file ONLY — whole-dir hangs)**

`grep -rl "divergence" tests/commands/` matches 3 files, but each only passes `divergence_codes=()` to the unchanged `SignalRecord` constructor — no command test exercises `divergence_caveat`, `divergence_caveat_detail`, or risk-block content. `risk_block_html` (unchanged signature) does flow into `render_html` → `monitor_cmd`, so run the three matching files individually as a safety net:

```bash
uv run pytest tests/commands/test_monitor_cmd_drilldown.py -q
uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q
uv run pytest tests/commands/test_monitor_cmd_nav_history.py -q
```
Expected: each passes (exit 0). NEVER run `uv run pytest tests/commands/` as a directory.

- [ ] **Step 5: Done**

Do NOT push. Report completion with the commit SHAs from Tasks 1–4.
