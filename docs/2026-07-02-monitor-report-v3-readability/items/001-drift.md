Verdict: PASS

Subagent: sonnet
Plan checklist items: 6 phases (P1–P6) + 19 final-verification items (V1–V19); phase step counts: P1 19 steps, P2 16 steps, P3 47 steps, P4 21 steps, P5 (steps not individually numbered above the excerpt read but verified via commit+tests), P6 46 steps. Core per-phase deliverables audited below = 6/6.
Verified present in diff: 6/6 phases' mandated deliverables confirmed against actual diff hunks (cited below), plus V1–V19 spot-verified by direct command execution (ruff, pytest, `irc config validate`).

## Per-phase verification (diff evidence)

**P1 — source tiers + ingest gate (commit `79e2b124`)**
- `src/irc/monitor/source_tiers.py` new file: `SourceTiers`, `classify()`, `tiers_from_config()`, `TIER_LABEL` — byte-for-byte matches plan Step 1.3.
- `src/irc/schemas/monitor.py`: new `SourceTiersConfig` + `MonitorConfig.source_tiers` field (diff hunk `+class SourceTiersConfig` / `+    source_tiers: SourceTiersConfig`).
- `config/monitor.yaml` AND `src/irc/templates/config/monitor.yaml` both got the identical `source_tiers:` block (config-template trap #141 respected; verified via `sed` on both diff hunks at lines 73–122 and 2666–2715 of the package diff).
- `_search_theme` gated at ingest edge (`monitor_cmd.py`, commit `79e2b124`): `classify(domain, tiers) == "blocked"` drop-before-`make_evidence_item`, confirmed via `git show 79e2b124 -- src/irc/commands/monitor_cmd.py`.

**P2 — theme-search consolidation (commit `6857e03a`)**
- `_search_all_themes(provider, themes, *, tiers)` searches once per unique theme (`git show 6857e03a`), replacing per-fund `_search_theme` (removed same commit).
- `build_evidence_pool(fund, *, theme_results)` is pure per-fund assembly reading a shared map — signature change confirmed.
- Same-cids equivalence test present: `tests/commands/test_monitor_cmd_theme_consolidation.py::test_build_evidence_pool_two_funds_same_hit_share_url_but_differ_by_owner` (asserts differing owner-bound cids but identical `(url, date)` — Phase-4 dedup precondition). `test_run_monitor_searches_each_theme_exactly_once_across_whole_fund_set` verifies the end-to-end call count. All 6 tests pass (`pytest tests/commands/test_monitor_cmd_theme_consolidation.py` → 6 passed).

**P3 — narrative v3 (commit `45acb421`)**
- `gather_narrative` import removed from `monitor_cmd.py`; per-fund call site replaced with `empty_narr = NarrativeDoc(fund.id, (), (), (), "empty_pool")` (confirmed via diff, line `-narr = gather_narrative(` / `+empty_narr = NarrativeDoc(...)`).
- `src/irc/monitor/narrative_macro.py` (239 lines): `build_macro_pool`, `gather_macro_narrative`, `THEME_DISPLAY_NAME`, CJK guard (`_cjk_ratio`, `_passes_language_guard`, `_CJK_MIN_RATIO = 0.30`) all present and grep-confirmed.
- `eval/trace.py`: `_SCHEMA_VERSION` bumped `"5"` → `"6"`; `_macro_narrative()` serializer + `macro_narrative=None` kwarg on `build_eval_trace` — confirmed via diff.
- `narrative.json`'s reserved `"__macro__"` key confirmed present in `_narrative_dump`'s diff hunk.
- 8 monkeypatch-site sweep (plan Step 3.23b) verified by direct grep of current tree: `tests/monitor/test_narrative.py` still directly imports/calls `gather_narrative` (module retained, by design — untouched); `tests/commands/test_monitor_cmd.py` carries the affirmative absence-assertion `test_run_monitor_never_calls_gather_narrative_per_fund` (`assert not hasattr(mc, "gather_narrative")` — passes); `tests/commands/test_monitor_cmd_theme_consolidation.py` uses `raising=False` as specified; zero lingering `gather_narrative`/`NarrativeResult`/`_FakeNarr` references in `test_monitor_cmd_heat.py`, `test_monitor_cmd_drilldown.py`, `test_monitor_cmd_valuation.py`, `test_monitor_constituent.py`, `test_monitor_cmd_trace.py`.

**P4 — citation UX v2 (commit `18b4c67b`, amended by `c599d455`)**
- `CitationIndex`/`build_citation_index`/`_identity_key` — canonical `(url or title, date)` dedup confirmed in `render_html.py`.
- `build_tier_badges`: constituent-pool cids always `"快照"`, theme-pool via `classify()` → `TIER_LABEL` — confirmed.
- Hover-date parity in **both** `render_html.py::_sup_local` and `render_cards.py::_sup` — both functions read identically (`date_part = f" · {date}" if date else ""`), confirming the plan-amendment commit `c599d455` (Step 4.8c, added *after* the original Step 4.8b under-scoped the fix to `_sup_local` only) was actually implemented, not just documented.
- `constituent_pool_items` threaded end-to-end: `render_report(..., constituent_pool_items=...)` → `_write_outputs(..., constituent_pool_items=...)` → `run_monitor`'s `constituent_pool_items = tuple(ev for b in bundles for ev in b.constituent_pool)` — all 3 call sites confirmed via grep.

**P5 — 今日速览 overview strip (commit `7db0c53f`)**
- `src/irc/monitor/render_overview.py`: 3 rows (`_flip_row`, `_actionable_row`, `_health_row`) + `overview_html`, `compute_flips`, `compute_actionable`, `compute_data_health` all present.
- Gate-respect confirmed: `compute_actionable` imports and filters on `irc.monitor.eval.gate.published_state`, excluding `EVAL_GATED`.
- `today` is a required kwarg on `compute_data_health`/`_stale_count`, derived purely as `now[:10]` inside `render_report` — no clock read under `render_*`.
- Divergence note (non-blocking, see Plan amendments below): overview wiring lives inside `render_html.py::render_report` (calling the `compute_*` builders there) rather than in `monitor_cmd.py` calling `overview_html` directly and passing a pre-built string, as the plan's docstring implied ("consumed by monitor_cmd.py at the edge"). All required inputs (views/gates/prior_signal/panel_rows/prior_run_date/purchase_tags) are already `render_report` parameters and the `compute_*` functions remain pure (no I/O) — functionally equivalent, purity intact. Treated as an authorized plan amendment (see below), not a drift finding, since the plan's data-shape docstring was descriptive/vague on placement, not prescriptive of a specific call-site.

**P6 — dark-data honesty + stale badges + timeline names + 盘中提示 (commit `86b26aa7`)**
- `eval/panel.py`: `_INFORMATIONAL_STAGES = frozenset({"flow_coverage", "valuation_coverage"})`, `_INFORMATIONAL_LABEL = "观测"`, amber at `flow_cover < 0.50`, `age >= STALE_EVAL_DAYS` (10d) amber — all confirmed via grep; `STALE_EVAL_DAYS`/`STALE_AFTER_DAYS` (10 vs 14) kept decoupled per `test_stale_after_14_days_is_separate_from_10_day_amber_cue`.
- `render_drilldown.py::all_na_columns` present, matches plan's pure-helper signature exactly.
- `render_timeline.py`: `_row_html`/`bias_timeline_html` gained `fund_names` kwarg, renders `名称(代码)`, falls back to bare code when unknown — confirmed.
- `provisional_flow_annotation_html(*, symbol_value, as_of_hhmm)` renders `截至{HH:MM}` from an edge-stamped actual fetch time (not hardcoded `"12:15"`) — confirmed; `_provisional_flow_for_fund` pure helper + `run_monitor`'s once-per-run `_provisional_flow_note` call + `now_dt`/`validation_panel_html` required-now threading all confirmed via grep and passing tests.
- `industry_reason` metadata fix in `src/irc/monitor/_dual_track.py` (`dual_track_score`'s self-score-None early-return branch now sets `industry_reason = "industry_no_data"` when the industry leg is also unusable) — this is the item pre-authorized in the task's "known adjudicated extras" list. Verified as a genuine, narrowly-scoped, well-documented bug fix directly exposed by Phase 6's new `all_na_columns`/`_row_reason` header-note-collapse mechanism (confirmed via `tests/monitor/test_holding_metrics.py::test_dual_track_self_and_industry_both_na_sets_industry_no_data_reason`, whose docstring explicitly names it "Phase 6 review fix" and explains the metadata-leak it closes). In scope, not drift.

## Non-goals verified

- `_ENGINE_VERSION = "3"` unchanged (`src/irc/commands/monitor_cmd.py:79`).
- No hunk touching `factors.py`, `eval/gate.py`, or any composite/scoring/weights/bands file (`git diff --stat` + targeted `diff --git a/src/irc/monitor/factors.py` / `eval/gate.py` greps return zero hits in the package diff).
- No `datetime.now()` calls under `render_*` (only docstring *mentions* of the constraint in `render_overview.py`/`eval/panel.py`, no live calls); `now`/`now_dt` are threaded as required kwargs end-to-end (verified in `render_html.py`, `eval/panel.py`, `monitor_cmd.py`).
- No `requests`/`open(` calls introduced under `src/irc/monitor/render_*.py`.
- No `<script>` tags or `http(s)://` remote refs introduced in render output (grep clean).
- `基金概况` absent repo-wide (`grep -rn "基金概况" src/irc/` → no output).
- `tests/monitor/test_report_v2_invariants.py` (which encodes several of these invariants as executable assertions) passes.

## Test execution evidence

Ran directly (not delegated): `tests/monitor/test_source_tiers.py` (15 passed), `test_narrative_macro.py` (17 passed), `test_monitor_cmd_theme_consolidation.py` (6 passed), `test_render_html_citations.py` (15 passed), `test_render_overview.py` (18 passed), `test_eval_panel.py` (9 passed), `test_all_na_columns.py` (4 passed), `test_render_timeline.py` (9 passed), `test_render_drilldown.py` (21 passed), `test_monitor_constituent.py` (18 passed), `test_monitor_cmd_theme_consolidation/trace/eval_wiring/heat.py` (21 passed), `test_monitor_cmd_timeline/valuation.py` (14 passed), `test_render_html/render_cards/evidence/report_v2_invariants.py` (73 passed), `test_render_html_eval/predictive/timeline + eval/test_panel.py` (24 passed). All V-checklist-cited new tests in `test_monitor_cmd.py` pass individually (`eval_gated_fund_excluded`, `theme_chips_end_to_end`, `never_calls_gather_narrative`, `threads_macro_narrative`, `provisional_flow_*` ×5). `uv run ruff check` over the full touched surface (V17) → `All checks passed!`. `uv run irc config validate` (V15) → exit 0, `source_tiers` accepted.

Non-blocking observation (not a drift finding): `tests/commands/test_monitor_cmd.py` run as a whole file is intermittently slow/appears-to-hang (~7s per e2e test, occasionally longer) because `_patch_edges`/some individual tests never stub `fetch_purchase_table`, which does a real (gracefully-degrading) network call. Confirmed via `git show b9b4f132:tests/commands/test_monitor_cmd.py` that this gap pre-dates item 001 (present since PR #128) — it is not introduced or worsened by this diff, and every test that matters for this drift check passes when run individually or in small groups. Flagged for awareness, not a plan violation.

## Drift findings

None. No unimplemented plan items, no functional scope creep, no missing functionality found. Every file touched by the diff maps to: (a) a phase's mandated deliverable, (b) an explicitly pre-authorized "known adjudicated extra" (P2 sibling-test fixes, `_build_theme_results` stubs, `metrics_narrative.py` theme-keyed scorer fix, `test_holding_metrics.py`/e2e coverage tests, `CitationIndex` call-site/golden regens), or (c) authorized bookkeeping (`PROGRESS.md`, `001-plan.md` itself via the `c599d455` amendment commit, and the final `c04129aa` tracker-only commit).

## Plan amendments made

One amendment, of the "small divergence + genuinely vague plan text" kind (not touching plan step *content*, only noting an implementation-mechanism note already present in the plan's own docstring language):

- **Before** (plan, Phase 5 data-shapes section): "Pure builder helpers (consumed by `monitor_cmd.py` at the edge — these take already-computed views/gates/prior, no I/O themselves)."
- **After** (as-built): `compute_flips`/`compute_actionable`/`compute_data_health`/`overview_html` are called from inside `render_html.py::render_report` (which already receives views/gates/prior_signal/panel_rows/prior_run_date/purchase_tags as parameters), not from `monitor_cmd.py` directly.
- **Rationale**: the plan's own phrase "no I/O themselves" is the load-bearing constraint (purity), and it holds — `render_report` is itself a pure function; calling the `compute_*` builders one level deeper (inside `render_report` instead of at `monitor_cmd.py` and passing a finished string) changes only which pure function orchestrates other pure functions, not the purity boundary, the data flow, or any observable behavior. All the V7 gate-respect test and the wiring is confirmed correct end-to-end. This is not amending any checkbox item's pass/fail criteria — it is a one-line placement clarification for a genuinely under-specified sentence ("consumed by monitor_cmd.py at the edge" was describing intent/data-availability, not mandating a specific call-site), and I am not editing `001-plan.md` itself (no plan-file edit made or needed; this note exists only in this verdict per the amendment-rules' "every amendment must appear in your verdict body" requirement — since no plan text was actually changed, no separate commit to `001-plan.md` was made for it).
