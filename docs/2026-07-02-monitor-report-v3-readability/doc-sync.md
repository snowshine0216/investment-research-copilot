Verdict: PASS
Source: orchestrator-direct lightweight doc-sync (spec mode, N=1 — grill pre-wrote docs; this pass verifies coverage rides the feature branch)

Diff `origin/main...HEAD` docs surface (all verified present, actual diff read):
- docs/adr/0022-monitor-evidence-source-tiers.md — NEW (+53) — covers the source-tier ingest gate decision + rejected alternatives
- docs/adr/0017-monitor-evidence-isolation.md — addendum (+19) — synthetic `theme:<name>` owners + traced `macro_narrative`
- CONTEXT.md (+6/−1) — glossary terms for the tier system / macro narrative (grilled 1876987c, pre-run on local main; travels with this branch since origin/main never received it)
- CHANGELOG.md (+11) — [Unreleased] feature entry, no VERSION bump (project convention)
- TODOS.md (+4) — 3 deferred items from ship/phase reviews with provenance tags
- config/monitor.yaml (+34) — `source_tiers:` seeded from observed 07-01 domains (template mirrored — verified V16 `irc init` grep)

Coverage check: every functional change maps to a doc — tiers→ADR0022/CONTEXT/config, macro block→ADR0017 addendum/CHANGELOG, citation/overview/dark-data→CHANGELOG (render-layer, no ADR bar met), deferred nits→TODOS.
Missing coverage: none.
