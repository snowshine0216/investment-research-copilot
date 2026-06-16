# PROGRESS — Monitor Eval M3 backtest

**Mode:** spec · **Project type:** non-web · **PR shape:** A · **Feature branch:** `claude/stupefied-swirles-a9365f`

| # | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|---|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ✅ | ✅ eff270b | 🔄 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

**Legend:** ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped (mode) · ⛔ refused gate

## Notes

- **001 spec** ✅ — user-provided design spec copied verbatim to [`items/001-spec.md`](items/001-spec.md) (871 lines, rev 6, 9 review rounds). Goal + Scope + Acceptance (§9 Testing) + Pinned decisions (§10) all present.
- **001 grill** ⏭️ — spec mode: user-grilled (9 documented adversarial review rounds in the spec appendix). Orchestrator must NOT auto-invoke grill on user-authored content.
- **001 verify** column = `/verify` (non-web XOR). No `/qa` column — this is a Python CLI, no browser surface.
- Phase 2 entry: Opus `superpowers:writing-plans` → `items/001-plan.md`.

## Impl notes (001)

- **11 phases / 26 plan tasks implemented** across 27 commits (`4904b36`..`eff270b`). Pure cores: constants, nav_history, stats, baselines, join, backtest, forward_score, review, predictive_panel. Edge: monitor_forward runner+metrics, registry, monitor_cmd producer-append + panel wiring, render_html, backfill script. Shared: latest_report `StageReportEntry`+history API (M0/M1 back-compat preserved).
- **Orchestrator-applied correction (`d572ec4`)** — the Opus plan's retro grid excluded on `status=="insufficient_evidence"`, which (verified empirically) emptied the retro grid entirely, since trend-only ALWAYS carries that status even above the 251-obs floor where the composite is a real non-zero value. Per spec §3 retro scores the continuous composite regardless of status; corrected to exclude only the degenerate `composite==0.0` case. Plan Task 11 amended to match; tests strengthened (non-empty-grid guard + flat-series degenerate fixture).
- **New-feature test surface: 435 passed**, all M3 source files <200 lines, ruff clean on all M3 files.
- **Known pre-existing failure (NOT introduced):** `tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports` — verified failing identically on the feature-branch base (one of the 24 baseline failures).

## Artifact links (filled as phases complete)

- spec: [`items/001-spec.md`](items/001-spec.md)
- plan: [`items/001-plan.md`](items/001-plan.md) (commit b6e8cc1 — 11 phases, 26 tasks, TDD-ordered)
- drift: _pending_
- ship: _pending_
- verify: _pending_
- review: _pending_
- pr-review: _pending_
