# MASTER-SPEC — Monitor Report v2

**Mode:** spec (single feature, N=1)
**Source:** [docs/superpowers/specs/2026-06-30-monitor-report-v2-design.md](../superpowers/specs/2026-06-30-monitor-report-v2-design.md)
**Detected:** 2026-06-30
**Base branch:** `main`
**Feature branch:** `claude/wizardly-shamir-60a599` (worktree branch, non-protected; item sub-branch PRs land here; feature→main PR opened, NOT merged — no opt-in this turn)

## Scope

The input is a single, already-grilled design spec for `irc monitor` report v2. It defines six render-derived components plus an inline forward scorer, all of which land as **one feature** (one PR, TDD'd in 5 internal phases). This is a single IN-scope item.

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | Monitor Report v2 — market composite anchor, news overlay, charts, annotations, freshness, 限购 tag, market-composite forward logging/scoring | **IN** | The whole spec is one cohesive feature; the author explicitly chose a single PR with 5 TDD sub-phases (§13). |

## Hard non-goals (from spec §2 / §16 — enforced as constraints, not separate items)

- No change to composite-`C` math, factor weights, gating, `published_state`, or `_ENGINE_VERSION` (stays 3).
- Full composite `C` stays the canonical published/tracked signal.
- `render_report` / `render_*` stay PURE (no I/O, no JS, no remote refs).
- No new network or LLM calls.
- Per-constituent daily news (existing v2.1 item) — OUT.
- Faster forward maturation — OUT (function of engine-3 day accrual only).

## OUT-scope items

None. The spec's "Out of scope" entries are non-goals/constraints, not deferred work items — recorded above, not in SKIPPED.md.
