# MASTER-PLAN — Monitor Report v3 readability

Mode: **spec**
Project type: **non-web** (Python CLI/data pipeline; no browser surface — `/verify` runs post-ship, never `/qa`)
PR shape: **A** (per-item PR — default; no `--rollup` opt-in given this turn)
Base branch: `main` (protected, no merge opt-in given this turn)
Feature branch: `autodev/monitor-report-v3-readability-feature` (synthesized off `main`, pushed to origin)

## Per-mode skill skips (spec mode)

- `superpowers:brainstorming` — **skipped**. The source file is a user-authored design spec (`docs/superpowers/specs/2026-07-02-monitor-report-v3-readability-design.md`); brainstorming would silently rewrite intent.
- `grill-with-docs` — **pre-completed ⏭️**. Grill already ran directly on `main` before this autodev invocation: commit `1876987c` added ADR 0022 (evidence source tiers), the ADR 0017 addendum (synthetic `theme:<name>` owners + traced `macro_narrative`), and CONTEXT.md glossary terms. The spec text already reflects grilled decisions (§13 cites both ADRs). Orchestrator does not re-invoke grill per spec-mode contract.
- `superpowers:writing-plans` — **runs** (Opus, session-default model, no override). This is the entry point for Phase 2.

## Item order

Single item (001) — spec mode is degenerate N=1.

## Notes

- Source spec's own §12 "Phasing" lists 6 internal implementation phases (source tiers → theme consolidation → narrative v3 → citation v2 → 今日速览 → dark-data/stale badges), all within **one PR** ("single PR, each phase TDD'd + committed atomically"). This maps to one autodev item (001) with a plan that preserves those 6 phases as sequential, atomically-committed implementation steps — not 6 separate autodev items.
- Signature-change test-scope trap is called out explicitly in the source spec (§4, §11, §12-2) and in project memory ([feedback_test_scope_signature_changes](../../../../../.claude/projects/-Users-snow-Documents-Repository-investment-research-copilot/memory/feedback_test_scope_signature_changes.md)): after the theme-search consolidation signature change, run `tests/monitor/` AND `tests/commands/` **per-file** (whole-dir hangs on suite ordering), not just the mirror dir.
- `irc config validate` must be re-run after the `source_tiers:` config addition (template `src/irc/templates/config/monitor.yaml` — the #141 trap from project memory: forgetting the template breaks `irc init` + ~80 `tests/commands/` tests).
