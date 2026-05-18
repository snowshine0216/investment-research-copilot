# MASTER-SPEC — Eval truthfulness Phase 1

**Source:** [docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md](../docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md)

**Feature branch:** `claude/intelligent-shtern-d84f4d` (current worktree branch)

**Final integration:** single PR worktree → main after all items merge.

---

## Decomposition

The source spec has two phases. **Phase 1 (truthfulness)** is fully implementable now and lands as 10 items below. **Phase 2 (green suite)** depends on classifying the output of the repaired Phase 1 evals — judgment work that requires Phase 1 to land first, so it is OUT-of-scope for this run (see [SKIPPED.md](SKIPPED.md)).

Items are ordered so that foundational changes land first (packaging, registry, locator, report-date policy) and the runner modernizations follow. Each runner item is independent of the others once the foundations are in.

## IN-scope items

| ID | Title | Why | Depends on |
|---|---|---|---|
| 001 | Package `evals/` for installed CLI + regression test | Fix the immediate `ModuleNotFoundError` from `uv run irc eval research`; keep top-level `evals/` namespace per spec §Recommended-architecture-1. | — |
| 002 | Eval registry with lifecycle classification | Replace inline runner dict with a registry that records lifecycle (active / inactive_legacy / inactive_uninstrumented / unimplemented_active) and `in_all_suite` flag; CLI emits clear inactive-stage error and excludes `news` + `queries` from `--all`. | 001 |
| 003 | Shared artifact locator `evals/_shared/locator.py` | Pure helpers that find today's valid dated artifact set, fall back to latest, return `(paths, artifact_date)`; support single- and multi-file contracts; reject partial multi-file sets. | 001 |
| 004 | Report-date policy: dated reports follow source date | Update report-writing helpers so dated runners place reports under `outputs/<artifact-date>/evals/<stage>/report.json`. Mutable sources (DuckDB, research_status.json) keep run-date. Apply to `scoring` and `opportunity` runners whose read contracts are already current. | 003 |
| 005 | Discovery runner modernization | Read dated `discovered_watchlist.csv`; use shared locator + report-date policy; fail loudly on missing required CSV columns. | 002, 003, 004 |
| 006 | Gold_score runner modernization | Read dated `gold_regime.json` + `gold_band.yaml`; preserve only metrics supportable by current artifacts. | 002, 003, 004 |
| 007 | Allocation runner modernization | Read dated `proposed_allocation.yaml`; metrics that depend on absent fields must be flagged for Phase 2, not silently zeroed. | 002, 003, 004 |
| 008 | Trade_plan runner modernization | Read dated `trade_plan.yaml` and its `trades` list. | 002, 003, 004 |
| 009 | Memo runner modernization | Read dated `memo.md`; use current sidecars only where the metric can still be grounded in them. | 002, 003, 004 |
| 010 | Architecture runner modernization | Replace `research_memo.md` in `_REQUIRED_OUTPUTS` with current names; use shared locator to find latest valid dated output dir; do not relax `max_file_loc`. | 002, 003, 004 |

## OUT-of-scope items

| ID | Title | Why OUT |
|---|---|---|
| OOS-A | Phase 2A re-run + classify | Requires Phase 1 to land first; bucketing failures into product-defect / metric-defect / unfinished / warning needs human judgment on which signals to trust. |
| OOS-B | Phase 2B metric redesign (opportunity unthemed grouping, scoring distribution stability, etc.) | Each metric is a design call (what invariant should it measure?). Should follow 2A triage. |
| OOS-C | Phase 2C product/data defects (data freshness, scoring completeness, `ingest_cmd.py` 632-line refactor) | Real product changes that should be planned from fresh reports, not stale ones. |
| OOS-D | Phase 2D trigger implementation; queries persistence vs. retire; news retirement | Product decisions about whether to keep, implement, or remove stages. |
| OOS-E | Phase 2E green active suite end-state | Composite goal that's the consequence of finishing 2A–2D. |

See [SKIPPED.md](SKIPPED.md) for the explicit unblock path for each.

## Cross-cutting requirements (apply to every item)

- TDD per `~/.claude/CLAUDE.md`: write the failing test first.
- Pure functions for metric logic; isolate IO at runner edges.
- No mutation of arguments; immutable dataclasses / dicts.
- Each runner change must keep the existing missing-input FAIL discipline (input absent → FAIL exit code 2, FAIL report written).
- No threshold relaxation to make reports green.
- Active inactive stages (`news`, `queries`) MUST emit a distinct "inactive stage" CLI message when invoked directly, not a misleading missing-input report. `triggers` stays in active suite as an honest unimplemented FAIL.

## Stop conditions (red flags for this run)

- A runner change requires modifying the producer (CLI command) to change its artifact contract — that's a Phase 2 product change, stop and surface.
- Tests on the feature branch start failing for reasons unrelated to the eval framework — stop, do not paper over.
- A locator design discovers that some "current" artifact contract isn't actually written by today's pipeline — stop, surface; do not invent the contract.
