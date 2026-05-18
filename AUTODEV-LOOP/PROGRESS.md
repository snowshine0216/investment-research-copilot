# PROGRESS — live tracker

States: ⏳ pending · 🔄 in-flight · ✅ done · ⚠️ blocked · ⏭️ skipped

| ID | Title | spec | plan | impl | QA | review | fix | merge |
|---|---|---|---|---|---|---|---|---|
| 001 | Package evals/ for installed CLI + regression test | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| 002 | Eval registry with lifecycle classification | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| 003 | Shared artifact locator | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| 004 | Report-date policy follows source | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 005 | Discovery runner modernization | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 006 | Gold_score runner modernization | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 007 | Allocation runner modernization | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 008 | Trade_plan runner modernization | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 009 | Memo runner modernization | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 010 | Architecture runner modernization | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

## Notes

- Working branch: `claude/intelligent-shtern-d84f4d`
- Per-item PRs collapsed into per-item squashed commits (worktree mode); see MASTER-PLAN.md.
- Phase 3 final validation: ⏳

## Status log

- 2026-05-18 — Skill fired. MASTER-SPEC.md, MASTER-PLAN.md, SKIPPED.md drafted. Beginning 001.
- 2026-05-18 — Item 001 merged. `pyproject.toml` packages `evals` alongside `src/irc`; `tests/evals/test_packaging.py` guards via isolated subprocess import. CLI no longer raises ModuleNotFoundError. Full suite: 1143 pass, 20 skipped.
- 2026-05-18 — Item 002 merged. `evals/_shared/registry.py` is the single source of truth for stage list, runner module, lifecycle, and active-suite membership. `eval_cmd.py` rewritten to use registry. Direct invocation of `news`/`queries` now prints inactive-stage message (verified manually); `--all` skips them. Full suite: 1156 pass.
- 2026-05-18 — Item 003 merged. `evals/_shared/locator.py` provides pure `locate(repo_root, required_filenames, *, today_iso=None)` returning `LocatedArtifacts | None`. 12 tests cover today-vs-fallback, partial multi-file sets, non-date dirs, immutability. No runners consume it yet (items 005–010).
