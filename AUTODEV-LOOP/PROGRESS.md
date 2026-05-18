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
| 007 | Allocation runner modernization | ✅ | — | ✅ | ✅ | ✅ | — | ✅ |
| 008 | Trade_plan runner modernization | ✅ | — | ✅ | ✅ | ✅ | — | ✅ |
| 009 | Memo runner modernization | ✅ | — | ✅ | ✅ | ✅ | — | ✅ |
| 010 | Architecture runner modernization | ✅ | — | ✅ | ✅ | ✅ | — | ✅ |

## Notes

- Working branch: `claude/intelligent-shtern-d84f4d`
- Per-item PRs collapsed into per-item squashed commits (worktree mode); see MASTER-PLAN.md.
- Phase 3 final validation: ✅ — see [cross-branch-diff.md](cross-branch-diff.md).

## Status log

- 2026-05-18 — Skill fired. MASTER-SPEC.md, MASTER-PLAN.md, SKIPPED.md drafted. Beginning 001.
- 2026-05-18 — Item 001 merged. `pyproject.toml` packages `evals` alongside `src/irc`; `tests/evals/test_packaging.py` guards via isolated subprocess import. CLI no longer raises ModuleNotFoundError. Full suite: 1143 pass, 20 skipped.
- 2026-05-18 — Item 002 merged. `evals/_shared/registry.py` is the single source of truth for stage list, runner module, lifecycle, and active-suite membership. `eval_cmd.py` rewritten to use registry. Direct invocation of `news`/`queries` now prints inactive-stage message (verified manually); `--all` skips them. Full suite: 1156 pass.
- 2026-05-18 — Item 003 merged. `evals/_shared/locator.py` provides pure `locate(repo_root, required_filenames, *, today_iso=None)` returning `LocatedArtifacts | None`. 12 tests cover today-vs-fallback, partial multi-file sets, non-date dirs, immutability. No runners consume it yet (items 005–010).
- 2026-05-18 — Item 004 merged. `evals/_shared/report_paths.py` (`report_dir`, `write_report`) is the single path-builder; `write_missing_input_report` delegates. `scoring` and `opportunity` runners migrated to `locate` + `write_report`. Full suite: 1173 pass. Pre-existing lint issues (6) left for a later cleanup commit — not introduced by this change.
- 2026-05-18 — Item 005 merged. Discovery runner reads dated `discovered_watchlist.csv` via shared locator; `filter_integrity` default columns aligned with producer's CSV (`instrument_id`, `ticker`, `role`); schema-mismatch FAIL surfaces missing columns in `notes` instead of silently degrading. 172 tests in `tests/evals/` pass.
- 2026-05-18 — Item 006 merged. Gold_score runner reads dated (`gold_regime.json`, `gold_band.yaml`) pair via locator. Historical metrics (drivers_freshness, regime_flip_4w, tilt_within_preferences_band) removed from runner — they needed fields the current producer no longer writes — and the report `notes` lists them as Phase 2 redesign candidates. Three new metrics grounded in current schema: `gold_regime_schema_completeness`, `gold_tilt_valid_enum`, `gold_score_in_range`. 177 evals tests pass.
- 2026-05-18 — Item 007 merged. Allocation runner reads dated `proposed_allocation.yaml` via locator. Historical metrics (`in_band_per_class`, `currency_in_tolerance`, `max_pair_correlation_1y`) removed from runner — current producer does not write `class_bands`, `currency_targets`, `currency_exposure`, or `correlation_matrix_1y`. Two metrics preserved: `weight_sum_deviation`, `effective_n`. Deferred set listed in report `notes`. 180 evals tests pass.
- 2026-05-18 — Item 008 merged. Trade_plan runner reads dated `trade_plan.yaml` via locator; trades list at `payload["trades"]`. Metric functions updated to read TradePlanRow field names (`venue_note`, `asset_class`, `triggers` list) — semantically equivalent to the historical metrics that read retired field names. Allowed-method map extended for `cn_etf`/`global_etf`. 184 evals tests pass.
- 2026-05-18 — Item 009 merged. Memo runner reads dated (`memo.md`, `memo_traceability.json`) pair via locator (multi-file contract). New `verbatim_ref_rate` metric grounded in `n_refs_quoted_verbatim / n_refs_provided`. Deferred: `auditor_no_factual_flags` (current `memo_audit.txt` is free-form), `length_drift_vs_baseline` (no baseline-chars contract). 188 evals tests pass.
- 2026-05-18 — Item 010 merged. Architecture runner picks today's outputs/<date>/ if present, otherwise the latest dated directory; report lands under that artifact date (not today). `_REQUIRED_OUTPUTS` updated from `research_memo.md` to `memo.md` to match producer. `max_file_loc` threshold unchanged — `ingest_cmd.py` at 632 lines remains an honest FAIL signal for Phase 2. 190 evals tests pass.
- 2026-05-18 — Phase 3 validation complete. Merged `origin/main` (`449615d`). Full suite: 1194 pass, 20 skipped, 0 fail. `irc eval --all` surfaces only the active suite. Ready to push and open PR.
