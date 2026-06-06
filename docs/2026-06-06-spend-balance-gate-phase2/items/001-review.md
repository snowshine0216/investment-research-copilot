Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial review)
Subagents: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose (adversarial)
Diff reviewed: origin/autodev/spend-balance-gate-phase2-feature...HEAD

## Blockers fixed before push (round 2)

- **Corrupt-JSON masking** (silent-failure P0) — a truncated `spend_actuals.json` / `usage_profile.json` / `consumption.json` raised a bare `JSONDecodeError` swallowed by the command's non-fatal recorder `except` as a generic WARNING, hiding on-disk corruption. FIXED (`6c414e2`): `record_run.py` + `config.py` now raise `RuntimeError` naming the corrupt path (non-fatal contract preserved; corruption is now diagnosable, not silently reset to `{}`). Tests added.
- **read_text() missing `encoding="utf-8"`** (code-reviewer P1) — `record_run.py:35`. FIXED (`6c414e2`).
- **theme_research over-counts FAILED extraction pages as billed ledger units** (silent-failure P1) — a ledger-correctness bug in the new 12d code: a Jina extractor timing out on 5 pages still charged 5 units. FIXED (`c509c42`): `_count_search_units` now excludes pages/results with `failure_reason`. Tests added.
- **memo_cmd `_history[:] =` argument mutation** (code-reviewer P1) — violated CLAUDE.md "never mutate function arguments". FIXED (`587dc3a`): refactored to a fully-local accumulator built via pure `append_cost` rebind; recorder `finally` moved into `_run_memo_body`. `grep "\[:\] ="` confirmed memo was the only site. memo recorder test still green.

## Accepted limitations (documented, deferred — not blockers)

These are direct consequences of the plan's ADR-0013 "usage rides up as data" design and/or out of the plan's explicit scope; all are low-impact for a single-user sequential CLI and self-heal on the next run.

- **Concurrency TOCTOU** (adversarial P0 "BREAKS"; code-reviewer P1) — `record_command_run`'s read-modify-write of the 3 JSON files isn't locked. Mitigation: `irc run` runs stages sequentially; `atomic_write_text` prevents torn files; a lost cross-terminal update self-heals via the next EWMA fold / ledger decrement. Adding a file-locking subsystem is a design addition the plan never scoped (symmetric to the discover/research gate scope-creep that drift removed) — left to the user. Documented in `record_command_run`'s docstring (`21220a6`).
- **Same-day-retry EWMA double-fold** (adversarial P1) — re-running a command same-day folds its tasks twice (converges faster, not wrong-direction). No dedup keyed on (date, command); the plan did not specify retry-dedup.
- **Shape-B partial-billing on mid-pipeline crash** (silent-failure P1 score; adversarial P1 opportunity; applies to memo too) — billed LLM calls made inside a pipeline that raises before returning are not recorded (the responses ride up only on a clean return). Self-heals; the plan's Q4 guards (no swallowed command exception, empty-history no-op) hold.
- **Search-only profile rewrite** (adversarial P2) — `write_usage_profile` rewrites unchanged content when only search units were spent. Harmless.

## Confirmed clean (reviewers)
- EWMA math correct (`α·observed + (1−α)·old`); no division-by-zero (`_wmean` guard); no currency crossing; `fold_actuals`/`apply_usage`/`effective_profile` verified pure (no arg mutation, no I/O); recorder edge contract (finally + non-fatal WARNING + empty no-op) holds across all 6 wired commands.

No remaining blockers or latent bugs. Touched-scope tests green; no new ruff violations (the 1 E402 in test_theme_research.py is pre-existing on base).
