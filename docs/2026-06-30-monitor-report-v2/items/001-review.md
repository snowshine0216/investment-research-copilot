Verdict: PASS-WITH-NITS
Source: /ship steps 8+9 (pre-landing parallel review + adversarial review)
Reviewers: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose (adversarial)
Base: claude/wizardly-shamir-60a599 ... HEAD (claude/monitor-report-v2-001)

## Outcome

3 reviewers ran against the feature diff. One latent crash (A) + three minor defects (B/C/D)
were found and FIXED before push (TDD); one clarity comment (E) added; three P2 nits are
documented-and-deferred (acceptable / consistency-preserving). No wiring, purity, or math
defects. All three reviewers independently confirmed NO dark-factor regression — the new
`market_view`, `purchase_tag`, and `market_composite_directional` panel row all flow
end-to-end (computed at the edge AND consumed in render/ledger/panel).

## Findings found → FIXED before push

- **A (latent crash; silent-failure P0 / code-review P1) — FIXED `33c2eb6e`.**
  `_build_bias_timeline` did an unguarded `latest_per_key(...)` + bare `r["run_date"]`/
  `r["fund_id"]` read of the long-lived append-only ledger, in `run_monitor`'s hot path
  (between the contained `_run_forward_eval` and `_write_outputs`). A JSON-valid but
  structurally-malformed row → `KeyError` → brief crashes AFTER artifacts written, before
  report.html — violating the "never crash the brief" invariant. Fixed: filter rows lacking
  `run_date`/`fund_id`, then wrap the body in try/except → empty `BiasTimeline` + warning
  (mirrors `_run_forward_eval` containment). Test `test_build_bias_timeline_malformed_row_no_crash`
  proves no-crash.
- **B (honesty; code-review P1) — FIXED `33c2eb6e`.** Timeline gap-fill rendered absent
  `(fund,date)` cells as a real `NEUTRAL`. Now uses a `(None,"0")` no-data sentinel,
  rendered distinctly (`class="tl-cell no-data"`) vs a true NEUTRAL cell. Test asserts the
  distinction.
- **C (observability; silent-failure P1) — FIXED `33c2eb6e`.** `_read_ledger_rows` silently
  dropped malformed JSONL lines; now counts + `_log.warning(... skipped %d ...)`. caplog test.
- **D (broken output; adversarial P1) — FIXED `ceb618d1`.** `contribution_bars_svg` produced
  `x="nan"` on a non-finite contribution; now guarded with `math.isfinite` → 0. Tests for
  nan/inf/-inf assert no `nan`/`inf` in SVG.
- **E (clarity; code-review P1) — `1980b438`.** Comment on `_market_composite_rows` clarifying
  `label=sign(market_composite)` is the intended permutation-null prediction label.

## Deferred P2 nits (acceptable — documented, not fixed)

- `purchase_tag_for` double-float dead path — unreachable in practice (cap already parsed by
  `_cap_below_threshold`).
- `_is_market` defaults unknown factors to "market" — acceptable; `_FAMILY_OF` is the single
  source of truth and any new factor must be registered there anyway.
- `sign(0.0)=0` counts a zero market-composite as a directional miss — consistent with the
  existing `_composite_rows`/`raw_composite_directional` convention; changing one in isolation
  would diverge. Cosmetic, immature-data only.

## Re-verification (orchestrator-run, post-fix)
- fix-targeted suites (timeline/contrib/metrics/invariants) → 52 passed.
- broad `tests/monitor/` + `tests/evals/` → 1072 passed, 12 skipped, 1 pre-existing unrelated
  FAIL (`test_dag_acyclic_check`; fundamentals↔data cycle, identical on main).
- per-file `tests/commands/`: monitor_cmd 10, eval_wiring 7, predictive_panel 6 — pass.
- ruff clean on all touched files. `_ENGINE_VERSION` "3"; invariants intact.

Cleared for push.
