# Monitor Eval M2 — Deterministic Rigor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline `hypothesis`-driven property + hybrid-oracle suite over the six pure monitor scorers (D1) and an in-run, panel-only `deterministic_scoring` health check that recomputes the full signal block from the persisted trace and diffs it (D2), generalizing the validation panel from one row to N rows.

**Architecture:** `KNOWN_NA_REASONS` becomes a single-source frozenset of named constants in `factors.py` (the producer). A new pure `eval/determinism.py` re-derives `compute_signal`'s output from `factor_scores + resolved` (fund_id passed explicitly, since it is only the trace `funds`-dict key) and diffs it. A test-only `tests/monitor/_oracle.py` holds independent reference impls. The panel data-flow is made explicit: `_compute_gates` stops discarding per-fund healths and returns `(gates, signal_healths, deterministic_healths)`; a new pure `build_panel_rows` builds both rows; `validation_panel_html` renders N `ValidationPanelRow`s. `deterministic_scoring` is **panel-only** — never gated.

**Tech Stack:** Python 3.12, pytest, `hypothesis>=6.100` (derandomized profile), `uv`, ruff. All pure/offline; no LLM, no network, sub-second.

**Hard constraints baked in (from spec §3–§8, §11 — do NOT drift):**
- `recompute_signal_from_trace(fund_id, trace_fund)` and `deterministic_health(fund_id, trace_fund)` take `fund_id` **explicitly** — it is the `funds`-dict key, absent from the per-fund value; `compute_signal` reads `fund.id` (`signal.py:80`). `aggregate_deterministic_health` passes `fund_id` from the dict key (spec §4.1 P0 rev-3 fix).
- `aggregate_news_factor` VALUE is `clamp(Σ wᵢ·impactᵢ·confᵢ)` — a clamped weighted **SUM**, NOT normalized by Σw. Only `confidence` is the weighted mean. Properties assert the clamped-sum form + monotonicity in a row's `impact` when `weight≥0` and `confidence≥0`. Asserting a "weighted mean" for the value is WRONG (spec §3.1 P2).
- `KNOWN_NA_REASONS` frozenset + named per-reason constants live in **`factors.py`** (producer = single source); `determinism.py` imports them. Do NOT put the set in `determinism.py` (inverts eval→core layering). `_na()` call sites refactor to the named constants (spec §6 divergence 2).
- `determinism.py` may import pure `evals._shared.status.worst_status` (mirrors `structural.py:6`). The ADR-0017 ban is I/O/AkShare/providers/LLM/settings/filesystem only (spec §4.1 P1).
- Divergence 1: the `monitor_signal` panel row now reflects aggregated **raw `signal_health`** (worst-of across funds), NOT the gate outcome. Gate-outcome visibility moves to `badge_counts`/`EVAL-GATED`. Re-express `test_render_html_eval.py::test_validation_panel_overall_is_not_pass_when_fund_is_gated` and `test_acceptance_eval.py` against `badge_counts`/`EVAL-GATED`; extend `test_panel.py` for multi-row.
- `deterministic_scoring` is panel-only, NEVER added to `GATING_STAGES_*`, NEVER passed to `apply_eval_gate`. M1 gate wiring unchanged (`test_gate_flip_m1.py` stays green).
- `_compute_gates` returns `(gates, signal_healths, deterministic_healths)` from ONE per-fund projection (no extra `build_eval_trace` pass beyond the one already in the loop). New pure `build_panel_rows(signal_healths, deterministic_healths, now)` builds both rows.
- Float policy: exact equality for categoricals (status/bias/reason codes/divergence codes); `abs(diff)<1e-9` for the numeric composite oracle; production rounds composite to 4dp.
- `hypothesis>=6.100` added to BOTH dev dependency blocks. No new pytest marker (`--strict-markers` stays satisfied).
- Suite stays green + offline + sub-second; no new live marker.

---

## File Structure

**Create:**
- `src/irc/monitor/eval/determinism.py` — pure: `recompute_signal_from_trace`, `diff_signal`, `deterministic_health`, `aggregate_deterministic_health`, `build_panel_rows` (panel-only).
- `tests/monitor/_oracle.py` — test-only independent reference impls (composite/renorm, gate predicate, band classifier, valuation/heat decision tables).
- `tests/conftest.py` (MODIFY) — append register + load of the hypothesis derandomize profile to the existing root conftest (spec §3.4 — extend, do not create a new conftest).
- `tests/monitor/test_signal_property.py`, `test_factors_property.py`, `test_trend_property.py`, `test_factor_maps_oracle.py`, `test_news_factor_property.py` — D1 property/oracle modules.
- `tests/monitor/test_known_na_reasons.py` — two-way exhaustiveness test.
- `tests/monitor/eval/test_determinism.py` — D2 crafted-trace example tests.
- `tests/monitor/eval/test_panel_rows.py` — `build_panel_rows` + guard test (a FAILing deterministic health never gates).

**Modify:**
- `src/irc/monitor/factors.py` — add `KNOWN_NA_REASONS` + named constants; refactor `_na()` call sites.
- `src/irc/monitor/eval/types.py` — add `ValidationPanelRow`.
- `src/irc/monitor/eval/panel.py` — generalize `validation_panel_html` to N rows.
- `src/irc/monitor/render_html.py` — `_panel` renders passed rows; `render_report` receives `panel_rows`.
- `src/irc/commands/monitor_cmd.py` — `_compute_gates` returns 3-tuple; call site builds + passes panel rows.
- `tests/monitor/eval/test_panel.py` — extend for multi-row (existing single-row tests re-expressed).
- `tests/monitor/test_render_html_eval.py` — re-express the gated-overall assertion against `badge_counts`/`EVAL-GATED`.
- `tests/monitor/test_acceptance_eval.py` — re-express gated panel assertion against `EVAL-GATED`.
- `tests/monitor/eval/test_gate_flip_m1.py` — unpack the new 3-tuple from `mc._compute_gates` (3 call sites).
- `pyproject.toml` — add `hypothesis>=6.100` to both dev blocks.

---

## Milestone 0 — `hypothesis` dependency + derandomize profile

### Task 0: Add hypothesis to both dev dependency blocks

**Files:**
- Modify: `pyproject.toml:26-32` (`[project.optional-dependencies].dev`) and `pyproject.toml:63-67` (`[dependency-groups].dev`)

- [ ] **Step 1: Add hypothesis to `[project.optional-dependencies].dev`**

Edit `pyproject.toml`. Change the `dev = [...]` block under `[project.optional-dependencies]` from:

```toml
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "respx>=0.21",
    "ruff>=0.4",
]
```

to:

```toml
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "respx>=0.21",
    "ruff>=0.4",
    "hypothesis>=6.100",
]
```

- [ ] **Step 2: Add hypothesis to `[dependency-groups].dev`**

Change the `[dependency-groups]` block from:

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "respx>=0.23.1",
]
```

to:

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "respx>=0.23.1",
    "hypothesis>=6.100",
]
```

- [ ] **Step 3: Install**

Run: `uv sync --all-extras`
Expected: resolves and installs `hypothesis` (a new package line in the output). No errors.

- [ ] **Step 4: Verify import**

Run: `uv run python -c "import hypothesis; print('hypothesis', hypothesis.__version__)"`
Expected: prints `hypothesis 6.x.y` (≥6.100).

- [ ] **Step 5: Verify markers unaffected**

Run: `uv run pytest --co -q tests/monitor/test_signal.py 2>&1 | tail -3`
Expected: collection succeeds (no `--strict-markers` error; no marker was added).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build(monitor-eval-m2): add hypothesis>=6.100 to dev deps"
```

### Task 1: Register the derandomize hypothesis profile in the **existing** `tests/conftest.py`

> **Orchestrator amendment (spec fidelity).** Spec §3.4 is explicit: register the profile in the **existing** `tests/conftest.py` (it "already defines an autouse `_skip_spend_gate` fixture; a module-level `register_profile` + `load_profile` coexists fine"). This is a rev-3 P2 resolution — the spec author already weighed and rejected a separate conftest. EXTEND the root file; do **not** create `tests/monitor/conftest.py`. The profile is global (hypothesis reads profiles from code), so `load_profile` at the root conftest's import time covers every property test wherever it lives.

Append a **module-level** profile registration to `tests/conftest.py` after the existing fixtures. `derandomize=True`, `deadline=None`, bounded `max_examples`.

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Append the profile registration to `tests/conftest.py`**

Add the hypothesis import to the top imports and append the registration block **after** the existing `tmp_repo` fixture (do NOT touch `_skip_spend_gate` or `tmp_repo`). The resulting file:

```python
from __future__ import annotations
from pathlib import Path
import pytest
from hypothesis import settings, HealthCheck


@pytest.fixture(autouse=True)
def _skip_spend_gate(monkeypatch):
    """Bypass the preflight spend/balance gate by default in the test suite.

    The gate does live, read-only balance probes when provider keys are present
    in the environment (they are, in dev), so leaving it active would make any
    test that drives a real command runner hit the network and depend on the
    current account balance. The gate's own behaviour is covered directly by
    tests/spend/ (run_preflight, estimator, ledger, gate, probes) and by the
    dedicated wiring tests that monkeypatch the gate, so skipping it here removes
    a network dependency without losing coverage. A test that needs the live
    gate can monkeypatch.delenv("IRC_SKIP_SPEND_GATE", raising=False).
    """
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Empty temporary repo root with inputs/ and config/ ready to populate."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    return tmp_path


