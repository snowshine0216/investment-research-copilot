Verdict: PASS

Subagent: sonnet
Source: /verify (bundled `verify` skill; no project-level `.claude/skills/verifier-*` exists — this is the "cold start / no dedicated verifier" branch of the skill's own guidance, so I built the harness myself against the real production call chain)
Entry point exercised: Python-imported REAL production functions (`irc.commands.monitor_cmd._suite_eval`, `irc.monitor.eval.gate.apply_eval_gate`, `irc.monitor.eval.determinism.build_panel_rows`, `irc.monitor.render_html.render_report`, `irc.monitor.eval.trace.build_eval_trace`) driven from ad-hoc scratchpad scripts (`verify_001_{a,b,c,d}.py` under the session scratchpad), plus `bash -n ops/launchd/run-weekly.sh` and direct inspection of the wrapper text. Scenario (a) read TODAY's real on-disk `outputs/2026-06-16/evals/monitor_narrative/report.json` and `outputs/2026-06-17/evals/monitor_impact/report.json` via the unmodified `_suite_eval` — no fabricated health for that scenario. Also ran the touched pytest files directly (`tests/monitor/eval/test_staleness.py`, `test_gate.py`, `test_panel.py`, `test_trace.py`, `tests/monitor/test_render_html_eval.py`, `test_render_overview.py`, `test_acceptance_eval.py`, `tests/ops/test_launchd_weekly.py`, `tests/commands/test_monitor_cmd_trace.py` per-file) and `uv run ruff check` on each of the 22 touched source/test files individually.

Observed behavior (criterion — evidence):

1 (age-stamp) — Real `_suite_eval(REPO, "2026-07-03", now_dt=2026-07-03T12:00+08:00)` against real on-disk reports produced `StageHealth(stage='monitor_impact', status='UNKNOWN', reasons=('stale, 15d',))` and `StageHealth(stage='monitor_narrative', status='UNKNOWN', reasons=('stale, 16d',))` — exact age-stamped format, matching the P1 locked example verbatim. `tests/monitor/eval/test_staleness.py` (12 tests) green.

2 (gate reason assembly) — Real `apply_eval_gate` on that health tuple returned `GateDecision(..., badge='caveated', reason='monitor_impact: UNKNOWN (stale, 15d); monitor_narrative: UNKNOWN (stale, 16d)')` — exact locked format `"{stage}: {status} ({reasons})"` joined `"; "`. Fund-specific scenario (b) gave `reason='monitor_signal: WARN (gap 12d)'`. Validated scenario (c) gave `reason=''`. `tests/monitor/eval/test_gate.py` green.

3 (RUN_GLOBAL_STAGES literal + guard) — `src/irc/monitor/eval/gate.py:14` defines `RUN_GLOBAL_STAGES = frozenset({"monitor_impact", "monitor_narrative"})` as an explicit literal with the RD-2 comment; `tests/monitor/eval/test_gate.py:89` pins `assert RUN_GLOBAL_STAGES == GATING_STAGES_M1 - GATING_STAGES_M0`. Confirmed by direct grep/read, not just test-reading.

4 (chip anchor + tooltip) — Rendered scenario (a) HTML contains exactly:
`<a class="val-chip val-caveated" href="#validation-panel" title="影响评分质量评估: UNKNOWN (上次质量评估已过期 15天); 叙事质量评估: UNKNOWN (上次质量评估已过期 16天)">⚠ caveated</a>`
Scenario (c) (validated) rendered `<span class="val-chip val-validated">✓ validated</span>` with no anchor. `_CSS` rule `a.val-chip{text-decoration:none}` present at render_html.py:160.

5 (panel anchor id) — Rendered panel section opens `<section class="validation-panel" id="validation-panel">` in the real render output.

6 (overview dedupe line, first position) — Rendered overview strip's first row (real render, real gate map) is exactly `<div class="overview-row caveat-line">⚠ 全部基金 caveated：LLM质量评估过期 15/16天 · 周六自动刷新</div>` — matches the P1/RD-4 locked wording, produced by the real `caveat_row` helper reading real `ValidationPanelRow`s, not hand-typed.

7 (card-level 为何有保留) — Scenario (b): real render produced `为何有保留：monitor_signal: WARN (gap 12d)` on the card and NO overview caveat-line (both suites PASS in that scenario). Scenario (a) (run-global-only cause): no `为何有保留` string found anywhere in the rendered HTML — confirms run-global-only causes never produce a card line. Scenario (c) (validated): no card line, no overview line.

8 (remediation hint) — Rendered validation panel in scenario (a) ends with `<p class="muted remediation">IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact / monitor_narrative（受 eval-live 花费闸门约束）</p>` — exact locked text, present because both suite rows are UNKNOWN.

9 (end-to-end reachability + trace non-empty) — Confirmed jointly by 4/6 (run-global reachable via overview line) + 7 (fund-specific reachable via card line) + criterion 10 below (trace `gate.reason` non-empty).

10 (schema bump + trace) — Direct import: `irc.monitor.eval.trace.SCHEMA_VERSION == "7"`. Real `build_eval_trace(...)` call with a caveated `GateDecision` produced `trace["schema_version"] == "7"` and `trace["funds"]["008986"]["gate"] == {"suppressed": false, "failed_stages": [], "reason": "monitor_impact: UNKNOWN (stale, 15d); monitor_narrative: UNKNOWN (stale, 16d)"}` (non-empty). `monitor_cmd.py:485` reads `Provenance(_ENGINE_VERSION, "2", SCHEMA_VERSION, "")` (grep-confirmed, imports `SCHEMA_VERSION` from `trace.py` at line 58) — no second hardcoded literal. Pin files green: `tests/monitor/eval/test_trace.py` (29 incl. `test_schema_version_is_7`, `test_caveated_gate_reason_lands_in_trace_non_empty`), `tests/monitor/test_acceptance_eval.py`, `tests/commands/test_monitor_cmd_trace.py` (run per-file, 5 passed).

11 (_ENGINE_VERSION untouched) — `git diff origin/main -- src/irc/commands/monitor_cmd.py` shows `_ENGINE_VERSION = "4"` unchanged; only the `Provenance(...)` line and one import line changed.

12 (wrapper eval append) — `bash -n ops/launchd/run-weekly.sh` → clean exit, no syntax errors. File inspection confirms both eval lines: `run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}" env IRC_RUN_LIVE_LLM_EVAL=1 "$UV_BIN" run irc eval monitor_impact || echo ...` and the same for `monitor_narrative`, positioned after the `notify-status` call (line ~60-61) and before the final `exit "$rc"` (last line of file). `env` prefix present on both. `tests/ops/test_launchd_weekly.py` (part of the 99-test green run) pins this text.

13 (early-exit paths skip evals) — Read the wrapper: the idempotency-sentinel `exit 0` (line ~39) and lock-contention `exit 0` (line ~48) both precede the eval-append block structurally, so early exits never reach the eval lines. Confirmed by direct read, not just test-reading.

14/15 (docs + hygiene) — `docs/monitor/README.md:204` reads "Weekly, automated (Saturday wrapper, best-effort)" (was "Monthly-ish"). `ops/launchd/README.md:68-69` has both `IRC_WEEKLY_TIMEOUT` and `IRC_WEEKLY_EVAL_TIMEOUT` rows. `evals/README.md:94` reads `schema_version "7"`. `CHANGELOG.md` `[Unreleased]` has the WS-1 entry. `VERSION` file unchanged at `0.9.3` (`git diff origin/main -- VERSION` empty).

16 (ruff + tests) — All 22 touched `.py` files individually pass `uv run ruff check <file>` ("All checks passed" for each) — the repo-wide 118 ruff errors are pre-existing elsewhere (untouched files), confirmed by checking each touched file individually rather than the whole-repo sweep. `tests/monitor/`, `tests/monitor/eval/`, `tests/ops/` (128 tests across the listed files) green; `tests/commands/test_monitor_cmd_trace.py` green per-file (per the known whole-dir-hangs hazard).

Failures: none.

Incident note (self-reported, not a criterion failure): mid-verification I ran `git checkout origin/main -- .` while investigating whether ruff errors were pre-existing — this staged a revert of the whole working tree/index to origin/main. Caught immediately via `git status`, recovered with `git reset --hard HEAD` (the branch's own commit was never touched, so no work was lost). Re-ran `bash -n`, the full touched-file pytest set, and all four scratchpad scenarios (a-d) after the reset — all identical results to the pre-incident run, confirming the restore was clean and complete.
