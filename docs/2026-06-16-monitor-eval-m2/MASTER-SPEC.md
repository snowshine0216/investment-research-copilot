# MASTER-SPEC — Monitor Eval M2 (Deterministic Rigor)

**Mode:** spec (single feature, N=1)
**Run dir:** `docs/2026-06-16-monitor-eval-m2/`
**Source spec:** [`docs/superpowers/specs/2026-06-16-monitor-eval-m2-deterministic-rigor-design.md`](../superpowers/specs/2026-06-16-monitor-eval-m2-deterministic-rigor-design.md) (rev 3, approved for planning 2026-06-16)
**Feature branch:** `claude/xenodochial-cohen-339150` (current worktree branch; non-protected). Sub-PR base = this branch. Final roll-up PR base = `main` (opened, not merged).

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | Monitor Eval M2 — deterministic rigor (D1 property+oracle pytest suite over the 6 pure scorers; D2 in-run `deterministic_scoring` panel row + `ValidationPanelRow` contract; `KNOWN_NA_REASONS` single-source extraction) | **IN** | One cohesive milestone; both deliverables share the `KNOWN_NA_REASONS` extraction and the pure monitor cores. Approved-for-planning design doc with explicit In/Out scope, oracle policy, float policy, and a TDD order (§8). |

No OUT-scope items — the spec already declares its own non-goals (no new eval registry stage, no gating stage, no calibration, no LLM/network, M0 metrics.py consolidation deferred). Those are design constraints inside item 001, not separate backlog items. See SKIPPED.md (empty).

## Key constraints carried from the spec (must hold in impl)

- **No new `irc eval <stage>`** and **no new gating stage.** `deterministic_scoring` is panel-only, **excluded from `apply_eval_gate`**; `GATING_STAGES_*` unchanged. Guard test required (§8.4).
- **Fully pure / offline.** No weight/band calibration, no LLM, no network, no new live marker. Full suite stays green and offline.
- **Hybrid oracle policy (§3.1):** independent oracles only where a genuinely different formulation exists; pure formula-transcriptions get properties only. Oracles live in test-only `tests/monitor/_oracle.py`, never in production.
- **`aggregate_news_factor` value = `clamp(Σ wᵢ·impactᵢ·confᵢ)`** (clamped weighted **sum**, NOT normalized by Σw); only the returned **confidence** is the weighted mean. Properties must reflect this (§3.1 P2).
- **`KNOWN_NA_REASONS` lives in `factors.py`** (the producer — single source), NOT in the eval overlay. `determinism.py` imports it. Refactor `_na()` call sites to named constants. Two-way exhaustiveness test; `constituent_no_coverage` is emitted by two branches (many-to-one codes→branches, not a dead-code false positive).
- **`recompute_signal_from_trace` takes `fund_id` explicitly** (P0, rev 3) — `fund_id` is only the `funds` dict key, absent from the per-fund trace value; `compute_signal` reads `fund.id`.
- **`determinism.py` may import pure `evals._shared.status.worst_status`** (as `structural.py`/`staleness.py` already do) — the ADR 0017 ban is I/O/AkShare/LLM/settings/filesystem, none of which `evals._shared.status` is.
- **Decided divergence 1:** the `monitor_signal` panel row now shows the aggregated raw `signal_health` (worst-of), not the gate outcome. Gate-outcome visibility preserved via `badge_counts`/`EVAL-GATED`. Re-express `test_render_html_eval.py`, `test_acceptance_eval.py`, `test_panel.py` (§8).
- **Float policy (§3.3):** exact equality for categoricals; `abs(diff) < 1e-9` for the numeric `composite` oracle; production rounds to 4dp.
- **Determinism config (§3.4):** register a `derandomize=True` hypothesis profile in the **existing** `tests/conftest.py` (extend, do not create); no new pytest marker (`--strict-markers` unaffected).
- **`hypothesis>=6.100`** added to BOTH `[dependency-groups].dev` and `[project.optional-dependencies].dev`.
