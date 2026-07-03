# MASTER-SPEC — Monitor Report v3 readability

Mode: **spec**
Source input: [`docs/superpowers/specs/2026-07-02-monitor-report-v3-readability-design.md`](../../superpowers/specs/2026-07-02-monitor-report-v3-readability-design.md)
Status of source: design (brainstormed 2026-07-02); already grilled on `main` at `1876987c` (ADR 0022 — evidence source tiers; ADR 0017 addendum — synthetic `theme:<name>` owners + traced `macro_narrative`; CONTEXT.md glossary terms). Grill verdict is treated as pre-completed per spec-mode contract — the orchestrator does not re-run grill.

## IN scope (single item)

| id | Title | One-line goal |
|----|-------|----------------|
| 001 | Monitor report v3 readability | Make `irc monitor`'s report trustworthy in its *words*, not just its numbers: gate junk/unranked evidence sources at ingest (ADR 0022), consolidate 28→8 theme-search provider calls, replace 10 near-duplicate per-fund LLM narratives with one macro-narrative block + deterministic per-fund cards, dedup the citation appendix (134→~36), add a 今日速览 overview strip, and make dark-data / stale-eval states render honestly. **No scoring/engine-math change** — engine stays version 3. |

## OUT of scope

None — single-item spec mode, degenerate decomposition (N=1).

## Non-goals (carried from source spec §2 — binding constraints for impl/drift, not owned by this item)

- No change to composite math, factor weights, bands, gating, `published_state`, or `_ENGINE_VERSION` (stays 3).
- Not fixed here: constituent factor ±1 saturation (`news_factor.py:25`), macro_tilt same-day instability, stalled weekly pipeline, WS-C scout.
- `render_*` stay PURE (no I/O, no JS, no remote refs). ADR 0001 16-hex `[ref:]` format unchanged. ADR 0017 owner-binding preserved.
- Ingest drops are logged, not traced, except the one deliberate trace addition: run-level `macro_narrative` field in `eval_trace.json`, `schema_version` 5→6.

## Acceptance criteria (rolled up from source spec §11 Testing — full detail in items/001-spec.md)

- `source_tiers` classification truth table (blocked/1/2/3, suffix match, unknown→3, malformed config→3) passes.
- Theme-search consolidation: provider called exactly once per unique theme; per-fund pools equivalent to status quo for same hits; blocked hits absent from pools/impacts.
- Language guard (CJK-ratio) retry + persistent-failure drop; banned-verb guards still enforced.
- Macro block: ≤3 claims/theme, empty-evidence theme absent, fund chips deterministic, every fund card renders correctly with an EMPTY per-fund narrative doc.
- `eval_trace.json` schema 5→6 additive, old traces without `macro_narrative` still load.
- 今日速览: EVAL-GATED ADD_BIAS fund appears in 数据健康, never in 可操作.
- Panel vocabulary: informational stages render 观测 (never PASS); amber at `flow_cover` < 0.50; `ran_at` age amber at >10d, UNKNOWN(stale) still at >14d.
- Citation index: dedup by `(url or title, date)`; date + tier badge rendered; first-seen order; `[ref:` closure invariant holds.
- Dark data: all-N/A column collapse with reason code; flow chip at coverage 0 / below floor.
- Stale badges: 10-day boundary (9 green, 10 amber).
- Invariants re-asserted: no `<script>`/remote refs; `基金概况` absent; engine version untouched.
- Test-scope discipline: `tests/monitor/` + `tests/commands/` run **per-file** (whole-dir hangs, known repo trap — see [feedback_test_scope_signature_changes](../../../CLAUDE.md)) after the theme-search signature change (§4).

## Links

- Full spec: [`items/001-spec.md`](items/001-spec.md) (verbatim copy of source)
- ADR 0022: [`docs/adr/0022-monitor-evidence-source-tiers.md`](../../adr/0022-monitor-evidence-source-tiers.md)
- ADR 0017 addendum: [`docs/adr/0017-monitor-evidence-isolation.md`](../../adr/0017-monitor-evidence-isolation.md)
- Prior workstream (WS-A, merged): PR #190 (squash `284bfaeb`) — CN-egress data-plane light-up; this item is WS-B of the same roadmap (per memory `project_monitor_report_reliability_roadmap`)
