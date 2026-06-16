# 001 ship-blocked — /ship steps 8+9 review findings (pre-push)

`/ship` pre-landing (code-reviewer + silent-failure-hunter) and adversarial review surfaced a
blocker plus real bugs in new M0 code. Fixing before the PR is opened (ship.md "review can
demand fixes before push"). After fixes + green suite, /ship resumes and the clean review is
captured into items/001-review.md.

## Must-fix (this fix round)

1. **[BLOCKER] `tests/commands/test_monitor_constituent.py:326,390` unpack `_process_fund` as a 2-tuple.**
   `_process_fund` now returns `(FundView, list, FundTraceBundle)`. These two existing tests fail
   with `ValueError: too many values to unpack`. The impl updated the production call site but
   missed this test file. Fix: `view, costs, _bundle = mc._process_fund(...)` (or `*_`). Run
   `uv run pytest tests/commands/test_monitor_constituent.py` → expect all green.

2. **[bug · new code] `evals/_shared/latest_report.py` `_parse_report` is unguarded.**
   A truncated/corrupt `report.json` (e.g. interrupted atomic write) makes `latest_stage_report`
   raise `json.JSONDecodeError` instead of honoring its "return None / skip" contract. Fix: in
   `latest_stage_report`, wrap the per-date parse in try/except, `_log.warning("corrupt report at
   %s, skipping", path, exc_info=True)`, and `continue` to the next-newest date. Add a regression
   test: a corrupt newest report → falls through to the next valid date (or None).

3. **[latent bug · new code] `src/irc/monitor/eval/staleness.py:18` `resolve_health` crashes on a
   naive `ran_at`.** `datetime.fromisoformat(report.ran_at)` is naive if the report omits a tz
   offset; subtracting from the tz-aware `now` raises `TypeError`. Not reached in M0 (resolve_health
   is built-not-wired per OQ3) but fires the moment M1 wires it. Fix: normalize — if parsed `ran_at`
   is naive, attach `now.tzinfo` (Asia/Shanghai) before subtracting (or compare both naive). Add a
   regression test with a naive `ran_at`.

4. **[contract violation · new code] `src/irc/monitor/eval/structural.py:70` `nav_quality` calls
   `date.today()`.** The module is declared pure (no I/O, ADR 0017 §3.3); an ambient clock read
   breaks determinism and makes `test_structural` date-boundary-flaky. Fix: add a
   `today: date | None = None` parameter to `nav_quality` AND `monitor_signal_health`, thread it
   through, and pass `today=date.today()` ONLY at the edge call site in
   `src/irc/commands/monitor_cmd.py`. Update `tests/monitor/eval/test_structural.py` to inject a
   fixed `today`. (Effects-at-edges per CLAUDE.md.)

5. **[bug · new code] `src/irc/monitor/render_html.py:141-142` Validation panel hardcodes
   `StageHealth("monitor_signal", "PASS", ())`.** It shows `PASS` even when funds are `EVAL_GATED`
   — a visible contradiction against the badge counts in the same row. Fix: derive the panel overall
   from the gates — `FAIL` if any `gate.suppressed`, else `WARN` if any badge is `caveated`, else
   `PASS`. Update `tests/monitor/test_render_html_eval.py` (and regenerate the golden if the panel
   markup changes). Add a test: a run with a gated fund → panel overall is not `PASS`.

6. **[hardening · new code] `src/irc/monitor/eval/forward_log.py:57` `latest_per_key` does
   `row["written_at"]`.** A corrupt JSONL line lacking `written_at` raises `KeyError`. Fix:
   `row.get("written_at", "")`. The M3 scorer reuses this reader, so harden now. Add a test: a row
   missing `written_at` doesn't crash dedup.

## Out of scope (noted, NOT fixed in this PR)

- **Pre-existing:** `src/irc/commands/eval_cmd.py` `_run_active_suite` swallows stage exceptions with
  `print(...)` instead of `_log.exception(...)` (lines ~67-75). Confirmed NOT in the M0 diff — it
  predates this work. Spawned as a follow-up task; not expanding M0 scope.
- **Pre-existing:** `tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports`
  fails on the base `monitor-eval` too (one of the repo's known failures). Not introduced by M0.
- **Cosmetic, not reachable from the typed `EvidenceItem` path:** `structural._pool_ids` puts `None`
  into the id set when an evidence item lacks `citation_id`. Only reachable from a hand-corrupted
  trace. Noted; no change.

## Constraints for the fix
- Address ONLY the must-fix list. Do not refactor adjacent code.
- TDD where adding behavior (corrupt-file guard, naive-tz, panel-overall, latest_per_key.get):
  write/extend the test first, see it fail, then fix.
- Keep changes minimal and within the new M0 modules + the two test files named.
- `uv run ruff check src tests` must stay clean.
