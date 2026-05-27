Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (initial review found 1 P0 + 2 P1; adversarial CLEAN) → triage-fix round 1 (3 commits) → re-review found 1 P0 pre-existing nit (line 37 print missing `file=sys.stderr`), fixed in follow-up commit.

## Reviewers

- Step 8 code-reviewer: `pr-review-toolkit:code-reviewer` (sonnet) — verdict PASS-WITH-NITS (1 P1 — `or 0.0` corruption pattern)
- Step 8 silent-failure-hunter: `pr-review-toolkit:silent-failure-hunter` (sonnet) — verdict PASS-WITH-NITS (1 P0 — bare except in live_inputs.py; 1 P1 — silent NAV<5 skip)
- Step 9 adversarial: general-purpose (sonnet) — verdict CLEAN (no new findings)
- Post-fix re-review: `pr-review-toolkit:code-reviewer` (sonnet) — verdict PASS-WITH-NITS (1 P0 — pre-existing stdout-vs-stderr defect on line 37, fixed in follow-up)

## P0 findings (all fixed before PR opened)

- **P0-1** (silent-failure-hunter) — Bare `except Exception: pass` at `live_inputs.py:68` swallowed all query failures with zero log signal. Fixed in `96675ab`: `except Exception as exc:` + `print("WARNING: ...", file=sys.stderr)`. Test `test_read_live_decision_inputs_logs_on_query_failure` asserts via `capsys`.
- **P0-2** (re-review) — Pre-existing connect-failure `print` at `live_inputs.py:37` emitted to stdout instead of stderr. Fixed in `7ea4b64`: added `file=sys.stderr`. The other two new prints from `96675ab` already had it; this one was older code from the original `decision_cmd.py` extraction. Tests still pass (`tests/decision/test_live_inputs.py`: 4 passed).

## P1 findings (all fixed in this PR)

- **P1-1** (code-reviewer) — `float(trig.get("threshold") or 0.0)` corrupts integer 0 / explicit 0.0. Fixed in `36700b6`: explicit `0.0 if trig.get("threshold") is None else float(trig.get("threshold"))`. Test `test_format_trigger_status_compact_preserves_zero_threshold` verifies integer 0 thresholds are honored.
- **P1-2** (silent-failure-hunter) — Silent NAV<5 skip. Fixed in `96675ab`: `if os.environ.get("DEBUG"):` block emits `DEBUG: ...` to stderr when the project's debug env is set.

## P2 findings (deferred to TODOs)

- Pipe-injection in trigger `name` and other table cells — pre-existing, not a regression from this PR.
- `field.startswith("macro.")` case-sensitivity in `sizing.py:149` — pre-existing in the extracted helper; YAML is human-authored and `irc config validate` could catch elsewhere.
- Fragile `cells[-3]/[-2]` test isolation pattern — pre-existing test design choice; works for the current 12-column layout.

## Tests after fix

`56 passed in 0.27s` on the targeted scope (`tests/decision/test_live_inputs.py tests/memo/test_picks_table.py tests/memo/test_trigger_status_compact.py tests/memo/test_pick_rows.py`). Ruff clean on all changed files.

## Pre-existing test failures (not caused by item 003)

Same 7-8 pre-existing failures from items 001/002 carry over — unrelated to the memo §5 picks-table.
