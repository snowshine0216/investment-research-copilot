# PROGRESS — live tracker

States: ⏳ pending · 🔄 in-flight · ✅ done · ⚠️ blocked · ⏭️ skipped

| ID | Title | spec | plan | impl | tests | merge |
|---|---|---|---|---|---|---|
| 011 | Scoring reweight for DCA horizon | ✅ | ✅ | ✅ | ✅ | ✅ |
| 015 | Sector QDII sizing constraint | ✅ | ✅ | ✅ | ✅ | ✅ |
| 008 | Correlation filter caps intra-index | ✅ | ✅ | ✅ | ✅ | ✅ |
| 005 | Bond valuation yield anchor | ✅ | ✅ | ✅ | ✅ | ✅ |
| 007 | Equity earnings-yield sanity anchor | ✅ | ✅ | ✅ | ✅ | ✅ |
| 004 | Source-quality tiering | ✅ | ✅ | ✅ | ✅ | ✅ |
| 001 | Theme research query relevance | ✅ | ✅ | ✅ | ✅ | ✅ |
| 002 | Thesis intact requires relevance | ✅ | ✅ | ✅ | ✅ | ✅ |
| 003 | Provider degradation gate | ✅ | ✅ | ✅ | ✅ | ✅ |
| 006 | Gold drivers into tilt | ✅ | ✅ | ✅ | ✅ | ✅ |
| 012 | Trim-side discipline triggers | ✅ | ✅ | ✅ | ✅ | ✅ |
| 013 | Execution-drift alert | ✅ | ✅ | ✅ | ✅ | ✅ |
| 014 | FX / QDII premium diagnostics | ✅ | ✅ | ✅ | ✅ | ✅ |
| 010 | Role-bucket failure banner | ✅ | ✅ | ✅ | ✅ | ✅ |
| 009 | Audit becomes blocking gate | ✅ | ✅ | ✅ | ✅ | ✅ |

## Notes

- Working branch: `claude/adversarial-fixes-2026-05-19`
- Implementation collapsed into per-item squash commits on the feature
  branch (worktree mode), following the precedent of the prior
  `AUTODEV-LOOP/` run. Single PR to `main` at the end.
- Phase 3 final validation: re-run `irc run` and check each acceptance
  criterion against regenerated artifacts.

## Status log

- 2026-05-19 — Skill fired. MASTER-SPEC, MASTER-PLAN, SKIPPED drafted.
  Beginning with item 011 (config-only reweight) to validate the loop.
- 2026-05-19 — All 15 IN-scope items merged into
  `claude/adversarial-fixes-2026-05-19`. Focused unit suite green
  (607 pass). 2 pre-existing e2e failures unrelated to this branch.
  Phase 3 acceptance checks all PASS — see [cross-branch-diff.md](cross-branch-diff.md).
