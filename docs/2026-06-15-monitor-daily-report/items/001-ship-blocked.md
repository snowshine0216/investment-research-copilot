# Ship blocked — pre-landing review (steps 8+9) surfaced P0

Verdict: FAIL (pre-PR; routed to triage-fix, no PR opened yet)
Source: /ship steps 8+9 — pr-review-toolkit:code-reviewer + silent-failure-hunter + adversarial (general-purpose, sonnet)
Reviewers' consensus verdict: **BREAKS** (P0)

## P0 — blocker (all 3 reviewers, independently)

**`irc monitor` crashes on every real run — `TypeError: 'NoneType' object is not callable`.**
`src/irc/commands/monitor_cmd.py` `_process_fund` (lines ~192-194, ~209) passes `route=None, call=None`
to `gather_impacts` / `gather_narrative`, which immediately execute `resp = call(...)` as the first
statement of their retry loop (`impacts.py:54`, `narrative.py:75`). `call=None` → `None(...)` → uncaught
`TypeError` (only `JSONDecodeError`/`ImpactValidationError`/`_NarrErr` are caught; `run_monitor` has no
try/except). The headline command + the scheduled `com.irc.monitor` job fail 100% with no degraded report.

Root cause vs plan: the plan's Task 32 specified `call=llm_call` (the real `irc.llm.gateway.call`) but
the impl passed `call=None`; AND the plan's own `route=None` is also wrong (the gateway `call(task,
messages, config)` needs the **`LLMConfig`** as its 3rd arg). BOTH the plan and impl are corrected in the
amended Task 32 (commit pending). `build_evidence_pool` was also left as a `return ()` stub — the plan's
**Step 3a (real research wiring) was skipped entirely**.

Drift-check miss: drift verified structural presence (function exists, gather called) but not the
value-level `call=None` nor the skipped Step 3a. The integration test (`tests/commands/test_monitor_cmd.py`)
monkeypatches `gather_impacts`/`gather_narrative`, so the production wiring is never exercised → green
tests, broken command.

## P1 — latent (silent-failure-hunter)

**`impacts.status` (schema-retry-exhaustion typed reason) is silently dropped.** `monitor_cmd.py` reads only
`impacts.impacts` + `impacts.cost_entries`; when all retries fail, impacts is `()` and macro/constituent
degrade to the GENERIC reasons `macro_empty_pool`/`constituent_no_coverage`, masking the real
`schema_invalid:`/`unresolved_citation:` reason. Surface `impacts.status` into `FundView` (mirror how
`narrative.status` is surfaced).

## P1 — latent (adversarial)

**`trend.py:_r60` ZeroDivisionError on a zero-valued NAV point.** `vals[-1] / vals[-61] - 1.0` crashes if
`COALESCE(nav_acc, nav)` is `0.0` for any point (possible for QDII with missing acc-NAV). Guard the
denominator → `trend → N/A` reason `trend_insufficient_history`/`trend_bad_data`, not a crash. `trend` is the
highest-weight factor and the coverage-gate prerequisite, so a crash here kills `_process_fund`.

## Defended (verified clean — no action)

- SSRF guard re-runs on env-resolved base_url (`_validate_base_url` + `verify_host_resolves_publicly`).
- HTML escaping correct (hostile-title test passes; url never an href; citation ids validated 16-hex).
- `available_weight=0` divide-by-zero guarded; `bias=None`≠`NEUTRAL` in renderer; duplicate-id rejected at parse;
  band `buy==sell` rejected; MiniMax `base_resp!=0` on HTTP 200 detected before reading choices; atomic writes crash-safe.
- MiniMax live 401 = placeholder credential, not a code defect (auth header `Authorization: Bearer` correct).

## Resolution

Routed to triage-fix → fix subagent completes the corrected Task 32 (real `call`/`llm_config` wiring +
graceful degradation + real `build_evidence_pool` + surface impacts.status + guard `_r60` + end-to-end
degradation test through the real gather path). Then re-run ship steps 8+9; on clean, open the PR and write
`items/001-review.md`.
