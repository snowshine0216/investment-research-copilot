Verdict: PASS-WITH-NITS
Source: /ship steps 8+9

Reviewers: pr-review-toolkit:code-reviewer (clean), pr-review-toolkit:silent-failure-hunter (1 note, fixed pre-push), general-purpose adversarial (CLEAN). Targeted tests: 69 passed, 2 skipped (live double-gated). Broader monitor+commands surface green (565 passed baseline; item-001 eval-wiring regression fixed). Zero blockers/latent bugs.

## Findings
- **FIXED pre-push (silent-failure-hunter) — parse-layer schema-drift silence.** If AkShare renames
  the `基金代码`/`申购状态` columns, `parse_purchase_status` (pure, can't log) returned None for every
  fund with no signal — indistinguishable from all-absent (§10 risk). Fixed at the I/O edge
  (commit `ac5fba7`): `fetch_purchase_table` now checks required columns via `_has_required_columns`,
  logs a structured "fund_purchase_em schema drift" WARNING, and returns None — heat degrades to
  honest `heat_no_data` WITH a log signal. Parser stays pure. +3 schema-drift tests.
- **NIT/P2 (adversarial) — `场内交易` + cap=0 → restricted.** An exchange-only fund with cap=0 is
  flagged restricted by the literal rule. Spec §5.1 acknowledges `场内交易 ∉ {开放申购}` counts as
  restricted; no monitor fund is `场内交易` (the gold fund `008986` is `开放申购`), so no monitor fund
  is affected. Not actioned.
- **NIT/P2 (adversarial) — negative cap untested.** `cap < 1e8` would flag a negative cap restricted;
  no real-world AkShare analog (float64 caps are ≥0). Cosmetic. Not actioned.

## Confirmed clean (introduced code)
- `fetch_purchase_table` truly never raises (bare except wraps only `fetch()`, logs with exc_info=True);
  exactly ONE akshare call per run (hoisted to run_monitor, threaded per-fund); None table → every
  fund `heat_no_data`, brief still renders.
- `parse_purchase_status` robust: exact `zfill(6)` code match (int `8986` → `"008986"`, no wrong-fund
  match); cap comparison guards `float()` TypeError/ValueError + `pd.isna` (NaN/"—"/None → status leg);
  strict `<` so cap==1e8 not restricted; missing columns → None; pure + per-fund isolated.
- heat_score unchanged; no new N/A reason codes (`heat_no_data` pre-existing); CN endpoint direct.
- No item-001/002 regression: valuation wiring intact; gold/qdii_global heat eligibility correct
  (both list `heat` as eligible; gated by `eligible_factors`); determinism for a fixed table.
- Fixes item-001 test-scope regression: `tests/commands/test_monitor_cmd_eval_wiring.py` 4 RED → GREEN
  (the `**kw` lambda fix).
