# PROGRESS — live tracker

States: ⏳ pending · 🔄 in-flight · ✅ done · ⚠️ blocked · ⏭️ skipped

| ID | Title | spec | plan | impl | QA | review | fix | merge |
|---|---|---|---|---|---|---|---|---|
| 001 | Package evals/ for installed CLI + regression test | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| 002 | Eval registry with lifecycle classification | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| 003 | Shared artifact locator | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| 004 | Report-date policy follows source | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| 005 | Discovery runner modernization | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| 006 | Gold_score runner modernization | ✅ | — | ✅ | ✅ | ✅ | — | ✅ |
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
- 2026-05-18 — Item 004 merged. `evals/_shared/report_paths.py` (`report_dir`, `write_report`) is the single path-builder; `write_missing_input_report` delegates. `scoring` and `opportunity` runners migrated to `locate` + `write_report`. Full suite: 1173 pass. Pre-existing lint issues (6) left for a later cleanup commit — not introduced by this change.
- 2026-05-18 — Item 005 merged. Discovery runner reads dated `discovered_watchlist.csv` via shared locator; `filter_integrity` default columns aligned with producer's CSV (`instrument_id`, `ticker`, `role`); schema-mismatch FAIL surfaces missing columns in `notes` instead of silently degrading. 172 tests in `tests/evals/` pass.
- 2026-05-18 — Item 006 merged. Gold_score runner reads dated (`gold_regime.json`, `gold_band.yaml`) pair via locator. Historical metrics (drivers_freshness, regime_flip_4w, tilt_within_preferences_band) removed from runner — they needed fields the current producer no longer writes — and the report `notes` lists them as Phase 2 redesign candidates. Three new metrics grounded in current schema: `gold_regime_schema_completeness`, `gold_tilt_valid_enum`, `gold_score_in_range`. 177 evals tests pass.
