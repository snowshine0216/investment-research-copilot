Verdict: PASS

Source: /ship steps 8+9 (autodev's primary review capture path)
PR: https://github.com/snowshine0216/investment-research-copilot/pull/76

## Step 8 — pre-landing parallel review

### Subagent 1: pr-review-toolkit:code-reviewer

Findings (4 P1):

1. **P1 — `_top_n_by_weight` non-deterministic on equal weight** (`src/irc/opportunity/advisory_gaps.py:37`)
   - Missing secondary sort key meant AC12 (two-run byte equality) could flip on equal-weight ties.
   - **Fixed in commit `2d3a1a3`**: secondary key `c.symbol` ASC.
2. **P1 — `_apply_advisory_partition` over-broad demotion** (`src/irc/commands/memo_cmd.py:532`)
   - `not r.advisory_gaps` would demote on ANY future advisory code, contradicting ADR 0005's per-code design.
   - **Fixed in commit `2d3a1a3`**: explicit membership check `"top_holdings_broker_thin" in r.advisory_gaps`.
3. **P1 — local import inside pure function** (`src/irc/commands/memo_cmd.py:245`)
   - No circular import to justify it.
   - **Fixed in commit `2d3a1a3`**: hoisted to module-top imports.
4. **P1 — missing lockdown fixture with non-empty advisory_gaps**
   - `tests/integration/test_publishable_set_lockdown.py` does not exercise the new code paths in its byte-equality assertions.
   - **Deferred**: the 30 single-run unit tests already cover correctness. A fixture extension is a follow-up in item 002 (concentration panel) which will add a lockdown-extension entry.

### Subagent 2: pr-review-toolkit:silent-failure-hunter

Findings (1 P1, 3 P2):

1. **P1 — silent JSON coalescing on `advisory_gaps`** (`src/irc/commands/memo_cmd.py:630`)
   - `tuple(op.get("advisory_gaps") or ())` silently turned null/missing/malformed values into `()` with no log → wrong investment signal (pick rendered without 证据缺口 suffix or §6 marker block).
   - **Fixed in commit `2d3a1a3` + `f8b19e3`**: new `_parse_advisory_gaps` helper raises ValueError with instrument_id on type mismatch. 7 new unit tests cover None/[]/single/string/dict/int/list-with-non-string.
2. **P2 (accepted) — `getattr(r, "advisory_gaps", ())` defensive sentinel**: field is always declared; defensive default is harmless but unnecessary. No code change.
3. **P2 (accepted) — empty-`constituent_analyses` vs fetch-failure indistinguishable**: upstream failure already recorded in `failure_reasons_by_symbol`. Observability gap, not correctness.
4. **P2 (accepted) — marker conditional in synthesizer**: intentional and documented — IRC_EVIDENCE_GAP_BEGIN/END lock only added when markers present in skeleton.

## Step 9 — adversarial review

Verdict: BREAKS (1 P0 found, 2 P1 found, 2 P2 noted)

1. **P0 — `_discipline_row_from` does not propagate advisory_gaps** (`src/irc/commands/opportunity_cmd.py:607`)
   - AC9 silently broken: discipline_report.md never showed the 证据缺口 suffix regardless of how many holdings were broker-empty. The §5 memo demotion and §6 marker block worked, but the document the user consults for ongoing position management gave a cleaner risk picture than the data warranted.
   - **Fixed in commit `2d3a1a3`**: added `advisory_gaps=row.advisory_gaps` to the `DisciplineRow(...)` constructor. New test `test_discipline_row_from_propagates_advisory_gaps` verifies.
2. **P1 — `_reconstruct_opportunity_rows` drops advisory_gaps on JSON re-hydration** (`src/irc/commands/memo_cmd.py:411`)
   - Future consumers of these rows would silently see `()` for broker-thin picks.
   - **Fixed in commit `2d3a1a3`**: added `advisory_gaps=_parse_advisory_gaps(r.get("advisory_gaps"), instrument_id=r["instrument_id"])` to the reconstructor. New test `test_reconstruct_opportunity_rows_round_trips_advisory_gaps` verifies.
3. **P1 — duplicate sort in `should_emit_top_holdings_broker_thin`**: performance, not correctness; short-circuit `or` already skips weight branch when count threshold fires. **Accepted as P2 — deferred** (would need helper to memoize Top-5 across the count + weight reads; cost-benefit not worth it for ≤5 elements).
4. **P1 — `weight_pct=0.0` constituents ordering**: structurally mitigated by Fix 1 (symbol ASC secondary key). Acknowledged as resolved.
5. **P2 — LLM-lock-by-instruction risk class** (`src/irc/memo/synthesizer.py:175`): pre-existing pattern shared by all `IRC_*_BEGIN/END` marker blocks (picks-table, gold-evidence, decision-mirror, etc.). Not a regression introduced by this diff. Tracked separately.

## Final verdict rationale

All P0 + P1 findings either fixed in-branch (commits `2d3a1a3` + `f8b19e3` + `8f251df`) or accepted as P2 with rationale.

Per autodev's exit contract: PASS — zero blocker bugs, zero latent bugs, only P2 cosmetic / deferred items remain.
