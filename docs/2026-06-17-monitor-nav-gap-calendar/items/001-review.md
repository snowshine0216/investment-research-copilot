Verdict: PASS-WITH-NITS
Source: /ship steps 8+9 (pre-landing parallel review + adversarial)

Subagents: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter,
general-purpose (adversarial)

## Findings

- **code-reviewer** — P0: none. P1: none. Verdict "ship it." Confirmed the degrade contract, the
  strict-bounds (`d0 < td < d1`) trading-day count, the back-compatible default-`None` param, and
  the gate dominance. Note (non-blocking, P2): `_missing_trading_days` rescans the full SSE-history
  frozenset per gap — negligible at this scale (≤19 gaps × 7 funds); accepted.

- **silent-failure-hunter** — P0: none. **P1 (latent): empty/all-NaT AkShare frame** silently
  yields `()`, cached as today's calendar → `_missing_trading_days` scores 0 for every gap → false
  `nav_quality` PASS (the exact failure this feature prevents). **FIXED pre-merge** — commit
  `6789abd`: `fetch_trade_calendar` now raises on an empty result so the loader degrades to `None`.

- **adversarial** (verdict RISKS) — P0: none. **P1 (latent): empty/poisoned cache** `{"dates": []}`
  → non-`None` `frozenset()` bypasses the `None`→fallback path → false PASS. **FIXED pre-merge** —
  commit `6789abd`: `_read_cache` treats empty `dates` as a miss (refetch / degrade). P2 cosmetic:
  `window=0` quirk and no unsorted-series guard — accepted (no caller passes `window=0`;
  `nav_series` is date-ascending by construction, per `fetch.py`). All other vectors CLEAN.

## Resolution

The two reviewers converged on **one** latent bug (empty calendar → false PASS). FIXED pre-merge in
`6789abd` with regression tests:
- `tests/data/test_akshare_client.py::test_fetch_trade_calendar_raises_on_empty_frame`
- `tests/monitor/test_trading_calendar.py::test_empty_cached_dates_does_not_serve_empty_calendar`
- `tests/monitor/test_trading_calendar.py::test_empty_cache_and_empty_fetch_degrades_to_none`

Post-fix: 528 monitor tests + akshare green; ruff clean. Zero remaining blockers / latent bugs;
P2 notes accepted by data contract → PASS-WITH-NITS.