# --- Hypothesis determinism config (Monitor Eval M2, spec §3.4) ---------------
# The global rule requires fast, deterministic tests. Register a derandomized
# profile (no deadline, bounded max_examples — cheap for pure functions) and load
# it at import time so every property run is reproducible and offline. Hypothesis
# reads profiles from code, so there is no [tool.hypothesis] in pyproject.toml and
# no new pytest marker (--strict-markers stays satisfied).
settings.register_profile(
    "monitor_deterministic",
    derandomize=True,
    deadline=None,
    max_examples=150,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("monitor_deterministic")
```

- [ ] **Step 2: Verify it loads without breaking collection**

Run: `uv run pytest --co -q tests/monitor/ 2>&1 | tail -3`
Expected: collection succeeds; no import error from `tests/conftest.py`.

- [ ] **Step 3: Verify existing tests still pass (profile is inert until a property test exists)**

Run: `uv run pytest tests/monitor/test_signal.py tests/monitor/test_factors.py tests/spend -q`
Expected: all pass (the new block does not change example-based tests or the spend-gate fixture; `tests/spend` confirms the root conftest still behaves).

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test(monitor-eval-m2): register derandomized hypothesis profile"
```

**Verification point (Milestone 0):** `import hypothesis` works; `tests/conftest.py` loads the `monitor_deterministic` profile; `uv run pytest -q tests/monitor` still green; `uv run pytest -q tests/spend` still green.

---

## Milestone 1 — `KNOWN_NA_REASONS` single source + two-way exhaustiveness

Spec §6 + §8 step 1. Smallest change; unblocks D1 reason properties and D2 reason validation. `constituent_no_coverage` is emitted by **two** branches (`factors.py:70` and `:73`) — codes→branches is many-to-one, NOT a dead-code false positive.

### Task 2: Add `KNOWN_NA_REASONS` + named constants to `factors.py` and refactor `_na()` call sites

**Files:**
- Modify: `src/irc/monitor/factors.py`
- Test: `tests/monitor/test_known_na_reasons.py`

- [ ] **Step 1: Write the failing exhaustiveness test**

Create `tests/monitor/test_known_na_reasons.py`:

```python
"""Two-way exhaustiveness of KNOWN_NA_REASONS (spec §6).

Every _na() branch in build_factor_scores emits a member of KNOWN_NA_REASONS,
and every member is reachable from some branch (no dead codes). Note
constituent_no_coverage is emitted by TWO branches (factors.py:70 and :73) —
codes-to-branches is many-to-one, so two branches sharing one code is NOT a
dead-code false positive.
"""
from __future__ import annotations
import inspect
import re
from irc.monitor import factors
from irc.monitor.factors import KNOWN_NA_REASONS


# The eight named constants the spec enumerates (§6).
_EXPECTED = {
    "profile_ineligible",
    "trend_insufficient_history",
    "valuation_no_anchor",
    "valuation_unknown_state",
    "heat_no_data",
    "macro_insufficient_families",
    "macro_empty_pool",
    "constituent_no_coverage",
}


def test_known_na_reasons_is_exactly_the_eight_codes():
    assert KNOWN_NA_REASONS == frozenset(_EXPECTED)


def _emitted_reason_constants() -> set[str]:
    """Every NA-reason constant name referenced in the build_factor_scores source
    that resolves to a KNOWN_NA_REASONS member. We read the module source and
    resolve each _NA_* constant the helper bodies reference."""
    src = inspect.getsource(factors)
    names = set(re.findall(r"\b(_NA_[A-Z_]+)\b", src))
    return {getattr(factors, n) for n in names if hasattr(factors, n)}


def test_every_na_branch_emits_a_known_reason():
    emitted = _emitted_reason_constants()
    assert emitted, "no _NA_* constants referenced in factors.py"
    assert emitted <= KNOWN_NA_REASONS


def test_every_known_reason_is_reachable_from_a_branch():
    # Reachability: every member must be referenced by at least one _NA_* constant
    # used in the module (constituent_no_coverage reached via two branches → still
    # one code, counted once).
    emitted = _emitted_reason_constants()
    assert KNOWN_NA_REASONS <= emitted
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/monitor/test_known_na_reasons.py -q`
Expected: FAIL — `ImportError: cannot import name 'KNOWN_NA_REASONS' from 'irc.monitor.factors'`.

- [ ] **Step 3: Add the named constants + frozenset to `factors.py`**

In `src/irc/monitor/factors.py`, after the imports (after line 7, before `_MACRO_MIN_FAMILIES`), insert:

```python
# ── N/A reason codes (single source — spec §6) ────────────────────────────────
# The producer owns these; eval/determinism.py imports them. Do NOT move the set
# into the eval overlay (would invert the eval → core layering).
_NA_PROFILE_INELIGIBLE = "profile_ineligible"
_NA_TREND_INSUFFICIENT_HISTORY = "trend_insufficient_history"
_NA_VALUATION_NO_ANCHOR = "valuation_no_anchor"
_NA_VALUATION_UNKNOWN_STATE = "valuation_unknown_state"
_NA_HEAT_NO_DATA = "heat_no_data"
_NA_MACRO_INSUFFICIENT_FAMILIES = "macro_insufficient_families"
_NA_MACRO_EMPTY_POOL = "macro_empty_pool"
_NA_CONSTITUENT_NO_COVERAGE = "constituent_no_coverage"

KNOWN_NA_REASONS: frozenset[str] = frozenset({
    _NA_PROFILE_INELIGIBLE,
    _NA_TREND_INSUFFICIENT_HISTORY,
    _NA_VALUATION_NO_ANCHOR,
    _NA_VALUATION_UNKNOWN_STATE,
    _NA_HEAT_NO_DATA,
    _NA_MACRO_INSUFFICIENT_FAMILIES,
    _NA_MACRO_EMPTY_POOL,
    _NA_CONSTITUENT_NO_COVERAGE,
})
```

- [ ] **Step 4: Refactor `_na()` call sites to the named constants**

In `src/irc/monitor/factors.py`, replace each inline string literal in the helper bodies. The exact edits (keep everything else identical):

`_trend` (line 30): `return _na("trend", "trend_insufficient_history")` → `return _na("trend", _NA_TREND_INSUFFICIENT_HISTORY)`

`_valuation` (lines 35, 38, 41):
- `return _na("valuation", "profile_ineligible")` → `return _na("valuation", _NA_PROFILE_INELIGIBLE)`
- `return _na("valuation", "valuation_no_anchor")` → `return _na("valuation", _NA_VALUATION_NO_ANCHOR)`
- `return _na("valuation", "valuation_unknown_state")` → `return _na("valuation", _NA_VALUATION_UNKNOWN_STATE)`

`_heat` (lines 46, 50):
- `return _na("heat", "profile_ineligible")` → `return _na("heat", _NA_PROFILE_INELIGIBLE)`
- `return _na("heat", "heat_no_data")` → `return _na("heat", _NA_HEAT_NO_DATA)`

`_macro` (lines 55, 59, 62):
- `return _na("macro_tilt", "profile_ineligible")` → `return _na("macro_tilt", _NA_PROFILE_INELIGIBLE)`
- `return _na("macro_tilt", "macro_insufficient_families")` → `return _na("macro_tilt", _NA_MACRO_INSUFFICIENT_FAMILIES)`
- `return _na("macro_tilt", "macro_empty_pool")` → `return _na("macro_tilt", _NA_MACRO_EMPTY_POOL)`

`_constituent` (lines 67, 70, 73):
- `return _na("constituent", "profile_ineligible")` → `return _na("constituent", _NA_PROFILE_INELIGIBLE)`
- `return _na("constituent", "constituent_no_coverage")` (line 70) → `return _na("constituent", _NA_CONSTITUENT_NO_COVERAGE)`
- `return _na("constituent", "constituent_no_coverage")` (line 73) → `return _na("constituent", _NA_CONSTITUENT_NO_COVERAGE)`

- [ ] **Step 5: Run the exhaustiveness test to verify it passes**

Run: `uv run pytest tests/monitor/test_known_na_reasons.py -q`
Expected: 4 passed.

- [ ] **Step 6: Run the existing factor tests to confirm no behaviour change**

Run: `uv run pytest tests/monitor/test_factors.py -q`
Expected: all pass (the reason strings are byte-identical — only their source spelling changed).

- [ ] **Step 7: Lint**

Run: `uv run ruff check src/irc/monitor/factors.py tests/monitor/test_known_na_reasons.py`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add src/irc/monitor/factors.py tests/monitor/test_known_na_reasons.py
git commit -m "feat(monitor-eval-m2): single-source KNOWN_NA_REASONS + exhaustiveness test"
```

**Verification point (Milestone 1):** `from irc.monitor.factors import KNOWN_NA_REASONS` works; the frozenset is exactly the 8 codes; existing `test_factors.py` unchanged-green.

---

## Milestone 2 — D1: independent oracle + property suites (one scorer at a time)

Spec §3 + §8 step 2. `tests/monitor/_oracle.py` holds independent reference impls **only** where a genuinely different formulation exists (composite/renorm, gate predicate, band classifier, valuation/heat decision tables). Direct formula transcriptions get **properties only**.

### Task 3: Independent oracle module `tests/monitor/_oracle.py`

**Files:**
- Create: `tests/monitor/_oracle.py`

- [ ] **Step 1: Write the oracle module (test-only; no production import of it)**

Create `tests/monitor/_oracle.py`:

```python
"""TEST-ONLY independent reference impls for D1 (spec §3.1).

Independent formulations where one genuinely exists; NEVER imported by production.
A second copy of a direct formula transcription would be circular, so trend /
build_factor_scores / news_factor get PROPERTIES (in their *_property modules),
not an oracle here.
"""
from __future__ import annotations

# ── compute_signal: composite via a separate Σw'·s formulation ────────────────
_MIN_FAMILIES = 2
_MIN_AVAILABLE_WEIGHT = 0.60
_FAMILY_OF = {
    "trend": "price-momentum", "valuation": "valuation",
    "heat": "crowding", "macro_tilt": "news", "constituent": "news",
}


def present_scores(scores):
    """(name, value, confidence) for eligible-and-present factors."""
    return [(s.name, s.value, s.confidence) for s in scores
            if s.eligible and s.value is not None]


def available_weight(weights: dict, scores) -> float:
    return sum(weights.get(n, 0.0) for n, _, _ in present_scores(scores))


def composite_oracle(weights: dict, scores) -> float:
    """Σ (w_i / Σw_present) · s_i — a different grouping than production's
    per-contribution accumulation. Unrounded; caller applies the §3.3 eps."""
    present = present_scores(scores)
    avail = sum(weights.get(n, 0.0) for n, _, _ in present)
    if avail <= 0:
        return 0.0
    return sum((weights.get(n, 0.0) / avail) * v for n, v, _ in present)


def renorm_weight_sum(weights: dict, scores) -> float:
    present = present_scores(scores)
    avail = sum(weights.get(n, 0.0) for n, _, _ in present)
    if avail <= 0:
        return 0.0
    return sum(weights.get(n, 0.0) / avail for n, _, _ in present)


def gate_predicate_ok(weights: dict, scores) -> bool:
    """status == 'ok' is GATED by: trend present AND ≥2 families AND avail ≥ .60.
    (Confidence gate is a separate check.) Independent boolean form."""
    present = present_scores(scores)
    families = {_FAMILY_OF[n] for n, _, _ in present}
    avail = sum(weights.get(n, 0.0) for n, _, _ in present)
    trend_present = any(n == "trend" for n, _, _ in present)
    return trend_present and len(families) >= _MIN_FAMILIES and avail >= _MIN_AVAILABLE_WEIGHT


def band_classifier(composite: float, bands: dict) -> str:
    """ADD_BIAS / REDUCE_BIAS / NEUTRAL via explicit boundaries."""
    if composite >= bands["buy"]:
        return "ADD_BIAS"
    if composite <= bands["sell"]:
        return "REDUCE_BIAS"
    return "NEUTRAL"


# ── valuation / heat: re-expressed decision tables (different shape) ───────────
def valuation_oracle(state: str):
    """Re-expressed as an explicit if-ladder instead of a dict lookup."""
    if state == "cheap":
        return 1.0
    if state == "fair_cheap":
        return 0.5
    if state == "fair":
        return 0.0
    if state == "fair_expensive":
        return -0.5
    if state == "expensive":
        return -1.0
    return None


def heat_oracle(*, restricted, aum_delta_pct):
    """Re-expressed decision table (no-data → None; both → -1; either → -0.5; calm → .3)."""
    if restricted is None and aum_delta_pct is None:
        return None
    rapid = aum_delta_pct is not None and aum_delta_pct >= 20.0
    if restricted is True and rapid:
        return -1.0
    if restricted is True or rapid:
        return -0.5
    return 0.3
```

- [ ] **Step 2: Verify the oracle imports cleanly (no collection error)**

Run: `uv run python -c "import importlib.util, pathlib; spec=importlib.util.spec_from_file_location('o', 'tests/monitor/_oracle.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Lint**

Run: `uv run ruff check tests/monitor/_oracle.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add tests/monitor/_oracle.py
git commit -m "test(monitor-eval-m2): independent D1 oracle reference impls"
```

### Task 4: `compute_signal` property suite — `tests/monitor/test_signal_property.py`

**Files:**
- Create: `tests/monitor/test_signal_property.py`

- [ ] **Step 1: Write the property test (against the oracle + invariants)**

Create `tests/monitor/test_signal_property.py`:

```python
"""D1 properties + hybrid oracle for compute_signal (spec §3.1, §3.2, §3.3)."""
from __future__ import annotations
from hypothesis import given, strategies as st
from irc.monitor.types import MonitorFund, FactorScore
from irc.monitor.signal import compute_signal
from tests.monitor import _oracle

_FACTOR_NAMES = ("trend", "valuation", "heat", "macro_tilt", "constituent")
_EPS = 1e-9


def _weights():
    return st.fixed_dictionaries(
        {n: st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)
         for n in _FACTOR_NAMES})


@st.composite
def _score(draw, name):
    eligible = draw(st.booleans())
    if eligible:
        value = draw(st.floats(-1.0, 1.0, allow_nan=False, allow_infinity=False))
        return FactorScore(name=name, value=value, eligible=True, reason="",
                           confidence=draw(st.floats(0.0, 1.0, allow_nan=False)))
    return FactorScore(name=name, value=None, eligible=False, reason="x",
                       confidence=draw(st.floats(0.0, 1.0, allow_nan=False)))


@st.composite
def _scores(draw):
    return tuple(draw(_score(n)) for n in _FACTOR_NAMES)


@st.composite
def _bands(draw):
    sell = draw(st.floats(-1.0, 0.0, allow_nan=False))
    buy = draw(st.floats(0.0, 1.0, allow_nan=False))
    return {"sell": sell, "buy": buy}


@st.composite
def _fund(draw):
    return MonitorFund(
        id="X", name_cn="x", market="cn", analysis_profile="gold",
        themes=(), constituent_news=False, weights=draw(_weights()),
        bands=draw(_bands()),
        minimum_confidence=draw(st.floats(0.0, 1.0, allow_nan=False)),
    )


@given(fund=_fund(), scores=_scores())
def test_composite_equals_rounded_oracle(fund, scores):
    rec = compute_signal(fund, scores)
    expected = round(_oracle.composite_oracle(fund.weights, scores), 4)
    assert abs(rec.composite - expected) < _EPS


@given(fund=_fund(), scores=_scores())
def test_renorm_sums_to_one_or_zero(fund, scores):
    rec = compute_signal(fund, scores)
    s = sum(c.renorm_weight for c in rec.contributions)
    if rec.contributions and _oracle.available_weight(fund.weights, scores) > 0:
        assert abs(s - 1.0) < _EPS
    else:
        assert abs(s - 0.0) < _EPS


@given(fund=_fund(), scores=_scores())
def test_bias_none_iff_status_not_ok(fund, scores):
    rec = compute_signal(fund, scores)
    assert (rec.bias is None) == (rec.status != "ok")


@given(fund=_fund(), scores=_scores())
def test_status_ok_matches_gate_and_confidence_predicate(fund, scores):
    rec = compute_signal(fund, scores)
    gate_ok = _oracle.gate_predicate_ok(fund.weights, scores)
    conf_ok = rec.signal_confidence >= fund.minimum_confidence
    assert (rec.status == "ok") == (gate_ok and conf_ok)


@given(fund=_fund(), scores=_scores())
def test_bias_matches_band_classifier_when_ok(fund, scores):
    rec = compute_signal(fund, scores)
    if rec.status == "ok":
        assert rec.bias == _oracle.band_classifier(rec.composite, fund.bands)


@given(fund=_fund(), scores=_scores())
def test_raising_composite_never_moves_bias_toward_reduce(fund, scores):
    # Band monotonicity: a higher composite never yields REDUCE when the lower one
    # yielded ADD/NEUTRAL. Compare the band classifier at composite and composite+δ.
    lo = _oracle.band_classifier(0.0, fund.bands)
    hi = _oracle.band_classifier(1.0, fund.bands)
    order = {"REDUCE_BIAS": 0, "NEUTRAL": 1, "ADD_BIAS": 2}
    assert order[hi] >= order[lo]


@given(fund=_fund(), scores=_scores())
def test_reproducible_same_inputs_equal_record(fund, scores):
    assert compute_signal(fund, scores) == compute_signal(fund, scores)
```

- [ ] **Step 2: Run to verify it passes (derandomized, sub-second)**

Run: `uv run pytest tests/monitor/test_signal_property.py -q`
Expected: 7 passed, fast (< 2s). The `tests/conftest.py` derandomize profile makes every run reproducible.

- [ ] **Step 3: Lint**

Run: `uv run ruff check tests/monitor/test_signal_property.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add tests/monitor/test_signal_property.py
git commit -m "test(monitor-eval-m2): D1 property suite for compute_signal"
```

### Task 5: `build_factor_scores` property suite — `tests/monitor/test_factors_property.py`

**Files:**
- Create: `tests/monitor/test_factors_property.py`

- [ ] **Step 1: Write the property test (properties only — no second impl)**

Create `tests/monitor/test_factors_property.py`:

```python
"""D1 properties for build_factor_scores (spec §3.1: properties only).

Each score is (eligible=True, value∈[-1,1], reason="") OR
(eligible=False, value=None, reason∈KNOWN_NA_REASONS); per-profile eligibility
correctness; N/A reason coverage.
"""
from __future__ import annotations
from hypothesis import given, strategies as st
from irc.monitor.factors import build_factor_scores, FactorInputs, KNOWN_NA_REASONS
from irc.monitor.news_factor import ImpactRow
from irc.monitor.profiles import PROFILES, eligible_factors

_PROFILES = tuple(PROFILES.keys())
_FACTOR_NAMES = ("trend", "valuation", "heat", "macro_tilt", "constituent")


def _nav(n):
    return tuple((f"d{i:04d}", 1.0 + 0.001 * i) for i in range(n))


@st.composite
def _impact_rows(draw, keys):
    n = draw(st.integers(0, 4))
    return tuple(
        ImpactRow(
            key=draw(st.sampled_from(keys)),
            weight=draw(st.floats(0.0, 100.0, allow_nan=False)),
            impact=draw(st.floats(-1.0, 1.0, allow_nan=False)),
            confidence=draw(st.floats(0.0, 1.0, allow_nan=False)),
        )
        for _ in range(n)
    )


@st.composite
def _inputs(draw):
    return FactorInputs(
        acc_nav=_nav(draw(st.integers(0, 300))),
        minimum_observations=draw(st.integers(1, 251)),
        valuation_state=draw(st.sampled_from(
            [None, "cheap", "fair", "expensive", "???"])),
        valuation_cached=draw(st.booleans()),
        restricted=draw(st.sampled_from([None, True, False])),
        aum_delta_pct=draw(st.sampled_from([None, 0.0, 30.0])),
        macro_rows=draw(_impact_rows(("a", "b", "c"))),
        constituent_rows=draw(_impact_rows(("x", "y"))),
    )


@given(profile=st.sampled_from(_PROFILES), inp=_inputs())
def test_every_score_is_eligible_value_coherent(profile, inp):
    for s in build_factor_scores(profile, inp):
        if s.eligible:
            assert s.value is not None and -1.0 <= s.value <= 1.0
            assert s.reason == ""
        else:
            assert s.value is None
            assert s.reason in KNOWN_NA_REASONS


@given(profile=st.sampled_from(_PROFILES), inp=_inputs())
def test_ineligible_factors_are_profile_ineligible(profile, inp):
    elig = set(eligible_factors(profile))
    by_name = {s.name: s for s in build_factor_scores(profile, inp)}
    for name in _FACTOR_NAMES:
        if name not in elig:
            assert by_name[name].eligible is False
            assert by_name[name].reason == "profile_ineligible"


@given(profile=st.sampled_from(_PROFILES), inp=_inputs())
def test_all_five_factor_names_present_exactly_once(profile, inp):
    names = [s.name for s in build_factor_scores(profile, inp)]
    assert names == list(_FACTOR_NAMES)
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/monitor/test_factors_property.py -q`
Expected: 3 passed.

- [ ] **Step 3: Lint + commit**

Run: `uv run ruff check tests/monitor/test_factors_property.py`
Expected: `All checks passed!`

```bash
git add tests/monitor/test_factors_property.py
git commit -m "test(monitor-eval-m2): D1 property suite for build_factor_scores"
```

### Task 6: `trend_score` property suite — `tests/monitor/test_trend_property.py`

**Files:**
- Create: `tests/monitor/test_trend_property.py`

- [ ] **Step 1: Write the property test (properties only — direct formula transcription)**

Create `tests/monitor/test_trend_property.py`:

```python
"""D1 properties for trend_score (spec §3.1: properties only).

clamp ∈ [-1,1]; monotone non-decreasing in r60 with structure/drawdown fixed;
tanh saturation at extremes.
"""
from __future__ import annotations
import math
from hypothesis import given, strategies as st
from irc.monitor.trend import trend_score


def _flat_then_ramp(base: float, ramp: float, n: int = 300):
    """A series whose r60 grows with `ramp` while ma_struct/drawdown stay fixed:
    constant `base` for the first n-61 points (flat MA + no drawdown anchor below
    the recent window), then a single jump to base*(1+ramp) at the end."""
    head = [base] * (n - 1)
    return tuple((f"d{i:04d}", v) for i, v in enumerate(head + [base * (1.0 + ramp)]))


@given(
    base=st.floats(0.5, 5.0, allow_nan=False),
    ramp=st.floats(-0.9, 5.0, allow_nan=False),
)
def test_output_always_in_unit_interval(base, ramp):
    s = _flat_then_ramp(base, ramp)
    assert -1.0 <= trend_score(s) <= 1.0


@given(
    base=st.floats(1.0, 3.0, allow_nan=False),
    r_lo=st.floats(-0.5, 0.5, allow_nan=False),
    bump=st.floats(0.0, 2.0, allow_nan=False),
)
def test_monotone_nondecreasing_in_r60(base, r_lo, bump):
    # Raising the terminal value (→ higher r60) with the rest of the series fixed
    # never lowers the score (structure + drawdown are functions of the head only
    # here, held fixed across the two series).
    lo = _flat_then_ramp(base, r_lo)
    hi = _flat_then_ramp(base, r_lo + bump)
    assert trend_score(hi) >= trend_score(lo) - 1e-9


def test_tanh_saturation_at_extreme_positive():
    # A huge positive r60 drives tanh(8·r60) → 1; with positive structure the blend
    # saturates near the upper clamp.
    s = _flat_then_ramp(1.0, 100.0)
    assert trend_score(s) >= 0.5


def test_tanh_saturation_at_extreme_negative():
    s = _flat_then_ramp(1.0, -0.99)
    assert trend_score(s) <= 0.0


@given(base=st.integers(1, 100).map(float))  # AMENDED: integers→float avoids FP drift in MA windows (non-representable floats make MAs diverge from the level, spuriously breaking the invariant; integer-floats are exactly representable and preserve mathematical intent)
def test_flat_series_is_near_zero_momentum(base):
    # base must be exactly representable (integer float) so that repeated summation of
    # equal values yields identical means across all windows — no MA float drift.
    s = tuple((f"d{i:04d}", base) for i in range(300))
    # flat → r60=0 → tanh(0)=0; structure 0; drawdown 0 → score 0
    assert math.isclose(trend_score(s), 0.0, abs_tol=1e-9)
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/monitor/test_trend_property.py -q`
Expected: 5 passed.

- [ ] **Step 3: Lint + commit**

Run: `uv run ruff check tests/monitor/test_trend_property.py`
Expected: `All checks passed!`

```bash
git add tests/monitor/test_trend_property.py
git commit -m "test(monitor-eval-m2): D1 property suite for trend_score"
```

### Task 7: `valuation_state_score` / `heat_score` oracle suite — `tests/monitor/test_factor_maps_oracle.py`

**Files:**
- Create: `tests/monitor/test_factor_maps_oracle.py`

- [ ] **Step 1: Write the oracle + ordering property test**

Create `tests/monitor/test_factor_maps_oracle.py`:

```python
"""D1 oracle + properties for valuation_state_score / heat_score (spec §3.1).

re-expressed lookup / decision table oracle; ordering monotonicity (cheaper→higher;
more crowded→lower); None on unrecognised state / no data.
"""
from __future__ import annotations
from hypothesis import given, strategies as st
from irc.monitor.factor_maps import valuation_state_score, heat_score
from tests.monitor import _oracle

_KNOWN_STATES = ("cheap", "fair_cheap", "fair", "fair_expensive", "expensive")


@given(state=st.sampled_from(_KNOWN_STATES + ("???", "", "unknown")))
def test_valuation_matches_oracle(state):
    assert valuation_state_score(state) == _oracle.valuation_oracle(state)


def test_valuation_ordering_cheaper_is_higher():
    scores = [valuation_state_score(s) for s in _KNOWN_STATES]
    assert scores == sorted(scores, reverse=True)  # strictly descending cheap→expensive
    assert scores[0] == 1.0 and scores[-1] == -1.0


@given(state=st.text(min_size=0, max_size=12))
def test_valuation_none_on_unrecognised(state):
    if state not in _KNOWN_STATES:
        assert valuation_state_score(state) is None


@given(
    restricted=st.sampled_from([None, True, False]),
    aum=st.sampled_from([None, 0.0, 19.9, 20.0, 30.0]),
)
def test_heat_matches_oracle(restricted, aum):
    assert heat_score(restricted=restricted, aum_delta_pct=aum) == \
        _oracle.heat_oracle(restricted=restricted, aum_delta_pct=aum)


def test_heat_more_crowded_is_lower():
    calm = heat_score(restricted=False, aum_delta_pct=0.0)
    one = heat_score(restricted=True, aum_delta_pct=0.0)
    both = heat_score(restricted=True, aum_delta_pct=30.0)
    assert calm > one > both


def test_heat_none_when_no_data():
    assert heat_score(restricted=None, aum_delta_pct=None) is None
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/monitor/test_factor_maps_oracle.py -q`
Expected: 6 passed.

- [ ] **Step 3: Lint + commit**

Run: `uv run ruff check tests/monitor/test_factor_maps_oracle.py`
Expected: `All checks passed!`

```bash
git add tests/monitor/test_factor_maps_oracle.py
git commit -m "test(monitor-eval-m2): D1 oracle suite for valuation/heat maps"
```

### Task 8: `aggregate_news_factor` property suite — `tests/monitor/test_news_factor_property.py`

Spec §3.1 P2: VALUE is `clamp(Σ wᵢ·impactᵢ·confᵢ)` (clamped weighted SUM). Asserting a "weighted mean" for the value is WRONG.

**Files:**
- Create: `tests/monitor/test_news_factor_property.py`

- [ ] **Step 1: Write the property test**

Create `tests/monitor/test_news_factor_property.py`:

```python
"""D1 properties for aggregate_news_factor (spec §3.1 P2).

VALUE = clamp(Σ wᵢ·impactᵢ·confᵢ)  — a clamped weighted SUM, NOT a weighted mean.
Only the returned CONFIDENCE is the weighted mean Σ(wᵢ·confᵢ)/Σwᵢ.
None on empty pool or non-positive total weight; value non-decreasing in a row's
impact when that row's weight ≥ 0 and confidence ≥ 0.
"""
from __future__ import annotations
import dataclasses
from hypothesis import given, strategies as st
from irc.monitor.news_factor import aggregate_news_factor, ImpactRow

_EPS = 1e-9


@st.composite
def _rows(draw, min_size=0, max_size=5):
    n = draw(st.integers(min_size, max_size))
    return tuple(
        ImpactRow(
            key=f"k{i}",
            weight=draw(st.floats(0.0, 100.0, allow_nan=False)),
            impact=draw(st.floats(-1.0, 1.0, allow_nan=False)),
            confidence=draw(st.floats(0.0, 1.0, allow_nan=False)),
        )
        for i in range(n)
    )


def _clamp(x):
    return max(-1.0, min(1.0, x))


@given(rows=_rows())
def test_value_is_clamped_weighted_sum_not_mean(rows):
    value, _ = aggregate_news_factor(rows)
    wsum = sum(r.weight for r in rows)
    if not rows or wsum <= 0:
        assert value is None
        return
    expected = _clamp(sum(r.weight * r.impact * r.confidence for r in rows))
    assert abs(value - expected) < _EPS


@given(rows=_rows())
def test_value_in_unit_interval(rows):
    value, _ = aggregate_news_factor(rows)
    if value is not None:
        assert -1.0 <= value <= 1.0


@given(rows=_rows(min_size=1))
def test_confidence_is_weighted_mean(rows):
    _, conf = aggregate_news_factor(rows)
    wsum = sum(r.weight for r in rows)
    if wsum > 0:
        expected = sum(r.weight * r.confidence for r in rows) / wsum
        assert abs(conf - expected) < _EPS


@given(rows=_rows(min_size=1), idx=st.integers(0, 4), bump=st.floats(0.0, 2.0))
def test_value_nondecreasing_in_a_rows_impact(rows, idx, bump):
    # Raising one row's impact (its weight ≥ 0 and confidence ≥ 0 by strategy) must
    # never lower the unclamped sum; clamp is monotone, so the clamped value too.
    i = idx % len(rows)
    base_val, _ = aggregate_news_factor(rows)
    raised = list(rows)
    raised[i] = dataclasses.replace(raised[i], impact=min(1.0, rows[i].impact + bump))
    raised_val, _ = aggregate_news_factor(tuple(raised))
    if base_val is None:        # Σw ≤ 0 → both None; nothing to compare
        assert raised_val is None
        return
    assert raised_val >= base_val - _EPS


@given(rows=_rows())
def test_none_on_empty_or_nonpositive_weight(rows):
    value, conf = aggregate_news_factor(rows)
    wsum = sum(r.weight for r in rows)
    if not rows or wsum <= 0:
        assert value is None and conf == 0.0
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/monitor/test_news_factor_property.py -q`
Expected: 5 passed.

- [ ] **Step 3: Lint + commit**

Run: `uv run ruff check tests/monitor/test_news_factor_property.py`
Expected: `All checks passed!`

```bash
git add tests/monitor/test_news_factor_property.py
git commit -m "test(monitor-eval-m2): D1 property suite for aggregate_news_factor"
```

**Verification point (Milestone 2):**

Run: `uv run pytest tests/monitor/test_signal_property.py tests/monitor/test_factors_property.py tests/monitor/test_trend_property.py tests/monitor/test_factor_maps_oracle.py tests/monitor/test_news_factor_property.py -q`
Expected: all pass, total wall-clock < 5s (derandomized, pure functions).

---

## Milestone 3 — D2: `eval/determinism.py` (recompute / diff / health / aggregate)

Spec §4. Pure module; recompute the full signal block from `factor_scores + resolved`, diff vs the recorded `signal`, validate N/A reasons. `fund_id` is required and passed explicitly (P0 rev-3 fix). May import pure `evals._shared.status.worst_status`.

### Task 9: Implement `recompute_signal_from_trace` + `diff_signal` with crafted-trace example tests

**Files:**
- Create: `src/irc/monitor/eval/determinism.py`
- Test: `tests/monitor/eval/test_determinism.py`

- [ ] **Step 1: Write the failing example tests for recompute + diff**

Create `tests/monitor/eval/test_determinism.py`:

```python
"""D2 example tests over crafted trace fixtures (spec §8 step 3).

A clean trace → PASS; a trace with a corrupted contribution / bad reason → FAIL
naming the field. recompute/health take fund_id EXPLICITLY (P0 rev-3 fix):
fund_id is the funds-dict key, absent from the per-fund value.
"""
from __future__ import annotations
import copy
from irc.monitor.eval.determinism import (
    recompute_signal_from_trace, diff_signal, deterministic_health,
    aggregate_deterministic_health,
)


def _clean_fund() -> dict:
    """A single gold fund whose recorded signal exactly matches a recompute of its
    factor_scores under its resolved params (trend+macro present, heat N/A)."""
    return {
        "resolved": {
            "analysis_profile": "gold",
            "weights": {"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20},
            "bands": {"buy": 0.40, "sell": -0.40},
            "minimum_confidence": 0.50,
        },
        "factor_scores": [
            {"name": "trend", "value": 0.6, "eligible": True, "reason": "", "confidence": 1.0},
            {"name": "macro_tilt", "value": 0.5, "eligible": True, "reason": "", "confidence": 1.0},
            {"name": "heat", "value": None, "eligible": False, "reason": "heat_no_data", "confidence": 1.0},
        ],
        # signal block filled in by _record_signal below so it is self-consistent.
    }


def _record_signal(fund: dict) -> dict:
    """Stamp the recorded `signal` from a faithful recompute (so the clean fixture
    is consistent by construction). fund_id is the dict key '008986'."""
    rec = recompute_signal_from_trace("008986", fund)
    fund["signal"] = {
        "status": rec.status, "bias": rec.bias, "composite": rec.composite,
        "signal_confidence": rec.signal_confidence,
        "available_weight": rec.available_weight,
        "present_families": list(rec.present_families),
        "contributions": [
            {"name": c.name, "renorm_weight": c.renorm_weight, "value": c.value,
             "contribution": c.contribution, "confidence": c.confidence}
            for c in rec.contributions
        ],
        "divergence_codes": list(rec.divergence_codes),
    }
    return fund


def test_recompute_uses_fund_id_for_the_record():
    fund = _clean_fund()
    rec = recompute_signal_from_trace("008986", fund)
    assert rec.fund_id == "008986"
    assert rec.status == "ok" and rec.bias == "ADD_BIAS"


def test_diff_empty_on_clean_trace():
    fund = _record_signal(_clean_fund())
    rec = recompute_signal_from_trace("008986", fund)
    assert diff_signal(rec, fund["signal"]) == ()


def test_diff_names_corrupted_contribution():
    fund = _record_signal(_clean_fund())
    fund["signal"]["contributions"][0]["contribution"] = 99.0   # tamper
    rec = recompute_signal_from_trace("008986", fund)
    fields = diff_signal(rec, fund["signal"])
    assert any("contribution" in f for f in fields)


def test_diff_names_corrupted_composite():
    fund = _record_signal(_clean_fund())
    fund["signal"]["composite"] = 0.0   # tamper (was ~0.556)
    rec = recompute_signal_from_trace("008986", fund)
    assert "composite" in diff_signal(rec, fund["signal"])


def test_diff_names_corrupted_status_and_bias():
    fund = _record_signal(_clean_fund())
    fund["signal"]["status"] = "low_confidence"
    fund["signal"]["bias"] = None
    rec = recompute_signal_from_trace("008986", fund)
    fields = diff_signal(rec, fund["signal"])
    assert "status" in fields and "bias" in fields


def test_health_pass_on_clean_trace():
    fund = _record_signal(_clean_fund())
    h = deterministic_health("008986", fund)
    assert h.stage == "deterministic_scoring" and h.status == "PASS"
    assert h.reasons == ()


def test_health_fail_names_field_on_corrupted_signal():
    fund = _record_signal(_clean_fund())
    fund["signal"]["composite"] = 0.0
    h = deterministic_health("008986", fund)
    assert h.status == "FAIL"
    assert any("composite" in r for r in h.reasons)


def test_health_fail_on_unknown_na_reason():
    fund = _record_signal(_clean_fund())
    fund["factor_scores"][2]["reason"] = "not_a_real_reason"   # ineligible factor
    h = deterministic_health("008986", fund)
    assert h.status == "FAIL"
    assert any("not_a_real_reason" in r or "reason" in r for r in h.reasons)


def test_aggregate_worst_of_passes_fund_id_from_key():
    clean = _record_signal(_clean_fund())
    bad = _record_signal(_clean_fund())
    bad["signal"]["composite"] = 0.0
    traces = {"funds": {"008986": clean, "159934": bad}}
    agg = aggregate_deterministic_health(traces)
    assert agg.stage == "deterministic_scoring" and agg.status == "FAIL"
    # the offending fund id appears in the aggregated reasons
    assert any("159934" in r for r in agg.reasons)


def test_aggregate_pass_when_all_clean():
    traces = {"funds": {"008986": _record_signal(_clean_fund())}}
    agg = aggregate_deterministic_health(traces)
    assert agg.status == "PASS"


def test_aggregate_empty_is_pass():
    assert aggregate_deterministic_health({"funds": {}}).status == "PASS"
```

- [ ] **Step 2: Run to verify it fails (module not yet created)**

Run: `uv run pytest tests/monitor/eval/test_determinism.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.eval.determinism'`.

- [ ] **Step 3: Implement `determinism.py` (recompute + diff + health + aggregate)**

Create `src/irc/monitor/eval/determinism.py`:

```python
"""PURE D2 in-run deterministic-scoring health (spec §4). Recompute the full
signal block from factor_scores + resolved and diff vs the recorded block — NOT
self-referential; catches stale/malformed derived metadata.

ADR 0017 §3.3 ban: I/O, AkShare, providers, LLM gateway, settings, filesystem.
Pure evals._shared helpers are allowed (mirrors structural.py:6) — worst_status
is none of the banned categories.

PANEL-ONLY: deterministic_health is NEVER passed to apply_eval_gate and the
'deterministic_scoring' stage is NEVER added to GATING_STAGES_* (spec §4.3).
"""
from __future__ import annotations
from irc.monitor.factors import KNOWN_NA_REASONS
from irc.monitor.signal import compute_signal
from irc.monitor.types import FactorScore, MonitorFund, SignalRecord
from irc.monitor.eval.types import StageHealth
from evals._shared.status import worst_status

_STAGE = "deterministic_scoring"
_EPS = 1e-9


def _rebuild_fund(fund_id: str, resolved: dict) -> MonitorFund:
    """fund_id is the funds-dict KEY (absent from the per-fund value). compute_signal
    reads fund.id (signal.py:80), so it must be supplied — mirrors M0
    metrics._rebuild_fund(fund_id, resolved)."""
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


def recompute_signal_from_trace(fund_id: str, trace_fund: dict) -> SignalRecord:
    """Rebuild MonitorFund from fund_id + `resolved`, FactorScores from
    `factor_scores`, then run compute_signal. fund_id is required (P0 rev-3)."""
    return compute_signal(
        _rebuild_fund(fund_id, trace_fund["resolved"]),
        _scores(trace_fund["factor_scores"]),
    )


def _ne(a: float, b: float) -> bool:
    return abs(a - b) >= _EPS


def _diff_contributions(recomputed, recorded: list[dict]) -> list[str]:
    out: list[str] = []
    if len(recomputed) != len(recorded):
        out.append("contributions:length")
        return out
    for i, (c, rc) in enumerate(zip(recomputed, recorded)):
        if c.name != rc.get("name"):
            out.append(f"contributions[{i}].name")
        if _ne(c.renorm_weight, rc.get("renorm_weight", 0.0)):
            out.append(f"contributions[{i}].renorm_weight")
        if _ne(c.value, rc.get("value", 0.0)):
            out.append(f"contributions[{i}].value")
        if _ne(c.contribution, rc.get("contribution", 0.0)):
            out.append(f"contributions[{i}].contribution")
        if _ne(c.confidence, rc.get("confidence", 0.0)):
            out.append(f"contributions[{i}].confidence")
    return out


def diff_signal(recomputed: SignalRecord, recorded: dict) -> tuple[str, ...]:
    """Names of mismatched fields between a recompute and the recorded signal.
    Float fields via the §3.3 eps; categoricals exact. Does NOT compare fund_id."""
    out: list[str] = []
    if _ne(recomputed.available_weight, recorded.get("available_weight", 0.0)):
        out.append("available_weight")
    if list(recomputed.present_families) != list(recorded.get("present_families", [])):
        out.append("present_families")
    out.extend(_diff_contributions(recomputed.contributions,
                                   recorded.get("contributions", [])))
    if _ne(recomputed.composite, recorded.get("composite", 0.0)):
        out.append("composite")
    if _ne(recomputed.signal_confidence, recorded.get("signal_confidence", 0.0)):
        out.append("signal_confidence")
    if recomputed.status != recorded.get("status"):
        out.append("status")
    if recomputed.bias != recorded.get("bias"):
        out.append("bias")
    if list(recomputed.divergence_codes) != list(recorded.get("divergence_codes", [])):
        out.append("divergence_codes")
    return tuple(out)


def _bad_reasons(factor_scores: list[dict]) -> tuple[str, ...]:
    return tuple(
        f"reason:{s['name']}={s['reason']}"
        for s in factor_scores
        if not s.get("eligible") and s.get("reason") not in KNOWN_NA_REASONS
    )


def deterministic_health(fund_id: str, trace_fund: dict) -> StageHealth:
    """Per-fund PASS/FAIL. FAIL if the recompute diffs the recorded signal OR any
    ineligible factor's reason is not in KNOWN_NA_REASONS. fund_id required (P0)."""
    rec = recompute_signal_from_trace(fund_id, trace_fund)
    fields = diff_signal(rec, trace_fund["signal"])
    bad = _bad_reasons(trace_fund["factor_scores"])
    reasons = tuple(fields) + bad
    status = "FAIL" if reasons else "PASS"
    return StageHealth(stage=_STAGE, status=status, reasons=reasons)


def aggregate_deterministic_health(traces: dict) -> StageHealth:
    """Worst-of over the funds dict; reasons name the offending funds. Passes
    fund_id from the dict KEY into the per-fund health (P0 rev-3)."""
    funds = traces.get("funds", {})
    per_fund = [
        (fid, deterministic_health(fid, f)) for fid, f in funds.items()
    ]
    overall = worst_status([h.status for _, h in per_fund])
    reasons = tuple(
        f"{fid}: {r}" for fid, h in per_fund for r in h.reasons
    )
    return StageHealth(stage=_STAGE, status=overall, reasons=reasons)
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `uv run pytest tests/monitor/eval/test_determinism.py -q`
Expected: 11 passed.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/irc/monitor/eval/determinism.py tests/monitor/eval/test_determinism.py`
Expected: `All checks passed!`

- [ ] **Step 6: Verify the M0 oracle still passes (D2 must not regress it — D2 is a superset)**

Run: `uv run irc eval monitor_signal`
Expected: writes a `monitor_signal` report and prints its overall verdict (PASS/WARN/FAIL/SKIPPED depending on the latest run) — runs to completion with a 0/1/3 exit, never crashes. (D2 added no import into the M0 path; this confirms the new module does not break the eval registry.)

- [ ] **Step 7: Commit**

```bash
git add src/irc/monitor/eval/determinism.py tests/monitor/eval/test_determinism.py
git commit -m "feat(monitor-eval-m2): D2 deterministic_scoring recompute/diff/health"
```

**Verification point (Milestone 3):** `recompute_signal_from_trace`/`diff_signal`/`deterministic_health`/`aggregate_deterministic_health` exist and are pure; clean trace → PASS, corrupted contribution/composite/status/bias and bad N/A reason → FAIL naming the field; aggregate is worst-of and names offending funds; `irc eval monitor_signal` still runs.

---

## Milestone 4 — Panel wiring: `ValidationPanelRow` + multi-row panel + `_compute_gates` 3-tuple

Spec §5 + §8 step 4. New render contract, N-row panel, explicit data flow, and the guard test that a FAILing deterministic health never gates.

### Task 10: Add `ValidationPanelRow` to `eval/types.py`

**Files:**
- Modify: `src/irc/monitor/eval/types.py`
- Test: covered by Task 11 (`build_panel_rows`) and Task 12 (panel render); add a minimal shape test here.

- [ ] **Step 1: Write the failing shape test**

Append to `tests/monitor/eval/test_determinism.py`:

```python
def test_validation_panel_row_is_frozen_dataclass():
    from irc.monitor.eval.types import ValidationPanelRow
    row = ValidationPanelRow(stage="monitor_signal", status="PASS",
                             ran_at="t", reasons=())
    assert row.stage == "monitor_signal" and row.status == "PASS"
    try:
        row.status = "FAIL"  # frozen → must raise
        raised = False
    except Exception:
        raised = True
    assert raised
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_determinism.py::test_validation_panel_row_is_frozen_dataclass -q`
Expected: FAIL — `ImportError: cannot import name 'ValidationPanelRow'`.

- [ ] **Step 3: Add the dataclass to `eval/types.py`**

In `src/irc/monitor/eval/types.py`, after the `StageHealth` dataclass (after line 21), insert:

```python
@dataclass(frozen=True)
class ValidationPanelRow:
    stage: str
    status: str                  # PASS | WARN | FAIL | UNKNOWN
    ran_at: str
    reasons: tuple[str, ...]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_determinism.py::test_validation_panel_row_is_frozen_dataclass -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/types.py tests/monitor/eval/test_determinism.py
git commit -m "feat(monitor-eval-m2): ValidationPanelRow render contract"
```

### Task 11: Implement `build_panel_rows` (pure) + guard test

`build_panel_rows(signal_healths, deterministic_healths, now)` aggregates per-fund healths → worst-of via `worst_status` and returns **both** rows: `monitor_signal` (raw signal_health, divergence 1) and `deterministic_scoring`. Lives in `determinism.py` (pure, alongside the deterministic health it consumes).

**Files:**
- Modify: `src/irc/monitor/eval/determinism.py`
- Test: `tests/monitor/eval/test_panel_rows.py`

- [ ] **Step 1: Write the failing test (rows + the gating guard)**

Create `tests/monitor/eval/test_panel_rows.py`:

```python
"""build_panel_rows builds both rows from per-fund healths (spec §5); a FAILing
deterministic_scoring health is PANEL-ONLY and never reaches the gate (§4.3, §8
step 4 guard)."""
from __future__ import annotations
from irc.monitor.eval.determinism import build_panel_rows
from irc.monitor.eval.gate import apply_eval_gate, GATING_STAGES_M1
from irc.monitor.eval.types import StageHealth
from irc.monitor.types import SignalRecord


def _sig(fid="A", status="ok", bias="ADD_BIAS"):
    return SignalRecord(fund_id=fid, status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(), divergence_codes=())


def test_build_panel_rows_returns_two_rows_named_correctly():
    sig = {"A": StageHealth("monitor_signal", "PASS", ())}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ())}
    rows = build_panel_rows(sig, det, now="t")
    stages = {r.stage for r in rows}
    assert stages == {"monitor_signal", "deterministic_scoring"}
    assert all(r.ran_at == "t" for r in rows)


def test_monitor_signal_row_is_worst_of_raw_signal_health():
    # Divergence 1: the row reflects RAW signal_health worst-of, NOT a gate outcome.
    sig = {"A": StageHealth("monitor_signal", "PASS", ()),
           "B": StageHealth("monitor_signal", "WARN", ("gap 7d",))}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ()),
           "B": StageHealth("deterministic_scoring", "PASS", ())}
    rows = {r.stage: r for r in build_panel_rows(sig, det, now="t")}
    assert rows["monitor_signal"].status == "WARN"
    assert rows["deterministic_scoring"].status == "PASS"


def test_deterministic_row_worst_of_and_carries_reasons():
    sig = {"A": StageHealth("monitor_signal", "PASS", ())}
    det = {"A": StageHealth("deterministic_scoring", "FAIL", ("composite",))}
    rows = {r.stage: r for r in build_panel_rows(sig, det, now="t")}
    assert rows["deterministic_scoring"].status == "FAIL"
    assert any("composite" in r for r in rows["deterministic_scoring"].reasons)


def test_failing_deterministic_health_never_gates_a_bias():
    # GUARD (§8 step 4): a FAIL deterministic_scoring health is NOT in the gating set,
    # so apply_eval_gate (M1) never suppresses on it. Only monitor_signal/llm suites gate.
    det_fail = StageHealth("deterministic_scoring", "FAIL", ("composite",))
    healths = (StageHealth("monitor_signal", "PASS", ()),
               StageHealth("monitor_impact", "PASS", ()),
               StageHealth("monitor_narrative", "PASS", ()),
               det_fail)
    gate = apply_eval_gate(_sig(), health=healths, gating_stages=GATING_STAGES_M1)
    assert gate.suppressed is False
    assert "deterministic_scoring" not in GATING_STAGES_M1
    assert gate.badge == "validated"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_panel_rows.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_panel_rows'`.

- [ ] **Step 3: Add `build_panel_rows` to `determinism.py`**

In `src/irc/monitor/eval/determinism.py`, add the import of `ValidationPanelRow` to the existing types import line:

```python
from irc.monitor.eval.types import StageHealth, ValidationPanelRow
```

Then append at the end of the file:

```python
def _row(stage: str, healths: dict, now: str) -> ValidationPanelRow:
    """Aggregate per-fund StageHealths → worst-of one panel row (spec §5)."""
    statuses = [h.status for h in healths.values()]
    overall = worst_status(statuses) if statuses else "PASS"
    reasons = tuple(r for h in healths.values() for r in h.reasons)
    return ValidationPanelRow(stage=stage, status=overall, ran_at=now, reasons=reasons)


def build_panel_rows(
    signal_healths: dict, deterministic_healths: dict, *, now: str,
) -> tuple[ValidationPanelRow, ...]:
    """Both panel rows from the per-fund healths. monitor_signal reflects RAW
    signal_health worst-of (divergence 1); deterministic_scoring is panel-only."""
    return (
        _row("monitor_signal", signal_healths, now),
        _row("deterministic_scoring", deterministic_healths, now),
    )
```

Note: `build_panel_rows` keyword-onlys `now` so the call site reads `build_panel_rows(sig, det, now=...)`. The test passes `now="t"` positionally-by-keyword — keep the `*` so `now` is keyword-only (matches the test and the spec signature `build_panel_rows(signal_healths, deterministic_healths, now)`).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_panel_rows.py -q`
Expected: 4 passed.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check src/irc/monitor/eval/determinism.py tests/monitor/eval/test_panel_rows.py`
Expected: `All checks passed!`

```bash
git add src/irc/monitor/eval/determinism.py tests/monitor/eval/test_panel_rows.py
git commit -m "feat(monitor-eval-m2): build_panel_rows + panel-only gating guard"
```

### Task 12: Generalize `validation_panel_html` to N rows

Spec §5: `validation_panel_html(*, rows: tuple[ValidationPanelRow, ...], badge_counts: dict[str, int])`. Renders N rows (was hardcoded to one); `badge_counts` stays the gate summary.

**Files:**
- Modify: `src/irc/monitor/eval/panel.py`
- Test: `tests/monitor/eval/test_panel.py` (re-express existing two tests + add multi-row)

- [ ] **Step 1: Rewrite `tests/monitor/eval/test_panel.py` for the new N-row signature**

Replace the entire contents of `tests/monitor/eval/test_panel.py` with:

```python
from __future__ import annotations
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import ValidationPanelRow


def _row(stage, status, reasons=()):
    return ValidationPanelRow(stage=stage, status=status,
                              ran_at="2026-06-16T09:00:00+08:00", reasons=reasons)


def test_panel_renders_both_rows_with_counts():
    rows = (_row("monitor_signal", "PASS"),
            _row("deterministic_scoring", "PASS"))
    html = validation_panel_html(
        rows=rows,
        badge_counts={"validated": 2, "caveated": 1, "gated": 1})
    assert "Validation" in html
    assert "monitor_signal" in html
    assert "deterministic_scoring" in html
    assert "2026-06-16T09:00:00+08:00" in html
    assert "PASS" in html
    assert "validated: 2" in html and "gated: 1" in html and "caveated: 1" in html


def test_panel_is_pure_string():
    html = validation_panel_html(
        rows=(_row("monitor_signal", "FAIL", ("nav",)),),
        badge_counts={"gated": 7})
    assert isinstance(html, str) and html.startswith("<section")
    assert "FAIL" in html and "gated: 7" in html


def test_panel_renders_per_row_reasons():
    rows = (_row("monitor_signal", "WARN", ("gap 7d",)),
            _row("deterministic_scoring", "FAIL", ("159934: composite",)))
    html = validation_panel_html(rows=rows, badge_counts={"gated": 1})
    assert "gap 7d" in html
    assert "159934: composite" in html
```

- [ ] **Step 2: Run to verify it fails (old single-row signature)**

Run: `uv run pytest tests/monitor/eval/test_panel.py -q`
Expected: FAIL — `TypeError: validation_panel_html() got an unexpected keyword argument 'rows'` (current signature takes `stage_health=`).

- [ ] **Step 3: Rewrite `panel.py` to render N rows**

Replace the entire contents of `src/irc/monitor/eval/panel.py` with:

```python
"""PURE Validation panel HTML. M2: N rows (monitor_signal + deterministic_scoring).
No I/O."""
from __future__ import annotations
from html import escape
from irc.monitor.eval.types import ValidationPanelRow

_BADGE_ORDER = ("validated", "caveated", "gated")


def _counts_str(badge_counts: dict[str, int]) -> str:
    parts = [f"{b}: {badge_counts[b]}" for b in _BADGE_ORDER if b in badge_counts]
    return ", ".join(parts)


def _row_html(row: ValidationPanelRow, badges: str) -> str:
    reasons = "; ".join(row.reasons)
    return (
        f"<tr><td>{escape(row.stage)}</td>"
        f"<td>{escape(row.status)}</td>"
        f"<td>{escape(row.ran_at)}</td>"
        f"<td>{escape(badges)}</td></tr>"
        f'<tr class="panel-reasons"><td colspan="4" class="muted">'
        f"{escape(reasons)}</td></tr>"
    )


def validation_panel_html(
    *, rows: tuple[ValidationPanelRow, ...], badge_counts: dict[str, int],
) -> str:
    badges = _counts_str(badge_counts)
    body = "".join(_row_html(r, badges) for r in rows)
    return (
        '<section class="validation-panel"><h2>Validation</h2>'
        '<table class="validation"><tr><th>stage</th><th>overall</th>'
        '<th>ran_at</th><th>badges</th></tr>'
        f"{body}</table></section>"
    )
```

- [ ] **Step 4: Run to verify the panel tests pass**

Run: `uv run pytest tests/monitor/eval/test_panel.py -q`
Expected: 3 passed.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check src/irc/monitor/eval/panel.py tests/monitor/eval/test_panel.py`
Expected: `All checks passed!`

```bash
git add src/irc/monitor/eval/panel.py tests/monitor/eval/test_panel.py
git commit -m "feat(monitor-eval-m2): multi-row validation panel"
```

### Task 13: Rewire `render_html._panel` + `render_report` to take explicit `panel_rows`

Spec §5: `render_report` receives `panel_rows` explicitly; `_panel` no longer reverse-engineers a row from `GateDecision`. `badge_counts` is still computed from gates and passed separately.

**Files:**
- Modify: `src/irc/monitor/render_html.py`
- Test: `tests/monitor/test_render_html_eval.py` (re-express divergence-1 assertion)

- [ ] **Step 1: Re-express the divergence-1 test in `test_render_html_eval.py`**

In `tests/monitor/test_render_html_eval.py`, the `_render` helper must now pass `panel_rows`. First update `_render` (lines 31-36) to build panel rows from healths and pass them. Replace the `_render` helper with:

```python
def _render(view, gate):
    from irc.monitor.render_html import render_report
    from irc.monitor.eval.determinism import build_panel_rows
    from irc.monitor.eval.types import StageHealth
    prov = Provenance("1", "1", "1", "")
    # Build panel rows from RAW healths: a clean-but-gated fund's signal health is
    # PASS (divergence 1) — the gate outcome lives in badge_counts/EVAL-GATED.
    sig_health = {"008986": StageHealth("monitor_signal", "PASS", ())}
    det_health = {"008986": StageHealth("deterministic_scoring", "PASS", ())}
    rows = build_panel_rows(sig_health, det_health, now=_NOW)
    return render_report((view,), prov, prior_signal=None, now=_NOW,
                         gates={"008986": gate}, panel_rows=rows)
```

Then re-express `test_validation_panel_overall_is_not_pass_when_fund_is_gated` (lines 76-83). Replace it with:

```python
def test_validation_panel_gate_outcome_visible_via_badge_when_fund_gated():
    # Divergence 1 (spec §5/§8): the monitor_signal ROW now shows RAW signal_health
    # (PASS for a clean fund), NOT the gate outcome. Gate-outcome visibility moves
    # to the EVAL-GATED badge + badge_counts, which still render.
    html = _render(_view(), _gate(badge="gated", suppressed=True, reason="nav_quality FAIL"))
    assert "EVAL-GATED" in html        # gate outcome still visible (badge)
    assert "gated: 1" in html          # gate outcome still visible (badge_counts)
    assert "Validation" in html        # panel still renders
```

Also update `test_render_report_backwards_compatible_without_gates` (lines 68-73) — `panel_rows` defaults to `None`/`()`, so the bare call must still work. Leave that test as-is (it calls `render_report` without `gates` and without `panel_rows`; the default must keep it green).

- [ ] **Step 2: Run to verify it fails (panel_rows kwarg not yet accepted)**

Run: `uv run pytest tests/monitor/test_render_html_eval.py -q`
Expected: FAIL — `TypeError: render_report() got an unexpected keyword argument 'panel_rows'`.

- [ ] **Step 3: Rewire `render_html.py`**

In `src/irc/monitor/render_html.py`:

(a) Update the panel import line (line 10) and the types import (line 11). Replace:

```python
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import GateDecision, StageHealth
```

with:

```python
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.types import GateDecision, ValidationPanelRow
```

(b) Replace the `_panel` function (lines 133-147) with one that takes pre-built rows + computes `badge_counts` from gates:

```python
def _badge_counts(views: tuple[FundView, ...], gates: dict[str, GateDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in views:
        g = gates.get(v.fund_id)
        if g is not None:
            counts[g.badge] = counts.get(g.badge, 0) + 1
    return counts


def _panel(
    views: tuple[FundView, ...], gates: dict[str, GateDecision] | None,
    panel_rows: tuple[ValidationPanelRow, ...],
) -> str:
    if not gates or not panel_rows:
        return ""
    return validation_panel_html(rows=panel_rows, badge_counts=_badge_counts(views, gates))
```

(c) Update `render_report` (lines 150-176) to accept `panel_rows` and pass them. Change the signature and the `_panel(...)` call. Replace:

```python
def render_report(
    views: tuple[FundView, ...],
    provenance: Provenance,
    *,
    prior_signal: dict | None,
    now: str,
    gates: dict[str, GateDecision] | None = None,
) -> str:
```

with:

```python
def render_report(
    views: tuple[FundView, ...],
    provenance: Provenance,
    *,
    prior_signal: dict | None,
    now: str,
    gates: dict[str, GateDecision] | None = None,
    panel_rows: tuple[ValidationPanelRow, ...] = (),
) -> str:
```

and change the `panel = _panel(views, gates, now)` line (line 171) to:

```python
    panel = _panel(views, gates, panel_rows)
```

- [ ] **Step 4: Run to verify the render tests pass**

Run: `uv run pytest tests/monitor/test_render_html_eval.py -q`
Expected: all pass (the re-expressed gated test + the rest).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check src/irc/monitor/render_html.py tests/monitor/test_render_html_eval.py`
Expected: `All checks passed!`

```bash
git add src/irc/monitor/render_html.py tests/monitor/test_render_html_eval.py
git commit -m "feat(monitor-eval-m2): render_report takes explicit panel_rows (divergence 1)"
```

### Task 14: `_compute_gates` returns the 3-tuple; call site builds + passes panel rows

Spec §5/§7: `_compute_gates` stops discarding health → returns `(gates, signal_healths, deterministic_healths)` from the SAME single per-fund projection already built in its loop (no extra `build_eval_trace` pass). The `run_monitor` call site builds `panel_rows` via `build_panel_rows` and passes them to `_write_outputs → render_report`.

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Modify: `tests/monitor/eval/test_gate_flip_m1.py` (3 call sites unpack the 3-tuple)
- Modify: `tests/monitor/test_acceptance_eval.py` (re-express gated panel assertion)

- [ ] **Step 1: Update the M1 gate test call sites to unpack the 3-tuple**

In `tests/monitor/eval/test_gate_flip_m1.py`, the three `gates = mc._compute_gates(...)` calls (lines 91, 103, 116) must unpack. Change each:

Line 91-92:
```python
    gates = mc._compute_gates([fund], [view], [_bundle()], min_obs=2,
                              root=tmp_path, today=today)
```
→
```python
    gates, _sig_h, _det_h = mc._compute_gates([fund], [view], [_bundle()], min_obs=2,
                                              root=tmp_path, today=today)
```

Apply the identical change to the call at lines 103-104 and the call at lines 116-117.

- [ ] **Step 2: Run to verify the gate test fails (old single-return shape)**

Run: `uv run pytest tests/monitor/eval/test_gate_flip_m1.py -q`
Expected: FAIL — the unpack `gates, _sig_h, _det_h = ...` raises `ValueError: too many values to unpack` because `_compute_gates` still returns a bare tuple of gates. (Or `cannot unpack non-iterable` depending on length.) This is the red state.

- [ ] **Step 3: Change `_compute_gates` to return the 3-tuple**

In `src/irc/commands/monitor_cmd.py`, replace the `_compute_gates` function (lines 347-370). The key changes: build `signal_health` AND `deterministic_health` from the SAME `projection`; collect both into dicts; return the 3-tuple.

First add the import. In the eval-import block (after line 42 `from irc.monitor.eval.trace import build_eval_trace`), add:

```python
from irc.monitor.eval.determinism import deterministic_health, build_panel_rows
```

Replace the function body:

```python
def _compute_gates(
    funds: list[MonitorFund], views: list[FundView], bundles: list[FundTraceBundle],
    *, min_obs: int, root: Path, today: str,
) -> tuple[tuple[GateDecision, ...], dict, dict]:
    """Build each fund's trace projection ONCE, derive its monitor_signal health AND
    its deterministic_scoring health from that single projection, append the two
    run-global LLM-suite healths, and apply the M1 gate. The suite healths are
    resolved once (run-global) — identical for every fund (OQ-E). Returns
    (gates, signal_healths, deterministic_healths); deterministic_scoring is
    PANEL-ONLY and never gates (spec §4.3)."""
    now = datetime.now(timezone(timedelta(hours=8)))
    suite_healths = _suite_healths(root, today, now)
    gates: list[GateDecision] = []
    signal_healths: dict = {}
    deterministic_healths: dict = {}
    for fund, view, bundle in zip(funds, views, bundles):
        stub = GateDecision(fund.id, False, (), "validated", "")
        projection = build_eval_trace(
            ((fund, view, stub, bundle),), engine_version=_ENGINE_VERSION,
            run_date="",
        )["funds"][fund.id]
        signal_health = monitor_signal_health(
            projection, minimum_observations=min_obs,
            stale_days=_NAV_STALE_DAYS, today=date.today(),
        )
        signal_healths[fund.id] = signal_health
        deterministic_healths[fund.id] = deterministic_health(fund.id, projection)
        health = (signal_health, *suite_healths)
        gates.append(apply_eval_gate(view.signal, health=health,
                                     gating_stages=GATING_STAGES_M1))
    return tuple(gates), signal_healths, deterministic_healths
```

- [ ] **Step 4: Update the `run_monitor` call site to unpack + build panel rows**

In `src/irc/commands/monitor_cmd.py`, update the `run_monitor` orchestration (lines 488-495). Replace:

```python
    gates = _compute_gates(list(funds), views, bundles,
                           min_obs=cfg.history.minimum_observations,
                           root=root, today=_today)
    prior = _read_prior_signal(root, _today)
    out = root / "outputs" / _today / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    _write_eval_artifacts(out, root, list(funds), views, bundles, gates, run_date=_today)
    _write_outputs(out, views, prior, gates)
```

with:

```python
    gates, signal_healths, deterministic_healths = _compute_gates(
        list(funds), views, bundles,
        min_obs=cfg.history.minimum_observations, root=root, today=_today)
    panel_rows = build_panel_rows(signal_healths, deterministic_healths, now=_now_iso())
    prior = _read_prior_signal(root, _today)
    out = root / "outputs" / _today / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    _write_eval_artifacts(out, root, list(funds), views, bundles, gates, run_date=_today)
    _write_outputs(out, views, prior, gates, panel_rows)
```

- [ ] **Step 5: Thread `panel_rows` through `_write_outputs`**

In `src/irc/commands/monitor_cmd.py`, update `_write_outputs` (lines 309-314). Add the import of `ValidationPanelRow` to the eval-types import line (line 44). Replace:

```python
from irc.monitor.eval.types import FundTraceBundle, GateDecision
```

with:

```python
from irc.monitor.eval.types import FundTraceBundle, GateDecision, ValidationPanelRow
```

Then replace the `_write_outputs` signature + the `render_report` call:

```python
def _write_outputs(out: Path, views: list[FundView], prior: dict | None,
                   gates: tuple[GateDecision, ...] = ()) -> None:
    prov = Provenance(_ENGINE_VERSION, "1", "1", "")
    gate_map = {g.fund_id: g for g in gates} if gates else None
    html = render_report(tuple(views), prov, prior_signal=prior, now=_now_iso(),
                         gates=gate_map)
```

with:

```python
def _write_outputs(out: Path, views: list[FundView], prior: dict | None,
                   gates: tuple[GateDecision, ...] = (),
                   panel_rows: tuple[ValidationPanelRow, ...] = ()) -> None:
    prov = Provenance(_ENGINE_VERSION, "1", "1", "")
    gate_map = {g.fund_id: g for g in gates} if gates else None
    html = render_report(tuple(views), prov, prior_signal=prior, now=_now_iso(),
                         gates=gate_map, panel_rows=panel_rows)
```

- [ ] **Step 6: Run the M1 gate test to verify it passes (wiring unchanged, just unpacks)**

Run: `uv run pytest tests/monitor/eval/test_gate_flip_m1.py -q`
Expected: all pass (M1 gating behaviour is unchanged; only the return shape grew).

- [ ] **Step 7: Re-express the acceptance test's gated-panel assertion**

In `tests/monitor/test_acceptance_eval.py`, `test_stale_nav_fund_is_eval_gated_and_panel_names_it` (lines 63-75) already asserts only `"EVAL-GATED" in html and "Validation" in html` for the panel — both still hold under divergence 1 (the EVAL-GATED badge and the panel both render). No assertion in this file keys off the `monitor_signal` row showing FAIL, so the existing assertions remain valid. Add an explicit gate-outcome-visibility assertion to lock divergence 1. Replace the last two lines of that test:

```python
    html = (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").read_text(encoding="utf-8")
    assert "EVAL-GATED" in html and "Validation" in html
```

with:

```python
    html = (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").read_text(encoding="utf-8")
    # Divergence 1 (spec §5/§8): gate outcome stays visible via the EVAL-GATED badge
    # and the badge tally, NOT via the monitor_signal row status.
    assert "EVAL-GATED" in html and "Validation" in html
    assert "gated: 1" in html
    assert "deterministic_scoring" in html   # the new panel row renders
```

- [ ] **Step 8: Run the acceptance test**

Run: `uv run pytest tests/monitor/test_acceptance_eval.py -q`
Expected: 2 passed.

- [ ] **Step 9: Lint + commit**

Run: `uv run ruff check src/irc/commands/monitor_cmd.py tests/monitor/eval/test_gate_flip_m1.py tests/monitor/test_acceptance_eval.py`
Expected: `All checks passed!`

```bash
git add src/irc/commands/monitor_cmd.py tests/monitor/eval/test_gate_flip_m1.py tests/monitor/test_acceptance_eval.py
git commit -m "feat(monitor-eval-m2): wire deterministic_scoring panel row through _compute_gates"
```

**Verification point (Milestone 4):** `_compute_gates` returns `(gates, signal_healths, deterministic_healths)` from one projection; `build_panel_rows` produces both rows; the panel renders 2 rows; the EVAL-GATED badge + `gated: N` tally still show the gate outcome; `deterministic_scoring` is absent from `GATING_STAGES_M1`; `test_gate_flip_m1.py` green.

---

## Milestone 5 — Whole-suite verification

### Task 15: Full monitor suite + lint + M0 oracle

**Files:** none (verification only).

- [ ] **Step 1: Run the entire monitor test tree**

Run: `uv run pytest tests/monitor -q`
Expected: all pass, sub-10s total. Confirms the new D1/D2 modules, the re-expressed render/acceptance/panel tests, and the unchanged M1 gate tests are all green together.

- [ ] **Step 2: Run the eval tests that touch the M0 oracle path**

Run: `uv run pytest tests/monitor/eval -q`
Expected: all pass (including `test_gate_flip_m1.py`, `test_determinism.py`, `test_panel.py`, `test_panel_rows.py`).

- [ ] **Step 3: Lint the full src + tests touched**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 4: Run the free in-run eval to confirm no registry breakage**

Run: `uv run irc eval monitor_signal`
Expected: completes with a `monitor_signal` report verdict; D2's new module did not alter the M0 metrics path (D2 is a superset surfaced in-run, the offline `oracle_signal_match` is untouched).

- [ ] **Step 5: Confirm no new pytest marker leaked in**

Run: `uv run pytest --co -q tests/monitor/test_signal_property.py 2>&1 | tail -3`
Expected: collection succeeds; `--strict-markers` does not complain (hypothesis needs no marker).

- [ ] **Step 6: Final commit (if any verification surfaced a fix)**

Only if Steps 1-5 required a code change. Otherwise skip.

```bash
git add -A
git commit -m "test(monitor-eval-m2): verification pass — full monitor suite green"
```

**Verification point (Milestone 5):** `uv run pytest tests/monitor -q` green; `uv run ruff check src tests` clean; `uv run irc eval monitor_signal` runs; no new marker; suite offline + sub-second-per-property.

---

## Self-Review notes (author)

- **Spec coverage:** §3 D1 (oracle Task 3; per-scorer properties Tasks 4-8) · §3.4 derandomize profile (Task 1) · §4 D2 determinism module (Tasks 9, 11) · §4.1 P0 fund_id-explicit (Task 9 signatures) · §4.3 not-a-gate (Task 11 guard) · §5 panel data-flow + ValidationPanelRow + build_panel_rows + multi-row panel + render_report (Tasks 10-14) · §5 divergence 1 re-expressions (Tasks 12-14) · §6 KNOWN_NA_REASONS single source + two-way exhaustiveness (Task 2) · §7 architecture map (every NEW/MODIFY file has a task) · §8 TDD ordering (milestones follow steps 1→4).
- **Float policy:** categoricals exact; composite/numeric via `_EPS = 1e-9`; production's `round(...,4)` honored by `test_composite_equals_rounded_oracle` and `diff_signal`.
- **Layering:** `determinism.py` imports `factors.KNOWN_NA_REASONS` (core, single source) + `evals._shared.status.worst_status` (allowed pure helper, mirrors `structural.py:6`). No I/O/AkShare/LLM/settings/fs import.
- **Judgment calls:** (1) `build_panel_rows` placed in `determinism.py` rather than a new module — the spec lists it in §5 without a file; `determinism.py` is the pure home that already owns `deterministic_health` and `worst_status`, and §7 does not mandate a separate file. (2) ~~`tests/monitor/conftest.py` (monitor-scoped) created rather than editing root `tests/conftest.py`~~ — **CORRECTED by orchestrator (spec fidelity, Task 1):** spec §3.4 explicitly says extend the existing `tests/conftest.py` (a rev-3 P2 resolution the author already weighed). The profile is now appended to the root `tests/conftest.py`; no new conftest is created. `tests/spend` is added to the Milestone-0 verification to confirm the root `_skip_spend_gate` fixture still behaves. (3) The M1 gate test's 3 call sites were not enumerated in the spec but MUST change because `_compute_gates`'s return shape grows (Task 14 Step 1) — confirmed by reading `test_gate_flip_m1.py:91,103,116`.
