Verdict: FAIL

Subagent: sonnet
Items reviewed: 5 (004 rotation join fix, 005 seed freshness, 001 data-health notify, 002 docs-sync, 003 conventions)

## Doc changes verified (per functional change)

- **004 — name→code translation at rotation candidates join** (`rotation.resolve_candidates`,
  squashed `76359c69`): covered.
  - `CONTEXT.md` "Stock-industry map (cross-day store)" term gets the
    "行业 names, never codes — for both consumers" clause, naming the exact prior
    docstring error and the fix.
  - `CHANGELOG.md` "Fixed" entry describes the dead join and the translation-map fix.
  - `industry_map_store.py` docstring corrected per 004-grill AC3 (confirmed in diff stat:
    `src/irc/monitor/industry_map_store.py | 11 +-`).

- **005 — seed skip-set freshness** (`fresh_slice(existing, today)` skip-set, squashed
  `6dc5d83b`): covered.
  - `CONTEXT.md` same term gets the seed-writer clause ("rotation SEED's re-fetch skip-set
    honors this SAME ≤30-calendar-day window... Seed (WRITER) and both joins (READERS)
    therefore move in lockstep").
  - `CHANGELOG.md` "Fixed" entry describes the stale-skip bug and the `fresh_slice`-derived
    fix, plus a "Ship-hardening (review-followup-005)" paragraph that explicitly names all
    three post-ship additions: the unresolved-chunk-symbol whole-run warning, the
    `chunk_size=0` → 1-symbol-chunk guard, and the `merge_seen`-matching stripped-truthy
    done/unresolved accounting (commits `77426054` + `c9bfdde5`, confirmed present in
    current `src/irc/rotation/seed.py`).

- **001 — data-health digest, `degraded` severity, `flow-capture` run-kind, wrapper tail**
  (squashed `ecf264f6`): partially covered.
  - `CONTEXT.md` new "Data-health digest" term (severity precedence, never-persisted,
    interim honesty-vs-report property).
  - `docs/adr/0016-local-scheduling-and-notification.md` §7 amendment (severity precedence,
    `_ALWAYS_NOTIFY`, `flow-capture` run-kind semantics, wrapper `$rc` passthrough).
  - `docs/monitor/README.md` new "What the 15:45 flow-capture run does" section + schedule
    table pointing to `ops/launchd/README.md` as single owner.
  - `ops/launchd/README.md` flow-capture row: notify semantics (silent-on-ok, pages on
    rotation abstain/degraded_*, one-time recovery notice, timeout→`failed`) +
    `run-flow-capture.sh` timeout-table row rewritten to page `failed` instead of
    "does NOT page".
  - `CHANGELOG.md` "Added" entry for the digest/severity/run-kind.
  - **Gap (see Missing coverage):** the flow-capture **coverage-delta** health check
    (`flow_capture_health` / `_capture_coverage_items` in `src/irc/notify/health.py` +
    `src/irc/commands/notify_health.py`, from commit `d9a06161`, landed inside the same
    squash `ecf264f6`) is absent from all five doc surfaces above.

- **002 — docs-sync + TODOS reconciliation**: is itself the doc-sync item; its D1-D15
  corrections are visible throughout the diff (schema 6→7, engine-3→4, f127→f100,
  7-fund→10-fund, six→seven scorers, three→four `MetricReport` rows, retired-17:30-agent
  cleanup, single-owner doc-map added to README.md). Verified present in `CONTEXT.md`,
  `README.md`, `docs/monitor/README.md`, `evals/README.md`.

- **003 — Opus-enablement pass**: content-only change to `CLAUDE.md` (43 lines) +
  `FACTS.md` header rule; no external doc-coverage obligation (it IS the doc).

## Missing coverage

1. **[BLOCKER] Flow-capture coverage-delta health check undocumented.** Commit `d9a06161`
   (squashed into `ecf264f6`, item 001) added `flow_capture_health` (pure builder,
   `src/irc/notify/health.py:147-159`) and the edge reader `_capture_coverage_items`
   (`src/irc/commands/notify_health.py:118-125`): when today's capture appends fewer than
   80% of the flow store's union symbols, notify renders a `warn` item
   `flow-capture: {N}/{M}` and an otherwise-ok rotation day now pages `degraded`. This is a
   new, operator-visible paging trigger — distinct from "capture failure" (rc≠0) or
   "rotation abstain" — yet it is not mentioned in `docs/adr/0016-local-scheduling-and-notification.md`
   §7, `ops/launchd/README.md` (flow-capture row or the wrapper timeout table),
   `docs/monitor/README.md`, `CONTEXT.md` ("Data-health digest" term), or `CHANGELOG.md`.
   An operator who receives an unexplained `degraded` page on a day when the capture
   wrapper exited 0 and rotation was `ok` has no doc surface that explains why.

2. **[minor] Seed ship-hardening not surfaced in the rotation ops manual.** The
   unresolved-chunk-symbol warning log, `chunk_size=0` guard, and stripped-truthy
   done/unresolved accounting (`77426054` + `c9bfdde5`, item 005) are described in
   `CHANGELOG.md` but not in `src/irc/rotation/README.md`'s Troubleshooting section (the
   doc an operator actually consults when the seed logs a new
   `seed_stock_board_map: N symbol(s) unresolved after batch_fetch` warning). Lower
   severity than #1 because CHANGELOG.md does record the behavior; flagged since the
   task's ops-facing-doc bar (README.md doc map names `src/irc/rotation/README.md` as the
   single owner of rotation ops) is not met.

Manual fix path: add a short paragraph to `docs/adr/0016-local-scheduling-and-notification.md`
§7 (or a new §8) and the `ops/launchd/README.md` flow-capture row describing the
coverage-delta warn (`flow-capture: N/M`, <80% union-symbol threshold, pages `degraded`
even when rc=0), and cross-reference it from `docs/monitor/README.md`'s new
"What the 15:45 flow-capture run does" section; optionally add one line to
`src/irc/rotation/README.md`'s Troubleshooting section pointing at the seed's
unresolved-symbol warning log and the `chunk_size=0` guard.
