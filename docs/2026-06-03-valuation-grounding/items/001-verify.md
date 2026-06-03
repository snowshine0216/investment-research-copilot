Verdict: PASS

Subagent: sonnet
Source: /verify (skill invoked; no project verifier-* skill found; cold-start)
Entry point exercised: `uv run irc --help`, `uv run irc opportunity --help`, `python -c "...index_valuation..."` wiring check, `uv run python /tmp/verify_001.py` (behavioral exercise against real production functions via temp DuckDB)

Observed behavior:
  - AC1 — `valuation_percentile_fundamental = 1.0` for csi300 with 35 rising PE rows; `classify_valuation` returns `very_expensive` with reason `"PE 百分位 100% 极高。"`. `valuation_percentile_self` was seeded at `0.10` (cheap) — fundamental overrides it. Reason contains `"PE 百分位"`, not `"估值百分位"`.
  - AC2 — With no `index_valuation_history` rows, `valuation_percentile_fundamental = None`; `populate_inputs` sets `valuation_percentile_self = 1.0` from 35-row rising price series; `classify_valuation` returns `very_expensive` with reason `"估值百分位 100% 极高。"`. `"PE 百分位"` absent from reason — byte-for-byte NAV fallback path used.
  - AC4 — `build_opportunity_row` with `valuation_percentile_fundamental=0.10` (cheap) and `valuation_percentile_self=0.85` (expensive): `advisory_gaps = ('valuation_price_fundamental_divergence',)`, `evidence_gaps` does not contain the divergence code. Row is publishable. `valuation_state = cheap` (fundamental decides).
  - AC5 — With `cn_10y_yield = 2.45` (percent as stored) and `pe_ttm = 39.0`: `earnings_yield = 0.02564` (= 1/39, ratio), `real_yield_10y = 0.0245` (= 2.45/100, ratio). `expected_real_return_positive` returns `True` (0.02564 > 0.0245).
  - AC6 — Provider stub whose `fetch_index_valuation` raises `AssertionError` passed to `populate_inputs`; function returns with `valuation_percentile_fundamental = 1.0` from cached table without invoking the stub. No exception raised.
  - AC8 — `derive_position_risk_level` with `RiskEvalView(valuation_state="very_expensive", ...)` returns `level="elevated"`, `drivers=("valuation_state",)`, rationale `"elevated — very_expensive valuation"`. Same view with `valuation_state="cheap"` returns `level="low"`, no valuation driver. No change to `risk.py` was needed; the grounded state is consumed transparently.

Additional probes (all held):
  - Sector ETF with non-broad `tracked_index` falls back to NAV percentile; no PE label in reason.
  - Bond fund with `valuation_percentile_fundamental=0.95` ignores fundamental pct; uses `cn_bond_yield_percentile` path as before.
  - Same-band, small-gap inputs (both in `fair`, gap=0.05) produce `valuation_divergence_code = None` (no spurious advisory).

Failures: none
