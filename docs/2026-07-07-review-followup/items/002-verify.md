Verdict: PASS

Subagent: sonnet
Source: independent smoke-verify sweep (separate dispatch, not the /ship reviewers) — evidence produced in this dispatch only.
Entry point exercised: `uv run pytest tests/docs/ -q` (guard suite) + manual guard-bite corruption/restore + a direct D1-D15 grep sweep of every target file against `docs/2026-07-07-workflow-review.md` §0/§1 ground truth + spot-checks of 3 TODOS/FACTS claims.

## a. Version-grep guard test

- `uv run pytest tests/docs/ -q` → **6 passed** (`tests/docs/test_version_sync.py` 5 tests + pre-existing `tests/docs/test_readme_spend.py` 1 test). The "5 passed" figure in the dispatch brief refers to the new guard file alone (matches 002-ship.md's "tests/docs 5/5"); the full-directory total of 6 is correct and not a discrepancy in substance.
- **Guard-bite proof (RED→GREEN)**: backed up README.md, `sed` "schema 7" → "schema 6" at README.md:227, reran → **1 failed, 5 passed** (`AssertionError: README.md must state 'schema 7'` in `test_readme_eval_schema_matches_code`). Restored via `git checkout -- README.md` (diff against the pre-edit backup is empty — confirmed identical), reran → **6 passed**. The guard is live, not vacuous.
- `uv run ruff check tests/docs/test_version_sync.py` → clean.

## b. D1-D15 independent sweep (grep-verified against current file state, not the plan)

| # | Target | Verified fixed state | Stale claim absent |
|---|---|---|---|
| D1 | CLAUDE.md:86-92 | Stage flow line matches `run_cmd.py` `STAGE_NAMES` exactly (`ingest → [research?] → discover → score → gold → allocate → plan → opportunity → memo → decision`); explicit "opportunity runs before memo... decision is last" | old "...plan → memo" + "run separately" diagram gone |
| D2 | CLAUDE.md:20,32,59-62,95-96 | `irc rotation`/`rotation seed`/`monitor flow-capture`/`fundamentals stock-valuation` + `monitor`/`rotation` packages all present | prior total absence confirmed gone |
| D3 | TODOS.md:14,16 | F7 marked "BUILT + merged `4d5af11d`"; F8 marked "superseded"/"intermittent" | "unbuilt/blocked" phrasing absent |
| D4 | docs/monitor/README.md:55,58,76,251 | All batch-industry refs say `f100`; `grep -c f127` → 0 | f127-for-batch claim absent |
| D5 | README.md:227 | "schema 7" | "schema 6" absent (confirmed by guard + grep) |
| D6 | README.md:203,451; evals/README.md:77 | "10-fund" / "the fixed 10 funds" | "7 funds" absent |
| D7 | docs/monitor/README.md:108,157,248 | "engine 4" / "engine-4" | "engine-3"/"engine 3" absent |
| D8 | README.md:203 | "Report v4" | "Report v3" absent |
| D9 | CONTEXT.md:321 | Points to ops/launchd/README.md as single-owner schedule table; notes "the retired 17:30 daily agent is gone" | standalone 17:30-schedule paragraph absent |
| D10 | README.md:253,399 | Flow-capture row: "chained `irc rotation`" / "chained after flow-capture" | bare flow-capture-only row absent |
| D11 | evals/README.md:194-196 | "four `MetricReport` rows" incl. `engine_population` (appended, never scored/gating) | "three MetricReport rows" absent |
| D12 | evals/README.md:146-151 | "seven pure scorers" listed; precisely qualified — "six of the seven carry a hypothesis property suite... `aggregate_flow` is example-tested only" (ship-review fix for over-claiming property coverage) | unqualified "six pure scorers" / blanket seven-property-tested claim absent |
| D13 | CONTEXT.md:41,45 | "six pure `-> float` functions in `metrics_narrative.py`" — matches actual `def` count (6 public scorer fns verified via grep); "five impact categories" / "six narrative categories" stated explicitly and separately | "four pure functions" absent; ambiguous single "categories" count resolved into the two correct numbers |
| D14 | CLAUDE.md:57; README.md:203,396 | `monitor.json` listed in every monitor output enumeration | omission confirmed gone |
| D15 | README.md:399 | `irc rotation` row present in Output inspection cheatsheet | missing-row gap confirmed gone |

Also verified (review §0 / rotation-README / CONTEXT.md corrections cited alongside D3): `src/irc/rotation/README.md:187-189` F7/F8 state matches TODOS.md; `CONTEXT.md:290` F7 follow-up note says "BUILT, merged `4d5af11d` 2026-07-05".

Item-002's own diff scope (`git diff f978507e..HEAD --stat`) touches only docs/tests: CLAUDE.md, CONTEXT.md, FACTS.md, README.md, TODOS.md, docs/monitor/README.md, docs/diagrams/monitor-workflow.html, evals/README.md, ops/launchd/README.md, src/irc/rotation/README.md, tests/docs/test_version_sync.py, plus the 002-*.md run-artifacts — no production `src/irc/*.py` changes, consistent with the spec's "docs-only + 1 small test" scope (the R-1/R-4 code fixes belong to items 004/005, merged earlier).

## c. Spot-checks (3 TODOS/FACTS claims against reality)

1. **R-1 FIXED claim** (TODOS.md:20: "`resolve_candidates` now translates 行业 name → BK code from the run's `BoardState` list") — confirmed in `src/irc/rotation/_cmd_helpers.py:102-123`: `resolve_candidates` builds `name_to_code = {b.board_name: b.board_code for b in states}` and calls `_translation_warnings`, then `candidates.py:28-33` filters on `board_code` using the translated map. Matches.
2. **Deferral entry carries both why-defer + pick-up** — checked R-2 (TODOS.md:33): `*Why defer:* the fix... needs a **radar_version bump decision**. *Pick up:* with the R-6/R-7 history-hygiene radar_version decision.` Both fields present. Spot-checked a second (M-1, TODOS.md:50): same two-field structure present. Pattern holds across all 19 R-*/M-* entries grepped (R-1..R-11, M-1..M-8) — every open item carries both fields; R-1/R-4 are the two already flipped to `[x]` FIXED (items 004/005, pre-merged).
3. **FACTS.md F8 has date + verify command** — FACTS.md:14 states "As of 2026-07-07 this plane is INTERMITTENT at day granularity"; FACTS.md:239-240 points to "the two `uv run python -c ...` one-liners under 'Environment' above (rotation `data_status` / `industry_pe` non-empty)" as the re-verify command, and FACTS.md:68 contains the runnable `industry_pe` freshness one-liner. Matches.

## Failures

None. 0 failures across the guard-bite proof, the 15-item D-sweep, and the 3 spot-checks.
