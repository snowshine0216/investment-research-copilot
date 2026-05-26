Verdict: PASS-WITH-NITS

Source: /code-review on PR #73
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/73#issuecomment-4543717177
Findings: 2
  - src/irc/commands/memo_cmd.py:33 — nit — `_format_trigger_status_compact` (private symbol) imported cross-module; violates the project convention that cross-module exports drop the `_` prefix. Works today but creates undiscoverable coupling.
  - src/irc/decision/report.py:519 — nit — `or 0.0` zero-threshold corruption pattern unchanged while picks_table.py was fixed (P1-1); creates visible asymmetry between the two trigger-evaluation code paths for `threshold: 0` inputs. Pre-existing, explicitly deferred as P2.

## Review method

- Angles: line-by-line diff scan (Angle A) + removed-behavior audit (Angle B) + cross-file tracer (Angle C)
- Verification: 1-vote per candidate; REFUTED when provably pre-existing or covered; PLAUSIBLE/CONFIRMED when reachable
- Tests run: `uv run pytest tests/memo/ tests/decision/ -q` → 434 passed, 0 failed; `ruff check` → all checks passed

## Non-issues confirmed

- `live_inputs.py` graceful degrade: both connect-fail and query-fail paths log WARNING to stderr. Tested.
- `MACRO_FIELD_TO_KEY` case handling: `field.lower()` inside the `startswith("macro.")` branch is correct. Pre-existing in the extracted helper.
- Venue-suffix mismatch in nav_history queries: pre-existing from original `_read_live_decision_inputs`; faithfully preserved.
- `PickRow` backward compat: all 30+ call sites use keyword arguments. Clean.
- SAME-3 invariant: zero `[ref:...]` markers in new cells. Tested by `test_picks_table_new_columns_carry_no_citation_markers`.
- `decision_report.md` byte-identity: 40 tests in `test_three_section_markdown.py` pass.
- Pipe-injection in table cells: pre-existing, explicitly deferred as P2.
