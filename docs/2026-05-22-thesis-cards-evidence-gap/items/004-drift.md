Verdict: PASS-WITH-NOTES

Subagent: sonnet
Plan tasks: 13 (8 original + 5 pivot)
Verified present in diff: 13/13
Authorized pivot: Q4 option (a) — original `fund_announcement_em` target replaced by 3 topic-specific endpoints (`fund_announcement_dividend_em`, `fund_announcement_report_em`, `fund_announcement_personnel_em`); user-authorized 2026-05-23; documented in items/004-spec.md §"Pivot — Q4 option (a)" + items/004-verify.md line 1 + 004-plan.md Pivot tasks section.

## Drift findings

- Task 3 / Task 4 / Task 5 commit cadence — incidental
  Evidence: commit `5fb2332` (labeled task 3 "adapter-existence preflight") added the full live test file including `_capture_fixture`, `_assert_announcement_df`, `_call_fund_announcement_em`, and all 3 per-symbol tests + aggregate gate in one shot. Commits `c50ad57` (task 4) and `f2e8cd1` (task 5) are empty commits carrying no file changes (verified via `git show --name-status`). The plan specified one commit per task; the impl batched tasks 3+4+5 into task 3's commit.
  Action: accepted — the implementation content is correct and fully present in the diff; the commit cadence is a process divergence only. The plan was vague on granularity ("append to the live file") vs the impl's single-shot approach. Amend plan to record the actual cadence (see below).

- Task 7 (README) — stale content after pivot (incidental, not a regression)
  Evidence: `tests/fundamentals/README-live-tests.md` (commit `5b278d1`) was written for the original spec; it still references `ak.fund_announcement_em`, "5 tests pass (1 preflight + 3 per-symbol + 1 aggregate gate)", and fixture filenames `fund_announcement_em_{518880,000001,005827}.json` that were never committed. The pivot (tasks P2–P5) rewrote the live test file but did NOT update this README.
  Action: accepted with rationale — the README is documentation of run discipline, not test logic. The stale fixture filenames and test count are cosmetic post-pivot; the core run command (`IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare ...`), dual-gate discipline, and failure-meaning sections remain accurate. A follow-up cleanup (update README to reflect 11 tests and 9 pivot fixture names) is recommended before item 005 ships but does not block this gate. Amend plan to record this note.

- Task 8 commit `b44a7ca` label mismatch — incidental
  Evidence: commit `b44a7ca` is labeled "capture initial fund_announcement_em fixtures from live AkShare (item 004 task 8)" but its diff shows only a one-line removal (`_resolve_column` dropped from the failure-modes companion import). No `fund_announcement_em_*.json` fixture files were committed here; that was expected because the live gate for the original endpoint FAILed (`fund_announcement_em` missing in AkShare 1.18.63). The pivot fixtures (`fund_announcement_{dividend,report,personnel}_em_*.json`) were correctly committed in pivot task P5 (`f2bdf2a`). The commit label is misleading but the diff content is correct.
  Action: accepted — the label describes the intent (fixture capture), not the actual diff (import cleanup). The real fixture capture occurred under the pivot commit. Amend plan to note the actual diff content of this commit.

- P2 separate commit absent — incidental
  Evidence: plan task P2 specified a dedicated commit `test(fundamentals): update COLUMN_EQUIVALENCE for 3 topic-specific endpoints`. No such standalone commit exists. The `COLUMN_EQUIVALENCE` rewrite was combined with the full live test rewrite in `2c24edd` ("rewrite live tests for the 3 topic-specific announcement endpoints (Q4 pivot)"), which implements both P2 and P3 together.
  Action: accepted — the implementation content is correct (per-endpoint `COLUMN_EQUIVALENCE` map confirmed at `tests/fundamentals/test_fund_announcement_em_live.py:62-81`). Combining P2+P3 into one commit is a reasonable batching choice. Amend plan to reflect the actual combined commit.

