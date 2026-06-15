# MASTER-SPEC — `irc monitor` daily brief + configurable LLM routing + schedule rework

Mode: **spec** (single feature; design doc already grilled — see source §14)
Run dir: `docs/2026-06-15-monitor-daily-report/`
Source spec: [`docs/superpowers/specs/2026-06-15-monitor-daily-report-design.md`](../superpowers/specs/2026-06-15-monitor-daily-report-design.md)
Verbatim copy: [`items/001-spec.md`](items/001-spec.md)

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | New `irc monitor` vertical (config + factors + signal + impacts + narrative + render) **bundled with** configurable LLM provider routing (§8) and schedule rework (§9) | **IN** | One cohesive design with a single goal; the three sub-changes are interdependent (monitor tasks need provider routing; schedule needs the new command). Already grilled. |

No OUT-scope items (single-feature spec). The source doc's own **Non-goals** (§1) remain non-goals and are honored by the design, not separate backlog items:

- No broad fund discovery / watchlist generation.
- No executable portfolio actions (buy/trim/exit) — research **bias** only (ADR 0015 owns action semantics).
- No position-aware sizing (no `account.yaml` holdings dependency).

The source doc's §12 "Open verification items" are **resolve-during-build** tasks, captured in the plan, not deferred OUT items.

## Why N=1 (not decomposed into a backlog)

The document is a single design spec, not a backlog (no `Items`/`Tasks` heading; numbered §sections are design sections, not independent features). The sub-parts cannot ship as independent PRs — the signal engine depends on config + factors; impacts/narrative depend on provider routing; schedule depends on the command existing. `superpowers:writing-plans` will produce the multi-phase plan and `superpowers:subagent-driven-development` will sequence the implementation task-by-task inside the one item.
