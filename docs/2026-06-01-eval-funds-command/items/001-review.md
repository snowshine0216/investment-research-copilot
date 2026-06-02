Verdict: PASS-WITH-NITS
Source: /ship steps 8+9 (pre-landing parallel review + adversarial review)
Reviewers: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose adversarial (all model=sonnet)
Diff reviewed: feat/eval-funds-command...HEAD

## Outcome

Three independent reviews ran against the pre-push diff. No true P0 in the new code —
all three confirmed the **core honesty invariant holds**: a missing snapshot or
insufficient inputs degrade to `evidence_insufficient` / `small_watch`, never a
falsely-confident `core_dca=True`. The `_build_input` extraction was confirmed
behaviour-identical (byte-identical body; existing callers/tests unaffected).

Four latent bugs that the reviews surfaced in the **new edge code** were FIXED
pre-push (commit `9ad77a2`, TDD, edge-only — no classifier/pure-core change), so the
diff that ships is clean of them:

- A. Duplicate `--ids` produced duplicate rows + inflated `n_core` → `_parse_ids` now
  dedupes preserving first-seen order. (test: `test_parse_ids_deduplicates_preserving_order`)
- B. `--out foo.json` made md+json overwrite the same file → both paths now derived
  from the stem (`.md` / `.json`), collision-proof. (test:
  `test_run_eval_funds_out_path_json_produces_separate_md_and_json`)
- C. Unopenable/locked/corrupt DuckDB and a missing `--ids-file` raised unhandled
  tracebacks → now clean `return 2` matching the command's error contract. (tests:
  `test_run_eval_funds_returns_2_for_corrupt_db`, `..._missing_ids_file`)
- D. Unknown id silently fabricated `asset_class="cn_equity_fund"` → now emits a
  stderr WARNING (verdict/behaviour unchanged). (test: `test_run_eval_funds_warns_on_unknown_id`)

## Remaining findings (do NOT block — recorded, not introduced by this diff)

Pre-existing (filed to TODOS.md under Reliability, tagged `eval-funds ship ... 2026-06-01`):
- latent (pre-existing) — `opportunity/states.py` `derive_thesis_from_evidence`: the
  `ActiveFundSnapshot` branch sets `intact` on non-empty evidence WITHOUT the dual-leg
  (data+information) check that the `FundLevelSnapshot` branch has → data-only evidence
  can reach `core_dca`. The command reuses the pipeline classifier verbatim by design
  (spec §1 "no new business logic"), so this is out of scope here, but eval-funds makes
  it more visible. → TODOS Reliability.
- latent (pre-existing) — `fundamentals/snapshot_cache.py` `load_active_fund_cache`
  swallows `OSError`/`ValueError` without logging → corrupt cache indistinguishable from
  "not fetched". → TODOS Reliability.

Nit (kept, harmless):
- `fund_eval.py` `_sort_key` first element (`0 if core_dca else 1`) is redundant with
  the severity map today; kept as defensive ordering. Reviewer confidence 52 (below the
  P1 bar). No behaviour impact.

## Verification

- `tests/commands/test_fund_eval_cmd.py + tests/opportunity/test_fund_eval.py +
  test_opportunity_cmd.py + test_build_input_fallback.py` → 63 passed.
- `ruff check` on the edge + test → clean.
- Fix commit `9ad77a2` stat: only `commands/fund_eval_cmd.py` + its test (no classifier touched).
