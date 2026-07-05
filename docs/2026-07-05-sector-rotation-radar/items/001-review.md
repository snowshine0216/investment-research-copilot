Verdict: PASS-WITH-NITS
Source: /ship steps 8+9 (pre-landing parallel review + adversarial review)
Reviewers: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose adversarial (all Sonnet)
Reviewed range: badeaf10...HEAD (sector rotation radar impl)

## P0 — none (all three reviewers agree; safe to land)
- D6 flow_dark correctly global (flow5-aware); AC11 one-way import isolation enforced by test; AC10 wrapper exit-isolation hand-verified; abstain/degraded paths never mutate series/ledger; determinism (sorted keys, stored PE) sound; hysteresis/dedup/atomic-write verified against boundary/tie cases.

## P1 findings — ALL FIXED before push (commits 975ff0f5..67bb49e5)
1. **NaN/inf literal poisoned percentile ranks (adversarial, latent AC3 threat)** — `board_fetch._f` parsed `"nan"`/`"inf"` into non-finite floats escaping the None-guard → non-transitive comparisons in `_percentile_ranks`. FIXED: `math.isfinite` rejection + tests (`975ff0f5`).
2. **Forward-ledger key `chg_pct` stored `mom20` (code-review, contract clarity)** — name/value mismatch that a future F1 eval consumer would misread. FIXED: key renamed `chg_pct`→`mom20`, spec §5 synced in both spec copies, test updated (`c25f7622`).
3. **Calendar-failure silently disabled series pruning (adversarial, self-heals)** — `_resolve_trading_days` swallowed a None calendar into `()`. FIXED: `_log.warning` added (`6b0ccd04`).
4. **`_topup_budget` swallowed a malformed env var silently (silent-failure)** — FIXED: `_log.warning` on the bad value (`6b0ccd04`).
5. **`seed.py` docstring over-claimed "breaker-protected" (silent-failure note)** — board fetches raise + caller degrades; the injected seed fetchers don't use cached_fetch either. FIXED: docstring corrected to the real mechanism (`67bb49e5`).

(The flow5 fabricated-0 dark-factor bug — same class the reviewers watched for — was already fixed pre-ship via `flow_leg_dark`, commit `ac517d07`, and all three reviewers verified the fix is complete.)

## Remaining nits (documented; do NOT block — recorded for follow-up)
- **`turn_delta` defensive 0.0 fallback** (composite.py `board_signals`) — the same trap *shape* as flow5, but the "missing turnover" branch is **unreachable in practice** (turnover_pct is structurally always populated by snapshot f8 + kline volume/amount). A clarifying comment was added (`67bb49e5`); a real `turn_leg_dark` guard is a documented follow-up only if turnover coverage ever becomes unreliable.
- **Duplicate `board_signals(series)` computation** (rotation_cmd.py `_build_states`/`_pctl_series_by_day`) — pure perf nit, harmless + deterministic at current board/day counts. Follow-up if board count or keep_td grows.
- **AC10 wrapper test is string-presence only** (`tests/ops/test_flow_capture_wrapper.sh`) — the runtime exit-isolation was hand-verified by the adversarial reviewer; strengthening to a live-execution test is a test-quality follow-up.

## Verification after fixes
- `uv run pytest tests/rotation/ tests/commands/test_rotation_cmd.py tests/monitor/test_industry_map_store.py -q` → 77 passed.
- `uv run ruff check src/irc/rotation src/irc/commands/rotation_cmd.py` → clean.
