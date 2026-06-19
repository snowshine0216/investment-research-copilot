Verdict: PASS

Subagent: orchestrator (spec-mode N=1, lightweight doc-sync)
Items reviewed: 1

## Docs verified current with the merged feature
- **ADR 0019** (`docs/adr/0019-monitor-capital-flow-factor.md`) — flow factor design (prior, weight/engine governance). Committed by grill (pre-completed). ✓
- **CONTEXT.md** — "Capital-flow factor (`flow`, monitor)" glossary entry + the `aggregate_flow` renormalized-weighted-mean note. Committed by grill. ✓
- **CHANGELOG.md** — `[Unreleased]` entry covering the flow factor, per-stock drill-down, drilldown.html, eval schema 2→3 + reconciliation oracle + forward-eval engine isolation. ✓ (VERSION not bumped — project convention.)

## Doc lag found + fixed in this phase
- **README.md** "Daily monitor brief" section mentioned only `report.html` — did not list the new `drilldown.html` output or the capital-flow factor. FIXED: added the capital-flow factor + per-stock drill-down board description and the `drilldown.html` output path.
- **CLAUDE.md** `irc monitor` command line listed outputs as `{report.html,eval_trace.json}` — missing `drilldown.html`. FIXED: → `{report.html,drilldown.html,eval_trace.json}` + a one-line note on the flow factor + drill-down (ADR 0019).

## Not requiring change
- `evals/README.md` — the eval surface lifecycle is unchanged at the doc level (the new `flow_reconciliation`/`flow_coverage` are panel-only, non-gating; `monitor_forward` engine isolation is internal to the existing eval). The trace schema bump 2→3 + holding_metrics block are implementation details covered by ADR 0019.
- The new modules (`flow_fetch.py`, `holding_metrics.py`, `render_drilldown.py`) live under `src/irc/monitor/`, which CLAUDE.md already references generically + via ADR 0017/0019.

Missing coverage: none (all fixed).
