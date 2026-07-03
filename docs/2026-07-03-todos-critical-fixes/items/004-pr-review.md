Verdict: PASS-WITH-NITS

Source: /code-review on PR #198 (independent second pass — full diff re-read, not a
  re-trust of items/004-review.md)
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/198#issuecomment-4873590520

## Findings

0 gating findings. 1 new nit (does not gate).

### Nit — cache-write-failure visibility asymmetry (new finding)

The three pre-existing build/refresh call sites in `_build_rows` (`opportunity_cmd.py`) append
a `cache_write_failed:{id}:{type}` string into the *returned* snapshot's
`fund_level_failure_reasons` when `write_active_fund_cache` raises, so downstream readers
(Policy B, memo, discipline) can see the disk failure for that run. The new
`_maybe_fund_level_evidence_repair` (opportunity_cmd.py:354-360) only writes
`cache_write_failed:...` to stderr on the same exception — it does not fold the reason into
`merged.fund_level_failure_reasons`. Impact is low (in-memory evidence is still correct for
this run; no-backoff design means the next run retries anyway), and the existing test
(`test_repair_cache_write_failure_degrades_to_in_memory`) only asserts the stderr line, so the
gap is untested either way. Suggest matching the established pattern for consistency; not a
correctness bug, not gating.

## Independent verification performed

- Read the full diff (`gh pr diff 198`, 1494 lines / 11 files) plus the current state of
  `opportunity_cmd.py`, `fund_level_repair.py`, `policy_b.py`, `snapshot.py`, `types.py`,
  `CONTEXT.md` — not just the round-1 `/ship` review docs.
- Confirmed `_maybe_fund_level_evidence_repair` is wired ONLY in the `refresh == False` arm of
  `_maybe_freshness_probe`'s result; `_maybe_freshness_probe` returns `refresh=True`
  unconditionally when `_active_snapshot_has_required_data_leg_gap(snap)`, so a data-leg-gapped
  cache can never reach the 4-call repair instead of the full ~35-call rebuild. Same short-
  circuit shape mirrored in `_classify_active_fund_scores`'s early-`continue` chain
  (`stale_full` wins before the `foreign_heavy_fund_level_gap` check) — preflight estimate and
  runtime dispatch agree; no double-count possible at either layer.
- Traced `_fetch_active_fund_level_evidence` (`snapshot.py:483-524`): producer order is
  NAV(`data`)-first then announcements(`information`); failure strings
  `fund_nav_unavailable` then `fund_announcements_unavailable` — matches
  `_merged_failure_reasons`'s re-append order exactly.
- Confirmed `ActiveFundSnapshot` and `ThesisEvidence` are `@dataclass(frozen=True)`
  (`types.py:53,231`) and `merge_fund_level_evidence` derives new instances only via
  `dataclasses.replace` — no mutation.
- Confirmed budget math independently: `FetchPlan.total_calls()` charges
  `active_fund_fund_level_repair * 4` as a separate term from `per_active` (~35), never
  conflated; verified via the 4-only and 5-combined (probe+repair) unit tests and by reading
  `_classify_active_fund_scores` directly.
- `uv run ruff check` on all 4 touched source files: clean.
- `uv run pytest tests/fundamentals/test_fund_level_repair.py tests/opportunity/test_policy_b.py -q`:
  67 passed, 1 skipped.
- `uv run pytest tests/integration/test_publishable_set_lockdown.py -k "fund_level_evidence_repair or fund_level_no_repair"`:
  2 passed (AC7 heal-in-one-run + AC8 negative lock).
- `uv run pytest tests/commands/test_opportunity_cmd.py -q`: 5 failures observed locally, all
  date-fixture-dependent (hardcoded `2026-05-14` vs. real `today()`). Reproduced the identical
  5 failures on base (`autodev/todos-critical-fixes-feature`) via a throwaway git worktree —
  byte-identical — confirming known-context item (a) by direct measurement, not by trusting the
  PR's own claim (PR claims 12 across a broader multi-file sweep; this pass targeted the single
  file directly relevant to the change and got the same pre-existing-baseline result).
- Confirmed CONTEXT.md "Fund-level evidence repair (repair probe)" term is present and
  consistent with the ADR 0003 §7 addendum and the shipped code.
- Confirmed the round-1 P0×2/P1 observability fixes (93806fb9) are present and correct:
  `_log.warning(...)` in `refetch_fund_level_evidence` names `fund_id` + exception type on
  swallow; `fund_level_repair_attempted/healed/still_gapped` stderr lines are unconditional and
  match their tests.

## Known-context items (confirmed, not newly gating per review brief)

- (a) Caller-sweep failures are byte-identical on base — pre-existing date-fixture baseline,
  reconfirmed above via independent worktree replay.
- (b) Round-1 observability P0s fixed pre-push in 93806fb9 — reconfirmed present and correct.
- (c) The broad `except Exception` in `refetch_fund_level_evidence` is a deliberate fail-safe
  (repair must never crash the run), now with WARNING-level logging — confirmed present and
  covered by `test_refetch_raising_fetch_logs_warning_naming_fund_and_exc_type`.

No new bugs, no CLAUDE.md functional/immutability-convention violations, no silent failures
beyond the one nit above.
