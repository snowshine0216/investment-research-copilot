# Item 001 — WS-1 Caveat transparency (P1 + P2 + OD-3)

**Run:** monitor-v4-explainability · **Source spec:** [2026-07-03-monitor-report-v4-explainability-design.md](../../superpowers/specs/2026-07-03-monitor-report-v4-explainability-design.md) §2 P1/P2, OD-3, §3 WS-1, §4 bullet 1
**Carries the ONE eval-trace schema bump 6→7** (MASTER-SPEC cross-cutting; items 002/004 must NOT bump again).

## Goal

Make every `⚠ caveated` badge in the daily monitor report self-explanatory without hover on a phone, and stop the caveats from recurring. Today `apply_eval_gate` (`src/irc/monitor/eval/gate.py:18-19`) returns an **empty reason** on the WARN/UNKNOWN branch, so all 10 funds show `⚠ caveated` with no visible cause; the actual cause is run-global (both LLM-suite healths UNKNOWN-stale). This item: (1) age-stamps the stale reason inside `staleness.resolve_health` (`("stale",)` → `("stale, 15d",)`); (2) assembles a per-fund caveat reason on the gate's caveated branch, symmetric with the existing FAIL-branch assembly (`GateDecision.reason` already exists — no new types); (3) renders it — chip gets a Chinese-labeled tooltip and becomes an anchor to `#validation-panel`, run-global LLM-suite causes dedupe to ONE 今日速览 line, fund-specific (`monitor_signal`) causes get a card-level `为何有保留` line, and the validation panel gains the manual-refresh remediation hint; (4) appends two best-effort `IRC_RUN_LIVE_LLM_EVAL=1` live eval runs to the Saturday weekly wrapper (`ops/launchd/run-weekly.sh`) so a weekly cadence keeps the suites permanently fresh under `STALE_AFTER_DAYS = 14` (eval-live spend gate applies unchanged). Trace `gate.reason` stays per-fund and complete regardless of render dedupe; `schema_version` bumps `"6"` → `"7"` here (shape-unchanged; the field just stops being empty).

## Acceptance criteria

Each bullet is independently verifiable by the named test file or command.

**Slice 1 — staleness age-stamp + gate reason assembly (pure)**

1. `resolve_health` (src/irc/monitor/eval/staleness.py) emits `("stale, {N}d",)` where `N = (now - ran_at).days`, instead of bare `("stale",)`. The `absent` / `skipped` / `corrupt_ran_at` reasons are unchanged (no age available). Unit tests in `tests/monitor/eval/test_staleness.py` cover: stale-with-age (e.g. 15d and 16d fixtures), boundary (exactly `stale_after_days` days → NOT stale, unchanged behavior), absent/skipped/corrupt unchanged.
2. `apply_eval_gate` caveated branch builds `reason` from the considered WARN/UNKNOWN stages, in the order they appear in `health`, one segment per stage formatted `"{stage}: {status} ({reasons joined with ', '})"` — parenthetical omitted when a stage's reasons tuple is empty — segments joined with `"; "`. Example (matches P1 verbatim): `monitor_impact: UNKNOWN (stale, 15d); monitor_narrative: UNKNOWN (stale, 16d)`. Assembly lives in a named helper so `apply_eval_gate` stays under the function-size budget. Unit tests in `tests/monitor/eval/test_gate.py` cover ALL badge branches: WARN-only (monitor_signal), UNKNOWN-stale-with-age, mixed WARN + UNKNOWN, validated → reason stays `""`, gated (FAIL) branch byte-identical to today.
3. `gate.py` exports `RUN_GLOBAL_STAGES = GATING_STAGES_M1 - GATING_STAGES_M0` (i.e. `{monitor_impact, monitor_narrative}`) as the single source of the run-global/fund-specific classification used by the renderer.

**Slice 2 — render surfaces**

