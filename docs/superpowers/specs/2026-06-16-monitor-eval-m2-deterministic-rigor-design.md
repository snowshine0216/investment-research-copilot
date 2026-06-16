# Monitor Eval M2 — Deterministic Rigor

**Status:** Approved for planning (2026-06-16, rev 2 — incorporates the design-review block below)
**Owner:** Xue Yin
**Relates to:** [monitor-eval roadmap §5 M2](2026-06-16-monitor-eval-roadmap.md) · [M0/M1 design](2026-06-16-monitor-eval-m0-m1-design.md) · [ADR 0017](../../adr/0017-monitor-evidence-isolation.md) · CONTEXT.md "Monitor eval spine"
**Milestone position:** M0 (spine) + M1 (LLM suites) are **built + merged to main** (PR #134, `4b8fdf3`). M2 is the next milestone. M3 (retro backtest + forward-ledger scorer) and M4 (ablation + economic-rationale ADR) follow.

> **Scope note.** The roadmap's **M2 is "deterministic rigor"** — property + oracle tests for the pure scorers, plus surfacing deterministic-stage health in the panel. (The retro backtest is **M3**, not M2.) This spec covers M2 only.

---

## 1. Problem

The deterministic scoring core — `build_factor_scores` → `compute_signal`, and the helpers
`trend_score`, `valuation_state_score`, `heat_score`, `aggregate_news_factor` — has **example-based
unit tests** ([`tests/monitor/test_signal.py`](../../../tests/monitor/test_signal.py),
`test_factors.py`, `test_trend.py`, `test_factor_maps.py`, `test_news_factor.py`) and an M0
**self-recompute oracle** ([`evals/monitor_signal/metrics.py::oracle_signal_match`](../../../evals/monitor_signal/metrics.py))
that re-runs `compute_signal` on the persisted `eval_trace.json` and compares four fields
(`status/bias/composite/signal_confidence`).

Two gaps remain:

1. **No coverage of the whole input space.** Worked examples confirm a handful of points;
   monotonicity, clamp bounds, renorm-sum, gate-predicate equivalence, band boundaries, and
   divergence determinism are not asserted *for all inputs*.
2. **The M0 oracle only diffs four derived fields.** Stale or malformed
   `signal.contributions` / `available_weight` / `present_families` / `divergence_codes` in the
   persisted trace would pass unnoticed, and the in-run validation panel surfaces only the gate
   outcome — not the deterministic stage's own health.

M2 closes both: an **offline property + hybrid-oracle test suite** (D1) and an **in-run
`deterministic_scoring` panel row** that recomputes the full signal from raw inputs and diffs it (D2).

## 2. Scope

**In:**
- D1 — `hypothesis`-driven (derandomized) property + hybrid-oracle pytest suite over the six pure
  scorers.
- D2 — a pure in-run `deterministic_scoring` health check + a new `ValidationPanelRow` render
  contract; the panel generalizes from one row to N rows.

**Out / non-goals:**
- **No new eval registry stage.** D1 is pytest; D2 is in-run. Neither adds an `irc eval <stage>`.
- **No additional gating stage.** `deterministic_scoring` is **panel-only and excluded from
  `apply_eval_gate`**. The existing M1 gate wiring (`GATING_STAGES_M1`, fresh-LLM-suite-FAIL
  suppression asserted by [`test_gate_flip_m1.py`](../../../tests/monitor/eval/test_gate_flip_m1.py))
  is unchanged.
- No weight/band calibration, no LLM, no network. Fully pure / offline.
- No modification to M0's `monitor_signal` artifact eval (see §7 for an optional future consolidation).

## 3. D1 — Offline property + hybrid-oracle suite

### 3.1 Oracle policy (hybrid, avoids circularity)

An **independent oracle** is written *only* where a genuinely different formulation exists; functions
that are already direct formula transcriptions get **properties only** (a second copy would be
circular). Independent oracles live in a **test-only** `tests/monitor/_oracle.py`, never in production.

| Target | Oracle (independent) | Properties (no second impl) |
|---|---|---|
| `compute_signal` | composite/renorm via a separate Σw′·s formulation; gate predicate; band classifier | renorm sums to 1 (or 0 when no factor present); `bias is None ⟺ status≠"ok"`; band monotonicity (raising `composite` never moves `bias` toward `REDUCE_BIAS`); reproducibility (same inputs → equal record) |
| `build_factor_scores` | — | each score is `(eligible=True, value∈[-1,1], reason="")` **or** `(eligible=False, value=None, reason∈KNOWN_NA_REASONS)`; per-profile eligibility correctness (`eligible_factors`); N/A reason coverage |
| `trend_score` | — | clamp `∈[-1,1]`; monotone non-decreasing in `r60` with structure/drawdown fixed; tanh saturation at extremes |
| `valuation_state_score`, `heat_score` | re-expressed lookup / decision table | ordering monotonicity (cheaper→higher; more crowded→lower); `None` on unrecognised state / no data |
| `aggregate_news_factor` | — | value = **clamped weighted evidence sum** `clamp(Σ wᵢ·impactᵢ·confᵢ)`; `None` on empty pool or non-positive total weight; **non-decreasing in a row's `impact` when that row's `weight ≥ 0` and `confidence ≥ 0`** |

> **Correctness note (P2).** `aggregate_news_factor` ([`news_factor.py:25`](../../../src/irc/monitor/news_factor.py))
> computes `value = clamp(Σ wᵢ·impactᵢ·confᵢ)` (a clamped weighted **sum**, *not* normalized by Σw);
> only the returned **confidence** is the weighted mean `Σ(wᵢ·confᵢ)/Σwᵢ`. Properties must reflect
> this — asserting a "weighted mean" for the value would be wrong / a stealth behaviour change.

### 3.2 Strategies (encode domain invariants)

`hypothesis` strategies generate **valid-domain** inputs so the property space exercises real
behaviour rather than `KeyError` / invalid-config noise:

- **Profiles** ∈ `PROFILES` keys ([`profiles.py`](../../../src/irc/monitor/profiles.py));
  **factor names** ∈ the known set (`_FAMILY_OF` keys in [`signal.py`](../../../src/irc/monitor/signal.py)).
- **Weights** non-negative; bands with `sell < buy` (both ∈[-1,1]); `minimum_confidence` ∈ [0,1].
- **`FactorScore`s** use `value ∈ [-1,1]`, `confidence ∈ [0,1]`, and production's eligible/value
  coherence (`eligible ⟹ value is not None`; `¬eligible ⟹ value is None`).
- **NAV series** non-empty, positive, date-monotonic; length ≥ `minimum_observations` where the
  target requires a present trend.

**Invalid inputs** (unknown profile, empty NAV, NaN, negative weights) are covered by **separate
explicit example tests**, not folded into the main property space.

### 3.3 Float policy

Exact equality for categorical outputs (`status`, `bias`, reason codes, divergence codes);
`abs(diff) < 1e-9` for the numeric `composite = Σw′·s` oracle (production rounds to 4 dp via
`round(..., 4)` — the property asserts `composite == round(Σ w′·s, 4)`).

### 3.4 Determinism config

The global rule requires fast, deterministic tests. Register a `derandomize=True` hypothesis profile
(`deadline=None`, bounded `max_examples` — e.g. 100–200, cheap for pure functions) in
`tests/conftest.py` (create if absent) and `load_profile` it. No reliance on `[tool.hypothesis]` in
`pyproject.toml` (hypothesis reads profiles from code).

## 4. D2 — In-run `deterministic_scoring` panel row

### 4.1 Source of truth = `factor_scores + resolved`

The persisted trace ([`trace.py`](../../../src/irc/monitor/eval/trace.py)) carries the **raw inputs**
(`resolved` = profile/weights/bands/min-confidence; `factor_scores` = the five `FactorScore`s) **and**
the **derived `signal` block** (`status/bias/composite/signal_confidence/available_weight/`
`present_families/contributions/divergence_codes`) separately. D2 recomputes the signal from the raw
inputs and diffs it against the recorded block — so it is **not self-referential** and catches stale
or malformed derived metadata (P1).

New pure module `src/irc/monitor/eval/determinism.py`:

```
KNOWN_NA_REASONS                                          # imported from factors.py (single source — §6)
recompute_signal_from_trace(trace_fund) -> SignalRecord  # rebuild MonitorFund from `resolved`
                                                         # + FactorScores from `factor_scores`; run compute_signal
diff_signal(recomputed, recorded_signal: dict) -> tuple[str, ...]   # names of mismatched fields
deterministic_health(trace_fund) -> StageHealth          # per fund (PASS / FAIL)
aggregate_deterministic_health(traces) -> StageHealth     # worst-of; reasons name offending funds
```

`diff_signal` compares recomputed-vs-recorded for: `available_weight`, `present_families`, **every
contribution** (`name`/`renorm_weight`/`value`/`contribution`/`confidence`), rounded `composite`,
`signal_confidence`, `status`, `bias`, `divergence_codes` (float fields via the §3.3 eps; categoricals
exact). `deterministic_health` additionally checks **N/A-reason validity**: every
`factor_scores[].reason` on an ineligible factor ∈ `KNOWN_NA_REASONS`. A non-empty diff or an unknown
reason → `FAIL` with the field/fund named in `reasons`; otherwise `PASS`.

**Layering** (ADR 0017 §3.3 import table): `determinism.py` imports only pure monitor cores
(`signal.py`, `types.py`, `factors.py`) + eval's own types. No I/O, AkShare, LLM, settings, or
`evals/`-root imports.

### 4.2 Relationship to M0 / D1

- **D2 is a strict superset of M0's `oracle_signal_match`** (full signal block vs four fields),
  surfaced in-run rather than only via `irc eval monitor_signal`.
- **Division of labour:** D2 (in-run, self-recompute from raw) catches **persisted-artifact
  inconsistency**; D1 (offline, independent oracle + properties) catches **`compute_signal` logic
  bugs**. Complementary — they share only the pure cores.

### 4.3 Not a gate

`deterministic_health` is **never passed to `apply_eval_gate`** ([`gate.py`](../../../src/irc/monitor/eval/gate.py))
and is **not** added to `GATING_STAGES_*`. It renders as an informational panel row only. (A future
milestone may decide whether an in-run deterministic FAIL should gate; M2 deliberately does not —
roadmap: "hardens confidence; no new runtime gate".)

## 5. Panel data-flow contract

Today `_compute_gates` ([`monitor_cmd.py:347`](../../../src/irc/commands/monitor_cmd.py)) computes
per-fund `signal_health` then **discards it**, and `_panel`
([`render_html.py:133`](../../../src/irc/monitor/render_html.py)) **reverse-engineers** a single
`StageHealth("monitor_signal", overall, ())` from gate badges. M2 makes the row data flow explicit.

New render contract in `src/irc/monitor/eval/types.py`:

```python
@dataclass(frozen=True)
class ValidationPanelRow:
    stage: str
    status: str                  # PASS | WARN | FAIL | UNKNOWN
    ran_at: str
    reasons: tuple[str, ...]
```

Changes:
- `_compute_gates` **stops discarding health** → returns `(gates, signal_healths)`.
- New pure `build_panel_rows(signal_healths, deterministic_healths, now) -> tuple[ValidationPanelRow, ...]`
  builds **both** rows from the healths (aggregating per-fund → worst-of).
- `validation_panel_html(*, rows: tuple[ValidationPanelRow, ...], badge_counts: dict[str, int])`
  renders **N rows** (was hardcoded to one). `badge_counts` (validated/caveated/gated tally) remains a
  legitimate **gate summary**, computed from gates and passed separately.
- `render_report` receives `panel_rows` explicitly; `_panel` no longer reverse-engineers a row from
  `GateDecision`.

**Decided divergence 1 (approved).** The existing `monitor_signal` row's status now reflects the
**aggregated raw `signal_health`** (worst-of across funds), not the gate-outcome
(`suppressed→FAIL`). It is more honest — the row is labelled `monitor_signal`, the structural stage —
and the gate outcome stays visible via `badge_counts`.

## 6. `KNOWN_NA_REASONS` — single source

The N/A reason codes are produced as inline string literals in
[`factors.py`](../../../src/irc/monitor/factors.py): `profile_ineligible`,
`trend_insufficient_history`, `valuation_no_anchor`, `valuation_unknown_state`, `heat_no_data`,
`macro_insufficient_families`, `macro_empty_pool`, `constituent_no_coverage`.

**Decided divergence 2 (approved).** The canonical `KNOWN_NA_REASONS` frozenset (and named per-reason
constants) live in **`factors.py`** — the producer, so there is a single source — and `determinism.py`
imports it. Putting the set in `eval/determinism.py` (as first suggested) and importing it back into
`factors.py` would invert the `eval → core` layering; the core must not depend on the eval overlay.
`factors.py`'s `_na(...)` call sites are refactored to use the named constants.

A test asserts the set is **exhaustive both ways**: every `_na` branch in `build_factor_scores` emits
a member of `KNOWN_NA_REASONS`, and every member is reachable (no dead codes).

## 7. Architecture map

```
src/irc/monitor/
  factors.py                 # + KNOWN_NA_REASONS (single source) + named reason constants; _na() uses them
  eval/determinism.py        # NEW pure: recompute_signal_from_trace, diff_signal,
                             #           deterministic_health, aggregate_deterministic_health (panel-only)
  eval/panel.py              # GENERALIZE: single row → N rows; validation_panel_html(rows, badge_counts)
  eval/types.py              # + ValidationPanelRow
  render_html.py             # _panel renders passed rows + badge tally; no GateDecision reverse-engineering
src/irc/commands/monitor_cmd.py   # _compute_gates returns (gates, signal_healths); builds panel rows
                                  #   incl. aggregate_deterministic_health from per-fund projections

tests/monitor/
  _oracle.py                 # NEW test-only independent reference impls (composite/renorm, gate, bands, maps)
  test_signal_property.py    # NEW (D1)
  test_factors_property.py   # NEW (D1)
  test_trend_property.py     # NEW (D1)
  test_factor_maps_oracle.py # NEW (D1)
  test_news_factor_property.py  # NEW (D1)
  conftest.py                # NEW/extend: register + load hypothesis derandomize profile
  eval/test_determinism.py   # NEW (D2)
  eval/test_panel.py         # EXTEND for multi-row

pyproject.toml               # add hypothesis>=6.100 to BOTH [dependency-groups].dev
                             #   and [project.optional-dependencies].dev (uv sync --all-extras is documented)
```

**Optional future consolidation (out of M2 scope).** M0's
[`evals/monitor_signal/metrics.py`](../../../evals/monitor_signal/metrics.py) has its own
`_rebuild_fund`/`_scores`; it could later import `determinism.recompute_signal_from_trace` to dedupe
(`evals/`→`src/` is the correct direction). Left untouched here to keep M2 tight.

## 8. Testing strategy (TDD)

Red → green → refactor; test files mirror source. Order:

1. `KNOWN_NA_REASONS` extraction + exhaustiveness test (smallest, unblocks D1 reason properties).
2. D1 oracle reference (`_oracle.py`) + property modules, one scorer at a time, hypothesis profile
   registered first so every property run is reproducible.
3. D2 `determinism.py` (`recompute`/`diff`/`health`/`aggregate`) with example-based unit tests over
   crafted trace fixtures (a clean trace → PASS; a trace with a corrupted contribution / bad reason →
   FAIL naming the field).
4. `ValidationPanelRow` + multi-row `validation_panel_html` + `_panel`/`_compute_gates`/`render_report`
   wiring; extend `test_panel.py`; assert `deterministic_scoring` never enters `apply_eval_gate`
   (guard test: a FAILing deterministic health does not suppress any bias).

Full suite stays green and offline. No new live marker.

## 9. Risks

- **Float order-of-operations** in the renorm oracle → use the §3.3 eps, not bit-equality.
- **Suite runtime** → bounded `max_examples`; pure functions keep it sub-second.
- **Hypothesis nondeterminism** → `derandomize=True` profile loaded in `conftest.py`.
- **Panel-row meaning change** (§5 divergence 1) → covered by an updated `test_panel.py` expectation;
  `badge_counts` preserves gate-outcome visibility.

## 10. Open questions (deferred)

- Whether an in-run `deterministic_scoring` FAIL should *ever* gate (M2: no; revisit post-M3).
- Final `max_examples` per property (tune during implementation to keep the suite sub-second).
- Whether to fold the M0 metrics.py consolidation (§7) into a later cleanup PR.