## Invariant checks

- markers + strict-markers: `pyproject.toml:49-55` — `addopts = ["--strict-markers"]` and `markers = ["live_akshare: ...", "integration: ..."]` both present. Confirmed via `git diff autodev/thesis-cards-evidence-gap...HEAD -- pyproject.toml`.

- fixture directory + 10 files: `tests/fixtures/akshare/` directory confirmed present with `.gitkeep` (commit `666a63a`) + 9 endpoint×symbol JSON files + `q4_aggregate_gate_summary.json` = 10 files beyond `.gitkeep`, plus `.gitkeep` itself = 11 entries total (10 committed fixtures + `.gitkeep`). Plan P5 target was 9 fixture files; actual diff shows 9 + 1 aggregate summary = 10 new fixture files. Verified via `ls -la tests/fixtures/akshare/`.

- live tests call 3 topic-specific endpoints (not `fund_announcement_em`): `tests/fundamentals/test_fund_announcement_em_live.py:47-51` — `TOPIC_ENDPOINTS = ("fund_announcement_dividend_em", "fund_announcement_report_em", "fund_announcement_personnel_em")`. All 9 per-symbol tests and the aggregate gate use `_call_endpoint(endpoint, symbol)` which calls `_ak_call(endpoint, symbol=symbol)`. The original `fund_announcement_em` appears only in the legacy compatibility helpers at lines 421-477 (preserved for failure-modes companion; not called by any live test function).

- failure-mode companion present: `tests/fundamentals/test_fund_announcement_em_failure_modes.py` — 108 lines, 5 tests, confirmed present in diff (commit `87927e8`). No `live_akshare` marker. Imports `_assert_announcement_df` and `_call_fund_announcement_em` from live file (line 22-25).

- README run-discipline doc: `tests/fundamentals/README-live-tests.md` — 67 lines, confirmed present (commit `5b278d1`). Note stale content finding above.

- no `src/` changes: `git diff --name-only autodev/thesis-cards-evidence-gap...HEAD | grep '^src/'` returned no output. Confirmed zero `src/irc/` file changes.

- Q4 verify verdict PASS: `docs/2026-05-22-thesis-cards-evidence-gap/items/004-verify.md:1` — first line is exactly `Verdict: PASS`.

- COLUMN_EQUIVALENCE per-endpoint: `tests/fundamentals/test_fund_announcement_em_live.py:62-81` — `COLUMN_EQUIVALENCE` is a `dict[str, dict[str, tuple[str, ...]]]` keyed by all 3 endpoint names. Each endpoint sub-dict carries `"title"`, `"date"`, `"id"`, `"fund"` logical keys with endpoint-specific candidate tuples. All 3 endpoints have identical schemas in AkShare 1.18.63 but the map is correctly structured per-endpoint for future drift resilience.

- dual gate (env-var + marker): `tests/fundamentals/test_fund_announcement_em_live.py:37-43` — `_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"` at line 37; `pytestmark = [pytest.mark.live_akshare, pytest.mark.skipif(not _RUN, reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests")]` at lines 38-43. Both gates confirmed.

## Plan amendments (committed with this drift file)

1. Tasks 3–5 cadence: noted that commit `5fb2332` shipped all 3 tasks' content; commits `c50ad57` and `f2e8cd1` are empty bookmarks. Actual TDD cycle ran against the full scaffold.
2. Task 8 commit label: noted that `b44a7ca` diff is a one-line import cleanup (not fixture capture); original fixture capture was skipped because the live gate FAILed, correctly documented by the Q4 FAIL verdict in `cdcf531`.
3. P2+P3 combined: noted that the separate P2 commit was merged into the combined P3 rewrite commit `2c24edd`.
4. Task 7 README: noted that post-pivot stale content (test count "5", fixture names, endpoint name) in `README-live-tests.md` is a cosmetic follow-up for item 005 pre-ship.
