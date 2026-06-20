Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial review)
Subagents: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose (adversarial)
Diff reviewed: origin/autodev/monitor-engine-drop-warn-feature...HEAD (branch claude/monitor-engine-drop-warn-001)

## Blockers (P0)
None. All three reviewers: zero P0.

## Latent bugs
None. The one candidate (negative `ep_value` if `n_excluded_engine > n_total_raw`) was **proven unreachable** by the adversarial reviewer: `engine_mismatch` is counted from the same `ledger` list that `n_total_raw = len(ledger)` measures, so `n_excluded_engine <= n_total_raw` always holds. Not a fireable bug.

## Nits (do not block; PASS-WITH-NITS)
1. **Defensive assertion suggestion** (runner.py `ep_value` line) — both code-reviewer and silent-failure-hunter suggest `assert 0 <= n_excluded_engine <= n_total_raw` to convert a hypothetical upstream count corruption into a loud failure. Path is proven unreachable today (adversarial: CLEAN), so this is hardening, not a fix. Disposition: candidate for triage-fix; decide after pr-review. Aligns with the project's "no silent caps" invariant (spec §6) → lean toward adding if pr-review concurs.
2. **D3 structural-dependency comment** (silent-failure-hunter) — the "never changes rc" invariant relies on the logical fact that `engine_population` only WARNs when `publishable_bias_directional` is already `insufficient_data` (→ already WARN). No runtime enforcement. A one-line comment near the `worst_status` call documenting this would protect future threshold edits.
3. **Test robustness** (code-reviewer) — `test_engine_population_warns_on_transition` maturity depends on NAV coverage past `run_date+H`; loose `rc in (EVAL_RC_WARN, 0)` in the empty-ledger test reduces diagnostic precision. Both currently green; minor.

## Confirmed correct (reviewer cross-checks)
- D3 invariant holds: `engine_population` WARN cannot lift `overall`/`rc` (co-occurs only with an already-WARN headline). `metrics.py:_hit_rate_report` sets `status="WARN"` whenever `state=="insufficient_data"`.
- Direct indexing `details["publishable_bias_directional"]["state"]` is the correct non-silent choice (fails loudly on invariant break) — not softened to `.get()`.
- No dark-factor trap (the #168 bug class): the helper receives live `engine_mismatch` + live headline state; status reflects the real computation end-to-end.
- CI-None contract intact: explicit `None` → JSON `null` → `md.get("ci_low", m.value)` returns `None` → "CI pending". Pinned by the command-edge test.
- `details_ref` rewrite (`replace(m, details_ref=rel)`) covers the appended row (appended before that comprehension).
- `build_metric_reports` still returns exactly 3 (append is runner-edge only).
