Verdict: PASS

Source: /code-review on PR #196
PR comment URL: none — findings inline (source-control connector not authorized in this
  non-interactive session; GitHub OAuth requires an interactive `/mcp` flow. Reviewed the PR
  diff directly via `gh pr diff`/`gh pr view` instead, applying the skill's security/
  performance/correctness/maintainability dimensions manually.)
Findings: 0 new (2 prior-adjudicated items confirmed, not re-gated per instructions)

Independent verification performed (not just re-reading the first-pass /ship review):
- Read the full diff (`gh pr diff 196`) and the complete post-change
  `src/irc/opportunity/thesis_evidence.py`. Confirmed the new `_active_dual_leg_state`
  helper's empty-flattened guard is textually the FIRST statement, strictly before the
  `union = flattened + fund_level_evidence` leg check — matches the load-bearing ordering
  claimed for ADR 0003 §8 property 3.
- Verified `ThesisEvidence.citation_kind` (`src/irc/fundamentals/types.py:72,85-86`) is a
  `Literal["data","information"]` hard-validated in `__post_init__` (raises `ValueError`
  otherwise) — confirms the docstring's "both-legs-missing with non-empty evidence is
  unreachable" claim independently of the PR's own assertion.
- Traced every caller of `derive_thesis_from_evidence`: only `src/irc/opportunity/states.py`
  (`build_opportunity_row`, line ~663) calls it, and it consumes the returned 5-tuple
  generically with no baked-in assumption that non-empty evidence implies `intact`. No other
  call site exists in `src/irc/`, so the behavior change is contained to this module.
- Independently proved the "no Policy-B-publishable row changes thesis_state" claim by
  reading `src/irc/opportunity/policy_b.py`'s rule 3/4 logic directly (not just trusting the
  ADR text): rule 3 requires a data leg on every ranked constituent and rule 4 requires an
  info leg on the material top-half, so any row that clears both rules (publishable via 3/4)
  already has both legs present in `flattened` alone — the union check is redundant-but-safe
  for that path. Rule-2.5-publishable rows source both legs from `fund_level_evidence`
  instead; the empty-flattened guard is what keeps the reachable "all-constituents-pure-
  failure" rule-2.5 shape at `evidence_insufficient` rather than flipping to `intact` under a
  naive union-first implementation. This matches the AC5(b) test's stated intent.
- Ran `uv run pytest tests/opportunity/test_thesis_evidence.py tests/opportunity/test_fund_eval.py -q`:
  59 passed (matches PR claim).
- Ran `uv run pytest tests/opportunity/ -q`: 620 passed, 3 skipped, 0 failed (matches PR claim
  of a clean opportunity-package sweep).
- Ran the 3-file caller sweep the PR's own drift doc names (`tests/integration/
  test_publishable_set_lockdown.py`, `tests/commands/test_opportunity_cmd.py`,
  `tests/commands/test_opportunity_cmd_acceptance.py`): reproduced the exact same 10 failing
  test ids reported in the PR. Then independently git-worktree-checked out the PR's base
  (`autodev/todos-critical-fixes-feature`, commit `1653fefa`) and reran the identical 3 files:
  same 10 ids fail, same counts (10 failed, 79 passed, 1 skipped) — confirms known-context
  item (a) (byte-identical pre-existing baseline, not a regression) by direct measurement
  rather than accepting the PR's claim.
- Ran `uv run ruff check` on all 3 touched files: 5 pre-existing violations, all at lines
  95/101/102/103/526 of `tests/opportunity/test_thesis_evidence.py` (E402 import-not-at-top,
  F821 undefined name in a string-quoted forward-ref type hint) — all strictly above the
  newly appended section (line 696+) and confirmed present on the base branch too. Zero new
  violations introduced by this diff.
- Confirmed `fund_level_evidence` (`src/irc/fundamentals/types.py:244`, default `()`) and its
  documented `scope="instrument"` shape line up with what the new test fixtures
  (`_fund_level_leg` in `tests/opportunity/test_thesis_evidence.py`) construct.
- Re-confirmed known-context item (b): `fund_level_failure_reasons` (the detail the deferred
  P1 wants folded into the reason string) does surface independently through
  `derive_fetch_types_attempted` (`states.py:85-112`) and `rejection_log.py` — so the gap is
  cosmetic/duplicative, not a silent-failure hole. Not re-gating per instructions.

No new bugs, no CLAUDE.md-convention violations found. The change is a pure, narrowly-scoped
narrowing of one `ThesisState` branch (never widens `intact`), with effects confined to
`thesis_evidence.py`; evidence/gaps/analyses return slots are provably byte-identical for
every previously-`intact` case except the one false-confidence shape the item targets.
