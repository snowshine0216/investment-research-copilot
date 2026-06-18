# PROGRESS — Monitor valuation + heat factor wiring

Mode: spec (N=3) · Project type: non-web · PR shape: A · Feature branch: `monitor-valuation-heat-wiring`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ✅ `…001` | ✅ acdbfa7 | ✅ d792cac | ✅ [#163](https://github.com/snowshine0216/investment-research-copilot/pull/163) | ✅ verify | ✅ review | ✅ pr-review | ✅ 0 rounds (pre-push 7678c95) | ✅ 63f118a |
| 002 | ✅ | ⏭️ | ✅ (rev `1452551`) | ✅ `…002` | ✅ 1c7aae2 | ✅ 3a8a9bd | ✅ [#164](https://github.com/snowshine0216/investment-research-copilot/pull/164) | ✅ verify | ✅ review | ✅ pr-review | ✅ 0 rounds | ✅ 139e716 |
| 003 | ✅ | ⏭️ | ✅ `dce1e1a` | ✅ `…003` | ✅ 411691f | ✅ 40e5fc7 | ✅ [#165](https://github.com/snowshine0216/investment-research-copilot/pull/165) | ✅ verify | ✅ review | ✅ pr-review | ✅ 0 rounds (pre-push ac5fba7) | ✅ 83a9093 |

### Notes

- **spec** ✅: per-item spec excerpts written at decompose (`items/<id>-spec.md`), drawn verbatim
  from the master design doc. Source: `docs/superpowers/specs/2026-06-17-monitor-valuation-heat-factors-design.md`.
- **grill** ⏭️: pre-completed (spec mode) — user authored & grilled the design doc; orchestrator
  must not auto-invoke grill.
- **verify** column is the non-web post-ship verifier (`/verify`); `/qa` is N/A for this CLI project.
- Items: 001 = index-path valuation + vocab unification · 002 = look-through valuation ·
  003 = heat restriction leg.

### Artifact links (filled as phases complete)

- 001: spec → [items/001-spec.md](items/001-spec.md)
- 002: spec → [items/002-spec.md](items/002-spec.md)
- 003: spec → [items/003-spec.md](items/003-spec.md)

---

## FINAL STATUS — run complete ✅

- **Items merged: 3 / 3** (001 valuation index-path + vocab → PR #163 `63f118a`; 002 look-through → PR #164 `139e716`; 003 heat restriction leg → PR #165 `83a9093`). All squash-merged into the feature branch.
- **SKIPPED: 0 · BLOCKED: 0.** (AUM-Δ heat leg is a spec-design *deferral*, not a skip — see SKIPPED.md / TODOS.md.)
- **Per-item gates:** every item passed drift + ship + /verify + /ship-inline-review + /code-review (all PASS / PASS-WITH-NITS); grill ⏭️ (spec mode, user-authored).
- **Phase 3 (run-level):**
  - Workflow-completeness audit: PASS (ship/drift/verify/review/pr-review 3/3 each).
  - Integrated tests (monitor + command wiring + eval determinism): **576 passed, 12 skipped**, ruff clean.
  - Run-level /verify: PASS — `final-verify.md` (all 3 factors coexist; valuation+heat ELIGIBLE; gold/qdii_global stay profile_ineligible).
  - Doc-sync: PASS — `doc-sync.md` (CHANGELOG ×3 + TODOS follow-ups; CONTEXT/ADR no change needed).
- **Fixed in flow:** slice-1 query-time `CatalogException` crash + DuckDB connection leak (pre-push); slice-3 schema-drift observability (pre-push); **item-001 test-scope regression** — `tests/commands/test_monitor_cmd_eval_wiring.py` (4 RED→GREEN), surfaced at item 003 because items 001/002 scoped test runs to `tests/monitor/` only.
- **Deferred follow-ups (TODOS.md):** `009225`/`china_internet` not an index-valuation key; monitor-constituent stock-valuation coverage gap; unlogged corrupt-snapshot swallow in `load_latest_active_fund_cached`; AUM-Δ heat leg (no per-fund live QoQ source).

Feature branch: `monitor-valuation-heat-wiring`
Feature-branch PR: https://github.com/snowshine0216/investment-research-copilot/pull/166
Merged into protected branch: **no** (PR left open for user review)