4. The caveated chip in `render_html._badge` renders as `<a class="val-chip val-caveated" href="#validation-panel" title="...">⚠ caveated</a>`; the `title` is the gate reason with Chinese stage labels substituted (`monitor_impact` → `影响评分质量评估`, `monitor_narrative` → `叙事质量评估`) and a `stale, {N}d` reason rendered as `上次质量评估已过期 {N}天`; unmapped stage names and other reason strings pass through raw; the whole title is HTML-escaped. Validated chips remain plain spans (no tooltip, no anchor — validated funds show none). Tests in `tests/monitor/test_render_html_eval.py`.
5. The validation panel section carries `id="validation-panel"` (`src/irc/monitor/eval/panel.py`), so the chip anchor resolves. Test in `tests/monitor/eval/test_panel.py`.
6. Run-global dedupe: a new pure helper in `render_overview.py` computes ONE 今日速览 line from the suite panel rows (stage ∈ `RUN_GLOBAL_STAGES`, status WARN/UNKNOWN) plus the gate map — e.g. `全部基金 caveated：LLM质量评估过期 15/16天 · 周六自动刷新` (`全部基金` when every gated fund's badge is `caveated`, else `{N}只基金`; ages parsed from the `stale, {N}d` reason strings — never recomputed from a clock; suites with `absent`/`skipped` reasons render as `LLM质量评估缺失` with no age). The line is absent when both suites are PASS/fresh, and is rendered ONCE in the overview strip — never repeated per card. Render tests in `tests/monitor/test_render_overview.py`: present-when-stale (with exact ages), absent-when-fresh, count-vs-全部基金 wording, absent-suite wording.
7. Card-level `为何有保留：…` line renders directly under the fund card `<h2>` ONLY when the fund's gate reason contains segments from fund-specific stages (segments NOT prefixed by a `RUN_GLOBAL_STAGES` member — today that means `monitor_signal` WARNs, e.g. nav gaps); run-global-only caveats produce NO card line; validated funds produce NO card line. Tests in `tests/monitor/test_render_html_eval.py`: fund-specific-only, run-global-only, mixed (card line shows only the monitor_signal segment), validated.
8. The validation panel renders the remediation hint when either suite row's status is UNKNOWN or WARN, exact text: `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact / monitor_narrative（受 eval-live 花费闸门约束）`. Absent when both suites are healthy. Tests in `tests/monitor/eval/test_panel.py`.
9. Source-spec §4 bullet 1 holds end-to-end: every caveated fund's reason is reachable without hover on a phone (run-global → the ONE overview line; fund-specific → the card line), and `gate.reason` is non-empty in `eval_trace.json` for every caveated fund (assert via the trace test in criterion 10).

**Slice 2b — schema bump (this item carries it)**

10. `trace._SCHEMA_VERSION` becomes `"7"`; the constant is exported and `monitor_cmd.py:485` (`Provenance(_ENGINE_VERSION, "2", "6", "")`) consumes it instead of a second hardcoded literal (the report header and trace can no longer drift). Trace shape is otherwise unchanged. Updated pins: `tests/monitor/eval/test_trace.py`, `tests/monitor/test_acceptance_eval.py`, `tests/commands/test_monitor_cmd_trace.py` (run per-file — the `tests/commands/` dir hangs as a whole). A trace test asserts a caveated fund's entry has non-empty `gate.reason`.
11. `_ENGINE_VERSION` is untouched (`git diff` shows no change to it); forward-ledger append logic is untouched, preserving forward comparability.

**Slice 3 — weekly eval refresh (OD-3)**

12. `ops/launchd/run-weekly.sh` appends, AFTER `notify-status` and BEFORE `exit "$rc"`, the two live eval runs: `IRC_RUN_LIVE_LLM_EVAL=1 "$UV_BIN" run irc eval monitor_impact` then the same for `monitor_narrative`, each individually guarded `|| echo "..."` (breadcrumb with the eval's rc; never aborts under `set -e`) and each bounded by `run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}"`. The wrapper's exit code remains the pipeline's `rc` regardless of eval outcomes. The eval-live spend gate applies unchanged (it lives inside `eval_cmd._run_live_gated` — no code change there). Text-pin tests + `bash -n` in `tests/ops/test_launchd_weekly.py`.
13. Early-exit paths (idempotency sentinel, lock contention) skip the eval runs too — once-per-day semantics preserved; the manual-preempt edge (a same-day manual `irc run` suppresses that Saturday's eval refresh) degrades to the stale chip + panel hint and is documented in the ops manual.

**Docs + hygiene**

14. `docs/monitor/README.md`: the "Monthly-ish (paid, manual)" live-LLM-eval maintenance row becomes "Weekly, automated (Saturday wrapper, best-effort)" with the manual command retained as the remediation/fallback; the Weekly process section mentions the suite refresh. `docs/diagrams/monitor-workflow.html` synced (weekly eval-refresh edge + caveat-reason surfaces). `ops/launchd/README.md` weekly-agent description updated. `evals/README.md:94` stale `schema_version "5"` corrected to `"7"`. Post-merge launchd agent reinstall is recorded as a post-merge ops note in the run dir (NOT code).
15. CHANGELOG `[Unreleased]` entry added; `VERSION` NOT bumped (versioning convention).
16. `uv run ruff check src tests` clean; `tests/monitor/`, `tests/monitor/eval/`, `tests/ops/` green; touched `tests/commands/` files green per-file.

## Non-goals

- WS-2 (macro direction/mechanism), WS-3 (divergence detail), WS-4 (industry fill) — separate items 002/003/004.
- No new types or fields on `GateDecision` / `StageHealth` / trace shape — only the existing `gate.reason` string gets populated.
- No change to gate semantics: caveated still never suppresses; `GATING_STAGES_M1` membership unchanged; `STALE_AFTER_DAYS` stays 14; `STALE_EVAL_DAYS` panel boundary stays 10.
- No per-card repetition of run-global causes (locked P2 dedupe), and no Chinese translation of `monitor_signal` reason strings beyond the locked label map (raw metric strings like `gap 12d` render as-is).
- No `_ENGINE_VERSION` bump; no narrative prompt change (that is item 002).
- No changes to `eval_cmd.py` / the spend gate / `evals/` runners; no launchd plist changes (wrapper only — reinstall is post-merge ops).
- No 数据健康 dark-factor count changes, no WS-C scout, no nav_cover backfill (spec §5).

## Constraints

- **Purity / effects at edges:** all new reason-assembly and render helpers are pure (no clock reads — ages come from the already-stamped reason strings or the threaded `now_dt`; render purity rule from report v3 stands). The ONLY I/O change is the shell wrapper.
- **FP + size budget:** no mutation of arguments; frozen dataclasses stay frozen; new helpers keep functions < 20 lines ideal; put render additions in `render_overview.py` / `panel.py` — `render_html.py` (489 lines) grows minimally (badge + card line only).
- **Public-API stability:** `apply_eval_gate` and `resolve_health` signatures unchanged; `render_report` signature unchanged (overview line computed from existing `panel_rows` + `gates` params); `overview_html` may gain one keyword-only param (internal render API, callers updated in the same change).
- **TDD:** red → green per slice; test files mirror sources (`gate.py` → `tests/monitor/eval/test_gate.py`, etc.).
- **Schema discipline:** exactly one bump 6→7 in this item; items 002/004 land their fields under `"7"`.
- **Security:** reason strings and the label-mapped tooltip are HTML-escaped before entering `title`/body; the wrapper inlines no secrets (env comes from `.env` via `uv run`; `IRC_RUN_LIVE_LLM_EVAL=1` is a flag, not a credential); paid-spend exposure is bounded by the unchanged eval-live spend gate.
- **Perf:** negligible — string assembly per fund per run; two extra weekly LLM eval invocations, watchdog-bounded, already budgeted by the spend gate.
- **Known suite hazard:** `tests/commands/` must be run per-file (whole-dir hangs — pre-existing ordering issue).

## Open questions resolved during brainstorming

1. **Stale reason tuple shape** — one string `"stale, 15d"`, not `("stale", "15d")`. It is a single fact (staleness with its age); P1's example renders it inside one parenthetical; a `startswith("stale")` check keeps the Chinese label mapping and the overview age-parse trivial.
2. **Segment format ambiguity** — locked as `"{stage}: {status} ({reasons})"` joined by `"; "`, parens omitted on empty reasons. Reason strings produced today (`gap 12d`, `missed N trading days`, `as_of older than Nd`, metric names) contain no `"; "`, so prefix-based segment filtering by the renderer is unambiguous; the gate test pins the format.
3. **How the renderer classifies run-global vs fund-specific** — via a new `RUN_GLOBAL_STAGES` frozenset in `gate.py` (derived `M1 − M0`, keeping classification next to the gating-set definitions), consumed two ways: the overview line derives from the run-global *panel rows* (structured, no string parsing); the card line filters *gate.reason segments* by stage prefix (per-fund data only exists there; panel rows are per-stage aggregates — verified in `determinism.build_panel_rows`).
4. **Where the overview ages come from** — parsed from the `stale, {N}d` reason string, not recomputed from `ran_at` vs a clock. Single source of truth: tooltip, trace, panel and overview can never disagree, and render stays clock-free.
5. **Do validated chips also become anchors?** — No. Acceptance says "validated funds show none"; an anchor with an empty tooltip invites misreading. Only the caveated chip changes.
6. **Wrapper placement of the eval runs** — after `notify-status`, before `exit`. A hung or failed eval can never delay the user's page or change the pipeline rc; each run gets its own watchdog (`IRC_WEEKLY_EVAL_TIMEOUT`, default 900 s) and `|| echo` breadcrumb. Early-exit paths (sentinel/lock) skip evals: keeps once-per-day semantics and lock protection; the rare manual-preempt Saturday degrades gracefully (chip + hint still point at the manual command) and is documented rather than engineered around.
7. **Provenance schema literal drift** — `monitor_cmd.py:485` hardcodes `"6"` separately from `trace._SCHEMA_VERSION`. Resolved: export the constant from `trace.py` and consume it in `monitor_cmd`, so this bump (and 002/004's non-bumps) cannot drift. In scope because both call sites are already touched by the bump.
8. **Stale doc found during exploration** — `evals/README.md:94` still says `schema_version "5"` (missed by the v3 5→6 bump). Corrected to `"7"` in this item's doc pass since we own the bump.
9. **Overview line prefix** — `全部基金` only when the actual caveated badge count equals the fund count; otherwise `{N}只基金`. Run-global causes hit every fund's gate, but a fund can simultaneously be gated (FAIL wins) — the locked example wording is kept for the common all-caveated case without ever overstating.
10. **Remediation hint trigger** — any suite row with status UNKNOWN *or* WARN (not just stale): absent/skipped/corrupt/warn are all remedied by the same manual command, and the locked hint text carries no age, so widening the trigger loses nothing.
11. **Tooltip label for `monitor_signal`** — kept as the raw stage name. P2 locks only the three Chinese labels; inventing a fourth would reopen a locked decision. The fund-specific card line carries the human framing (`为何有保留`) instead.

No open questions remain unresolved; none required input beyond MASTER-SPEC + source spec + code.
